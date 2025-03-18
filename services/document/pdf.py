"""
Service for processing PDF documents
"""
import os
import io
import pickle
import time
import tempfile
from flask import current_app
from llama_index.core import Document, VectorStoreIndex
from llama_index.core.node_parser.text.token import TokenTextSplitter
from llama_index.readers.file import PDFReader
from services.storage_service import get_storage_client
from services.document.metadata import extract_auto_metadata

def process_pdf_file(file_stream, filename, custom_name=None):
    """Process a PDF file and cache it for LLM processing"""
    start_time = time.time()
    try:
        current_app.logger.info(f"Processing PDF file: {filename}")
        
        # Extract document ID from filename
        doc_id = f"doc_{int(time.time())}"
        
        # Use custom name or filename
        doc_title = custom_name.strip() if custom_name and custom_name.strip() else os.path.basename(filename)
        current_app.logger.info(f"Using document title: {doc_title}")
        
        # Create a temporary file using tempfile module for cross-platform compatibility
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
        current_app.logger.info(f"PDF file size: {file_size/1024/1024:.2f} MB")
        
        # Use PDFReader to extract text - with a timeout for large files
        reader = PDFReader()
        current_app.logger.info(f"Starting PDF text extraction")
        extraction_start = time.time()
        
        try:
            documents = reader.load_data(file=temp_file_path)
            extraction_time = time.time() - extraction_start
            current_app.logger.info(f"PDF text extraction completed in {extraction_time:.2f} seconds")
        except Exception as pdf_error:
            current_app.logger.error(f"Error extracting text from PDF: {str(pdf_error)}")
            
            # For very large PDFs, try an alternative approach with reduced features
            current_app.logger.info("Trying alternative PDF processing for large file")
            from pypdf import PdfReader
            
            with open(temp_file_path, 'rb') as f:
                pdf_reader = PdfReader(f)
                documents = []
                # Process pages in batches to avoid memory issues
                batch_size = 10
                total_pages = len(pdf_reader.pages)
                
                for i in range(0, total_pages, batch_size):
                    batch_text = ""
                    end_page = min(i + batch_size, total_pages)
                    current_app.logger.info(f"Processing PDF pages {i+1} to {end_page} of {total_pages}")
                    
                    for page_num in range(i, end_page):
                        try:
                            page = pdf_reader.pages[page_num]
                            page_text = page.extract_text() or ""
                            batch_text += f"Page {page_num+1}:\n{page_text}\n\n"
                        except Exception as e:
                            current_app.logger.warning(f"Error extracting text from page {page_num+1}: {str(e)}")
                    
                    if batch_text.strip():
                        documents.append(Document(
                            text=batch_text,
                            metadata={
                                "filename": filename,
                                "title": doc_title,
                                "page_range": f"{i+1}-{end_page}"
                            }
                        ))
                        
                current_app.logger.info(f"Extracted text from {len(documents)} batches of PDF pages")
        
        # Clean up temporary file
        try:
            os.remove(temp_file_path)
            current_app.logger.info(f"Removed temporary file: {temp_file_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove temporary file: {str(e)}")
        
        if not documents:
            raise ValueError("No content could be extracted from the PDF file")
        
        # Extract automatic metadata from a sample of the content to avoid memory issues
        combined_text = ""
        text_limit = 10000  # Limit the amount of text for metadata extraction
        
        for doc in documents[:5]:  # Only use first 5 documents/chunks for metadata
            if hasattr(doc, 'text'):
                combined_text += doc.text[:2000] + "\n\n"  # Take first 2000 chars from each
                if len(combined_text) >= text_limit:
                    break
                    
        auto_metadata = extract_auto_metadata(combined_text[:text_limit])
        
        # Get GCS client and bucket
        current_app.logger.info("Getting storage client")
        client = get_storage_client()
        bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
        bucket = client.bucket(bucket_name)
        
        # Store metadata with document title and auto-extracted metadata
        metadata = {
            'doc_id': doc_id,
            'title': doc_title,
            'type': 'document',
            'format': 'pdf',
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
        
        # Save raw document data to GCS in batches if needed
        current_app.logger.info(f"Saving raw document data to GCS")
        
        # For very large document sets, split into multiple pickle files
        if len(documents) > 100:
            # Split into batches of 100 documents
            batch_size = 100
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
        batch_size = min(50, len(documents))  # Process up to 50 documents at a time
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i+batch_size]
            nodes = text_splitter.get_nodes_from_documents(batch)
            all_nodes.extend(nodes)
            current_app.logger.info(f"Processed batch {i//batch_size + 1} with {len(nodes)} chunks")
        
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
                "format": "pdf",
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
            "format": "pdf",
            "chunks": len(all_nodes),
            "document_data_blob": doc_data_blob_name,
            "vector_index_blob": vector_index_blob.name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error processing PDF file after {elapsed_time:.2f} seconds: {str(e)}")
        raise