"""
LLM service for handling interactions with language models
"""
from flask import current_app
import os
import pickle
import io
from typing import List, Dict, Any, Optional
from llama_index.core import VectorStoreIndex
from llama_index.llms.openai import OpenAI
from services.storage_service import get_storage_client
from services.notion_service import download_blob_to_memory
import time

# Cache storage for file indexes
_file_index_cache = {
    'data': None,
    'timestamp': 0
}
CACHE_TTL = 300  # Cache time-to-live in seconds (5 minutes)

def _is_cache_valid():
    """Check if the cache is still valid based on TTL"""
    return (_file_index_cache['data'] is not None and 
            time.time() - _file_index_cache['timestamp'] < CACHE_TTL)

def get_available_notion_indexes():
    """
    Get a list of available cached Notion indexes from GCS bucket.
    Uses an in-memory cache with TTL to avoid frequent GCS requests.
    
    Returns:
        list: List of available index IDs and types with titles
    """
    try:
        # Check if we have valid cached data
        if _is_cache_valid():
            current_app.logger.debug("Returning cached file index list")
            return _file_index_cache['data']

        current_app.logger.debug("Cache miss or expired, fetching fresh file index list")
        
        # Get GCS client and bucket
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # List blobs with cache/ prefix
        vector_blobs = list(bucket.list_blobs(prefix="cache/vector_"))
        metadata_blobs = list(bucket.list_blobs(prefix="cache/metadata_"))
        
        # Create a dictionary of metadata by ID
        metadata_dict = {}
        for blob in metadata_blobs:
            try:
                # Extract ID from the blob name
                blob_name = blob.name
                if "metadata_db_" in blob_name:
                    item_id = blob_name.split("metadata_db_")[1].replace('.pkl', '')
                    metadata = download_blob_to_memory(blob_name)
                    metadata_dict[item_id] = metadata
                elif "metadata_doc_" in blob_name:
                    item_id = blob_name.split("metadata_doc_")[1].replace('.pkl', '')
                    metadata = download_blob_to_memory(blob_name)
                    metadata_dict[item_id] = metadata
                elif "metadata_" in blob_name:
                    item_id = blob_name.split("metadata_")[1].replace('.pkl', '')
                    metadata = download_blob_to_memory(blob_name)
                    metadata_dict[item_id] = metadata
            except Exception as e:
                current_app.logger.error(f"Error processing metadata blob {blob_name}: {str(e)}")
                continue
        
        indexes = []
        for blob in vector_blobs:
            blob_name = blob.name
            # Skip non-pickle files
            if not blob_name.endswith('.pkl'):
                continue
            
            # Extract ID and type from blob name
            if "vector_index_" in blob_name:
                item_id = blob_name.split("vector_index_")[1].replace('.pkl', '')
                
                # Get title from metadata if available
                title = f"Page: {item_id[:8]}..."
                if item_id in metadata_dict and 'title' in metadata_dict[item_id]:
                    title = metadata_dict[item_id]['title']
                
                indexes.append({
                    'id': item_id,
                    'type': 'page',
                    'title': title,
                    'path': blob_name
                })
            elif "vector_database_" in blob_name:
                item_id = blob_name.split("vector_database_")[1].replace('.pkl', '')
                
                # Get title from metadata if available
                title = f"Database: {item_id[:8]}..."
                if item_id in metadata_dict and 'title' in metadata_dict[item_id]:
                    title = metadata_dict[item_id]['title']
                
                indexes.append({
                    'id': item_id,
                    'type': 'database',
                    'title': title,
                    'path': blob_name
                })
            elif "vector_document_" in blob_name:
                item_id = blob_name.split("vector_document_")[1].replace('.pkl', '')
                
                # Get title and format from metadata if available
                title = f"Document: {item_id[:8]}..."
                doc_type = "document"
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    if 'format' in metadata_dict[item_id]:
                        doc_type = metadata_dict[item_id]['format']
                
                indexes.append({
                    'id': item_id,
                    'type': doc_type,
                    'title': title,
                    'path': blob_name
                })
        
        # Update cache with new data
        _file_index_cache['data'] = indexes
        _file_index_cache['timestamp'] = time.time()
        current_app.logger.debug("Updated file index cache")
        
        return indexes
    
    except Exception as e:
        current_app.logger.error(f"Error getting available indexes: {str(e)}")
        # On error, return cached data if available (even if expired), otherwise empty list
        if _file_index_cache['data'] is not None:
            current_app.logger.warning("Returning stale cache data due to error")
            return _file_index_cache['data']
        return []

def refresh_file_index_cache():
    """
    Force a refresh of the file index cache.
    Call this after adding or deleting files.
    """
    global _file_index_cache
    _file_index_cache['data'] = None
    _file_index_cache['timestamp'] = 0
    return get_available_notion_indexes()

def query_notion_content(query: str, index_ids: List[str] = None) -> Dict[str, Any]:
    """
    Query cached Notion content using vector search.
    
    Args:
        query (str): The query to search for
        index_ids (list, optional): List of specific index IDs to search in
        
    Returns:
        dict: Search results with sources
    """
    try:
        # Find all available indexes if none specified
        available_indexes = get_available_notion_indexes()
        
        if not available_indexes:
            return {"error": "No cached content found"}
        
        # Filter indexes if specific ones requested
        if index_ids:
            indexes_to_query = [idx for idx in available_indexes if idx['id'] in index_ids]
        else:
            indexes_to_query = available_indexes
        
        if not indexes_to_query:
            return {"error": "Specified indexes not found in cache"}
        
        # Query each index and collect results
        all_results = []
        for idx_info in indexes_to_query:
            try:
                # Download index from GCS
                index = download_blob_to_memory(idx_info['path'])
                retriever = index.as_retriever(similarity_top_k=3)
                
                # Get relevant nodes from the index
                retrieved_nodes = retriever.retrieve(query)
                
                # Add results with source information
                for node in retrieved_nodes:
                    all_results.append({
                        "content": node.text,
                        "score": node.score if hasattr(node, 'score') else None,
                        "source": f"{idx_info['type']}:{idx_info['id']}"
                    })
            
            except Exception as e:
                current_app.logger.error(f"Error querying index {idx_info['id']}: {str(e)}")
                continue
        
        # Sort results by relevance score (if available)
        all_results.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
        
        return {
            "results": all_results,
            "query": query,
            "total_results": len(all_results)
        }
    
    except Exception as e:
        current_app.logger.error(f"Error querying cached content: {str(e)}")
        return {"error": str(e)}

def get_llm_response(query: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Get a response from an LLM based on the user's query.
    
    Args:
        query (str): The user's question or prompt
        context (dict, optional): Additional context for the query
            - use_notion (bool): Whether to search cached content
            - notion_ids (list): Specific cached content IDs to search
        
    Returns:
        str: The LLM's response
    """
    try:
        # Default system prompt
        system_prompt = "You are a helpful assistant."
        
        # Prepare messages for the LLM
        messages = []
        
        # Check if we should use cached content
        cached_context = ""
        if context and context.get('use_notion', False):
            notion_ids = context.get('notion_ids', [])
            
            try:
                # Retrieve relevant information from cached content
                notion_results = query_notion_content(query, notion_ids)
                
                if 'error' not in notion_results and notion_results.get('results'):
                    # Format the results as context
                    cached_context = "Here is relevant information from your documents:\n\n"
                    for i, result in enumerate(notion_results['results'][:5]):  # Limit to top 5 results
                        cached_context += f"Source {i+1} ({result['source']}):\n{result['content']}\n\n"
                    
                    # Add context to system prompt
                    system_prompt += f"\n\nUse the following information from documents to answer the query:\n{cached_context}"
                    
                    # Log that we're using cached content
                    current_app.logger.info(f"Using {len(notion_results['results'])} cached results for context")
            except Exception as e:
                error_msg = str(e)
                if "validation_error" in error_msg and "ai_block" in error_msg:
                    current_app.logger.error(f"Notion API validation error: AI blocks not supported: {error_msg}")
                    return "I couldn't access some of your Notion content because it contains AI blocks that aren't supported via the API. Please try using a different Notion page or database that doesn't contain AI blocks."
                else:
                    current_app.logger.error(f"Error retrieving Notion context: {error_msg}")
                    # Continue without context but don't fail completely
                    system_prompt += "\n\nNote: I tried to access your Notion content but encountered an error."
        
        # Add system message with context
        messages.append({"role": "system", "content": system_prompt})
        
        # Add additional context if provided
        if context and context.get('chat_history'):
            for msg in context['chat_history']:
                messages.append(msg)
        
        # Add the user's query
        messages.append({"role": "user", "content": query})
        
        # Create OpenAI client with API key
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Make the API call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        current_app.logger.error(f"Error in LLM service: {str(e)}")
        return f"Sorry, there was an error processing your request: {str(e)}"