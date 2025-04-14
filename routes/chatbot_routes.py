"""
Chatbot routes for the application
"""
import asyncio
import nest_asyncio
from flask import Blueprint, render_template, request, jsonify, current_app, make_response, Response, stream_with_context, session
from services.llm_service import get_available_indexes
from services.llm.chat import get_query_response_full, get_agent_response_full
    
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

@chatbot_bp.route('/get-query-response', methods=['POST'])
def get_query_response():
    """Get the response for a specific query."""
    try:
        message = request.form.get('message', '').strip()
        lstMessageHistory = request.form.getlist('lstMessagesHistory[]')
        temperature = request.form.get('temperature', '1')
        max_tokens = request.form.get('maxToken', '2000')
        useRag = request.form.get('useRag', 'false').lower() == 'true'
        mode = request.form.get('mode', 'files')
        listOfIndexes = request.form.getlist('listOfIndexes[]')
        
        # Get query response (it returns a generator)
        response_generator = get_query_response_full(
            message = message,
            lstMessageHistory=lstMessageHistory,
            temperature=temperature,
            maxTokens=max_tokens,
            useRag=useRag,
            mode=mode,
            listOfIndexes=listOfIndexes
        )

        # Set a type of response for processing
        response_type = "AI"
        
        # Collect the generated response content
        response_content = ""
        for chunk in response_generator:
            if chunk:
                response_content += chunk

        # If the response is empty, set a default message
        if not response_content in response_content:
            response_content = "Sorry, I couldn't find an answer to your question. Please try again."
        
        # If the response is an error message, set it as the response content
        if response_content.startswith("Error"):
            response_content = f"There was an error processing your request: \n{response_content.split('Error:')[-1]}"
            response_type = "Error"
            
        
        # Return the complete response as JSON
        #return jsonify({"response": response_content})
        return render_template('components/chat_messages.html',
                             user_message=message,
                             ai_response=response_content,
                             response_type=response_type,
                             ai_only=True,
                             response_element_id=1)  # Pass the response element ID to the template
        
    except Exception as e:
        current_app.logger.error(f"Error getting query response: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@chatbot_bp.route('/get-agent-response', methods=['POST'])
def get_agent_response():
    """Get the response from the agent."""
    try:
        message = request.form.get('message', '').strip()
        lstMessageHistory = request.form.getlist('lstMessagesHistory[]')
        temperature = request.form.get('temperature', '1')
        maxTokens = request.form.get('maxToken', '2000')
        modules = request.form.get('modules', '')
        useRag = request.form.get('useRag', 'false').lower() == 'true'
        mode = request.form.get('mode', 'files')
        listOfIndexes = request.form.getlist('listOfIndexes[]')
        
        print(f"DEBUG get_agent_response : Message: {message},lstMessageHistory: {lstMessageHistory}, temperature: {temperature}, maxTokens: {maxTokens}, useRag: {useRag}, modules: {modules}, mode: {mode}, listOfIndexes: {listOfIndexes}")

        # Apply nest_asyncio to allow nested event loops
        nest_asyncio.apply()
        
        # Run the async function in the current event loop if possible
        try:
            # Try to get the current event loop
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If there's no current event loop, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
              # Define and run the async function
        async def run_async_function():
            return await get_agent_response_full(
                message=message,
                lstMessageHistory=lstMessageHistory,
                temperature=temperature,
                maxTokens=maxTokens,
                useRag=useRag,
                modules=modules,
                mode=mode,
                listOfIndexes=listOfIndexes
            )
        
        # Run the function in the event loop
        response_generator = loop.run_until_complete(run_async_function())

        # Collect the generated response content
        response_content = ""
        for chunk in response_generator:
            if chunk:
                response_content += chunk

        # Set a type of response for processing
        response_type = "AI"

        # If the response is empty, set a default message
        if not response_content:
            response_content = "Sorry, I couldn't find an answer to your question. Please try again."

        # If the response is an error message, set it as the response content
        if response_content.startswith("Error"):
            response_content = f"There was an error processing your request: {response_content.split('Error: \n')[-1]}"
            response_type = "Error"

        # return the response as JSON
        print("=== End of get_agent_response ===") 
        print(response_content)
        #return jsonify(response)
        return render_template('components/chat_messages.html',
                             user_message=message,
                             ai_response=response_content,
                             response_type=response_type,
                             ai_only=True,
                             response_element_id=1)  # Pass the response element ID to the template
            
        
    except Exception as e:
        current_app.logger.error(f"Error getting agent response: {str(e)}")
        return jsonify({"error": str(e)}), 500


@chatbot_bp.after_request
def after_request(response):
    """Add cache headers after each request"""
    return add_cache_headers(response)