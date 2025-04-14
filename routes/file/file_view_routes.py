import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, jsonify, make_response
from services.utils.cache import get_folders, move_item_to_folder
from .route_utils import add_cache_headers
from services.storage_service import delete_file_from_storage
from services.llm_service import get_available_indexes, refresh_file_index_cache, refresh_file_index_cache,is_cache_loading 
from services.notion_service import cache_notion_page,cache_notion_database


file_view_bp = Blueprint('file_view', __name__, url_prefix='/files/view')

@file_view_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)

@file_view_bp.route("/delete/<path:file_id>", methods=["POST"])
def delete_file(file_id):
    """Delete a cached file from storage.
    
    The path parameter can handle slashes in the file_id.
    """
    try:
    
        
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        filter_folder = request.args.get('folder', '')
        
        current_app.logger.info(f"Attempting to delete file: {file_id}")
        delete_file_from_storage(file_id)
        refresh_file_index_cache()  # Refresh cache after deleting content
        flash(f"Cached content {file_id} deleted successfully!")
        
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
    
@file_view_bp.route("/list-cached-content")
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

@file_view_bp.route("/refresh-cache", methods=["POST"])
def refresh_cache():
    """Force a refresh of the file index cache."""
    try:
        # Get current pagination and filter parameters to preserve after redirect
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        filter_title = request.args.get('title', '')
        filter_type = request.args.get('type', '')
        filter_folder = request.args.get('folder', '')
        
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
                           type=filter_type,
                           folder=filter_folder))

@file_view_bp.route("/refresh-item", methods=["POST"])
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
    
    success_message = ""
    error_message = ""
    
    try:
        if not item_notion_id:
            error_message = "No Notion page/database ID provided"
            flash(error_message)
            return redirect(url_for('file_storage.view_files'))
        
        current_app.logger.info(f"Refreshing {item_type} with ID: {item_notion_id} (UUID: {item_id})")
        
        if item_type == 'page':
            result = cache_notion_page(item_notion_id, custom_name, item_id)
            success_message = f"Successfully refreshed Notion page '{result['title']}' with {result['chunks']} content chunks!"
            flash(success_message)
        elif item_type == 'database':
            result = cache_notion_database(item_notion_id, custom_name, item_id)
            success_message = f"Successfully refreshed Notion database '{result['title']}' with {result['pages_found']} pages!"
            flash(success_message)
        else:
            error_message = f"Unknown item type: {item_type}"
            flash(error_message)
            return redirect(url_for('file_storage.view_files'))
        
        refresh_file_index_cache()  # Refresh cache after updating content
        
    except Exception as e:
        current_app.logger.error(f"Error refreshing item: {str(e)}")
        error_message = f"Error refreshing item: {str(e)}"
        flash(error_message)
    
    # Check if this is an HTMX request
    if "HX-Request" in request.headers:
        # For HTMX requests, return a notification that can be displayed
        if error_message:
            return jsonify({
                "status": "error",
                "message": error_message,
                "title": custom_name or "Item"
            }), 400
        else:
            return jsonify({
                "status": "success",
                "message": success_message,
                "title": custom_name or "Item"
            })
    
    # For regular requests, redirect with pagination and filter parameters preserved
    return redirect(url_for('file_storage.view_files', 
                           page=page, 
                           per_page=per_page,
                           title=filter_title,
                           type=filter_type,
                           folder=filter_folder))
    

@file_view_bp.route("/move-item", methods=["POST"])
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
            return redirect(url_for('file_storage.view_files'))        # Move the item
        move_item_to_folder(item_id, folder_path)
        
        # Flash success message
        flash(f"Item moved successfully to {'Root' if not folder_path else folder_path}")
        
        # Force a refresh of the cache to ensure we have the latest data
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
        # For regular requests, redirect to the destination folder
        flash("Item moved successfully!")
        return redirect(url_for('file_storage.view_files', 
                              page=1,  # Start at first page in new folder 
                              per_page=per_page,
                              title=filter_title,
                              type=filter_type,
                              folder=folder_path))  # Redirect to destination folder
                              
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

@file_view_bp.route("/filtered-content")
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
    

@file_view_bp.route("/check-content-loading")
def check_content_loading():
    """Check if content is still loading."""
    try:
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


@file_view_bp.app_template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert a Unix timestamp to a human-readable date string."""
    try:
        dt = datetime.datetime.fromtimestamp(timestamp)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return 'Unknown'