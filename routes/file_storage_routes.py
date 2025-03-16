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
    """Manage cached Notion content."""
    try:
        from services.llm_service import get_available_notion_indexes
        
        notion_indexes = get_available_notion_indexes()
        bucket_name = current_app.config.get('GCS_BUCKET_NAME')
        
        response = make_response(render_template("manage_files.html", 
                                              notion_indexes=notion_indexes, 
                                              bucket_name=bucket_name))
        return add_cache_headers(response)
    
    except Exception as e:
        current_app.logger.error(f"ERROR in manage_files: {str(e)}")
        flash(f"Error accessing notion cache: {str(e)}")
        return redirect(url_for('main.home'))

@file_storage_bp.route("/cache-notion", methods=["POST"])
def cache_notion_page():
    """Cache a Notion page or database for LLM processing."""
    page_id = request.form.get('page_id', '').strip()
    database_id = request.form.get('database_id', '').strip()
    
    try:
        from services.notion_service import cache_notion_page, cache_notion_database, get_notion_client
        notion = get_notion_client()
        
        # CASE 1: Database ID is provided - process it directly
        if database_id:
            current_app.logger.info(f"Database ID provided: {database_id}")
            try:
                # Verify it's a valid database
                notion.databases.retrieve(database_id)
                result = cache_notion_database(database_id)
                flash(f"Successfully cached Notion database '{result['title']}' with {result['pages_found']} pages!")
                return redirect(url_for("file_storage.manage_files"))
            except Exception as e:
                current_app.logger.error(f"Error with database ID {database_id}: {str(e)}")
                flash(f"The provided database ID appears to be invalid: {str(e)}")
                return redirect(url_for("file_storage.manage_files"))
        
        # CASE 2: Only page ID is provided - first check if it's actually a database
        elif page_id:
            current_app.logger.info(f"Page ID provided: {page_id}")
            try:
                # First check if it's actually a database
                try:
                    notion.databases.retrieve(page_id)
                    current_app.logger.info(f"ID {page_id} is a database, caching all pages")
                    result = cache_notion_database(page_id)
                    flash(f"Successfully cached Notion database '{result['title']}' with {result['pages_found']} pages!")
                    return redirect(url_for("file_storage.manage_files"))
                except:
                    # Not a database, treat as a regular page
                    current_app.logger.info(f"ID {page_id} is not a database, treating as a page")
                    result = cache_notion_page(page_id)
                    flash(f"Successfully cached Notion page '{result['title']}' with {result['chunks']} content chunks!")
                    return redirect(url_for("file_storage.manage_files"))
            except Exception as e:
                current_app.logger.error(f"Error processing ID {page_id}: {str(e)}")
                flash(f"Error processing Notion content: {str(e)}")
                return redirect(url_for("file_storage.manage_files"))
        
        # CASE 3: No ID provided
        else:
            flash("Please enter either a Notion Database ID or Page ID")
            return redirect(url_for("file_storage.manage_files"))
        
    except Exception as e:
        current_app.logger.error(f"Error in cache_notion_page: {str(e)}")
        flash(f"Error caching Notion content: {str(e)}")
        return redirect(url_for('file_storage.manage_files'))

@file_storage_bp.route("/delete/<filename>", methods=["POST"])
def delete_file(filename):
    """Delete a cached Notion file from storage."""
    try:
        from services.storage_service import delete_file_from_storage
        
        delete_file_from_storage(filename)
        flash(f"Cached content {filename} deleted successfully!")
        
    except Exception as e:
        flash(f"Error: {str(e)}")
    
    return redirect(url_for('file_storage.manage_files'))

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

@file_storage_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)