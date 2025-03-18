"""
Service for processing text documents (txt, md, etc.)
"""
import os
import io
import pickle
import time
import tempfile
from flask import current_app
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser.text.token import TokenTextSplitter
from services.storage_service import get_storage_client
from services.document.metadata import extract_auto_metadata

def process_text_file(file_stream, filename, custom_name=None):
    """Process a text file (txt, md) and cache it for LLM processing"""
    start_time = time.time()
    try:
        current_app.logger.info(f"Processing text file: {filename}")
        
        # Extract document ID and format
        doc_id = f"doc_{int(time.time())}"
        file_ext = os.path.splitext(filename)[1].lower()
        
        if file_ext == '.md':
            format_type = 'markdown'
        else:
            format_type = 'text'
        
        # Use custom name or filename
        doc_title = custom_name.strip() if custom_name and custom_name.strip() else os.path.basename(filename)
        current_app.logger.info(f"Using document title: {doc_title}")
        
        # Create a temporary file to avoid memory issues with large text files
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, filename)
        
        current_app.logger.info(f"Creating temporary file at: {temp_file_path}")
        
        # Stream the file to disk instead of loading it all into memory
        with open(temp_file_path, "wb") as temp_file:
            # Process in chunks of 10MB to avoid memory issues
            chunk_size = 10 * 1024 * 1024  # 10MB chunks
            file_stream.seek(0)
            chunk = file_stream.read(chunk_size)
            while chunk:
                temp_file.write(chunk)
                chunk = file_stream.read(chunk_size)
        
        # Get file size for logging
        file_size = os.path.getsize(temp_file_path)
        current_app.logger.info(f"Text file size: {file_size/1024/1024:.2f} MB")
        
        # For large files, process in chunks to avoid memory issues
        documents = []
        
        if file_size > 50 * 1024 * 1024:  # If file is larger than 50MB, process in chunks
            current_app.logger.info("Large text file detected, processing in chunks")
            chunk_size = 1 * 1024 * 1024  # 1MB chunks for text processing
            chunk_num = 0
            
            with open(temp_file_path, 'r', encoding='utf-8', errors='replace') as f:
                while True:
                    chunk_text = f.read(chunk_size)
                    if not chunk_text:
                        break
                    
                    chunk_num += 1
                    documents.append(Document(
                        text=chunk_text,
                        metadata={
                            "filename": filename, 
                            "title": doc_title, 
                            "chunk": chunk_num
                        }
                    ))
                    current_app.logger.info(f"Processed text chunk {chunk_num}")
            
            current_app.logger.info(f"Finished processing text file in {chunk_num} chunks")
        else:
            # For smaller files, read the entire content
            with open(temp_file_path, 'r', encoding='utf-8', errors='replace') as f:
                text_content = f.read()
            
            # Create Document object
            documents = [Document(text=text_content, metadata={"filename": filename, "title": doc_title})]
        
        # Clean up temporary file
        try:
            os.remove(temp_file_path)
            current_app.logger.info(f"Removed temporary file: {temp_file_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove temporary file: {str(e)}")
        
        # Extract automatic metadata from a sample of the content
        combined_text = ""
        text_limit = 10000  # Limit the amount of text for metadata extraction
        
        if len(documents) > 1:  # Only take samples if we have multiple chunks
            for doc in documents[:5]:  # Only use first 5 documents/chunks for metadata
                if hasattr(doc, 'text'):
                    combined_text += doc.text[:2000] + "\n\n"  # Take first 2000 chars from each
                    if len(combined_text) >= text_limit:
                        break
            auto_metadata = extract_auto_metadata(combined_text[:text_limit])
        else:
            # For smaller files, use the first part of the document
            text_sample = documents[0].text[:10000] if len(documents[0].text) > 10000 else documents[0].text
            auto_metadata = extract_auto_metadata(text_sample)
        
        # Get GCS client and bucket
        current_app.logger.info("Getting storage client")
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Store metadata with document title
        metadata = {
            'doc_id': doc_id,
            'title': doc_title,
            'type': 'document',
            'format': format_type,
            'filename': filename,
            'file_size_bytes': file_size,
            'created_at': time.time(),
            'auto_metadata': auto_metadata
        }
        
        # Save metadata to GCS
        current_app.logger.info(f"Saving metadata to GCS")
        metadata_blob = bucket.blob(f"cache/metadata_doc_{doc_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(metadata, file_buffer)
            file_buffer.seek(0)
            metadata_blob.upload_from_file(file_buffer)
        
        # For very large document sets, split into multiple pickle files
        if len(documents) > 50:
            # Split into batches of 50 documents
            batch_size = 50
            batch_count = (len(documents) + batch_size - 1) // batch_size
            
            for batch_idx in range(batch_count):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, len(documents))
                batch = documents[start_idx:end_idx]
                
                doc_data_blob = bucket.blob(f"cache/document_data_{doc_id}_batch_{batch_idx}.pkl")
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
                
            doc_data_blob_name = f"cache/document_data_{doc_id}_batch_0.pkl"
        else:
            # Save in a single file for smaller documents
            doc_data_blob = bucket.blob(f"cache/document_data_{doc_id}.pkl")
            with io.BytesIO() as file_buffer:
                pickle.dump(documents, file_buffer)
                file_buffer.seek(0)
                doc_data_blob.upload_from_file(file_buffer)
            
            doc_data_blob_name = doc_data_blob.name
        
        # Create vector index from the documents
        current_app.logger.info(f"Creating text chunks for vector index")
        text_splitter = TokenTextSplitter(chunk_size=512)
        
        # Process nodes in batches to avoid memory issues with large documents
        all_nodes = []
        batch_size = min(20, len(documents))  # Process up to 20 documents at a time
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            try:
                nodes = text_splitter.get_nodes_from_documents(batch)
                all_nodes.extend(nodes)
                current_app.logger.info(f"Processed batch {i//batch_size + 1} with {len(nodes)} chunks")
            except Exception as chunk_error:
                current_app.logger.error(f"Error processing chunk batch {i//batch_size + 1}: {str(chunk_error)}")
        
        current_app.logger.info(f"Created {len(all_nodes)} text chunks from document")
        
        # Create and save the vector index to GCS
        current_app.logger.info(f"Creating vector index")
        try:
            # For very large documents, we may need to index in batches
            if len(all_nodes) > 1000:
                current_app.logger.info(f"Large document with {len(all_nodes)} nodes - creating simplified index")
                # Only index a subset of the document for very large documents
                sample_size = min(1000, len(documents))
                sample_docs = documents[:sample_size]
                index = VectorStoreIndex.from_documents(sample_docs)
                
                # Note this limitation in metadata
                metadata['partial_index'] = True
                metadata['indexed_pages'] = sample_size
                
                # Update metadata with partial indexing info
                with io.BytesIO() as file_buffer:
                    pickle.dump(metadata, file_buffer)
                    file_buffer.seek(0)
                    metadata_blob.upload_from_file(file_buffer)
            else:
                index = VectorStoreIndex.from_documents(documents)
                
            current_app.logger.info(f"Vector index created successfully")
        except Exception as e:
            current_app.logger.error(f"Error creating vector index: {str(e)}")
            # Return partial success - we've at least saved the raw data
            return {
                "success": True,
                "partial": True,
                "doc_id": doc_id,
                "title": doc_title,
                "format": format_type,
                "chunks": len(all_nodes),
                "document_data_blob": doc_data_blob_name,
                "error": f"Vector index creation failed: {str(e)}",
                "metadata": metadata
            }
            
        current_app.logger.info(f"Saving vector index to GCS")
        vector_index_blob = bucket.blob(f"cache/vector_document_{doc_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(index, file_buffer)
            file_buffer.seek(0)
            vector_index_blob.upload_from_file(file_buffer)
        
        elapsed_time = time.time() - start_time
        current_app.logger.info(f"Successfully cached document '{doc_title}' to GCS bucket {bucket_name} in {elapsed_time:.2f} seconds")
        
        return {
            "success": True,
            "doc_id": doc_id,
            "title": doc_title,
            "format": format_type,
            "chunks": len(all_nodes),
            "document_data_blob": doc_data_blob_name,
            "vector_index_blob": vector_index_blob.name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error processing text file after {elapsed_time:.2f} seconds: {str(e)}")
        raise