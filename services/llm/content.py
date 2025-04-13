"""
Content retrieval and querying functionality for LLM services
"""
import os
from flask import current_app
from typing import List, Dict, Any
from services.notion_service import download_blob_to_memory
from services.utils.cache import get_available_indexes 
from services.storage_service import get_storage_client, get_file_metadata

def _ensure_bucket_exists():
    """Ensure the GCS bucket exists and is accessible."""
    try:
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME environment variable or config not set")
            
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            current_app.logger.info(f"Creating bucket {bucket_name}")
            bucket.create()
            
        # Create the cache directory structure if it doesn't exist
        cache_blob = bucket.blob('cache/')
        if not cache_blob.exists():
            current_app.logger.info("Initializing cache directory structure")
            cache_blob.upload_from_string('')
            
        return True
    except Exception as e:
        current_app.logger.error(f"Error ensuring bucket exists: {str(e)}")
        raise

def get_content_metadata(index_id: str) -> Dict[str, Any]:
    """Get metadata for a specific content index."""
    _ensure_bucket_exists()
    try:
        # Use the storage service method that handles different metadata formats
        return get_file_metadata(index_id)
    except Exception as e:
        current_app.logger.error(f"Error getting content metadata: {str(e)}")
        raise

def query_content(query: str, index_ids: List[str] = None, use_metadata_filtering: bool = False) -> Dict[str, Any]:
    """
    Query content across one or more indexes.
    
    Args:
        query (str): The query string
        index_ids (List[str], optional): List of specific index IDs to query. If None, queries all available indexes.
        use_metadata_filtering (bool, optional): Whether to use metadata for filtering results
        
    Returns:
        Dict[str, Any]: Query results
    """
    _ensure_bucket_exists()
    try:
        if not index_ids:
            # Get all available indexes if none specified
            indexes = get_available_indexes()
            index_ids = [idx['id'] for idx in indexes if idx]
        
        results = []
        for index_id in index_ids:
            try:
                clean_id =index_id
                current_app.logger.info(f"Querying content with ID: {clean_id}")
                
                # Try all possible vector index paths for this ID
                client = get_storage_client()
                bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
                bucket = client.bucket(bucket_name)
                
                # Check if blobs exist before attempting to download
                vector_paths = []
                possible_paths = [
                    f"cache/vector_index_{clean_id}.pkl",
                ]
                
                for path in possible_paths:
                    if bucket.blob(path).exists():
                        vector_paths.append(path)
                        current_app.logger.info(f"Found vector index at {path}")
                
                if not vector_paths:
                    current_app.logger.warning(f"No vector index found for {clean_id}")
                    continue
                
                # Try to load the vector index from all found paths
                index = None
                for path in vector_paths:
                    try:
                        index = download_blob_to_memory(path)
                        if index:
                            current_app.logger.info(f"Successfully loaded index from {path}")
                            break
                    except Exception as e:
                        current_app.logger.warning(f"Error loading index from {path}: {str(e)}")
                
                if not index:
                    current_app.logger.warning(f"Could not load any index for {clean_id}")
                    continue
                
                # Create query engine and execute query
                query_engine = index.as_query_engine()
                response = query_engine.query(query)
                
                # Get metadata for this index
                try:
                    metadata = get_content_metadata(clean_id)
                    title = metadata.get('title', f'Content {clean_id}')
                except Exception as e:
                    current_app.logger.warning(f"Could not get metadata for {clean_id}: {str(e)}")
                    title = f"Content {clean_id}"
                
                results.append({
                    "index_id": clean_id,
                    "title": title,
                    "response": str(response)
                })
                
            except Exception as e:
                current_app.logger.error(f"Error querying index {index_id}: {str(e)}")
                continue
        
        if not results:
            raise ValueError("No results found for query across available indexes")
            
        return {
            "success": True,
            "query": query,
            "results": results
        }
        
    except Exception as e:
        current_app.logger.error(f"Error in query_content: {str(e)}")
        raise