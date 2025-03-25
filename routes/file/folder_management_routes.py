from flask import Blueprint, request, redirect, url_for, flash, current_app, jsonify
from services.llm.cache import get_folders, create_folder, rename_folder, delete_folder
from .route_utils import add_cache_headers

folder_bp = Blueprint('folder_management', __name__, url_prefix='/files/folders')

@folder_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)

@folder_bp.route("/create-folder", methods=["POST"])
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
            create_folder(folder_name, parent_path)
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

@folder_bp.route("/rename-folder", methods=["POST"])
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

@folder_bp.route("/get-folders", methods=["GET"])
def get_folders_route():
    """API endpoint to get all folders"""
    try:
        folders = get_folders()
        return jsonify({"folders": folders})
    except Exception as e:
        current_app.logger.error(f"Error getting folders: {str(e)}")
        return jsonify({"error": str(e)}), 500

@folder_bp.route("/delete-folder", methods=["POST"])
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