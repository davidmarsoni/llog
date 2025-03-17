"""
Notion cache routes for the application
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, make_response
import os

# Create a Blueprint for file storage routes (keeping name for compatibility)
file_storage_bp = Blueprint('file_storage', __name__, url_prefix='/files')

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@file_storage_bp.route("/")
def manage_files():
    """Redirects to the add_files page by default for backward compatibility."""
    return redirect(url_for('file_storage.add_files'))

@file_storage_bp.route("/add")
def add_files():
    """Page for adding new content (Notion, documents, etc.)"""
    # Get pagination parameters for passing to the form actions
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    filter_title = request.args.get('title', '')
    filter_type = request.args.get('type', '')
    
    bucket_name = current_app.config.get('GCS_BUCKET_NAME')
    
    response = make_response(render_template("add_files.html", 
                                          page=page,
                                          per_page=per_page,
                                          filter_title=filter_title,
                                          filter_type=filter_type,
                                          bucket_name=bucket_name))
    return add_cache_headers(response)

@file_storage_bp.route("/view")
def view_files():
    """View cached content with filtering and pagination."""
    try:
        from services.llm_service import get_available_notion_indexes
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # Get filter parameters
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        
        # Get all notion indexes
        notion_indexes = get_available_notion_indexes()
        
        # Apply filters if provided
        if filter_title:
            notion_indexes = [idx for idx in notion_indexes if filter_title.lower() in idx['title'].lower()]
        
        if filter_type:
            notion_indexes = [idx for idx in notion_indexes if idx['type'] == filter_type]
        
        # Calculate total items and pages
        total_items = len(notion_indexes)
        total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
        
        # Ensure page is within valid range
        if page < 1:
            page = 1
        elif page > total_pages and total_pages > 0:
            page = total_pages
        
        # Get paginated indexes - only if there are items
        paginated_indexes = []
        if total_items > 0:
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_indexes = notion_indexes[start_idx:end_idx]
        
        bucket_name = current_app.config.get('GCS_BUCKET_NAME')
        
        response = make_response(render_template("view_files.html", 
                                              notion_indexes=paginated_indexes,
                                              total_items=total_items,
                                              page=page,
                                              per_page=per_page,
                                              total_pages=total_pages,
                                              filter_title=filter_title,
                                              filter_type=filter_type,
                                              bucket_name=bucket_name,
                                              min=min))  # Add min function to the template context
        return add_cache_headers(response)
    
    except Exception as e:
        current_app.logger.error(f"ERROR in view_files: {str(e)}")
        flash(f"Error accessing cache: {str(e)}")
        # Show the page with the error
        response = make_response(render_template("view_files.html", 
                                              notion_indexes=[],
                                              total_items=0,
                                              page=1,
                                              per_page=10,
                                              total_pages=1,
                                              filter_title='',
                                              filter_type='',
                                              bucket_name=current_app.config.get('GCS_BUCKET_NAME'),
                                              min=min))  # Add min function to the template context
        return add_cache_headers(response)

@file_storage_bp.route("/cache-notion", methods=["POST"])
def cache_notion_page():
    """Cache a Notion page or database for LLM processing."""
    page_id = request.form.get('page_id', '').strip()
    database_id = request.form.get('database_id', '').strip()
    custom_name = request.form.get('custom_name', '').strip()
    
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
                           type=filter_type)
    
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
                    refresh_file_index_cache()  # Refresh cache after adding content
                    flash(f"Successfully cached Notion database '{result['title']}' with {result['pages_found']} pages!")
                    return redirect(redirect_url)
                except:
                    # Not a database, treat as a regular page
                    current_app.logger.info(f"ID {page_id} is not a database, treating as a page")
                    result = cache_notion_page(page_id, custom_name)
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
    
    # Build redirect URL with parameters - redirect to view_files after adding content
    redirect_url = url_for("file_storage.view_files", 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type)
    
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
            refresh_file_index_cache()  # Refresh cache after adding content
            flash(f"Successfully cached PDF '{result['title']}' with {result['chunks']} content chunks!")
        elif file_ext in ['.txt', '.md']:
            from services.document_service import process_text_file
            from services.llm_service import refresh_file_index_cache
            result = process_text_file(file, file.filename, custom_name)
            refresh_file_index_cache()  # Refresh cache after adding content
            flash(f"Successfully cached {file_ext[1:].upper()} file '{result['title']}' with {result['chunks']} content chunks!")
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
        from services.llm_service import get_available_notion_indexes, refresh_file_index_cache
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        
        current_app.logger.info(f"Attempting to delete file: {filename}")
        delete_file_from_storage(filename)
        refresh_file_index_cache()  # Refresh cache after deleting content
        flash(f"Cached content {filename} deleted successfully!")
        
        # Check if we need to adjust the page number after deletion
        notion_indexes = get_available_notion_indexes()
        if filter_title:
            notion_indexes = [idx for idx in notion_indexes if filter_title.lower() in idx['title'].lower()]
        if filter_type:
            notion_indexes = [idx for idx in notion_indexes if idx['type'] == filter_type]
        
        total_items = len(notion_indexes)
        total_pages = (total_items + per_page - 1) // per_page if total_items > 0 else 1
        
        # If current page is now beyond total pages, adjust it
        if page > total_pages and total_pages > 0:
            page = total_pages
        
    except Exception as e:
        current_app.logger.error(f"Error deleting file {filename}: {str(e)}")
        flash(f"Error: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type))

@file_storage_bp.route("/list-cached-notion")
def list_cached_notion():
    """List all cached Notion pages and databases."""
    try:
        from services.llm_service import get_available_notion_indexes
        cached_items = get_available_notion_indexes()
        response = make_response(jsonify({"cached_items": cached_items}))
        return add_cache_headers(response)
    
    except Exception as e:
        current_app.logger.error(f"Error listing cached Notion content: {str(e)}")
        error_response = make_response(jsonify({"error": str(e)}), 500)
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
        
        refresh_file_index_cache()
        flash("Cache refreshed successfully!")
        
    except Exception as e:
        current_app.logger.error(f"Error refreshing cache: {str(e)}")
        flash(f"Error refreshing cache: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type))

@file_storage_bp.route("/refresh-item", methods=["POST"])
def refresh_item():
    """Refresh a single Notion page or database."""
    try:
        from services.notion_service import cache_notion_page, cache_notion_database, get_notion_client
        from services.llm_service import refresh_file_index_cache
        
        # Get item information
        item_id = request.form.get('item_id')
        item_type = request.form.get('item_type')
        custom_name = request.form.get('custom_name', '').strip()
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        
        notion = get_notion_client()
        
        if item_type == 'database':
            result = cache_notion_database(item_id, custom_name)
            refresh_file_index_cache()
            flash(f"Successfully refreshed database '{result['title']}' with {result['pages_found']} pages!")
        else:
            result = cache_notion_page(item_id, custom_name)
            refresh_file_index_cache()
            flash(f"Successfully refreshed page '{result['title']}' with {result['chunks']} content chunks!")
            
    except Exception as e:
        current_app.logger.error(f"Error refreshing item {item_id}: {str(e)}")
        flash(f"Error refreshing item: {str(e)}")
    
    # Redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type))

@file_storage_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)