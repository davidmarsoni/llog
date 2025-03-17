"""
Storage service for handling Google Cloud Storage operations
"""
from flask import current_app
from google.cloud import storage
import os

def get_storage_client():
    """Get a Google Cloud Storage client."""
    try:
        # First try using Application Default Credentials
        return storage.Client()
    except Exception as e:
        current_app.logger.error(f"Error initializing storage client: {str(e)}")
        raise

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