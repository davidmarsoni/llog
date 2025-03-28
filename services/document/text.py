"""
Service for processing text documents (txt, md, etc.)
"""
import os
import io
import pickle
import time
from flask import current_app
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser.text.token import TokenTextSplitter
from services.storage_service import generate_uuid, get_storage_client
from services.document.metadata import extract_auto_metadata

def process_text_file(file_stream, filename, custom_name=None):
    """Process a text file (txt, md) and cache it for LLM processing"""
    start_time = time.time()
    try:
        current_app.logger.info(f"Processing text file: {filename}")
        
        # Extract document ID and format
        doc_id = f"doc_{int(time.time())}"
        uuid = generate_uuid()
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext == '.md':
            format_type = 'markdown'
        else:
            format_type = 'text'
        
        # Use custom name or filename
        doc_title = custom_name.strip() if custom_name and custom_name.strip() else os.path.basename(filename)
        current_app.logger.info(f"Using document title: {doc_title}")
        
        # Read file content
        file_stream.seek(0)
        text_content = file_stream.read().decode('utf-8', errors='replace')
        
        # Create Document object
        document = Document(text=text_content, metadata={"filename": filename, "title": doc_title})
        
        # Extract automatic metadata
        text_sample = text_content[:10000] if len(text_content) > 10000 else text_content
        auto_metadata = extract_auto_metadata(text_sample)
        
        # Get GCS client and bucket
        current_app.logger.info("Getting storage client")
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Store metadata with document title
        metadata = {
            'id': uuid,
            'doc_id': doc_id,
            'title': doc_title,
            'type': 'document',
            'format': format_type,
            'filename': filename,
            'file_size_bytes': len(text_content),
            'created_at': time.time(),
            'auto_metadata': auto_metadata
        }
        
        # Save metadata to GCS
        current_app.logger.info(f"Saving metadata to GCS")
        metadata_blob = bucket.blob(f"cache/metadata_{uuid}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(metadata, file_buffer)
            file_buffer.seek(0)
            metadata_blob.upload_from_file(file_buffer)
        
        # Save document data to GCS
        doc_data_blob = bucket.blob(f"cache/data_{uuid}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump([document], file_buffer)
            file_buffer.seek(0)
            doc_data_blob.upload_from_file(file_buffer)
        
        # Create vector index from the document
        current_app.logger.info(f"Creating text chunks for vector index")
        text_splitter = TokenTextSplitter(chunk_size=512)
        nodes = text_splitter.get_nodes_from_documents([document])
        current_app.logger.info(f"Created {len(nodes)} text chunks from document")
        
        # Create and save the vector index to GCS
        current_app.logger.info(f"Creating vector index")
        try:
            index = VectorStoreIndex.from_documents([document])
            current_app.logger.info(f"Vector index created successfully")
            
            current_app.logger.info(f"Saving vector index to GCS")
            vector_index_blob = bucket.blob(f"cache/vector_index_{uuid}.pkl")
            with io.BytesIO() as file_buffer:
                pickle.dump(index, file_buffer)
                file_buffer.seek(0)
                vector_index_blob.upload_from_file(file_buffer)
                
            vector_index_blob_name = vector_index_blob.name
            
        except Exception as e:
            current_app.logger.error(f"Error creating vector index: {str(e)}")
            # Return partial success - we've at least saved the raw data
            return {
                "success": True,
                "partial": True,
                "doc_id": doc_id,
                "title": doc_title,
                "format": format_type,
                "chunks": len(nodes),
                "document_data_blob": doc_data_blob.name,
                "error": f"Vector index creation failed: {str(e)}",
                "metadata": metadata
            }
        
        elapsed_time = time.time() - start_time
        current_app.logger.info(f"Successfully cached document '{doc_title}' to GCS bucket {bucket_name} in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "doc_id": doc_id,
            "title": doc_title,
            "format": format_type,
            "chunks": len(nodes),
            "document_data_blob": doc_data_blob.name,
            "vector_index_blob": vector_index_blob_name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error processing text file after {elapsed_time:.2f} seconds: {str(e)}")
        raise