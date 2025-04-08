"""
LLM chat interaction functionality using LlamaIndex
"""
import os
from typing import Dict, Any, List, Optional, Iterator
from flask import current_app
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
from llama_index.core.chat_engine import ContextChatEngine
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.retrievers import BaseRetriever
from services.llm.Agents.QueryResearch import QueryResearch
from services.llm.Agents.Review import Review
from services.llm.Agents.Write import Write
from services.llm.content import query_content

def get_llm_response(
    query: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    index_ids: Optional[List[str]] = None,
    temperature: float = 0.7,
    use_context: bool = True
) -> Dict[str, Any]:
    """
    Get a response from the LLM using relevant context from indexed content.
    
    Args:
        query (str): The user's query
        chat_history (list, optional): List of previous chat messages
        index_ids (list, optional): Specific index IDs to use for context
        temperature (float): Model temperature setting (0.0 to 1.0)
        use_context (bool): Whether to use indexed content for context
        
    Returns:
        dict: Response containing the LLM's answer and metadata
    """
    try:
        # Initialize chat history if None
        if chat_history is None:
            chat_history = []
            
        # Set up the LLM
        api_key = os.getenv("OPENAI_API_KEY") or current_app.config.get('OPENAI_API_KEY')
        if not api_key:
            return {"error": "OpenAI API key not configured"}
        
        # Initialize the OpenAI LLM
        llm = OpenAI(
            model="gpt-4o-mini",
            temperature=temperature,
            api_key=api_key
        )
        
        # Set LlamaIndex settings
        Settings.llm = llm
        
        # Convert chat history to LlamaIndex format
        llama_chat_history = []
        for message in chat_history:
            role = MessageRole.USER if message.get("role") == "user" else MessageRole.ASSISTANT
            llama_chat_history.append(ChatMessage(role=role, content=message.get("content", "")))
        
        # Create memory buffer with chat history
        memory = ChatMemoryBuffer.from_defaults(chat_history=llama_chat_history)
            
        # If using context, get relevant content from indexes
        context = ""
        retrieved_nodes = []
        if use_context:
            try:
                # Query content for relevant information
                content_results = query_content(
                    query=query,
                    index_ids=index_ids,
                    use_metadata_filtering=True
                )
                
                current_app.logger.info(f"Content results: {content_results}")
                
                # Combine relevant content for context
                relevant_texts = []
                
                # Check if we have successful results
                if content_results and content_results.get("success") and "results" in content_results:
                    for result in content_results.get("results", []):
                        # Get response text from the result
                        response_text = result.get("response", "").strip()
                        if response_text:
                            title = result.get("title", "Unknown")
                            source = f"{title}"
                            relevant_texts.append(f"From {source}:\n{response_text}")
                            
                            # Also add to retrieved_nodes for the retriever
                            from llama_index.core.schema import NodeWithScore, TextNode
                            node = NodeWithScore(
                                node=TextNode(text=response_text, metadata={"source": source}),
                                score=1.0
                            )
                            retrieved_nodes.append(node)
                            
                    if relevant_texts:
                        context = "\n\n".join(relevant_texts)
                        current_app.logger.info(f"Generated context: {context[:100]}...")
            except Exception as e:
                current_app.logger.error(f"Error retrieving context: {str(e)}")
                # Continue without context if there's an error
        
        # Generate response based on whether we have context
        if use_context and context:
            # Create system prompt with context
            system_prompt = f"""You are a helpful AI assistant. Use the following context 
            to help answer the user's question, but also draw on your general knowledge when needed. 
            If the context doesn't contain relevant information, just answer based on what you know.
            
            Context:
            {context}"""
            
            # Create a custom retriever that just returns the nodes we've already retrieved
            class CustomRetriever(BaseRetriever):
                def _retrieve(self, query_str):
                    return retrieved_nodes
                    
            retriever = CustomRetriever()
            
            # Create a context chat engine with the context in the system prompt
            chat_engine = ContextChatEngine.from_defaults(
                system_prompt=system_prompt,
                memory=memory,
                retriever=retriever,
                llm=llm
            )
            
            # Get response
            response = chat_engine.chat(query)
            answer = response.response
        else:
            # Simple query without context
            messages = [ChatMessage(role=MessageRole.USER, content=query)]
            response = llm.chat(messages)
            answer = response.message.content
        
        # Update chat history
        chat_history.append({"role": "user", "content": query})
        chat_history.append({"role": "assistant", "content": answer})
        
        return {
            "answer": answer,
            "chat_history": chat_history,
            "used_context": bool(context if use_context else False)
        }
        
    except Exception as e:
        current_app.logger.error(f"Error getting LLM response: {str(e)}")
        return {"error": str(e)}
 
def get_query_response_full(message,lstMessageHistory,creativity,maxTokens,useRag,mode,listOfIndexes):
    """
    Get a streaming response from the LLM using the provided parameters.
    
    Args:
        message (str): The user's query
        lstMessageHistory (list): List of previous chat messages
        creativity (float): Model temperature setting (0.0 to 1.0)
        maxToken (int): Maximum number of tokens for the response
        useRag (bool): Whether to use RAG for context
        mode (str): Mode of operation (e.g., "chat")
        listOfIndexes (list): List of index IDs to use for context
        
    Yields:
        str: Chunks of the response text if streaming, or the complete response if not streaming
    """
    try:
        # Set up the LLM
        api_key = os.getenv("OPENAI_API_KEY") or current_app.config.get('OPENAI_API_KEY')
        if not api_key:
            yield "Error: OpenAI API key not configured"
            return
        
        # Initialize the OpenAI LLM
        llm = OpenAI(
            model="gpt-4-turbo-preview",
            temperature=creativity,
            max_tokens=maxTokens,
            api_key=api_key
        )
        
        # Set LlamaIndex settings
        Settings.llm = llm
        
        context = getContext(listOfIndexes)
        
        # Create system prompt with context if provided
        if context:
            system_prompt = f"""You are a helpful AI assistant. Use the following context 
            to help answer the user's question, but also draw on your general knowledge when needed. 
            If the context doesn't contain relevant information, just answer based on what you know.
            
            Context:
            {context}"""
        else:
            system_prompt = "You are a helpful AI assistant."
            
        # Create messages lists
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=message)
        ]
        
        response = llm.chat(messages)
        
        yield response.message.content
            
    except Exception as e:
        current_app.logger.error(f"Error in chat response: {str(e)}")
        yield f"Error: {str(e)}"

def getContext(query,listOfIndexes):
    """
    Get context from the specified indexes.
    
    Args:
        listOfIndexes (list): List of index IDs to use for context
        
    Returns:
        str: Combined context from the specified indexes
    """
    try:
        # Query content for relevant information
        content_results = query_content(
            query=query,
            index_ids=listOfIndexes,
            use_metadata_filtering=True
        )
        
        current_app.logger.info(f"Content results: {content_results}")
        
        # Combine relevant content for context
        relevant_texts = []
        
        # Check if we have successful results
        if content_results and content_results.get("success") and "results" in content_results:
            for result in content_results.get("results", []):
                # Get response text from the result
                response_text = result.get("response", "").strip()
                if response_text:
                    title = result.get("title", "Unknown")
                    source = f"{title}"
                    relevant_texts.append(f"From {source}:\n{response_text}")
                    
        if relevant_texts:
            return "\n\n".join(relevant_texts)
        
    except Exception as e:
        current_app.logger.error(f"Error retrieving context: {str(e)}")
    
    return ""


def get_agent_response_full(message,lstMessageHistory,creativity,modules,maxTokens,useRag,mode,listOfIndexes):
    print(f"get_agent_response: {message}, {lstMessageHistory}, {creativity}, {modules}, {maxTokens}, {useRag}, {mode}, {listOfIndexes}")
    # Step 1: Research with QueryResearch agent
    research_agent = QueryResearch(current_app.logger)
    research_results = research_agent.research(message, listOfIndexes if listOfIndexes else None)
    
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
        index_ids=listOfIndexes if listOfIndexes else None
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
    print("==================================")
    print("==================================")
    print("==================================")
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
    