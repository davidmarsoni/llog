"""
Chatbot routes for the application
"""
from flask import Blueprint, render_template, request, jsonify, current_app, make_response
from services.llm_service import get_llm_response, get_available_notion_indexes

# Create a Blueprint for chatbot routes
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@chatbot_bp.route('/')
def chatbot_page():
    """Render the chatbot interface page."""
    # Get available Notion indexes for the UI to display
    notion_indexes = get_available_notion_indexes()
    response = make_response(render_template('chatbot.html', notion_indexes=notion_indexes))
    return add_cache_headers(response)

@chatbot_bp.route('/available-indexes')
def available_indexes():
    """Get available Notion indexes as JSON."""
    notion_indexes = get_available_notion_indexes()
    response = make_response(jsonify({'indexes': notion_indexes}))
    return add_cache_headers(response)

@chatbot_bp.route('/query', methods=['POST'])
def chatbot_query():
    """Process a query to the chatbot and return a response."""
    data = request.json
    query = data.get('query', '')
    use_notion = data.get('use_notion', False)
    notion_ids = data.get('notion_ids', [])
    chat_history = data.get('chat_history', [])
    
    if not query:
        response = make_response(jsonify({'response': 'Please provide a query.'}))
        return add_cache_headers(response)
    
    # Prepare context for the LLM
    context = {
        'use_notion': use_notion,
        'notion_ids': notion_ids,
        'chat_history': chat_history
    }
    
    # Log the query details
    current_app.logger.info(f"Chatbot query: {query}")
    if use_notion:
        current_app.logger.info(f"Using Notion content: {notion_ids if notion_ids else 'all available'}")
    
    # Use the LLM service to get a response with appropriate context
    response = get_llm_response(query, context)
    
    json_response = make_response(jsonify({
        'response': response,
        'used_notion': use_notion,
        'notion_ids_used': notion_ids if use_notion else []
    }))
    return add_cache_headers(json_response)

@chatbot_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)