"""
Cache management for LLM service components
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