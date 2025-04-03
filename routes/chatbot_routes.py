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
        
        # Get the response element ID from the form data
        response_element_id = request.form.get('response_element_id', 'ai-response-placeholder')
        
        # Get advanced parameters
        creativity = request.form.get('creativity', '50')
        max_tokens = request.form.get('maxToken', '1000')
        modules = request.form.get('modules', 'default')
        use_rag = request.form.get('useRag', 'false').lower() == 'true'
        
        if not message:
            return "Please enter a message."
            
        # Get response from LLM
        response = get_llm_response(
            query=message,
            use_context=use_content,
            index_ids=content_ids if content_ids else None#,
            # Pass advanced parameters
            #creativity=int(creativity),
            #max_tokens=int(max_tokens),
            #modules=modules,
            #use_rag=use_rag
        )
        
        # Render the message with a flag to only include AI response
        # This flag will be used in the template to conditionally render parts
        return render_template('components/chat_messages.html',
                             user_message=message,
                             ai_response=response.get('answer', 'Sorry, no response was generated.'),
                             ai_only=True,
                             response_element_id=response_element_id)  # Pass the response element ID to the template
                             
    except Exception as e:
        current_app.logger.error(f"Error processing message: {str(e)}")
        return f"Error: {str(e)}"

@chatbot_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)