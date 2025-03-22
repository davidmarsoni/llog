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

@chatbot_bp.route('/available-indexes')
def available_indexes():
    """Get available indexes for the chatbot."""
    indexes = get_available_indexes()
    response = make_response(jsonify({'indexes': indexes}))
    return add_cache_headers(response)

@chatbot_bp.route('/query', methods=['POST'])
def chatbot_query():
    """Process a query to the chatbot and return a response."""
    try:
        data = request.json
        query = data.get('query', '')
        use_content = data.get('use_content', False)
        content_ids = data.get('content_ids', [])
        chat_history = data.get('chat_history', [])
        
        if not query:
            response = make_response(jsonify({'response': 'Please provide a query.'}))
            return add_cache_headers(response)
        
        # Log the query details
        current_app.logger.info(f"Chatbot query: {query}")
        if use_content:
            current_app.logger.info(f"Using indexed content: {content_ids if content_ids else 'all available'}")
        
        # Use the LLM service to get a response with appropriate context
        try:
            # Call the get_llm_response function with proper parameters
            llm_response = get_llm_response(
                query=query,
                chat_history=chat_history,
                index_ids=content_ids if content_ids else None,
                use_context=use_content
            )
            
            # Handle different response formats
            if "error" in llm_response:
                return add_cache_headers(make_response(jsonify({
                    'error': llm_response["error"]
                }), 500))
            
            # Extract the answer from the response
            answer = llm_response.get("answer", "Sorry, no response was generated.")
            used_context = llm_response.get("used_context", False)
            
            json_response = make_response(jsonify({
                'answer': answer,
                'used_content': used_context,
                'content_ids_used': content_ids if use_content else []
            }))
            return add_cache_headers(json_response)
            
        except httpx.TimeoutException:
            current_app.logger.error("Request to LLM service timed out")
            return add_cache_headers(make_response(jsonify({
                'error': "I'm sorry, but the request timed out. Please try again with a shorter query or less context."
            }), 408))
    
    except Exception as e:
        current_app.logger.error(f"Error in chatbot query: {str(e)}")
        return add_cache_headers(make_response(jsonify({
            'error': f"Sorry, there was an error processing your request: {str(e)}"
        }), 500))

@chatbot_bp.route("/stream-response", methods=["POST"])
def stream_response():
    """Stream the AI response word by word for real-time feedback"""
    try:
        data = request.json
        query = data.get('query', '')
        use_content = data.get('use_content', False)
        content_ids = data.get('content_ids', [])
        
        def generate():
            # Initial response header
            yield "event: start\ndata: {}\n\n"
            
            try:
                # Get response from LLM service
                response_stream = get_streaming_response(query, use_content, content_ids)
                
                # Stream each word/chunk
                for chunk in response_stream:
                    yield f"data: {json.dumps({'text': chunk})}\n\n"
                    
                # End of response
                yield "event: end\ndata: {}\n\n"
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
        
    except Exception as e:
        current_app.logger.error(f"Error in stream_response: {str(e)}")
        return jsonify({"error": str(e)}), 500

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