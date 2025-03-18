"""
Content retrieval and querying functionality for LLM services
"""
from flask import current_app
import os
from typing import List, Dict, Any
from services.notion_service import download_blob_to_memory
from services.llm.cache import get_available_indexes

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