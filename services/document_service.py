"""
Document processing service for handling various document formats
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
# Remove SimpleDirectoryReader import as it's not needed and causing an import error
from services.storage_service import get_storage_client
import json

def extract_auto_metadata(text_content):
    """
    Extract metadata automatically from document content using AI.
    Returns a dictionary with theme, topics, and other important information.
    """
    try:
        # Check if OpenAI API key is available
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            current_app.logger.warning("OpenAI API key not available. Skipping automatic metadata extraction.")
            return {
                "auto_generated": False,
                "themes": [],
                "topics": [],
                "entities": [],
                "keywords": []
            }
            
        # Import here to avoid dependency issues if OpenAI is not available
        from openai import OpenAI
        import httpx
        
        # Create OpenAI client
        client = OpenAI(
            api_key=openai_api_key,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
        )
        
        # Prepare a sample of the text (first 4000 chars is usually enough for metadata)
        text_sample = text_content[:4000] if len(text_content) > 4000 else text_content
        
        # Create the prompt for metadata extraction
        prompt = f"""
        Analyze the following document content and extract key metadata.
        Return ONLY a JSON object with these fields:
        - themes: List of 3-5 main themes
        - topics: List of 5-10 specific topics covered
        - entities: List of important entities mentioned (people, organizations, products)
        - keywords: List of 10-15 relevant keywords for search
        - summary: A 2-3 sentence summary of the content
        - language: The detected language of the content
        - contentType: The likely type of the content (article, report, tutorial, etc.)
        
        Document content:
        {text_sample}
        
        Return ONLY the JSON object with the extracted metadata.
        """
        
        # Call OpenAI API
        current_app.logger.info("Extracting automatic metadata using OpenAI")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            timeout=25,
        )
        
        result_text = response.choices[0].message.content
        
        # Extract the JSON content from the response
        try:
            # Try to parse the entire response as JSON directly
            metadata = json.loads(result_text)
        except json.JSONDecodeError:
            # If that fails, try to find JSON within the text
            try:
                import re
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    metadata = json.loads(json_match.group(0))
                else:
                    raise ValueError("No valid JSON found in the response")
            except Exception as e:
                current_app.logger.error(f"Error extracting JSON from OpenAI response: {str(e)}")
                return {
                    "auto_generated": True,
                    "error": "Failed to parse metadata",
                    "themes": [],
                    "topics": [],
                    "entities": [],
                    "keywords": []
                }
        
        # Add auto_generated flag
        metadata["auto_generated"] = True
        
        current_app.logger.info(f"Successfully extracted automatic metadata: {len(metadata['topics'])} topics, {len(metadata['keywords'])} keywords")
        return metadata
        
    except Exception as e:
        current_app.logger.error(f"Error in automatic metadata extraction: {str(e)}")
        return {
            "auto_generated": False,
            "error": str(e),
            "themes": [],
            "topics": [],
            "entities": [],
            "keywords": []
        }

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
        with open(temp_file_path, "wb") as temp_file:
            file_stream.seek(0)
            temp_file.write(file_stream.read())
        
        # Use PDFReader to extract text
        reader = PDFReader()
        documents = reader.load_data(file=temp_file_path)
        
        # Clean up temporary file
        try:
            os.remove(temp_file_path)
            current_app.logger.info(f"Removed temporary file: {temp_file_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove temporary file: {str(e)}")
        
        if not documents:
            raise ValueError("No content could be extracted from the PDF file")
        
        # Extract automatic metadata if possible
        combined_text = ""
        for doc in documents:
            if hasattr(doc, 'text'):
                combined_text += doc.text + "\n\n"
        
        auto_metadata = extract_auto_metadata(combined_text)
        
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
        
        # Save raw document data to GCS
        current_app.logger.info(f"Saving raw document data to GCS")
        doc_data_blob = bucket.blob(f"cache/document_data_{doc_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(documents, file_buffer)
            file_buffer.seek(0)
            doc_data_blob.upload_from_file(file_buffer)
        
        # Create vector index from the documents
        current_app.logger.info(f"Creating text chunks for vector index")
        text_splitter = TokenTextSplitter(chunk_size=512)
        nodes = text_splitter.get_nodes_from_documents(documents)
        current_app.logger.info(f"Created {len(nodes)} text chunks from document")
        
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
                "doc_id": doc_id,
                "title": doc_title,
                "format": "pdf",
                "chunks": len(nodes),
                "document_data_blob": doc_data_blob.name,
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
            "chunks": len(nodes),
            "document_data_blob": doc_data_blob.name,
            "vector_index_blob": vector_index_blob.name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error processing PDF file after {elapsed_time:.2f} seconds: {str(e)}")
        raise

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
        
        # Read the text content
        file_stream.seek(0)
        text_content = file_stream.read().decode('utf-8')
        
        # Extract automatic metadata
        auto_metadata = extract_auto_metadata(text_content)
        
        # Create Document object
        documents = [Document(text=text_content, metadata={"filename": filename, "title": doc_title})]
        
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
        
        # Save raw document data to GCS
        current_app.logger.info(f"Saving raw document data to GCS")
        doc_data_blob = bucket.blob(f"cache/document_data_{doc_id}.pkl")
        with io.BytesIO() as file_buffer:
            pickle.dump(documents, file_buffer)
            file_buffer.seek(0)
            doc_data_blob.upload_from_file(file_buffer)
        
        # Create vector index from the documents
        current_app.logger.info(f"Creating text chunks for vector index")
        text_splitter = TokenTextSplitter(chunk_size=512)
        nodes = text_splitter.get_nodes_from_documents(documents)
        current_app.logger.info(f"Created {len(nodes)} text chunks from document")
        
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
                "doc_id": doc_id,
                "title": doc_title,
                "format": format_type,
                "chunks": len(nodes),
                "document_data_blob": doc_data_blob.name,
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
            "chunks": len(nodes),
            "document_data_blob": doc_data_blob.name,
            "vector_index_blob": vector_index_blob.name,
            "time_taken_seconds": elapsed_time,
            "metadata": metadata
        }
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        current_app.logger.error(f"Error processing text file after {elapsed_time:.2f} seconds: {str(e)}")
        raise