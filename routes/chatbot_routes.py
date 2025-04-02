"""
Chatbot routes for the application
"""
from flask import Blueprint, render_template, request, jsonify, current_app, make_response, Response, stream_with_context, session
from services.llm_service import get_llm_response, get_available_indexes, get_streaming_response
from services.llm.Agents.QueryResearch import QueryResearch
from services.llm.Agents.Write import Write
from services.llm.Agents.Review import Review
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

@chatbot_bp.route('/research', methods=['POST'])
def research_query():
    """Process a research query and return structured results."""
    try:
        data = request.get_json()
        
        if not data or 'query' not in data:
            return jsonify({
                "status": "error",
                "message": "No query provided"
            }), 400
            
        query = data.get('query', '').strip()
        index_ids = data.get('index_ids', None)
        
        if not query:
            return jsonify({
                "status": "error",
                "message": "Empty query provided"
            }), 400
            
        # Create research agent and perform research
        research_agent = QueryResearch(current_app.logger)
        results = research_agent.research(query, index_ids)
        
        # Return the structured research results
        return jsonify(results)
        
    except Exception as e:
        current_app.logger.error(f"Error processing research query: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e),
            "query": data.get('query', '') if 'data' in locals() else '',
            "total_results": 0,
            "themes": [],
            "keywords": [],
            "sources": []
        }), 500

@chatbot_bp.route('/write', methods=['POST'])
def write_content():
    """Generate written content using the Write agent."""
    try:
        data = request.get_json()
        
        if not data or 'request' not in data:
            return jsonify({
                "status": "error",
                "message": "No writing request provided"
            }), 400
            
        write_request = data.get('request', {})
        use_research = data.get('use_research', False)
        research_query = data.get('research_query', None)
        index_ids = data.get('index_ids', None)
        
        if not write_request.get('topic'):
            return jsonify({
                "status": "error",
                "message": "No topic provided for writing"
            }), 400
            
        # Create Write agent and generate content
        write_agent = Write(current_app.logger)
        result = write_agent.write(
            request=write_request,
            use_research=use_research,
            research_query=research_query,
            index_ids=index_ids
        )
        
        # Return the generated content
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error processing write request: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@chatbot_bp.route('/review', methods=['POST'])
def review_content():
    """Review content and provide structured feedback using the Review agent."""
    try:
        data = request.get_json()
        
        if not data or 'content' not in data:
            return jsonify({
                "status": "error",
                "message": "No content provided for review"
            }), 400
            
        content = data.get('content', '').strip()
        review_type = data.get('review_type', 'comprehensive')
        criteria = data.get('criteria', None)
        
        if not content:
            return jsonify({
                "status": "error",
                "message": "Empty content provided"
            }), 400
            
        # Create Review agent and analyze content
        review_agent = Review(current_app.logger)
        result = review_agent.review(
            content=content,
            review_type=review_type,
            criteria=criteria
        )
        
        # Return the review results
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"Error processing review request: {str(e)}")
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@chatbot_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)