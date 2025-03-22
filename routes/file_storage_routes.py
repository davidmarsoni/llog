"""
Content storage routes for the application
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, make_response
import os
import datetime
import json
import pickle
from werkzeug.utils import secure_filename
from services.storage_service import get_file_metadata, update_file_metadata, get_storage_client
from services.llm_service import get_available_indexes, refresh_file_index_cache
from services.document_service import extract_auto_metadata
from services.llm.cache import get_folders, create_folder, move_item_to_folder, rename_folder

# Create a Blueprint for content storage routes
file_storage_bp = Blueprint('file_storage', __name__, url_prefix='/files')

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@file_storage_bp.route("/")
def manage_files():
    """Redirects to the add_files page by default."""
    return redirect(url_for('file_storage.add_files'))

@file_storage_bp.route("/add")
def add_files():
    """Page for adding new content (Notion, documents, etc.)"""
    # Get pagination parameters for passing to the form actions
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    filter_title = request.args.get('title', '')
    filter_type = request.args.get('type', '')
    
    # Get folders for folder selection in forms
    folders = get_folders()
    
    bucket_name = current_app.config.get('GCS_BUCKET_NAME')
    
    response = make_response(render_template("add_files.html", 
                                          page=page,
                                          per_page=per_page,
                                          filter_title=filter_title,
                                          filter_type=filter_type,
                                          bucket_name=bucket_name,
                                          folders=folders))
    return add_cache_headers(response)

@file_storage_bp.route("/view")
def view_files():
    """View cached content with filtering and pagination."""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        filter_folder = request.args.get('folder', '')
        
        # Get folders for folder selection in forms
        folders = get_folders()
        
        # Get content indexes filtered by folder if specified
        content_indexes = get_available_indexes(filter_folder if filter_folder else None)
        
        # Apply title filter if specified
        if filter_title:
            content_indexes = [idx for idx in content_indexes if filter_title.lower() in idx['title'].lower()]
        
        # Apply type filter if specified
        if filter_type:
            content_indexes = [idx for idx in content_indexes if idx['type'] == filter_type]
        
        # Calculate total items and pages
        total_items = len(content_indexes)
        total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
        
        # Ensure page is within valid range
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # Get paginated indexes
        paginated_indexes = []
        if total_items > 0:
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_indexes = content_indexes[start_idx:end_idx]
        
        # Render template with all required data
        response = make_response(render_template("view_files.html", 
                                              content_indexes=paginated_indexes,
                                              total_items=total_items,
                                              page=page,
                                              per_page=per_page,
                                              total_pages=total_pages,
                                              filter_title=filter_title,
                                              filter_type=filter_type,
                                              filter_folder=filter_folder,
                                              folders=folders,
                                              current_folder=filter_folder,
                                              bucket_name=current_app.config.get('GCS_BUCKET_NAME'),
                                              min=min))  # Add min function to the template context
        return add_cache_headers(response)
    
    except Exception as e:
        current_app.logger.error(f"ERROR in view_files: {str(e)}")
        flash(f"Error accessing cache: {str(e)}")
        # Show the page with the error
        response = make_response(render_template("view_files.html", 
                                              content_indexes=[],
                                              total_items=0,
                                              page=1,
                                              per_page=10,
                                              total_pages=1,
                                              filter_title='',
                                              filter_type='',
                                              filter_folder='',
                                              folders=[{'path': '', 'name': 'Root'}],
                                              current_folder='',
                                              bucket_name=current_app.config.get('GCS_BUCKET_NAME'),
                                              min=min))  # Add min function to the template context
        return add_cache_headers(response)

@file_storage_bp.route("/cache-notion", methods=["POST"])
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
        from services.notion_service import cache_notion_page, cache_notion_database, get_notion_client
        from services.llm_service import refresh_file_index_cache
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

@file_storage_bp.route("/upload-document", methods=["POST"])
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
            from services.document_service import process_pdf_file
            from services.llm_service import refresh_file_index_cache
            
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
            from services.document_service import process_text_file
            from services.llm_service import refresh_file_index_cache
            
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

@file_storage_bp.route("/delete/<path:filename>", methods=["POST"])
def delete_file(filename):
    """Delete a cached file from storage.
    
    The path parameter can handle slashes in the filename.
    """
    try:
        from services.storage_service import delete_file_from_storage
        from services.llm_service import get_available_indexes, refresh_file_index_cache
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        filter_folder = request.args.get('folder', '')
        
        current_app.logger.info(f"Attempting to delete file: {filename}")
        delete_file_from_storage(filename)
        refresh_file_index_cache()  # Refresh cache after deleting content
        flash(f"Cached content {filename} deleted successfully!")
        
        # Check if we need to adjust the page number after deletion
        content_indexes = get_available_indexes(filter_folder if filter_folder else None)
        if filter_title:
            content_indexes = [idx for idx in content_indexes if filter_title.lower() in idx['title'].lower()]
        
        if filter_type:
            content_indexes = [idx for idx in content_indexes if idx['type'] == filter_type]
        
        # Calculate total pages
        total_items = len(content_indexes)
        total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
        
        # Adjust page if it's now out of range
        if page > total_pages and total_pages > 0:
            page = total_pages
            
    except Exception as e:
        current_app.logger.error(f"Error deleting content: {str(e)}")
        flash(f"Error deleting content: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type,
                           folder=filter_folder))

@file_storage_bp.route("/list-cached-content")
def list_cached_content():
    """List all cached content."""
    try:
        folder_path = request.args.get('folder', '')
        content_indexes = get_available_indexes(folder_path if folder_path else None)
        
        # Ensure we have a valid list even if get_available_indexes returns None
        if content_indexes is None:
            content_indexes = []
        
        # Transform content_indexes to include file paths and ids
        for item in content_indexes:
            if item is None:
                continue
                
            # Ensure item has an ID for metadata links
            if 'id' not in item:
                item['id'] = item.get('_storage_path', '').replace('cache/', '') or item.get('path', '')
                
            # Set display path
            if '_storage_path' in item:
                item['display_path'] = item['_storage_path'].replace('cache/', '')
            elif 'path' in item:
                item['display_path'] = item['path'].replace('cache/', '')
        
        # Filter out any None values that might have slipped through
        content_indexes = [idx for idx in content_indexes if idx is not None]
        
        response = make_response(jsonify({
            "cached_items": content_indexes,
            "is_loading": False
        }))
        return add_cache_headers(response)
    except Exception as e:
        current_app.logger.error(f"Error listing cached content: {str(e)}")
        error_response = make_response(jsonify({
            "error": str(e),
            "cached_items": [],  # Return empty list instead of None
            "is_loading": False
        }), 500)
        return add_cache_headers(error_response)

@file_storage_bp.route("/refresh-cache", methods=["POST"])
def refresh_cache():
    """Force a refresh of the file index cache."""
    try:
        from services.llm_service import refresh_file_index_cache
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        filter_folder = request.args.get('folder', '')
        
        get_available_indexes()  
        flash("Cache refreshed successfully!")
        
    except Exception as e:
        current_app.logger.error(f"Error refreshing cache: {str(e)}")
        flash(f"Error refreshing cache: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type,
                           folder=filter_folder))

@file_storage_bp.route("/refresh-item", methods=["POST"])
def refresh_item():
    """Refresh a single Notion page or database."""
    # Get current pagination and filter parameters to preserve when redirecting
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    filter_title = request.args.get('title', '')
    filter_type = request.args.get('type', '')
    filter_folder = request.args.get('folder', '')
    
    # Get the item_id (UUID used internally) and item_notion_id (actual Notion ID)
    item_id = request.form.get('item_id', '')
    item_notion_id = request.form.get('item_notion_id', '')
    item_type = request.form.get('item_type', '')
    custom_name = request.form.get('custom_name', '')
    
    try:
        if not item_notion_id:
            flash("No Notion page/database ID provided")
            return redirect(url_for('file_storage.view_files'))
        
        current_app.logger.info(f"Refreshing {item_type} with ID: {item_notion_id} (UUID: {item_id})")
        
        if item_type == 'page':
            from services.notion_service import cache_notion_page
            result = cache_notion_page(item_notion_id, custom_name, item_id)
            flash(f"Successfully refreshed Notion page '{result['title']}' with {result['chunks']} content chunks!")
        elif item_type == 'database':
            from services.notion_service import cache_notion_database
            result = cache_notion_database(item_notion_id, custom_name, item_id)
            flash(f"Successfully refreshed Notion database '{result['title']}' with {result['pages_found']} pages!")
        else:
            flash(f"Unknown item type: {item_type}")
            return redirect(url_for('file_storage.view_files'))
        
        from services.llm_service import refresh_file_index_cache
        refresh_file_index_cache()  # Refresh cache after updating content
        
    except Exception as e:
        current_app.logger.error(f"Error refreshing item: {str(e)}")
        flash(f"Error refreshing item: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type,
                           folder=filter_folder))

# New routes for folder management
@file_storage_bp.route("/create-folder", methods=["POST"])
def create_folder_route():
    """Create a new folder"""
    try:
        folder_name = request.form.get('folder_name', '').strip()
        parent_path = request.form.get('parent_path', '').strip()
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        
        if not folder_name:
            flash("Folder name cannot be empty")
        else:
            # Create the folder and force a complete refresh of the cache
            new_path = create_folder(folder_name, parent_path)
            # Explicitly reload the folder cache to immediately show the new folder
            from services.llm.cache import _sync_reload_folder_cache
            _sync_reload_folder_cache()
            flash(f"Folder '{folder_name}' created successfully!")
            
            # If we created a subfolder, return to that parent folder view
            if parent_path:
                return redirect(url_for('file_storage.view_files', 
                                      page=page, 
                                      per_page=per_page,
                                      title=filter_title,
                                      type=filter_type,
                                      folder=parent_path))
    
    except Exception as e:
        current_app.logger.error(f"Error creating folder: {str(e)}")
        flash(f"Error creating folder: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type))

@file_storage_bp.route("/rename-folder", methods=["POST"])
def rename_folder_route():
    """Rename a folder"""
    try:
        folder_path = request.form.get('folder_path', '').strip()
        new_name = request.form.get('new_name', '').strip()
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        
        if not folder_path or not new_name:
            flash("Folder path and new name are required")
        else:
            old_name = folder_path.split('/')[-1] if '/' in folder_path else folder_path
            parent_path = '/'.join(folder_path.split('/')[:-1]) if '/' in folder_path else ''
            
            rename_folder(folder_path, new_name)
            flash(f"Folder '{old_name}' renamed to '{new_name}' successfully!")
            
            # If renamed folder was in a parent folder, return to parent folder view
            if parent_path:
                return redirect(url_for('file_storage.view_files', 
                                      page=page, 
                                      per_page=per_page,
                                      title=filter_title,
                                      type=filter_type,
                                      folder=parent_path))
    
    except Exception as e:
        current_app.logger.error(f"Error renaming folder: {str(e)}")
        flash(f"Error renaming folder: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type))

def send_htmx_response(success, message, content=None):
    """Helper function to send consistent HTMX responses"""
    response = {
        'success': success,
        'message': message
    }
    if content:
        response.update(content)
    return jsonify(response)

@file_storage_bp.route("/move-item", methods=["POST"])
def move_item():
    """Move an item to a different folder"""
    try:
        item_id = request.form.get('item_id')
        folder_path = request.form.get('folder_path', '')  # Empty string is valid for root folder
        
        # Get current pagination and filter parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        current_folder = request.args.get('folder', '')
        
        if not item_id:
            flash("No item ID provided")
            return redirect(url_for('file_storage.view_files'))

        # Move the item
        move_item_to_folder(item_id, folder_path)
        
        # Force a refresh of the cache to ensure we have the latest data
        from services.llm_service import refresh_file_index_cache
        refresh_file_index_cache()
        
        # For HTMX requests, return the updated content table
        if "HX-Request" in request.headers:
            folders = get_folders()
            content_indexes = get_available_indexes(current_folder if current_folder else None)
            
            # Apply filters
            if filter_title:
                content_indexes = [idx for idx in content_indexes if filter_title.lower() in idx['title'].lower()]
            if filter_type:
                content_indexes = [idx for idx in content_indexes if idx['type'] == filter_type]
            
            # Calculate pagination
            total_items = len(content_indexes)
            total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
            page = min(max(1, page), total_pages)
            
            # Get paginated indexes
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_indexes = content_indexes[start_idx:end_idx] if total_items > 0 else []
            
            return render_template("components/content_table.html", 
                                content_indexes=paginated_indexes,
                                total_items=total_items,
                                page=page,
                                per_page=per_page,
                                total_pages=total_pages,
                                filter_title=filter_title,
                                filter_type=filter_type,
                                filter_folder=current_folder,
                                folders=folders,
                                current_folder=current_folder,
                                bucket_name=current_app.config.get('GCS_BUCKET_NAME'),
                                min=min)
        
        # For regular requests, redirect back to the view
        flash("Item moved successfully!")
        return redirect(url_for('file_storage.view_files', 
                              page=page, 
                              per_page=per_page,
                              title=filter_title,
                              type=filter_type,
                              folder=current_folder))
                              
    except Exception as e:
        current_app.logger.error(f"Error moving item: {str(e)}")
        if "HX-Request" in request.headers:
            return jsonify({"error": str(e)}), 500
        flash(f"Error moving item: {str(e)}")
        return redirect(url_for('file_storage.view_files', 
                              page=page, 
                              per_page=per_page,
                              title=filter_title,
                              type=filter_type,
                              folder=current_folder))

@file_storage_bp.route("/get-folders", methods=["GET"])
def get_folders_route():
    """API endpoint to get all folders"""
    try:
        folders = get_folders()
        return jsonify({"folders": folders})
    except Exception as e:
        current_app.logger.error(f"Error getting folders: {str(e)}")
        return jsonify({"error": str(e)}), 500

@file_storage_bp.route("/delete-folder", methods=["POST"])
def delete_folder_route():
    """Delete a folder and move all its contents to parent folder"""
    try:
        folder_path = request.form.get('folder_path', '').strip()
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        
        if not folder_path:
            flash("No folder path provided")
            return redirect(url_for('file_storage.view_files'))
        
        # Get parent folder path for redirect after deletion
        parent_path = '/'.join(folder_path.split('/')[:-1]) if '/' in folder_path else ''
        
        # Import the delete_folder function
        from services.llm.cache import delete_folder
        
        # Delete the folder and get the number of affected items
        num_affected = delete_folder(folder_path)
        
        folder_name = folder_path.split('/')[-1] if '/' in folder_path else folder_path
        flash(f"Folder '{folder_name}' deleted. {num_affected} items moved to parent folder.")
        
        # Redirect to parent folder or root if deleting a top-level folder
        return redirect(url_for('file_storage.view_files', 
                              page=page, 
                              per_page=per_page,
                              title=filter_title,
                              type=filter_type,
                              folder=parent_path))
    
    except Exception as e:
        current_app.logger.error(f"Error deleting folder: {str(e)}")
        flash(f"Error deleting folder: {str(e)}")
        
        # Redirect with pagination and filter parameters preserved
        return redirect(url_for('file_storage.view_files', 
                             page=page, 
                             per_page=per_page,
                             title=filter_title,
                             type=filter_type))

@file_storage_bp.route("/check-content-loading")
def check_content_loading():
    """Check if content is still loading."""
    try:
        from services.llm_service import is_cache_loading
        
        folder_path = request.args.get('folder', '')
        is_loading = is_cache_loading()
        
        response = make_response(jsonify({
            "is_loading": is_loading
        }))
        return add_cache_headers(response)
    except Exception as e:
        current_app.logger.error(f"Error checking content loading state: {str(e)}")
        error_response = make_response(jsonify({
            "error": str(e),
            "is_loading": False
        }), 500)
        return add_cache_headers(error_response)

@file_storage_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)

@file_storage_bp.app_template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert a Unix timestamp to a human-readable date string."""
    try:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return 'Unknown'

@file_storage_bp.route("/metadata/<path:file_id>")
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

@file_storage_bp.route("/metadata/<path:file_id>/update", methods=["POST"])
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

@file_storage_bp.route("/metadata/<path:file_id>/generate", methods=["POST"])
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

@file_storage_bp.route("/filtered-content")
def filtered_content():
    """Return filtered content for HTMX requests."""
    try:
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        filter_folder = request.args.get('folder', '')
        
        # Get folders for folder selection in forms
        folders = get_folders()
        
        # Get content indexes filtered by folder if specified
        content_indexes = get_available_indexes(filter_folder if filter_folder else None)
        
        # Apply title filter if specified
        if filter_title:
            content_indexes = [idx for idx in content_indexes if filter_title.lower() in idx['title'].lower()]
        
        # Apply type filter if specified
        if filter_type:
            content_indexes = [idx for idx in content_indexes if idx['type'] == filter_type]
        
        # Calculate total items and pages
        total_items = len(content_indexes)
        total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
        
        # Ensure page is within valid range
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # Get paginated indexes
        paginated_indexes = []
        if total_items > 0:
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_indexes = content_indexes[start_idx:end_idx]
            
        # For HTMX requests, return just the content table component
        response = make_response(render_template("components/content_table.html", 
                                            content_indexes=paginated_indexes,
                                            total_items=total_items,
                                            page=page,
                                            per_page=per_page,
                                            total_pages=total_pages,
                                            filter_title=filter_title,
                                            filter_type=filter_type,
                                            filter_folder=filter_folder,
                                            folders=folders,
                                            current_folder=filter_folder,
                                            bucket_name=current_app.config.get('GCS_BUCKET_NAME'),
                                            min=min))
        return add_cache_headers(response)
        
    except Exception as e:
        current_app.logger.error(f"ERROR in filtered_content: {str(e)}")
        error_response = make_response(render_template("components/content_table.html", 
                                                   content_indexes=[],
                                                   total_items=0,
                                                   page=1,
                                                   per_page=10,
                                                   total_pages=1,
                                                   filter_title='',
                                                   filter_type='',
                                                   filter_folder='',
                                                   folders=[{'path': '', 'name': 'Root'}],
                                                   current_folder='',
                                                   bucket_name=current_app.config.get('GCS_BUCKET_NAME'),
                                                   min=min))
        return add_cache_headers(error_response)