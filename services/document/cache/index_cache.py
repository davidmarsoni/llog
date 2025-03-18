"""
Cache management for document file indexes
"""
from flask import current_app
import os
import time
import threading
from typing import List, Dict, Any
from services.storage_service import get_storage_client
from services.notion_service import download_blob_to_memory

# Cache storage for file indexes
_file_index_cache = {
    'data': None,
    'timestamp': 0,
    'is_loading': False
}
CACHE_TTL = 60  # Cache time-to-live in seconds

def _is_cache_valid():
    """Check if the cache is still valid based on TTL"""
    return (_file_index_cache['data'] is not None and 
            time.time() - _file_index_cache['timestamp'] < CACHE_TTL)

def _process_metadata_blob(blob_name: str) -> tuple[str, Dict[str, Any]]:
    """Process a metadata blob and return its ID and content"""
    if "metadata_db_" in blob_name:
        item_id = blob_name.split("metadata_db_")[1].replace('.pkl', '')
    elif "metadata_doc_" in blob_name:
        item_id = blob_name.split("metadata_doc_")[1].replace('.pkl', '')
    else:
        item_id = blob_name.split("metadata_")[1].replace('.pkl', '')
    
    metadata = download_blob_to_memory(blob_name)
    return item_id, metadata

def _process_vector_blob(blob_name: str, metadata_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a vector blob and return its index information"""
    if not blob_name.endswith('.pkl'):
        return None
        
    if "vector_index_" in blob_name:
        item_id = blob_name.split("vector_index_")[1].replace('.pkl', '')
        item_type = 'page'
    elif "vector_database_" in blob_name:
        item_id = blob_name.split("vector_database_")[1].replace('.pkl', '')
        item_type = 'database'
    elif "vector_document_" in blob_name:
        item_id = blob_name.split("vector_document_")[1].replace('.pkl', '')
        item_type = 'document'
    else:
        return None
        
    title = f"{item_type.capitalize()}: {item_id[:8]}..."
    themes = []
    keywords = []
    
    if item_id in metadata_dict:
        metadata = metadata_dict[item_id]
        if 'title' in metadata:
            title = metadata['title']
        if item_type == 'document' and 'format' in metadata:
            item_type = metadata['format']
        if 'auto_metadata' in metadata:
            auto_metadata = metadata['auto_metadata']
            themes = auto_metadata.get('themes', [])[:3]
            keywords = auto_metadata.get('keywords', [])[:5]
    
    return {
        'id': item_id,
        'type': item_type,
        'title': title,
        'path': blob_name,
        'themes': themes,
        'keywords': keywords
    }

def _load_indexes() -> List[Dict[str, Any]]:
    """Load indexes from storage and process them"""
    client = get_storage_client()
    bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
    bucket = client.bucket(bucket_name)
    
    # List blobs with cache/ prefix
    vector_blobs = list(bucket.list_blobs(prefix="cache/vector_"))
    metadata_blobs = list(bucket.list_blobs(prefix="cache/metadata_"))
    
    # Process metadata blobs
    metadata_dict = {}
    for blob in metadata_blobs:
        try:
            item_id, metadata = _process_metadata_blob(blob.name)
            metadata_dict[item_id] = metadata
        except Exception as e:
            current_app.logger.error(f"Error processing metadata blob {blob.name}: {str(e)}")
            continue
    
    # Process vector blobs
    indexes = []
    for blob in vector_blobs:
        try:
            index_info = _process_vector_blob(blob.name, metadata_dict)
            if index_info:
                indexes.append(index_info)
        except Exception as e:
            current_app.logger.error(f"Error processing vector blob {blob.name}: {str(e)}")
            continue
    
    return indexes

def _async_reload_cache():
    """Asynchronously reload the file index cache"""
    if _file_index_cache['is_loading']:
        current_app.logger.debug("Cache reload already in progress")
        return
        
    try:
        _file_index_cache['is_loading'] = True
        current_app.logger.info("Starting async reload of file index cache")
        
        indexes = _load_indexes()
        
        # Update cache with new data
        _file_index_cache['data'] = indexes
        _file_index_cache['timestamp'] = time.time()
        current_app.logger.info(f"Async file index cache update completed with {len(indexes)} items")
        
    except Exception as e:
        current_app.logger.error(f"Error in async cache reload: {str(e)}")
    finally:
        _file_index_cache['is_loading'] = False

def _sync_reload_cache() -> List[Dict[str, Any]]:
    """Synchronously reload the file index cache"""
    if _file_index_cache['is_loading']:
        current_app.logger.debug("Cache reload already in progress")
        return _file_index_cache['data'] or []
        
    try:
        _file_index_cache['is_loading'] = True
        current_app.logger.info("Starting synchronous reload of file index cache")
        
        indexes = _load_indexes()
        
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

def get_available_indexes() -> List[Dict[str, Any]]:
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
            thread = threading.Thread(target=_async_reload_cache)
            thread.daemon = True
            thread.start()
            return _file_index_cache['data']
        
        # If no data in cache, load synchronously
        current_app.logger.info("No data in cache, loading synchronously")
        return _sync_reload_cache()
    
    except Exception as e:
        current_app.logger.error(f"Error getting available indexes: {str(e)}")
        # On error, return cached data if available (even if expired), otherwise empty list
        if _file_index_cache['data'] is not None:
            current_app.logger.warning("Returning stale cache data due to error")
            return _file_index_cache['data']
        return []

def refresh_file_index_cache() -> List[Dict[str, Any]]:
    """
    Force a refresh of the file index cache.
    Performs a synchronous reload to ensure fresh data is returned immediately.
    Call this after adding or deleting files.
    """
    current_app.logger.info("Force-refreshing file index cache synchronously")
    return _sync_reload_cache()