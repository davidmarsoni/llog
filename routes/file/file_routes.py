from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, make_response
from services.llm_service import get_available_indexes
from services.utils.cache import get_folders
from .route_utils import add_cache_headers

# Import sub-blueprints
from .file_add_routes import file_add_bp
from .file_view_routes import file_view_bp
from .file_metadata_routes import metadata_bp
from .folder_management_routes import folder_bp

# Create a Blueprint for content storage routes
file_bp = Blueprint('file_storage', __name__, url_prefix='/files')

@file_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)

@file_bp.route("/")
def manage_files():
    """Redirects to the add_files page by default."""
    return redirect(url_for('file_storage.add_files'))

@file_bp.route("/add")
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

@file_bp.route("/view")
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

# Register all file-related blueprints
def register_file_blueprints(app):
    """Register all file-related blueprints with the app"""
    # First register the main file blueprint
    app.register_blueprint(file_bp)
    
    # Then register all sub-blueprints
    app.register_blueprint(file_add_bp)
    app.register_blueprint(file_view_bp)
    app.register_blueprint(metadata_bp)
    app.register_blueprint(folder_bp)

