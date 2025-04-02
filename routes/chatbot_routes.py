"""
Chatbot routes for the application
"""
from flask import Blueprint, render_template, request, jsonify, current_app, make_response
from services.llm_service import get_llm_response, get_available_indexes
import httpx
from services.llm.agent.QueryResearch import QueryResearch
from services.llm.agent.WriteAgent import WriteAgent
from services.llm.agent.ReviewAgent import ReviewAgent

# Create a Blueprint for chatbot routes
chatbot_bp = Blueprint('chatbot', __name__, url_prefix='/chatbot')

USE_AGENTS = True

def add_cache_headers(response):
    """Add cache control headers to response"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@chatbot_bp.route('/')
def chatbot_page():
    """Render the chatbot interface page."""
    # Get available indexes for the chatbot
    indexes = get_available_indexes()
    response = make_response(render_template('chatbot.html', indexes=indexes))
    return add_cache_headers(response)

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
        

        if USE_AGENTS:
            research = QueryResearch().run(query, use_content=use_content, content_ids=content_ids)
            content = WriteAgent().run(research)
            final_output = ReviewAgent().run(content)

            json_response = make_response(jsonify({
                'answer': final_output,
                'used_content': use_content,  # Changed to reflect actual use of content
                'content_ids_used': content_ids if use_content else []
            }))
            return add_cache_headers(json_response)
        else:
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
            except httpx.TimeoutException:
                current_app.logger.error("Request to LLM service timed out")
                return add_cache_headers(make_response(jsonify({
                    'error': "I'm sorry, but the request timed out. Please try again with a shorter query or less context."
                }), 408))
                
            json_response = make_response(jsonify({
                'answer': answer,
                'used_content': used_context,
                'content_ids_used': content_ids if use_content else []
            }))
            return add_cache_headers(json_response)
    
    except Exception as e:
        current_app.logger.error(f"Error in chatbot query: {str(e)}")
        return add_cache_headers(make_response(jsonify({
            'error': f"Sorry, there was an error processing your request: {str(e)}"
        }), 500))

@chatbot_bp.route('/toggle-mode', methods=['POST'])
def toggle_mode():
    global USE_AGENTS
    USE_AGENTS = not USE_AGENTS
    mode = "Agents" if USE_AGENTS else "LLM Direct"
    return jsonify({"mode": mode})

@chatbot_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)