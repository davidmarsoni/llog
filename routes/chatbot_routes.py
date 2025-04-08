"""
Chatbot routes for the application
"""
from flask import Blueprint, render_template, request, jsonify, current_app, make_response, Response, stream_with_context, session
from services.llm_service import get_llm_response, get_available_indexes
from services.llm.Agents.QueryResearch import QueryResearch
from services.llm.Agents.Write import Write
from services.llm.Agents.Review import Review
from services.llm.chat import get_query_response_full, get_agent_response_full
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

@chatbot_bp.route('/get-query-response', methods=['POST'])
def get_query_response():
    """Get the response for a specific query."""
    try:
        message = request.form.get('message', '').strip()
        lstMessagesHistory = request.form.getlist('lstMessagesHistory[]')
        creativity = request.form.get('creativity', '50')
        max_tokens = request.form.get('maxToken', '2000')
        useRag = request.form.get('useRag', 'false').lower() == 'true'
        mode = request.form.get('mode', 'files')
        list_of_indexes = request.form.getlist('list_of_indexes[]')
        
        response = get_query_response_full(
            message = message,
            lstMessagesHistory=lstMessagesHistory,
            creativity=creativity,
            max_tokens=max_tokens,
            useRag=useRag,
            mode=mode,
            list_of_indexes=list_of_indexes
        )
        
        # cache evential error
        if response.status_code != 200:
            return jsonify({"error": response.text}), response.status_code
        
        # return the response as JSON
        return jsonify(response.json())
        
    except Exception as e:
        current_app.logger.error(f"Error getting query response: {str(e)}")
        return jsonify({"error": str(e)}), 500
    
@chatbot_bp.route('/get-agent-response', methods=['POST'])
def get_agent_response():
    """Get the response from the agent."""
    try:
        message = request.form.get('message', '').strip()
        lstMessageHistory = request.form.getlist('lstMessagesHistory[]')
        creativity = request.form.get('creativity', '50')
        maxTokens = request.form.get('maxToken', '2000')
        modules = request.form.get('modules', '')
        useRag = request.form.get('useRag', 'false').lower() == 'true'
        mode = request.form.get('mode', 'files')
        list_of_indexes = request.form.getlist('list_of_indexes[]')
        
        print(f"DEBUG : Message: {message}, Modules: {modules}, Use Rag: {useRag}, Mode: {mode}, List of Indexes: {list_of_indexes}")
         
        response = get_agent_response_full(
            message = message,
            lstMessageHistory=lstMessageHistory,
            creativity=creativity,
            maxTokens=maxTokens,
            useRag=useRag,
            modules=modules,
            mode=mode,
            listOfIndexes=list_of_indexes
        )
        
        # return the response as JSON
        print(response)
        return jsonify(response.json())
            
        
    except Exception as e:
        current_app.logger.error(f"Error getting agent response: {str(e)}")
        return jsonify({"error": str(e)}), 500


@chatbot_bp.route('/send-message', methods=['POST'])
def send_message():
    """Process a message and return the chat update."""
    try:
        message = request.form.get('message', '').strip()
        use_content = request.form.get('use_content', 'false').lower() == 'true'
        content_ids = request.form.getlist('content_ids[]')
        agent_type = request.form.get('agent_type', 'llm')  # Default to standard LLM
        
        # Get the response element ID from the form data
        response_element_id = request.form.get('response_element_id', 'ai-response-placeholder')
        
        # Get advanced parameters
        creativity = request.form.get('creativity', '50')
        max_tokens = request.form.get('maxToken', '1000')
        modules = request.form.get('modules', 'default')
        use_rag = request.form.get('useRag', 'false').lower() == 'true'
        
        print(f"DEBUG : Message: {message}, Use Content: {use_content}, Content IDs: {content_ids}, Agent Type: {agent_type}")
        
        if not message:
            return "Please enter a message."
            
        response_content = ""
        
        # Process based on selected response mode
        if agent_type == 'agents':
            # Step 1: Research with QueryResearch agent
            research_agent = QueryResearch(current_app.logger)
            research_results = research_agent.research(message, content_ids if content_ids else None)
            
            # Step 2: Analyze user request to determine content type
            content_type = "answer"  # Default type
            length = "medium"  # Default length
            
            # Special handling for "write a quiz" vs asking to create a quiz
            if message.lower().startswith("write a quiz") or message.lower().startswith("create a quiz"):
                # User wants to write/create a quiz about something
                content_type = "quiz"
                length = "medium"
            # Detect content type from user request
            elif message.strip().endswith("?") or any(q in message.lower() for q in ["what", "how", "why", "when", "where", "who", "can", "could", "would", "should"]):
                content_type = "answer"
                length = "medium"
            elif any(term in message.lower() for q in ["quiz", "quizzes", "multiple choice", "multiple-choice"] for term in [f"about {q}", f"on {q}", f"regarding {q}", f"{q} about", f"{q} on"]):
                # These are phrases about quizzes, not requests to create quizzes
                content_type = "answer" 
                length = "medium"
            elif any(term in message.lower() for term in ["quiz", "quizzes", "test", "multiple choice", "multiple-choice"]):
                content_type = "quiz"
                length = "medium" 
            elif any(term in message.lower() for term in ["summary", "summarize", "summarization", "brief", "overview"]):
                content_type = "summary"
                length = "short"
                
            # Adjust length based on modifiers in the request
            if any(term in message.lower() for term in ["brief", "short", "concise"]):
                length = "short"
            elif any(term in message.lower() for term in ["detailed", "comprehensive", "in-depth", "long"]):
                length = "long"
            
            # Generate content with Write agent
            write_agent = Write(current_app.logger)
            
            # Create write request with appropriate content type
            write_request = {
                "type": content_type,
                "topic": message,
                "length": length
            }
            
            # Add research keywords to the writing request
            if research_results.get('status') == 'success':
                keywords = research_results.get('keywords', [])
                if keywords:
                    write_request["keywords"] = [k["keyword"] for k in keywords[:5]]
            
            write_result = write_agent.write(
                request=write_request,
                use_research=True,
                research_query=message,
                index_ids=content_ids if content_ids else None
            )
            
            # Step 3: Review the content (if not a quiz)
            review_result = None
            if content_type != "quiz" and write_result.get('status') == 'success':
                review_agent = Review(current_app.logger)
                content = write_result.get('content', {})
                content_to_review = content.get('raw_text', '')
                
                if content_to_review:
                    review_result = review_agent.review(
                        content=content_to_review,
                        review_type='comprehensive'
                    )
            
            # Format the response based on content type
            if write_result.get('status') == 'success':
                content = write_result.get('content', {})
                
                if content_type == "answer":
                    response_content = content.get('answer', 'No answer generated.')
                    
                elif content_type == "summary":
                    response_content = f"# {content.get('title', 'Summary')}\n\n"
                    
                    if content.get('key_points'):
                        response_content += "**Key Points:**\n\n"
                        for point in content.get('key_points'):
                            response_content += f"- {point}\n"
                        response_content += "\n"
                    else:
                        response_content += content.get('content', '')
                
                elif content_type == "quiz":
                    quiz = content
                    response_content = f"# {quiz.get('title', 'Quiz')}\n\n"
                    
                    if quiz.get('description'):
                        response_content += f"{quiz.get('description')}\n\n"
                        
                    questions = quiz.get('questions', [])
                    if not questions:
                        response_content += "Sorry, I couldn't generate any quiz questions. Please try again."
                    else:
                        for i, q in enumerate(questions):
                            # Show the question and options
                            response_content += f"## Question {i+1}: {q.get('question')}\n\n"
                            
                            # Add options
                            for option in q.get('options', []):
                                response_content += f"**{option.get('letter')}:** {option.get('text')}\n"
                            
                            # Include the correct answer and explanation directly
                            correct = q.get('correct_answer')
                            explanation = q.get('explanation', '')
                            
                            response_content += f"\n**Correct Answer:** {correct}\n"
                            if explanation:
                                response_content += f"**Explanation:** {explanation}\n"
                            
                            # Add a divider between questions
                            response_content += "\n---\n\n"
                
                else:
                    # Fallback to raw text
                    response_content = content.get('raw_text', 'No content generated')
                
                # Add quality score for non-quiz content that was reviewed
                if review_result and review_result.get('status') == 'success' and content_type != "quiz":
                    review = review_result.get('review', {})
                    if 'overall_score' in review and review['overall_score'] >= 7:
                        # Only add score if it's good
                        response_content += f"\n\n---\n*Quality verified*"
            else:
                response_content = "Sorry, I wasn't able to generate content based on your request."
                
        else:
            # Default: Use standard LLM
            response = get_llm_response(
                query=message,
                use_context=use_content,
                index_ids=content_ids if content_ids else None
            )
            response_content = response.get('answer', 'Sorry, no response was generated.')
        
        # Render the message with a flag to only include AI response
        # This flag will be used in the template to conditionally render parts
        return render_template('components/chat_messages.html',
                            user_message=message,
                            ai_response=response_content)
                             
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