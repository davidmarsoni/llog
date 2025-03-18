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
import threading

# Cache storage for file indexes
_file_index_cache = {
    'data': None,
    'timestamp': 0,
    'is_loading': False
}
CACHE_TTL = 60  # Cache time-to-live in seconds (1 hour)

def _is_cache_valid():
    """Check if the cache is still valid based on TTL"""
    return (_file_index_cache['data'] is not None and 
            time.time() - _file_index_cache['timestamp'] < CACHE_TTL)

# Async reload function to be run in a separate thread
def _async_reload_cache():
    """Asynchronously reload the file index cache"""
    if _file_index_cache['is_loading']:
        current_app.logger.debug("Cache reload already in progress")
        return
        
    try:
        _file_index_cache['is_loading'] = True
        current_app.logger.info("Starting async reload of file index cache")
        
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
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': 'page',
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
            elif "vector_database_" in blob_name:
                item_id = blob_name.split("vector_database_")[1].replace('.pkl', '')
                
                # Get title from metadata if available
                title = f"Database: {item_id[:8]}..."
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': 'database',
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
            elif "vector_document_" in blob_name:
                item_id = blob_name.split("vector_document_")[1].replace('.pkl', '')
                
                # Get title and format from metadata if available
                title = f"Document: {item_id[:8]}..."
                doc_type = "document"
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    if 'format' in metadata_dict[item_id]:
                        doc_type = metadata_dict[item_id]['format']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': doc_type,
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
        
        # Update cache with new data
        _file_index_cache['data'] = indexes
        _file_index_cache['timestamp'] = time.time()
        current_app.logger.info(f"Async file index cache update completed with {len(indexes)} items")
        
    except Exception as e:
        current_app.logger.error(f"Error in async cache reload: {str(e)}")
    finally:
        _file_index_cache['is_loading'] = False

# The synchronous version of the reload cache function
def _sync_reload_cache():
    """Synchronously reload the file index cache"""
    if _file_index_cache['is_loading']:
        current_app.logger.debug("Cache reload already in progress")
        return _file_index_cache['data'] or []
        
    try:
        _file_index_cache['is_loading'] = True
        current_app.logger.info("Starting synchronous reload of file index cache")
        
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
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': 'page',
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
            elif "vector_database_" in blob_name:
                item_id = blob_name.split("vector_database_")[1].replace('.pkl', '')
                
                # Get title from metadata if available
                title = f"Database: {item_id[:8]}..."
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': 'database',
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
            elif "vector_document_" in blob_name:
                item_id = blob_name.split("vector_document_")[1].replace('.pkl', '')
                
                # Get title and format from metadata if available
                title = f"Document: {item_id[:8]}..."
                doc_type = "document"
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    if 'format' in metadata_dict[item_id]:
                        doc_type = metadata_dict[item_id]['format']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': doc_type,
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
        
        # Update cache with new data
        _file_index_cache['data'] = indexes
        _file_index_cache['timestamp'] = time.time()
        current_app.logger.info(f"Sync file index cache update completed with {len(indexes)} items")
        return indexes
        
    except Exception as e:
        current_app.logger.error(f"Error in sync cache reload: {str(e)}")
        return []
    finally:
        _file_index_cache['is_loading'] = False

def get_available_indexes():
    """
    Get a list of available indexes from GCS bucket.
    Uses an in-memory cache with TTL to avoid frequent GCS requests.
    
    Returns:
        list: List of available index IDs and types with titles
    """
    try:
        # Check if we have valid cached data
        if _is_cache_valid():
            current_app.logger.debug("Returning cached file index list")
            return _file_index_cache['data']

        current_app.logger.debug("Cache miss or expired")
        
        # If cache is expired but we have data, trigger async reload and return stale data
        if _file_index_cache['data'] is not None:
            current_app.logger.info("Returning stale cache and starting async reload")
            # Start async reload in the background
            thread = threading.Thread(target=_async_reload_cache)
            thread.daemon = True
            thread.start()
            return _file_index_cache['data']
        
        # If no data in cache, we need to load synchronously the first time
        current_app.logger.info("No data in cache, loading synchronously")
        
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
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': 'page',
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
            elif "vector_database_" in blob_name:
                item_id = blob_name.split("vector_database_")[1].replace('.pkl', '')
                
                # Get title from metadata if available
                title = f"Database: {item_id[:8]}..."
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': 'database',
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
            elif "vector_document_" in blob_name:
                item_id = blob_name.split("vector_document_")[1].replace('.pkl', '')
                
                # Get title and format from metadata if available
                title = f"Document: {item_id[:8]}..."
                doc_type = "document"
                themes = []
                keywords = []
                if item_id in metadata_dict:
                    if 'title' in metadata_dict[item_id]:
                        title = metadata_dict[item_id]['title']
                    if 'format' in metadata_dict[item_id]:
                        doc_type = metadata_dict[item_id]['format']
                    # Extract themes and keywords from auto_metadata if available
                    if 'auto_metadata' in metadata_dict[item_id]:
                        auto_metadata = metadata_dict[item_id]['auto_metadata']
                        themes = auto_metadata.get('themes', [])
                        keywords = auto_metadata.get('keywords', [])
                
                indexes.append({
                    'id': item_id,
                    'type': doc_type,
                    'title': title,
                    'path': blob_name,
                    'themes': themes[:3] if themes else [],  # Include top 3 themes
                    'keywords': keywords[:5] if keywords else []  # Include top 5 keywords
                })
        
        # Update cache with new data
        _file_index_cache['data'] = indexes
        _file_index_cache['timestamp'] = time.time()
        current_app.logger.debug("Updated file index cache with fresh data")
        
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
    Now performs a synchronous reload to ensure fresh data is returned immediately.
    Call this after adding or deleting files.
    """
    current_app.logger.info("Force-refreshing file index cache synchronously")
    # Use the synchronous reload method instead of async
    return _sync_reload_cache()

def get_content_metadata(index_id: str) -> Dict[str, Any]:
    """
    Get the full metadata for a specific content item.
    
    Args:
        index_id (str): The ID of the content to retrieve metadata for
        
    Returns:
        dict: Complete metadata including auto-generated metadata
    """
    try:
        # Determine the metadata blob path based on ID format
        blob_paths = [
            f"cache/metadata_{index_id}.pkl",  # Notion page
            f"cache/metadata_db_{index_id}.pkl",  # Notion database
            f"cache/metadata_doc_{index_id}.pkl"  # Document
        ]
        
        for path in blob_paths:
            try:
                metadata = download_blob_to_memory(path)
                current_app.logger.debug(f"Found metadata for {index_id} at {path}")
                return metadata
            except Exception:
                pass
                
        current_app.logger.warning(f"No metadata found for index {index_id}")
        return {}
        
    except Exception as e:
        current_app.logger.error(f"Error getting content metadata: {str(e)}")
        return {}

def query_content(query: str, index_ids: List[str] = None, use_metadata_filtering: bool = False) -> Dict[str, Any]:
    """
    Query cached content using vector search.
    
    Args:
        query (str): The query to search for
        index_ids (list, optional): List of specific index IDs to search in
        use_metadata_filtering (bool): Whether to use auto-metadata for filtering/ranking
        
    Returns:
        dict: Search results with sources and metadata
    """
    try:
        # Find all available indexes if none specified
        available_indexes = get_available_indexes()
        
        if not available_indexes:
            return {"error": "No cached content found"}
        
        # Filter indexes if specific ones requested
        if index_ids:
            indexes_to_query = [idx for idx in available_indexes if idx['id'] in index_ids]
        else:
            indexes_to_query = available_indexes
        
        if not indexes_to_query:
            return {"error": "Specified indexes not found in cache"}
        
        # If using metadata filtering, we'll use it for query enhancement or post-processing
        if use_metadata_filtering:
            current_app.logger.info("Using metadata for enhanced searching")
        
        # Query each index and collect results
        all_results = []
        for idx_info in indexes_to_query:
            try:
                # Download index from GCS
                index = download_blob_to_memory(idx_info['path'])
                retriever = index.as_retriever(similarity_top_k=3)
                
                # Get relevant nodes from the index
                retrieved_nodes = retriever.retrieve(query)
                
                # Add results with source information and metadata
                for node in retrieved_nodes:
                    # Get full metadata for this content if available
                    content_id = idx_info['id']
                    
                    result = {
                        "content": node.text,
                        "score": node.score if hasattr(node, 'score') else None,
                        "source": f"{idx_info['type']}:{idx_info['id']}",
                        "title": idx_info['title'],
                        "themes": idx_info.get('themes', []),
                        "keywords": idx_info.get('keywords', [])
                    }
                    
                    all_results.append(result)
            
            except Exception as e:
                current_app.logger.error(f"Error querying index {idx_info['id']}: {str(e)}")
                continue
        
        # Sort results by relevance score (if available)
        all_results.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
        
        # If using metadata filtering, we can boost results that match key themes/topics
        if use_metadata_filtering and query:
            # This is a simple boost mechanism; could be enhanced with more sophisticated methods
            query_lower = query.lower()
            for result in all_results:
                boost = 0
                # Check if query terms match themes/keywords
                for theme in result.get('themes', []):
                    if theme.lower() in query_lower or query_lower in theme.lower():
                        boost += 0.1
                for keyword in result.get('keywords', []):
                    if keyword.lower() in query_lower or query_lower in keyword.lower():
                        boost += 0.05
                
                # Apply the boost to the score
                if boost > 0 and 'score' in result and result['score'] is not None:
                    result['score'] = result['score'] * (1 + boost)
            
            # Re-sort after boosting
            all_results.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)
        
        return {
            "results": all_results,
            "query": query,
            "total_results": len(all_results),
            "metadata_enhanced": use_metadata_filtering
        }
    
    except Exception as e:
        current_app.logger.error(f"Error querying cached content: {str(e)}")
        return {"error": str(e)}

def get_recommender_system(query: str = None, include_metadata: bool = True) -> Dict[str, Any]:
    """
    Create content recommendations based on themes, topics, and metadata.
    
    Args:
        query (str, optional): Optional query to find related content
        include_metadata (bool): Whether to include detailed metadata in response
        
    Returns:
        dict: Recommended content grouped by themes/topics
    """
    try:
        # Get all available indexes with metadata
        all_indexes = get_available_indexes()
        
        if not all_indexes:
            return {"error": "No cached content available for recommendations"}
            
        # If query is provided, use it to find similar content
        if query:
            # Simple semantic similarity for recommendation
            results = query_content(query, use_metadata_filtering=True)
            if "error" in results:
                return {"error": results["error"]}
                
            # Get IDs of top results
            relevant_ids = [r["source"].split(":")[-1] for r in results["results"][:5]]
            
            # Filter indexes to those that are related to query results
            filtered_indexes = [idx for idx in all_indexes if idx["id"] in relevant_ids]
            
            # Add some recommended content based on themes of results
            result_themes = set()
            for r in results["results"][:5]:
                result_themes.update(r.get("themes", []))
                
            # Find content with similar themes
            if result_themes:
                for idx in all_indexes:
                    if idx["id"] not in relevant_ids:  # Don't duplicate
                        idx_themes = set(idx.get('themes', []))
                        if idx_themes.intersection(result_themes):
                            filtered_indexes.append(idx)
            
            # Use filtered indexes for recommendations            
            if filtered_indexes:
                all_indexes = filtered_indexes
        
        # Group content by themes for organization
        theme_groups = {}
        
        # Process each index to extract themes and group content
        for idx in all_indexes:
            for theme in idx.get('themes', []):
                if theme not in theme_groups:
                    theme_groups[theme] = []
                    
                # Add content to this theme group
                content_item = {
                    'id': idx['id'],
                    'title': idx['title'],
                    'type': idx['type']
                }
                
                # Include additional metadata if requested
                if include_metadata:
                    content_item['themes'] = idx.get('themes', [])
                    content_item['keywords'] = idx.get('keywords', [])
                    
                theme_groups[theme].append(content_item)
        
        # Create the recommendations response
        recommendations = {
            'query': query,
            'theme_groups': [],
            'total_items': len(all_indexes)
        }
        
        # Convert theme groups to list for the response
        for theme, items in theme_groups.items():
            recommendations['theme_groups'].append({
                'theme': theme,
                'items': items,
                'count': len(items)
            })
            
        # Sort groups by number of items descending
        recommendations['theme_groups'].sort(key=lambda x: x['count'], reverse=True)
        
        return recommendations
        
    except Exception as e:
        current_app.logger.error(f"Error generating recommendations: {str(e)}")
        return {"error": str(e)}

def get_llm_response(query: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Get a response from an LLM based on the user's query.
    
    Args:
        query (str): The user's question or prompt
        context (dict, optional): Additional context for the query
            - use_content (bool): Whether to search cached content
            - content_ids (list): Specific cached content IDs to search
            - use_metadata (bool): Whether to use metadata for enhancing the response
        
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
        auto_metadata_context = ""
        if context and context.get('use_content', False):
            content_ids = context.get('content_ids', [])
            use_metadata = context.get('use_metadata', True)  # Default to using metadata
            
            try:
                # Retrieve relevant information from cached content
                content_results = query_content(
                    query, 
                    content_ids,
                    use_metadata_filtering=use_metadata
                )
                
                if 'error' not in content_results and content_results.get('results'):
                    # Format the results as context
                    cached_context = "Here is relevant information from your documents:\n\n"
                    for i, result in enumerate(content_results['results'][:5]):  # Limit to top 5 results
                        cached_context += f"Source {i+1} ({result['title']}):\n{result['content']}\n\n"
                    
                    # Add context to system prompt
                    system_prompt += f"\n\nUse the following information from documents to answer the query:\n{cached_context}"
                    
                    # If using metadata, add that to the system prompt as well
                    if use_metadata and content_results['results'][0].get('themes'):
                        first_result = content_results['results'][0]
                        auto_metadata_context = "This question is related to the following themes and topics:\n"
                        auto_metadata_context += f"- Main themes: {', '.join(first_result.get('themes', []))}\n"
                        auto_metadata_context += f"- Key keywords: {', '.join(first_result.get('keywords', []))}\n\n"
                        system_prompt += auto_metadata_context
                    
                    # Log that we're using cached content
                    current_app.logger.info(f"Using {len(content_results['results'])} cached results for context")
            except Exception as e:
                error_msg = str(e)
                if "validation_error" in error_msg and "ai_block" in error_msg:
                    current_app.logger.error(f"API validation error: AI blocks not supported: {error_msg}")
                    return "I couldn't access some of your content because it contains AI blocks that aren't supported via the API. Please try using different content that doesn't contain AI blocks."
                else:
                    current_app.logger.error(f"Error retrieving context: {error_msg}")
                    # Continue without context but don't fail completely
                    system_prompt += "\n\nNote: I tried to access your content but encountered an error."
        
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
        import httpx
        client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=10.0)
        )
        
        # Make the API call with appropriate timeout settings
        current_app.logger.info("Making OpenAI API call with set timeouts")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=800,
            timeout=90,  # 90-second timeout for the whole request
        )
        
        return response.choices[0].message.content
        
    except httpx.TimeoutException:
        current_app.logger.error("OpenAI API request timed out")
        return "I'm sorry, but the request timed out. Please try again with a shorter query or less context."
    except Exception as e:
        current_app.logger.error(f"Error in LLM service: {str(e)}")
        return f"Sorry, there was an error processing your request: {str(e)}"