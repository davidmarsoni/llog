"""
Service for processing PDF documents
"""
import os
import io
import pickle
import time
import tempfile
import uuid
from flask import current_app
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser.text.token import TokenTextSplitter
from llama_index.readers.file import PDFReader
from services.storage_service import generate_uuid, get_storage_client
from services.utils.metadata import extract_auto_metadata

def process_pdf_file(file_stream, filename, custom_name=None):
    """Process a PDF file and cache it for LLM processing"""
    try:
        current_app.logger.info(f"Starting to process PDF file: {filename}")
        # Generate a numeric ID for this document
        doc_id = generate_uuid()
        
        # Save PDF to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            file_stream.save(temp_file)
            temp_file_path = temp_file.name
            
        try:
            # Extract text from PDF
            reader = PDFReader()
            documents = reader.load_data(temp_file_path)
            current_app.logger.info(f"Loaded {len(documents)} pages from PDF")
            
            # Combine text for metadata extraction
            combined_text = ""
            text_limit = 5000  # Limit text for metadata extraction to first 5000 characters
            
            if len(documents) > 0:
                for doc in documents:
                    if hasattr(doc, 'text'):
                        combined_text += doc.text + "\n\n"
                        if len(combined_text) >= text_limit:
                            break
            
            # Get file title
            if custom_name and custom_name.strip():
                doc_title = custom_name.strip()
                current_app.logger.info(f"Using custom document title: {doc_title}")
            else:
                # Use filename without extension as title
                doc_title = os.path.splitext(filename)[0]
                current_app.logger.info(f"Using filename as document title: {doc_title}")
            
            # Extract metadata
            auto_metadata = extract_auto_metadata(combined_text[:text_limit])
            current_app.logger.info(f"Extracted auto-metadata with {len(auto_metadata.get('topics', []))} topics")
            
            # Get GCS client and bucket
            current_app.logger.info("Getting storage client")
            client = get_storage_client()
            bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
            bucket = client.bucket(bucket_name)
            
            # Store metadata
            metadata = {
                'id': doc_id,
                'title': doc_title,
                'type': 'document',
                'format': 'pdf',
                'filename': filename,
                'pages': len(documents),
                'created_at': time.time(),
                'auto_metadata': auto_metadata,
                '_storage_path': f"cache/metadata_{doc_id}.pkl"  
            }
            
            # Save metadata to GCS
            current_app.logger.info("Saving metadata to GCS")
            metadata_blob = bucket.blob(f"cache/metadata_{doc_id}.pkl")
            with io.BytesIO() as file_buffer:
                pickle.dump(metadata, file_buffer)
                file_buffer.seek(0)
                metadata_blob.upload_from_file(file_buffer)
            
            # Save document
            batch_size = 100  # Number of chunks per batch
            batch_count = (len(documents) + batch_size - 1) // batch_size
            
            for batch_idx in range(batch_count):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, len(documents))
                batch = documents[start_idx:end_idx]
                
                doc_data_blob = bucket.blob(f"cache/data_{doc_id}_batch_{batch_idx}.pkl")
                with io.BytesIO() as file_buffer:
                    pickle.dump(batch, file_buffer)
                    file_buffer.seek(0)
                    doc_data_blob.upload_from_file(file_buffer)
                
                current_app.logger.info(f"Saved document batch {batch_idx+1}/{batch_count} to GCS")
            
            # Save batch info in metadata
            metadata['batched'] = True
            metadata['batch_count'] = batch_count
            
            # Update metadata with batch info
            with io.BytesIO() as file_buffer:
                pickle.dump(metadata, file_buffer)
                file_buffer.seek(0)
                metadata_blob.upload_from_file(file_buffer)
            
            # Create vector index from the documents
            current_app.logger.info("Creating text chunks for vector index")
            text_splitter = TokenTextSplitter(chunk_size=512)
            nodes = text_splitter.get_nodes_from_documents(documents)
            current_app.logger.info(f"Created {len(nodes)} text chunks for vector index")
            
            # Create and save the vector index
            current_app.logger.info("Creating vector index")
            try:
                index = VectorStoreIndex.from_documents(documents)
                current_app.logger.info("Vector index created successfully")
            except Exception as e:
                current_app.logger.error(f"Error creating vector index: {str(e)}")
                # Return partial success - we've at least saved the raw data
                return {
                    "success": True,
                    "partial": True,
                    "id": doc_id,
                    "title": doc_title,
                    "chunks": len(nodes),
                    "error": f"Vector index creation failed: {str(e)}",
                    "metadata": metadata
                }
                
            current_app.logger.info("Saving vector index to GCS")
            vector_index_blob = bucket.blob(f"cache/vector_index_{doc_id}.pkl")
            with io.BytesIO() as file_buffer:
                pickle.dump(index, file_buffer)
                file_buffer.seek(0)
                vector_index_blob.upload_from_file(file_buffer)
            
            return {
                "success": True,
                "id": doc_id,
                "title": doc_title,
                "chunks": len(nodes),
                "metadata": metadata
            }
            
        finally:
            # Clean up temp file
            try:
                os.remove(temp_file_path)
            except:
                pass
                
    except Exception as e:
        current_app.logger.error(f"Error processing PDF file: {str(e)}")
        raise