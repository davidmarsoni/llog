"""
Chatbot routes for the application
"""
from flask import Blueprint, render_template, request, jsonify
from services.llm_service import get_llm_response

# Create a Blueprint for chatbot routes
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

@chatbot_bp.route('/')
def chatbot_page():
    """Render the chatbot interface page."""
    return render_template('chatbot.html')

@chatbot_bp.route('/query', methods=['POST'])
def chatbot_query():
    """Process a query to the chatbot and return a response."""
    data = request.json
    query = data.get('query', '')
    
    if not query:
        return jsonify({'response': 'Please provide a query.'})
    
    # Use the LLM service to get a response
    response = get_llm_response(query)
    
    return jsonify({'response': response})