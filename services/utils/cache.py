"""
Cache management for LLM service components
"""
import io
import os
import time
import logging
import pickle
import json
from flask import current_app
from typing import Dict, Any
from services.storage_service import get_storage_client
from services.notion_service import download_blob_to_memory


# Configure logging for background tasks that can't access Flask's logger
background_logger = logging.getLogger('background_cache')
if not background_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    background_logger.addHandler(handler)
    background_logger.setLevel(logging.INFO)

# Cache storage for file indexes
_file_index_cache = {
    'data': None,
    'timestamp': 0,
    'is_loading': False
}
CACHE_TTL = 60  # Cache time-to-live in seconds

# Cache storage for folder structure
_folder_cache = {
    'data': None,
    'timestamp': 0,
    'is_loading': False
}

# Store empty folders in memory
_empty_folders = set()
# Store the empty folders information in the bucket root
_empty_folders_file = 'empty_folders.json'

# Global loading state flag
_cache_loading = False

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

def is_cache_loading():
    """Check if the cache is currently being loaded or refreshed."""
    global _cache_loading
    return _cache_loading

def set_cache_loading(state):
    """Set the cache loading state."""
    global _cache_loading
    _cache_loading = state

def _load_empty_folders():
    """Load empty folders from persistent storage in the bucket"""
    global _empty_folders
    try:
        # Get storage client and bucket
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME environment variable or config not set")
            
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_empty_folders_file)
        
        if blob.exists():
            # Download and parse the empty folders JSON
            content = blob.download_as_string()
            _empty_folders = set(json.loads(content))
            current_app.logger.info(f"Loaded {len(_empty_folders)} empty folders from bucket")
        else:
            _empty_folders = set()
            _save_empty_folders()
    except Exception as e:
        current_app.logger.error(f"Error loading empty folders: {str(e)}")
        _empty_folders = set()

def _save_empty_folders():
    """Save empty folders to persistent storage in the bucket"""
    try:
        # Get storage client and bucket
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME environment variable or config not set")
            
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(_empty_folders_file)
        
        # Convert set to list for JSON serialization and save to bucket
        json_data = json.dumps(list(_empty_folders))
        blob.upload_from_string(json_data, content_type='application/json')
        
        current_app.logger.info(f"Saved {len(_empty_folders)} empty folders to bucket root: {_empty_folders_file}")
    except Exception as e:
        current_app.logger.error(f"Error saving empty folders: {str(e)}")


def _is_folder_cache_valid():
    """Check if the folder cache is still valid based on TTL"""
    return (_folder_cache['data'] is not None and 
            time.time() - _folder_cache['timestamp'] < CACHE_TTL)

# Store app reference for background threads
_app_ref = None

# The synchronous version of the reload cache function
def _sync_reload_cache():
    """Synchronously reload the file index cache"""
    if _file_index_cache['is_loading']:
        current_app.logger.debug("Cache reload already in progress")
        return _file_index_cache['data'] or []
        
    try:
        _file_index_cache['is_loading'] = True
        current_app.logger.info("Starting synchronous reload of file index cache")
        
        # Ensure bucket exists before proceeding
        _ensure_bucket_exists()
        
        # Get GCS client and bucket
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # List blobs with cache/ prefix - only using standardized formats
        vector_blobs = list(bucket.list_blobs(prefix="cache/vector_index_"))
        metadata_blobs = list(bucket.list_blobs(prefix="cache/metadata_"))
        
        # Create a dictionary of metadata by ID
        metadata_dict = {}
        for blob in metadata_blobs:
            try:
                # Extract ID from the blob name using only standardized format
                blob_name = blob.name
                item_id = blob_name.split("metadata_")[1].replace('.pkl', '')
                metadata = download_blob_to_memory(blob_name)
                metadata_dict[item_id] = metadata
            except Exception as e:
                current_app.logger.error(f"Error processing metadata blob {blob_name}: {str(e)}")
                continue
        
        indexes = []
        for blob in vector_blobs:
            index_info = _process_vector_blob(blob.name, metadata_dict)
            if index_info:
                indexes.append(index_info)
        
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

def get_available_indexes(folder_path=None):
    """
    Get all available indexed content.
    Optionally filter by folder path.
    
    Args:
        folder_path (str, optional): The folder path to filter by. Will include items in this folder.
        
    Returns:
        List[Dict[str, Any]]: A list of available indexes, empty list if error occurs
    """
    try:
        # Get indexes from storage
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            current_app.logger.error("GCS_BUCKET_NAME environment variable not set")
            return []
        
        bucket = client.bucket(bucket_name)
        indexes = []
        
        # List all metadata files in the cache folder
        try:
            blobs = list(bucket.list_blobs(prefix="cache/"))
        except Exception as e:
            current_app.logger.error(f"Error listing blobs: {str(e)}")
            return []
        
        for blob in blobs:
            if blob.name.startswith("cache/metadata_"):
                try:
                    blob_name = blob.name
                    
                    # Download and parse metadata
                    metadata_bytes = blob.download_as_bytes()
                    if not metadata_bytes:
                        continue
                        
                    metadata = pickle.loads(metadata_bytes)
                    if not metadata:
                        continue
                    
                    # Get the item's folder path
                    item_folder = metadata.get('folder', '')
                    
                    # Include item if:
                    # 1. No folder filter is applied (folder_path is None)
                    # 2. Item is exactly in the requested folder
                    # 3. Item is in a subfolder of the requested folder (item_folder starts with folder_path/)
                    should_include = (
                        folder_path is None or
                        item_folder == folder_path or
                        (folder_path and item_folder and 
                         item_folder.startswith(folder_path + '/'))
                    )
                    
                    if should_include:
                        # Add the item's ID and other relevant info
                        index_item = {
                            'id': metadata.get('id', ''),
                            'notion_id': metadata.get('notion_id', ''),
                            'title': metadata.get('title', 'Untitled'),
                            'type': metadata.get('type', 'document') == 'document' and metadata.get('format', 'unknown') or metadata.get('type', 'unknown'),
                            'folder': item_folder,
                            'path': metadata.get('folder', ''),
                            '_storage_path': metadata.get('_storage_path', '')
                        }
                        indexes.append(index_item)
                except Exception as e:
                    current_app.logger.error(f"Error loading metadata from {blob.name}: {str(e)}")
                    continue
        
        return indexes or []
    except Exception as e:
        current_app.logger.error(f"Error in get_available_indexes: {str(e)}")
        return []
    finally:
        set_cache_loading(False)

def refresh_file_index_cache():
    """
    Force a refresh of the file index cache.
    Now performs a synchronous reload to ensure fresh data is returned immediately.
    Call this after adding or deleting files.
    """
    current_app.logger.info("Force-refreshing file index cache synchronously")
    # Use the synchronous reload method instead of async
    return _sync_reload_cache()

def _update_item_metadata(item_id: str, metadata_update: Dict):
    """
    Update metadata for an item
    
    Args:
        item_id (str): The item ID
        metadata_update (Dict): The metadata updates to apply
    """
    try:
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Only use standardized metadata blob format
        metadata_blob_name = f"cache/metadata_{item_id}.pkl"
        
        # Get current metadata
        metadata_blob = bucket.blob(metadata_blob_name)
        metadata = download_blob_to_memory(metadata_blob_name)
        
        # Update metadata
        metadata.update(metadata_update)
        
        # Save updated metadata
        with io.BytesIO() as file_buffer:
            pickle.dump(metadata, file_buffer)
            file_buffer.seek(0)
            metadata_blob.upload_from_file(file_buffer)
            
        current_app.logger.info(f"Updated metadata for item {item_id}")
        
    except Exception as e:
        current_app.logger.error(f"Error updating metadata for item {item_id}: {str(e)}")
        raise

def move_item_to_folder(item_id: str, folder_path: str):
    """
    Move an item to a different folder
    
    Args:
        item_id (str): The item ID
        folder_path (str): The destination folder path
    """
    try:
        # Make sure the folder exists in the folder structure first
        _ensure_folder_exists(folder_path)
        
        # Update item metadata with new folder
        _update_item_metadata(item_id, {'folder': folder_path})
        
        # If the folder was previously empty, it's now used by an item
        if folder_path in _empty_folders:
            _empty_folders.remove(folder_path)
            _save_empty_folders()
        
        # Force a full cache refresh sequence
        refresh_file_index_cache()
        _sync_reload_folder_cache()
        
    except Exception as e:
        current_app.logger.error(f"Error moving item {item_id} to folder {folder_path}: {str(e)}")
        raise

def _sync_reload_folder_cache():
    """Synchronously reload the folder cache"""
    global _cache_loading
    if _folder_cache['is_loading']:
        current_app.logger.debug("Folder cache reload already in progress")
        return _folder_cache['data'] or []
        
    try:
        set_cache_loading(True)
        _folder_cache['is_loading'] = True
        current_app.logger.info("Starting synchronous reload of folder cache")
        
        # Load empty folders if not already loaded
        if not hasattr(_sync_reload_folder_cache, '_loaded_empty_folders'):
            _load_empty_folders()
            _sync_reload_folder_cache._loaded_empty_folders = True
        
        # Get all indexed items
        items = get_available_indexes()
        
        # Prepare the folder structure
        folders = [{'path': '', 'name': 'Root'}]  # Start with Root folder
        
        # Track all folders found in items for later comparison
        item_folders = set()
        
        # Collect all unique folder paths from items
        for item in items:
            folder_path = item.get('folder', '')
            if folder_path:
                item_folders.add(folder_path)
                if not any(f['path'] == folder_path for f in folders):
                    # Break down path components to ensure we have all parent folders
                    path_parts = folder_path.split('/')
                    current_path = ''
                    
                    for i, part in enumerate(path_parts):
                        if part:
                            if current_path:
                                current_path = f"{current_path}/{part}"
                            else:
                                current_path = part
                            
                            item_folders.add(current_path)  # Add this path to found folders
                            if not any(f['path'] == current_path for f in folders):
                                folders.append({
                                    'path': current_path, 
                                    'name': part,
                                    'parent': '/'.join(path_parts[:i]) if i > 0 else ''
                                })
        
        # Add empty folders that aren't already included from items
        for empty_folder in _empty_folders:
            if empty_folder and not any(f['path'] == empty_folder for f in folders):
                # Break down path to get the folder name and parent
                path_parts = empty_folder.split('/')
                folder_name = path_parts[-1]
                parent_path = '/'.join(path_parts[:-1]) if len(path_parts) > 1 else ''
                
                folders.append({
                    'path': empty_folder,
                    'name': folder_name,
                    'parent': parent_path
                })
                
                # Make sure parent folders are also included
                current_path = ''
                for i, part in enumerate(path_parts[:-1]):  # Skip the last part as we already added it
                    if part:
                        if current_path:
                            current_path = f"{current_path}/{part}"
                        else:
                            current_path = part
                            
                        if not any(f['path'] == current_path for f in folders):
                            folders.append({
                                'path': current_path,
                                'name': part,
                                'parent': '/'.join(path_parts[:i]) if i > 0 else ''
                            })
        
        # Sort folders by path for consistent display
        folders.sort(key=lambda x: x['path'])
        
        # Update cache with new data
        _folder_cache['data'] = folders
        _folder_cache['timestamp'] = time.time()
        current_app.logger.info(f"Sync folder cache update completed with {len(folders)} folders")
        return folders
        
    except Exception as e:
        current_app.logger.error(f"Error in sync folder cache reload: {str(e)}")
        return []
    finally:
        set_cache_loading(False)
        _folder_cache['is_loading'] = False

def get_folders():
    """
    Get all available folders in the system.
    
    Returns:
        List[Dict[str, str]]: A list of folders with path and name
    """
    try:
        # Use cached data if it's still valid, otherwise reload
        if not _is_folder_cache_valid() or _folder_cache['data'] is None:
            current_app.logger.debug("Folder cache expired or not initialized")
            return _sync_reload_folder_cache()
            
        return _folder_cache['data']
        
    except Exception as e:
        current_app.logger.error(f"Error getting folders: {str(e)}")
        # On error, return cached data if available (even if expired), otherwise empty list
        if _folder_cache['data'] is not None:
            current_app.logger.warning("Returning stale folder cache data due to error")
            return _folder_cache['data']
        return [{'path': '', 'name': 'Root'}]  # Always include at least the root folder

def create_folder(name: str, parent_path: str = ''):
    """
    Create a new folder
    
    Args:
        name (str): The folder name
        parent_path (str, optional): The parent folder path
        
    Returns:
        str: The full path of the created folder
    """
    try:
        # Create the full path
        full_path = f"{parent_path}/{name}" if parent_path else name
        
        # Ensure parent folder exists
        if parent_path and not any(f['path'] == parent_path for f in get_folders()):
            raise ValueError(f"Parent folder {parent_path} does not exist")
        
        # Check if folder already exists
        if any(f['path'] == full_path for f in get_folders()):
            current_app.logger.warning(f"Folder {full_path} already exists")
            return full_path
            
        # Track this as an empty folder since it has no items yet
        global _empty_folders
        _empty_folders.add(full_path)
        _save_empty_folders()
        
        # We don't actually need to create a folder entry in storage, we just need to
        # ensure it's registered in our folder cache
        _ensure_folder_exists(full_path)
        
        # Refresh folder cache
        _sync_reload_folder_cache()
        
        return full_path
        
    except Exception as e:
        current_app.logger.error(f"Error creating folder {name} in {parent_path}: {str(e)}")
        raise

def _ensure_folder_exists(folder_path: str):
    """
    Ensure a folder exists in our folder cache structure.
    This is called whenever a folder is referenced to keep the folder structure consistent.
    
    Args:
        folder_path (str): The folder path to ensure exists
    """
    if not folder_path:
        return  # Root folder always exists
        
    folders = get_folders()
    
    # Check if folder already exists
    if any(f['path'] == folder_path for f in folders):
        return
        
    # Break down path components to ensure we have all parent folders
    path_parts = folder_path.split('/')
    current_path = ''
    
    for i, part in enumerate(path_parts):
        if part:
            if current_path:
                current_path = f"{current_path}/{part}"
            else:
                current_path = part
                
            if not any(f['path'] == current_path for f in folders):
                folders.append({
                    'path': current_path, 
                    'name': part,
                    'parent': '/'.join(path_parts[:i]) if i > 0 else ''
                })
    
    # Update the folder cache
    _folder_cache['data'] = folders
    _folder_cache['timestamp'] = time.time()

def rename_folder(folder_path: str, new_name: str):
    """
    Rename a folder and update all items in it, including subfolders
    
    Args:
        folder_path (str): The current folder path
        new_name (str): The new folder name
        
    Returns:
        str: The new full path of the renamed folder
    """
    try:
        # Check if folder exists
        folders = get_folders()
        if not any(f['path'] == folder_path for f in folders):
            raise ValueError(f"Folder {folder_path} does not exist")
            
        # Cannot rename root
        if not folder_path:
            raise ValueError("Cannot rename root folder")
            
        # Create the new path
        path_parts = folder_path.split('/')
        parent_path = '/'.join(path_parts[:-1])
        new_path = f"{parent_path}/{new_name}" if parent_path else new_name
        
        # Check if target name already exists
        if any(f['path'] == new_path for f in folders):
            raise ValueError(f"Folder {new_path} already exists")
        
        # Get all items in this folder and subfolders
        items = get_available_indexes()
        affected_items = [item for item in items if item['folder'] == folder_path or 
                          item['folder'].startswith(f"{folder_path}/")]
                          
        # Update each item's folder path
        for item in affected_items:
            old_folder = item['folder']
            if old_folder == folder_path:
                # Item directly in this folder
                new_folder = new_path
            else:
                # Item in subfolder
                new_folder = old_folder.replace(folder_path, new_path, 1)
                
            _update_item_metadata(item['id'], {'folder': new_folder})
        
        # Update empty folders list for subfolders
        global _empty_folders
        updated_empty_folders = set()
        
        for folder in _empty_folders:
            if folder == folder_path:
                # Direct match - use the new path
                updated_empty_folders.add(new_path)
            elif folder.startswith(f"{folder_path}/"):
                # Subfolder - replace the prefix
                updated_empty_folders.add(folder.replace(folder_path, new_path, 1))
            else:
                # Not affected - keep as is
                updated_empty_folders.add(folder)
        
        _empty_folders = updated_empty_folders
        _save_empty_folders()
            
        # Refresh caches
        refresh_file_index_cache()
        _sync_reload_folder_cache()
        
        current_app.logger.info(f"Renamed folder from {folder_path} to {new_path}, affecting {len(affected_items)} items")
        return new_path
        
    except Exception as e:
        current_app.logger.error(f"Error renaming folder {folder_path} to {new_name}: {str(e)}")
        raise

def delete_folder(folder_path: str, delete_contents: bool = False):
    """
    Delete a folder and manage all items within it and its subfolders
    
    Args:
        folder_path (str): The folder path to delete
        delete_contents (bool, optional): Whether to delete the folder contents or move them to the parent folder
        
    Returns:
        int: The number of items affected
    """
    try:
        # Check if folder exists
        folders = get_folders()
        if not any(f['path'] == folder_path for f in folders):
            raise ValueError(f"Folder {folder_path} does not exist")
            
        # Cannot delete root
        if not folder_path:
            raise ValueError("Cannot delete root folder")
            
        # Get all items in this folder and subfolders
        items = get_available_indexes()
        affected_items = [item for item in items if item['folder'] == folder_path or 
                          item['folder'].startswith(f"{folder_path}/")]
                          
        # Get parent folder path
        path_parts = folder_path.split('/')
        parent_path = '/'.join(path_parts[:-1])
        
        # Move all items to the parent folder (including those in subfolders)
        for item in affected_items:
            _update_item_metadata(item['id'], {'folder': parent_path})
        
        # Remove the deleted folder and all its subfolders from the empty folders list
        global _empty_folders
        folders_to_remove = set()
        
        for folder in _empty_folders:
            if folder == folder_path or folder.startswith(f"{folder_path}/"):
                folders_to_remove.add(folder)
        
        # Remove all the identified folders
        _empty_folders -= folders_to_remove
        
        # If the parent folder is now being used, ensure it's not in empty_folders
        if affected_items and parent_path in _empty_folders:
            _empty_folders.remove(parent_path)
        
        # Save the updated empty folders list
        _save_empty_folders()
            
        # Refresh caches
        refresh_file_index_cache()
        _sync_reload_folder_cache()
        
        current_app.logger.info(f"Deleted folder {folder_path}, moved {len(affected_items)} items to {parent_path}")
        return len(affected_items)
        
    except Exception as e:
        current_app.logger.error(f"Error deleting folder {folder_path}: {str(e)}")
        raise

def _process_vector_blob(blob_name: str, metadata_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Process a vector blob and return its index information"""
    if not blob_name.endswith('.pkl'):
        return None
    
    # Only support standardized ID format
    if "vector_index_" in blob_name:
        clean_id = blob_name.split("vector_index_")[1].replace('.pkl', '')
        item_type = 'page'
    else:
        return None
        
    title = f"{item_type.capitalize()}: {clean_id[:8]}..."
    themes = []
    keywords = []
    folder = ""
    
    # Get metadata if available
    if clean_id in metadata_dict:
        metadata = metadata_dict[clean_id]
        if 'title' in metadata:
            title = metadata['title']
        if 'format' in metadata and item_type == 'document':
            item_type = metadata['format']
        if 'folder' in metadata:
            folder = metadata['folder']
        if 'auto_metadata' in metadata:
            auto_metadata = metadata['auto_metadata']
            themes = auto_metadata.get('themes', [])[:3]
            keywords = auto_metadata.get('keywords', [])[:5]
    
    return {
        'id': clean_id,
        'type': item_type,
        'title': title,
        'path': blob_name,
        'folder': folder,
        'themes': themes,
        'keywords': keywords
    }
