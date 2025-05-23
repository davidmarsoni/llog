"""
Caching operations for Notion content to Google Cloud Storage
"""
import os
import pickle
import time
import io
from flask import current_app
from llama_index.readers.notion import NotionPageReader
from llama_index.core import VectorStoreIndex
from llama_index.core.node_parser.text.token import TokenTextSplitter
from services.storage_service import generate_uuid, get_storage_client
from services.utils.metadata import extract_auto_metadata
from services.notion.utils import get_notion_client, extract_notion_page_title, extract_notion_content_as_text, download_blob_to_memory

def cache_notion_page(page_id, custom_name=None, item_uuid=generate_uuid()):
    """Cache a single Notion page in Google Cloud Storage bucket."""
    start_time = time.time()
    try:
        current_app.logger.info(f"Starting to cache Notion page {page_id}")
        integration_token = os.getenv("NOTION_INTEGRATION_TOKEN")
        if not integration_token:
            raise ValueError("No Notion integration token found. Please set NOTION_INTEGRATION_TOKEN in .env")
        
        # Use NotionPageReader to load the page content
        current_app.logger.info(f"Loading Notion page with ID: {page_id}")
        reader = NotionPageReader(integration_token=integration_token)
        
        try:
            documents = reader.load_data(page_ids=[page_id])
            current_app.logger.info(f"Successfully loaded page content from Notion API")
        except Exception as e:
            error_msg = str(e)
            if "validation_error" in error_msg:
                current_app.logger.error(f"Validation error loading page {page_id}: {error_msg}")
                if "ai_block" in error_msg:
                    raise ValueError(f"The provided page ID ({page_id}) cannot be accessed because it contains AI blocks that are not supported via the API. Please use a page without AI blocks.")
                else:
                    raise ValueError(f"The provided page ID ({page_id}) appears to be invalid: {error_msg}")
            else:
                current_app.logger.error(f"Error loading Notion page: {error_msg}")
                raise ValueError(f"Failed to fetch content from Notion: {error_msg}")
        
        if not documents:
            raise ValueError("No content found in the specified Notion page")
        
        # Extract page title or use custom name if provided
        if custom_name and custom_name.strip():
            page_title = custom_name.strip()
            current_app.logger.info(f"Using custom page title: {page_title}")
        else:
            page_title = extract_notion_page_title(page_id, documents)
            current_app.logger.info(f"Extracted page title: {page_title}")
        
        # Extract automatic metadata
        combined_text = extract_notion_content_as_text(documents)
        auto_metadata = extract_auto_metadata(combined_text)
        current_app.logger.info(f"Extracted auto-metadata with {len(auto_metadata.get('topics', []))} topics")
        
        # Get GCS client and bucket
        current_app.logger.info(f"Getting storage client")
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Store metadata with page title
        metadata = {
            'id': item_uuid,
            'notion_id': page_id,
            'title': page_title,
            'type': 'page',
            'created_at': time.time(),
            'auto_metadata': auto_metadata
        }
        
        item_id = metadata['id']

        # Save metadata to GCS
        current_app.logger.info(f"Saving metadata to GCS")
        metadata_blob = bucket.blob(f"cache/metadata_{item_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(metadata, file_buffer)
            file_buffer.seek(0)
            metadata_blob.upload_from_file(file_buffer)
        
        # Save raw notion data to GCS
        current_app.logger.info(f"Saving raw Notion data to GCS")
        notion_data_blob = bucket.blob(f"cache/data_{item_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(documents, file_buffer)
            file_buffer.seek(0)
            notion_data_blob.upload_from_file(file_buffer)
        
        # Create vector index from the documents
        current_app.logger.info(f"Creating text chunks for vector index")
        text_splitter = TokenTextSplitter(chunk_size=512)
        nodes = text_splitter.get_nodes_from_documents(documents)
        current_app.logger.info(f"Created {len(nodes)} text chunks from Notion page")
        
        # Create and save the vector index to GCS
        current_app.logger.info(f"Creating vector index")
        try:
            index = VectorStoreIndex.from_documents(documents)
            current_app.logger.info(f"Vector index created successfully")
        except Exception as e:
            current_app.logger.error(f"Error creating vector index: {str(e)}")
            # Return partial success - we've at least saved the raw data
            return {
                "success": True,
                "partial": True,
                "notion_id": page_id,
                "title": page_title,
                "chunks": len(nodes),
                "notion_data_blob": notion_data_blob.name,
                "error": f"Vector index creation failed: {str(e)}",
                "metadata": metadata
            }
            
        current_app.logger.info(f"Saving vector index to GCS")
        vector_index_blob = bucket.blob(f"cache/vector_index_{item_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(index, file_buffer)
            file_buffer.seek(0)
            vector_index_blob.upload_from_file(file_buffer)
        
        elapsed_time = time.time() - start_time
        current_app.logger.info(f"Successfully cached Notion page '{page_title}' to GCS bucket {bucket_name} in {elapsed_time:.2f} seconds")
        return {
            "success": True,
            "notion_id": page_id,
            "title": page_title,
            "chunks": len(nodes),
            "notion_data_blob": notion_data_blob.name,
            "vector_index_blob": vector_index_blob.name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error caching Notion page after {elapsed_time:.2f} seconds: {str(e)}")
        raise

def cache_notion_database(database_id, custom_name=None):
    """Cache all pages in a Notion database to Google Cloud Storage bucket as a single unified index."""
    start_time = time.time()
    try:
        current_app.logger.info(f"Starting to cache Notion database {database_id}")
        notion = get_notion_client()
        
        # Try to get database title or use custom name if provided
        try:
            database = notion.databases.retrieve(database_id)
            
            if custom_name and custom_name.strip():
                database_title = custom_name.strip()
                current_app.logger.info(f"Using custom database title: {database_title}")
            else:
                database_title = "Unknown Database"
                if 'title' in database:
                    title_parts = [rich_text.get('plain_text', '') for rich_text in database['title']]
                    database_title = ''.join(title_parts) or f"Notion DB {database_id[:8]}..."
                current_app.logger.info(f"Using database title from Notion: {database_title}")
        except Exception as e:
            error_msg = str(e)
            if "validation_error" in error_msg:
                current_app.logger.error(f"Validation error with database ID {database_id}: {error_msg}")
                if "ai_block" in error_msg:
                    raise ValueError(f"The provided database ID ({database_id}) cannot be accessed because it contains AI blocks that are not supported via the API. Please use a database without AI blocks.")
                else:
                    raise ValueError(f"The provided database ID ({database_id}) appears to be invalid: {error_msg}")
            else:
                raise
        
        # Query the database for all pages
        try:
            results = notion.databases.query(database_id=database_id).get("results", [])
        except Exception as e:
            error_msg = str(e)
            if "validation_error" in error_msg:
                current_app.logger.error(f"Validation error querying database {database_id}: {error_msg}")
                if "ai_block" in error_msg:
                    raise ValueError(f"The provided database ID ({database_id}) cannot be accessed because it contains AI blocks that are not supported via the API. Please use a database without AI blocks.")
                else:
                    raise ValueError(f"The provided database ID ({database_id}) appears to be invalid: {error_msg}")
            else:
                raise
                
        if not results:
            raise ValueError("No pages found in the specified Notion database")
        
        page_ids = [page["id"] for page in results]
        current_app.logger.info(f"Found {len(page_ids)} pages in Notion database {database_id}")
        
        # Create and save a consolidated index for all pages at once
        integration_token = os.getenv("NOTION_INTEGRATION_TOKEN")
        reader = NotionPageReader(integration_token=integration_token)
        
        # Load all documents from the database with a single call
        current_app.logger.info(f"Loading content from all {len(page_ids)} pages in database")
        try:
            all_documents = reader.load_data(page_ids=page_ids)
        except Exception as e:
            error_msg = str(e)
            if "validation_error" in error_msg and "ai_block" in error_msg:
                current_app.logger.error(f"AI block error loading database pages: {error_msg}")
                raise ValueError(f"One or more pages in the database contains AI blocks that are not supported via the API. Please use a database without AI blocks.")
            else:
                current_app.logger.error(f"Error loading Notion database pages: {error_msg}")
                raise ValueError(f"Failed to fetch content from Notion database: {error_msg}")
        
        if not all_documents:
            raise ValueError("No content found in the specified Notion database pages")
            
        # Extract automatic metadata
        combined_text = extract_notion_content_as_text(all_documents)
        auto_metadata = extract_auto_metadata(combined_text)
        current_app.logger.info(f"Extracted auto-metadata with {len(auto_metadata.get('topics', []))} topics")
            
        # Create text chunks for the vector index
        current_app.logger.info(f"Creating text chunks for vector index")
        text_splitter = TokenTextSplitter(chunk_size=512)
        nodes = text_splitter.get_nodes_from_documents(all_documents)
        current_app.logger.info(f"Created {len(nodes)} text chunks from {len(page_ids)} database pages")
        
        # Get GCS client and bucket
        current_app.logger.info(f"Getting storage client")
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Generate a single UUID for this database
        item_id = generate_uuid()
        
        # Store metadata with database title
        metadata = {
            'id': item_id,
            'notion_id': database_id,
            'title': database_title,
            'type': 'database',
            'page_count': len(page_ids),
            'page_ids': page_ids,
            'created_at': time.time(),
            'auto_metadata': auto_metadata
        }
        
        # Save metadata to GCS
        current_app.logger.info(f"Saving database metadata to GCS")
        metadata_blob = bucket.blob(f"cache/metadata_{item_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(metadata, file_buffer)
            file_buffer.seek(0)
            metadata_blob.upload_from_file(file_buffer)
        
        # Save all documents from the database to GCS
        current_app.logger.info(f"Saving raw database content to GCS")
        all_data_blob = bucket.blob(f"cache/data_{item_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(all_documents, file_buffer)
            file_buffer.seek(0)
            all_data_blob.upload_from_file(file_buffer)
        
        # Create a consolidated vector index
        current_app.logger.info(f"Creating unified vector index for database")
        try:
            index = VectorStoreIndex.from_documents(all_documents)
        except Exception as e:
            current_app.logger.error(f"Error creating vector index: {str(e)}")
            # Return partial success - we've at least saved the raw data
            return {
                "success": True,
                "partial": True,
                "notion_id": database_id,
                "title": database_title,
                "pages_found": len(page_ids),
                "chunks": len(nodes),
                "all_data_blob": all_data_blob.name,
                "error": f"Vector index creation failed: {str(e)}",
                "metadata": metadata
            }
            
        current_app.logger.info(f"Saving vector index to GCS")
        all_index_blob = bucket.blob(f"cache/vector_index_{item_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(index, file_buffer)
            file_buffer.seek(0)
            all_index_blob.upload_from_file(file_buffer)
        
        elapsed_time = time.time() - start_time
        current_app.logger.info(f"Successfully cached Notion database '{database_title}' with {len(page_ids)} pages to GCS bucket {bucket_name} in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "id": item_id,
            "notion_id": database_id,
            "title": database_title,
            "pages_found": len(page_ids),
            "chunks": len(nodes),
            "all_data_blob": all_data_blob.name,
            "all_index_blob": all_index_blob.name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error caching Notion database after {elapsed_time:.2f} seconds: {str(e)}")
        raise

def query_cached_notion(page_id, query_text):
    """Query a cached Notion page from GCS bucket."""
    try:
        vector_index_blob_name = f"cache/vector_index_{page_id}.pkl"
        
        # Download and deserialize the vector index
        try:
            index = download_blob_to_memory(vector_index_blob_name)
        except Exception as e:
            raise ValueError(f"No cached vector index found for page {page_id}: {str(e)}")
        
        # Create query engine and execute query
        query_engine = index.as_query_engine()
        response = query_engine.query(query_text)
        
        return {
            "success": True,
            "query": query_text,
            "response": str(response),
            "page_id": page_id
        }
        
    except Exception as e:
        current_app.logger.error(f"Error querying cached Notion content: {str(e)}")
        raise