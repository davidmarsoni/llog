"""
Main routes for the application (home, about)
"""
from flask import Blueprint, render_template, make_response

# Create a Blueprint for main routes
main_bp = Blueprint('main', __name__)

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@main_bp.route('/')
def home():
    """Render the home page."""
    response = make_response(render_template('home.html'))
    return add_cache_headers(response)

@main_bp.route('/about')
def about():
    """Render the about page."""
    response = make_response(render_template('about.html'))
    return add_cache_headers(response)

@main_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)