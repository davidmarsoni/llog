"""
Contains routes for adding files to the LLM storage
"""
import os
from flask import Blueprint, request, redirect, url_for, flash, current_app
from .route_utils import add_cache_headers
from services.utils.cache import move_item_to_folder
from services.document_service import process_text_file,process_pdf_file
from services.llm_service import refresh_file_index_cache
from services.notion_service import cache_notion_page, cache_notion_database, get_notion_client


file_add_bp = Blueprint('file_add', __name__, url_prefix='/files/add')

@file_add_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)

@file_add_bp.route("/upload-document", methods=["POST"])
def upload_document():
    """Upload and cache a document file (PDF, TXT, MD) for LLM processing."""
    # Get pagination parameters to preserve when redirecting
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    filter_title = request.args.get('title', '')
    filter_type = request.args.get('type', '')
    folder_path = request.form.get('folder_path', '').strip()
    
    # Build redirect URL with parameters - redirect to view_files after adding content
    redirect_url = url_for("file_storage.view_files", 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type,
                           folder=folder_path)
    
    try:
        # Check if file was submitted
        if 'document' not in request.files:
            flash("No file was uploaded")
            return redirect(url_for('file_storage.add_files'))
        
        file = request.files['document']
        
        # Check if the file has a name
        if file.filename == '':
            flash("No file was selected")
            return redirect(url_for('file_storage.add_files'))
        
        # Get custom name if provided
        custom_name = request.form.get('document_name', '').strip()
        
        # Check file extension
        _, file_ext = os.path.splitext(file.filename)
        file_ext = file_ext.lower()
        
        if file_ext == '.pdf':
            result = process_pdf_file(file, file.filename, custom_name)
            
            # Update metadata with folder information if specified
            if folder_path and result["success"]:
                try:
                    move_item_to_folder(result["doc_id"], folder_path)
                except Exception as folder_error:
                    current_app.logger.error(f"Error setting folder for {result['doc_id']}: {str(folder_error)}")
                    
            refresh_file_index_cache()  # Refresh cache after adding content
            flash(f"Successfully cached PDF '{result['title']}' with {result['chunks']} content chunks!")
        elif file_ext in ['.txt', '.md']:
            result = process_text_file(file, file.filename, custom_name)
            
            # Update metadata with folder information if specified
            if folder_path and result["success"]:
                try:
                    move_item_to_folder(result["doc_id"], folder_path)
                except Exception as folder_error:
                    current_app.logger.error(f"Error setting folder for {result['doc_id']}: {str(folder_error)}")
                    
            refresh_file_index_cache()  # Refresh cache after adding content
            
            if result["success"]:
                flash(f"Successfully cached {file_ext[1:].upper()} file '{result['title']}' with {result['chunks']} content chunks!")
            else:
                flash(f"Error processing {file_ext[1:].upper()} file: {result.get('error', 'Unknown error')}")
                return redirect(url_for('file_storage.add_files'))
        else:
            flash(f"Unsupported file type: {file_ext}. Please upload PDF, TXT, or MD files.")
            return redirect(url_for('file_storage.add_files'))
        
        return redirect(redirect_url)
        
    except Exception as e:
        current_app.logger.error(f"Error in upload_document: {str(e)}")
        flash(f"Error caching document: {str(e)}")
        return redirect(url_for('file_storage.add_files'))
    
@file_add_bp.route("/cache-notion", methods=["POST"])
def cache_notion_page():
    """Cache a Notion page or database for LLM processing."""
    page_id = request.form.get('page_id', '').strip()
    database_id = request.form.get('database_id', '').strip()
    custom_name = request.form.get('custom_name', '').strip()
    folder_path = request.form.get('folder_path', '').strip()
    
    # Get pagination parameters to preserve when redirecting
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    filter_title = request.args.get('title', '')
    filter_type = request.args.get('type', '')
    
    # Build redirect URL with parameters - redirect to view_files after adding content
    redirect_url = url_for("file_storage.view_files", 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type,
                           folder=folder_path)
    
    try:
        notion = get_notion_client()
        
        # CASE 1: Database ID is provided - process it directly
        if database_id:
            current_app.logger.info(f"Database ID provided: {database_id}")
            try:
                # Verify it's a valid database
                notion.databases.retrieve(database_id)
                result = cache_notion_database(database_id, custom_name)
                
                # Update metadata with folder information if specified
                if folder_path and result["success"]:
                    try:
                        move_item_to_folder(database_id, folder_path)
                    except Exception as folder_error:
                        current_app.logger.error(f"Error setting folder for {database_id}: {str(folder_error)}")
                
                refresh_file_index_cache()  # Refresh cache after adding content
                flash(f"Successfully cached Notion database '{result['title']}' with {result['pages_found']} pages!")
                return redirect(redirect_url)
            except Exception as e:
                current_app.logger.error(f"Error with database ID {database_id}: {str(e)}")
                flash(f"The provided database ID appears to be invalid: {str(e)}")
                return redirect(url_for('file_storage.add_files'))
        
        # CASE 2: Only page ID is provided - first check if it's actually a database
        elif page_id:
            current_app.logger.info(f"Page ID provided: {page_id}")
            try:
                # First check if it's actually a database
                try:
                    notion.databases.retrieve(page_id)
                    current_app.logger.info(f"ID {page_id} is a database, caching all pages")
                    result = cache_notion_database(page_id, custom_name)
                    
                    # Update metadata with folder information if specified
                    if folder_path and result["success"]:
                        try:
                            move_item_to_folder(page_id, folder_path)
                        except Exception as folder_error:
                            current_app.logger.error(f"Error setting folder for {page_id}: {str(folder_error)}")
                    
                    refresh_file_index_cache()  # Refresh cache after adding content
                    flash(f"Successfully cached Notion database '{result['title']}' with {result['pages_found']} pages!")
                    return redirect(redirect_url)
                except:
                    # Not a database, treat as a regular page
                    current_app.logger.info(f"ID {page_id} is not a database, treating as a page")
                    result = cache_notion_page(page_id, custom_name)
                    
                    # Update metadata with folder information if specified
                    if folder_path and result["success"]:
                        try:
                            move_item_to_folder(page_id, folder_path)
                        except Exception as folder_error:
                            current_app.logger.error(f"Error setting folder for {page_id}: {str(folder_error)}")
                    
                    refresh_file_index_cache()  # Refresh cache after adding content
                    flash(f"Successfully cached Notion page '{result['title']}' with {result['chunks']} content chunks!")
                    return redirect(redirect_url)
            except Exception as e:
                current_app.logger.error(f"Error processing ID {page_id}: {str(e)}")
                flash(f"Error processing Notion content: {str(e)}")
                return redirect(url_for('file_storage.add_files'))
        
        # CASE 3: No ID provided
        else:
            flash("Please enter either a Notion Database ID or Page ID")
            return redirect(url_for('file_storage.add_files'))
        
    except Exception as e:
        current_app.logger.error(f"Error in cache_notion_page: {str(e)}")
        flash(f"Error caching Notion content: {str(e)}")
        return redirect(url_for('file_storage.add_files'))