"""
Shared utility functions for file routes
"""

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

def send_htmx_response(success, message, content=None):
    """Helper function to send consistent HTMX responses"""
    from flask import jsonify
    response = {
        'success': success,
        'message': message
    }
    if content:
        response.update(content)
    return jsonify(response)