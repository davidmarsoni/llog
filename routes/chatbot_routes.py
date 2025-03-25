"""
Chatbot routes for the application
"""
from flask import Blueprint, render_template, request, jsonify, current_app, make_response, Response, stream_with_context, session
from services.llm_service import get_llm_response, get_available_indexes, get_streaming_response
import httpx
import json

# Create a Blueprint for chatbot routes
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@chatbot_bp.route('/')

@chatbot_bp.route('/chat')
def chatbot_page():
    """Render the chatbot interface page."""
    try:
        # Get available indexes for the chatbot
        indexes = get_available_indexes()
        response = make_response(render_template('chatbot.html', 
                                               indexes=indexes,
                                               messages=[]))  # Initialize empty messages
        return add_cache_headers(response)
    except Exception as e:
        current_app.logger.error(f"Error accessing chatbot page: {str(e)}")
        return make_response(jsonify({"error": str(e)}), 500)

@chatbot_bp.route('/check-message-length')
def check_message_length():
    """Check the current message length."""
    message = request.args.get('message', '')
    length = len(message)
    max_length = 2000
    return f"{length}/{max_length}"

@chatbot_bp.route('/send-message', methods=['POST'])
def send_message():
    """Process a message and return the chat update."""
    try:
        message = request.form.get('message', '').strip()
        use_content = request.form.get('use_content', 'false').lower() == 'true'
        content_ids = request.form.getlist('content_ids[]')
        
        if not message:
            return "Please enter a message."
            
        # Get response from LLM
        response = get_llm_response(
            query=message,
            use_context=use_content,
            index_ids=content_ids if content_ids else None
        )
        
        # Render the message pair template
        return render_template('components/chat_messages.html',
                             user_message=message,
                             ai_response=response.get('answer', 'Sorry, no response was generated.'))
                             
    except Exception as e:
        current_app.logger.error(f"Error processing message: {str(e)}")
        return f"Error: {str(e)}"

@chatbot_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)