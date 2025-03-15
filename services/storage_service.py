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

def delete_file_from_storage(filename):
    """Delete a file from the storage bucket."""
    client = get_storage_client()
    bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
    bucket = client.bucket(bucket_name)
    
    # Get the blob and delete it
    blob = bucket.blob(filename)
    blob.delete()
    
    return True