"""
Storage service for handling Google Cloud Storage operations
"""
import uuid
from flask import current_app
from google.cloud import storage
import os
import io
import pickle
import time

def get_storage_client():
    """Get a Google Cloud Storage client."""
    try:
        # First try using Application Default Credentials
        client = storage.Client()
        
        # Ensure the bucket exists and we can access it
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        if not bucket_name:
            raise ValueError("GCS_BUCKET_NAME environment variable or config not set")
            
        bucket = client.bucket(bucket_name)
        if not bucket.exists():
            current_app.logger.info(f"Creating bucket {bucket_name}")
            bucket.create()
            
        return client
    except Exception as e:
        current_app.logger.error(f"Error initializing storage client: {str(e)}")
        raise

def generate_uuid():
    """Generate a new unique uuid"""
    return str(uuid.uuid4())

def get_all_files():
    """Get a list of all files in the storage bucket."""
    client = get_storage_client()
    bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
    bucket = client.bucket(bucket_name)
    
    # List all blobs/files in the bucket
    blobs = list(bucket.list_blobs())
    
    # Get file details
    files = []
    for blob in blobs:
        files.append({
            'name': blob.name,
            'size': blob.size,
            'updated': blob.updated,
            'content_type': blob.content_type
        })
        
    return files

def upload_file_to_storage(file):
    """Upload a file to the storage bucket."""
    client = get_storage_client()
    bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
    bucket = client.bucket(bucket_name)
    
    # Create a blob and upload the file
    blob = bucket.blob(file.filename)
    blob.upload_from_file(file)
    
    return True

def delete_file_from_storage(file_id):
    """Delete all related files associated with an index ID."""
    try:
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Determine the file type by the ID format
        current_app.logger.info(f"Attempting to delete content with ID: {file_id}")
        
        # Look for all possible file patterns for this ID
        patterns = [
            f"cache/metadata_{file_id}.pkl",
            f"cache/metadata_db_{file_id}.pkl",
            f"cache/metadata_doc_{file_id}.pkl",
            f"cache/notion_data_{file_id}.pkl",
            f"cache/notion_database_{file_id}.pkl",
            f"cache/document_data_{file_id}.pkl",
            f"cache/vector_index_{file_id}.pkl",
            f"cache/vector_database_{file_id}.pkl",
            f"cache/vector_document_{file_id}.pkl"
        ]
        
        deleted = False
        for pattern in patterns:
            try:
                blob = bucket.blob(pattern)
                if blob.exists():
                    blob.delete()
                    current_app.logger.info(f"Deleted file {pattern}")
                    deleted = True
            except Exception as e:
                current_app.logger.warning(f"Could not delete {pattern}: {str(e)}")
        
        if not deleted:
            # If no files matched our patterns, try direct path deletion as fallback
            try:
                blob = bucket.blob(file_id)
                if blob.exists():
                    blob.delete()
                    current_app.logger.info(f"Deleted file using direct path: {file_id}")
                    deleted = True
            except Exception as e:
                current_app.logger.error(f"Could not delete file using direct path {file_id}: {str(e)}")
        
        if not deleted:
            raise ValueError(f"No files found to delete for ID: {file_id}")
        
        return True
    except Exception as e:
        current_app.logger.error(f"Error in delete_file_from_storage: {str(e)}")
        raise

def get_file_metadata(file_id):
    """
    Get metadata for a specific file ID.
    
    Args:
        file_id (str): The file ID to retrieve metadata for
        
    Returns:
        dict: The file metadata or None if not found
    """
    try:
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Clean up the file_id by removing any cache/ or .pkl suffix
        clean_id = file_id.replace('cache/', '').replace('.pkl', '')
        
        # Look for metadata in all possible locations
        metadata_paths = [
            f"cache/metadata_{clean_id}.pkl",
            f"cache/metadata_db_{clean_id}.pkl",
            f"cache/metadata_doc_{clean_id}.pkl"
        ]
        
        metadata = None
        found_path = None
        
        for path in metadata_paths:
            blob = bucket.blob(path)
            if blob.exists():
                found_path = path
                with io.BytesIO() as file_buffer:
                    blob.download_to_file(file_buffer)
                    file_buffer.seek(0)
                    metadata = pickle.load(file_buffer)
                break
                
        if metadata:
            # Add the blob path to the metadata
            metadata['_storage_path'] = found_path
            current_app.logger.info(f"Retrieved metadata for {clean_id} from {found_path}")
            return metadata
        else:
            current_app.logger.warning(f"No metadata found for file ID: {clean_id}")
            return None
            
    except Exception as e:
        current_app.logger.error(f"Error retrieving file metadata: {str(e)}")
        return None

def update_file_metadata(file_id, updated_metadata):
    """
    Update metadata for a specific file ID.
    
    Args:
        file_id (str): The file ID to update metadata for
        updated_metadata (dict): The updated metadata
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # First get the existing metadata to determine the storage path
        existing_metadata = get_file_metadata(file_id)
        
        if not existing_metadata or '_storage_path' not in existing_metadata:
            current_app.logger.error(f"Cannot update metadata: no existing metadata found for {file_id}")
            return False
            
        # Get the storage path from the metadata
        storage_path = existing_metadata['_storage_path']
        
        # Remove the internal storage path before saving back
        if '_storage_path' in updated_metadata:
            del updated_metadata['_storage_path']
            
        # Save updated metadata back to the same location
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(storage_path)
        
        with io.BytesIO() as file_buffer:
            pickle.dump(updated_metadata, file_buffer)
            file_buffer.seek(0)
            blob.upload_from_file(file_buffer)
            
        current_app.logger.info(f"Successfully updated metadata for {file_id} at {storage_path}")
        return True
        
    except Exception as e:
        current_app.logger.error(f"Error updating file metadata: {str(e)}")
        return False