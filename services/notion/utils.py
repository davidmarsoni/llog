"""
Utility functions for Notion API operations
"""
import os
import pickle
import time
import io
import requests
from flask import current_app
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

def get_notion_client():
    """Get a Notion client."""
    integration_token = os.getenv("NOTION_INTEGRATION_TOKEN")
    if not integration_token:
        raise ValueError("No Notion integration token found. Please set NOTION_INTEGRATION_TOKEN in .env")
    
    # Create client without invalid client_options argument
    return Client(auth=integration_token)

def extract_notion_page_title(page_id, documents=None):
    """Extract the title of a Notion page."""
    try:
        # If documents are provided, try to extract title from them
        if documents and len(documents) > 0:
            # Try to get title from document metadata
            for doc in documents:
                if hasattr(doc, 'metadata') and doc.metadata:
                    if 'title' in doc.metadata and doc.metadata['title']:
                        return doc.metadata['title']
            
            # Try to extract title from content (first line might be title)
            for doc in documents:
                content = doc.text if hasattr(doc, 'text') else (doc.get_content() if hasattr(doc, 'get_content') else "")
                if content:
                    # Simple heuristic: first line might be the title
                    first_line = content.strip().split('\n')[0].strip()
                    if len(first_line) > 0 and len(first_line) < 100:  # Reasonable title length
                        return first_line
        
        # If no title found in documents, fetch from API
        notion = get_notion_client()
        try:
            # Add timeout to this specific API call
            page = notion.pages.retrieve(page_id)
            
            # Try to extract title from various potential Notion page structures
            if 'properties' in page:
                properties = page['properties']
                # Check common title property names
                for title_prop in ['title', 'Title', 'Name', 'name']:
                    if title_prop in properties:
                        title_property = properties[title_prop]
                        if 'title' in title_property and title_property['title']:
                            title_parts = [rich_text.get('plain_text', '') for rich_text in title_property['title']]
                            return ''.join(title_parts) or f"Notion Page {page_id[:8]}..."
        except requests.exceptions.Timeout:
            current_app.logger.warning(f"Timeout while retrieving Notion page title for {page_id}")
            return f"Notion Page {page_id[:8]}..."
        except Exception as e:
            current_app.logger.error(f"Error retrieving page title from Notion API: {str(e)}")
        
        return f"Notion Page {page_id[:8]}..."
    except Exception as e:
        current_app.logger.error(f"Error extracting Notion page title: {str(e)}")
        return f"Notion Page {page_id[:8]}..."

def extract_notion_content_as_text(documents):
    """Extract text content from Notion documents for metadata analysis."""
    combined_text = ""
    try:
        for doc in documents:
            if hasattr(doc, 'text'):
                combined_text += doc.text + "\n\n"
            elif hasattr(doc, 'get_content'):
                combined_text += doc.get_content() + "\n\n"
        
        # Limit the text to a reasonable size for processing
        if len(combined_text) > 10000:
            combined_text = combined_text[:10000] + "..."
            
        return combined_text
    except Exception as e:
        current_app.logger.error(f"Error extracting text from Notion documents: {str(e)}")
        return combined_text

def download_blob_to_memory(blob_name):
    """Download a blob from GCS to memory."""
    from services.storage_service import get_storage_client
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            client = get_storage_client()
            bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
            if not bucket_name:
                raise ValueError("GCS_BUCKET_NAME environment variable or config not set")
                
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)

            if not blob.exists():
                raise FileNotFoundError(f"Blob {blob_name} does not exist in bucket {bucket_name}")
            
            with io.BytesIO() as file_buffer:
                blob.download_to_file(file_buffer)
                file_buffer.seek(0)
                return pickle.load(file_buffer)
                
        except FileNotFoundError:
            current_app.logger.error(f"Blob {blob_name} not found in bucket {bucket_name}")
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                current_app.logger.warning(f"Error downloading blob {blob_name} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                time.sleep(retry_delay)
            else:
                current_app.logger.error(f"Failed to download blob {blob_name} after {max_retries} attempts: {str(e)}")
                raise