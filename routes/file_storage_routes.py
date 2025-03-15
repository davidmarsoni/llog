"""
File storage routes for the application
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

# Create a Blueprint for file storage routes
file_storage_bp = Blueprint('file_storage', __name__, url_prefix='/files')

# We'll import the storage service in a way that allows for dependency injection
# This makes it easier to replace the implementation or mock it for testing
@file_storage_bp.route("/")
def manage_files():
    """List all files in storage."""
    try:
        # We'll use a service for storage operations
        from services.storage_service import get_all_files
        
        files = get_all_files()
        bucket_name = current_app.config.get('GCS_BUCKET_NAME')
        
        return render_template("manage_files.html", files=files, bucket_name=bucket_name)
    
    except Exception as e:
        current_app.logger.error(f"ERROR in manage_files: {str(e)}")
        flash(f"Error accessing files: {str(e)}")
        return redirect(url_for('main.home'))

@file_storage_bp.route("/upload", methods=["POST"])
def upload_file():
    """Upload a file to storage."""
    if "file" not in request.files:
        flash("No file part")
        return redirect(url_for("file_storage.manage_files"))
    
    file = request.files["file"]
    
    if file.filename == "":
        flash("No selected file")
        return redirect(url_for("file_storage.manage_files"))
    
    try:
        from services.storage_service import upload_file_to_storage
        
        upload_file_to_storage(file)
        flash(f"File {file.filename} uploaded successfully!")
        
        return redirect(url_for("file_storage.manage_files"))
    
    except Exception as e:
        flash(f"Error: {str(e)}")
        return redirect(url_for('file_storage.manage_files'))

@file_storage_bp.route("/delete/<filename>", methods=["POST"])
def delete_file(filename):
    """Delete a file from storage."""
    try:
        from services.storage_service import delete_file_from_storage
        
        delete_file_from_storage(filename)
        flash(f"File {filename} deleted successfully!")
        
    except Exception as e:
        flash(f"Error: {str(e)}")
    
    return redirect(url_for('file_storage.manage_files'))