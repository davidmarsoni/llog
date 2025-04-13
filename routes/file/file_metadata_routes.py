from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify
import os
import tempfile
import pickle # Added import

from services.storage_service import get_file_metadata, update_file_metadata, get_storage_client
from services.utils.metadata import extract_auto_metadata 
from services.utils.cache import get_folders, move_item_to_folder, refresh_file_index_cache 
from .route_utils import add_cache_headers 

metadata_bp = Blueprint('file_metadata', __name__, url_prefix='/files/metadata')

@metadata_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)

@metadata_bp.route("/<path:file_id>")
def view_metadata(file_id):
    """View metadata for a specific file."""
    try:
        # Clean up file_id by removing any 'cache/' prefix if present
        file_id = file_id.replace('cache/', '')
        
        # Get metadata for the file
        metadata = get_file_metadata(file_id)
        
        if not metadata:
            flash("No metadata found for this file", "error")
            return redirect(url_for('file_storage.view_files'))
        
        # Ensure auto_metadata exists, even if empty
        if 'auto_metadata' not in metadata:
            metadata['auto_metadata'] = {
                'auto_generated': False,
                'themes': [],
                'topics': [],
                'entities': [],
                'keywords': [],
                'summary': '',
                'language': '',
                'contentType': ''
            }
        
        # Get all folders for the folder selection dropdown
        folders = get_folders()
            
        return render_template('metadata_view.html', 
                             metadata=metadata,
                             file_id=file_id,
                             folders=folders)
                              
    except Exception as e:
        current_app.logger.error(f"Error viewing metadata: {str(e)}")
        flash(f"Error viewing metadata: {str(e)}", "error")
        return redirect(url_for('file_storage.view_files'))

@metadata_bp.route("/<path:file_id>/update", methods=["POST"])
def update_metadata(file_id):
    """Update metadata for a specific file."""
    try:
        # Get the current metadata first
        current_metadata = get_file_metadata(file_id)
        
        if not current_metadata:
            return jsonify({"success": False, "error": "No metadata found for this file"})
        
        # Get the updated metadata from the request
        request_data = request.json
        
        # Update only specific fields to avoid losing other metadata
        if 'title' in request_data and request_data['title']:
            current_metadata['title'] = request_data['title']
        
        # Update folder if provided
        if 'folder' in request_data:
            # Update folder in metadata
            current_metadata['folder'] = request_data['folder']
            
        # Update auto_metadata fields
        if 'auto_metadata' in request_data:
            if 'auto_metadata' not in current_metadata:
                current_metadata['auto_metadata'] = {}
                
            for field in ['summary', 'language', 'contentType']:
                if field in request_data['auto_metadata']:
                    current_metadata['auto_metadata'][field] = request_data['auto_metadata'][field]
                    
            for list_field in ['themes', 'topics', 'keywords', 'entities']:
                if list_field in request_data['auto_metadata']:
                    current_metadata['auto_metadata'][list_field] = request_data['auto_metadata'][list_field]
            
            # Ensure auto_generated is set
            current_metadata['auto_metadata']['auto_generated'] = True
            
        # Save the updated metadata
        success = update_file_metadata(file_id, current_metadata)
        
        if success:
            # If folder changed, update folder structure
            if 'folder' in request_data:
                try:
                    # Ensure the folder exists and move the item to it
                    move_item_to_folder(file_id, request_data['folder'])
                except Exception as folder_error:
                    current_app.logger.error(f"Error setting folder for {file_id}: {str(folder_error)}")
                    # Continue even if folder update failed, the metadata was still updated
            
            # Refresh the file index cache
            refresh_file_index_cache()
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update metadata"})
            
    except Exception as e:
        current_app.logger.error(f"Error updating metadata: {str(e)}")
        return jsonify({"success": False, "error": str(e)})
    

@metadata_bp.route("/<path:file_id>/generate", methods=["POST"])
def generate_metadata(file_id):
    """Generate AI metadata for a specific file."""
    try:
        # Get the current metadata first
        current_metadata = get_file_metadata(file_id)
        
        if not current_metadata:
            return jsonify({"success": False, "error": "No metadata found for this file"})
        
        # Get the file content to analyze
        try:
            client = get_storage_client()
            bucket_name = os.getenv("GCS_BUCKET_NAME") or current_app.config.get('GCS_BUCKET_NAME')
            bucket = client.bucket(bucket_name)
            
            # Get storage path for the actual file content
            storage_path = current_metadata.get('_storage_path', '')
            if not storage_path:
                return jsonify({"success": False, "error": "File storage path not found in metadata"})
            
            # Determine the content blob path based on metadata storage path
            content_path = None
            file_content = ""
            
            # For document files (PDFs, text files, etc.)
            if "metadata_doc_" in storage_path:
                doc_id = storage_path.split("metadata_doc_")[1].replace('.pkl', '')
                content_path = f"cache/document_data_{doc_id}.pkl"
                
                # For pickle files, load the document objects
                try:
                    blob = bucket.blob(content_path)
                    if blob.exists():
                        # Download the pickle file and process it
                        with blob.open("rb") as f:
                            documents = pickle.load(f)
                            
                        # Extract text from the documents
                        for doc in documents:
                            if hasattr(doc, 'text'):
                                file_content += doc.text + "\n\n"
                except Exception as e:
                    current_app.logger.warning(f"Error reading document data pickle: {str(e)}")
            else:
                # For other file types, try to infer content path
                item_id = file_id
                # Try different possible content paths
                possible_paths = [
                    f"cache/content_{item_id}.txt",
                    f"cache/content_{item_id}.md"
                ]
                
                for path in possible_paths:
                    blob = bucket.blob(path)
                    if blob.exists():
                        content_path = path
                        try:
                            file_content = blob.download_as_string().decode('utf-8')
                        except UnicodeDecodeError:
                            # Try with a different encoding if utf-8 fails
                            file_content = blob.download_as_string().decode('latin-1')
                        break
                
                # Check for PDF content path
                pdf_path = f"cache/content_{item_id}.pdf"
                blob = bucket.blob(pdf_path)
                if blob.exists() and not file_content:
                    content_path = pdf_path
                    
                    # For PDF, download to temp file and extract text
                    import tempfile
                    import io
                    from llama_index.readers.file import PDFReader
                    
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                        temp_file_path = temp_file.name
                        blob.download_to_filename(temp_file_path)
                    
                    try:
                        reader = PDFReader()
                        documents = reader.load_data(temp_file_path)
                        
                        # Extract text from all pages
                        for doc in documents:
                            if hasattr(doc, 'text'):
                                file_content += doc.text + "\n\n"
                                
                        # Clean up temp file
                        os.remove(temp_file_path)
                    except Exception as e:
                        current_app.logger.warning(f"Error processing PDF: {str(e)}")
                        # Clean up temp file on error
                        try:
                            os.remove(temp_file_path)
                        except:
                            pass
            
            # Try to extract from metadata if nothing else worked
            if not file_content and "auto_metadata" in current_metadata and "summary" in current_metadata["auto_metadata"]:
                file_content = current_metadata["auto_metadata"]["summary"]
                current_app.logger.info("Using existing summary as content for metadata generation")
            
            if not file_content:
                return jsonify({"success": False, "error": "Could not extract text content from this file"})
            
            # Generate metadata with OpenAI
            current_app.logger.info(f"Generating AI metadata for file: {file_id}")
            auto_metadata = extract_auto_metadata(file_content)
            
            # Update the metadata with AI-generated content
            if auto_metadata:
                if 'auto_metadata' not in current_metadata:
                    current_metadata['auto_metadata'] = {}
                
                # Update the auto metadata fields
                current_metadata['auto_metadata'] = auto_metadata
                
                # Save the updated metadata
                success = update_file_metadata(file_id, current_metadata)
                
                if success:
                    # Refresh the file index cache
                    refresh_file_index_cache()
                    return jsonify({
                        "success": True, 
                        "metadata": current_metadata
                    })
                else:
                    return jsonify({
                        "success": False, 
                        "error": "Failed to update metadata"
                    })
            else:
                return jsonify({
                    "success": False,
                    "error": "Failed to generate metadata"
                })
                
        except Exception as e:
            current_app.logger.error(f"Error accessing file content for metadata generation: {str(e)}")
            return jsonify({
                "success": False, 
                "error": f"Error accessing file content: {str(e)}"
            })
            
    except Exception as e:
        current_app.logger.error(f"Error generating metadata: {str(e)}")
        return jsonify({"success": False, "error": str(e)})