"""
LLM chat interaction functionality using LlamaIndex
"""
import json
import os
import traceback
from flask import current_app
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
from services.llm.agents.review_agent import review_agent
from services.llm.agents.write_agent import write_agent
from services.llm.agents.main_agent_worflow import MainAgentWorflow
from services.llm.agents.query_agent import query_agent
from services.llm.content import query_content
 
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
            model="gpt-4o-mini",
            temperature=creativity,
            max_tokens=maxTokens,
            api_key=api_key
        )
        # Set LlamaIndex settings
        Settings.llm = llm
          # Remove duplicate index IDs to prevent multiple loading of the same index
        # Only attempt to get context if there are indexes provided
        context = ""
        if listOfIndexes and len(listOfIndexes) > 0:
            listOfIndexes = list(set(listOfIndexes))
            current_app.logger.info(f"Using unique index IDs: {listOfIndexes}")
            context = getContext(query=message, listOfIndexes=listOfIndexes)

        # Create system prompt
        system_prompt = (
            "You are a helpful AI assistant. Answer the user's question clearly and concisely. "
            "Use Markdown formatting (like lists, bolding, or code blocks) when it improves readability. "
            "Base your answer on the provided context and your general knowledge. "
            "If asked about your sources, list the titles of the documents you used from the context, but NEVER show the raw context itself."
        )
        if context:
            system_prompt += f"\n\nUse the following context if relevant:\nContext:\n{context}"

        # Create messages list starting with the system prompt
        messages = [ChatMessage(role=MessageRole.SYSTEM, content=system_prompt)]

        # Add message history
        if lstMessageHistory:
            for msg_str in lstMessageHistory:
                try:
                    msg_data = json.loads(msg_str)
                    role = msg_data.get('role', '').lower()
                    content = msg_data.get('content', '')
                    if role == 'user':
                        messages.append(ChatMessage(role=MessageRole.USER, content=content))
                    elif role == 'assistant':
                        messages.append(ChatMessage(role=MessageRole.ASSISTANT, content=content))
                except json.JSONDecodeError:
                    current_app.logger.warning(f"Could not parse message history item: {msg_str}")
                    continue # Skip malformed history items
                except Exception as e:
                    current_app.logger.error(f"Error processing message history item: {e}")
                    continue # Skip problematic history items

        # Add the current user message
        messages.append(ChatMessage(role=MessageRole.USER, content=message))

        response = llm.chat(messages)

        yield response.message.content
            
    except Exception as e:
        current_app.logger.error(f"Error in chat response: {str(e)}")
        yield f"Error: {str(e)}"

def getContext(query, listOfIndexes):
    """
    Get context from the specified indexes.
    
    Args:
        query (str): The query to use for retrieving context
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


async def get_agent_response_full(message,lstMessageHistory,creativity,modules,maxTokens,useRag,mode,listOfIndexes):
    current_app.logger.info("=" * 50)
    current_app.logger.info("AGENT WORKFLOW EXECUTION STARTED")
    current_app.logger.info("=" * 50)
    current_app.logger.info(f"Message: {message[:100]}...")
    current_app.logger.info(f"Parameters: creativity={creativity}, modules={modules}, maxTokens={maxTokens}, useRag={useRag}, mode={mode}")
    current_app.logger.info(f"Message history received: {len(lstMessageHistory) if lstMessageHistory else 0} messages")
    
    # Verify agent availability
    current_app.logger.info(f"Query Agent available: {query_agent is not None}")
    current_app.logger.info(f"Write Agent available: {write_agent is not None}")
    current_app.logger.info(f"Review Agent available: {review_agent is not None}")

    # Remove duplicate index IDs to prevent multiple loading of the same index
    if listOfIndexes:
        listOfIndexes = list(set(listOfIndexes))
        current_app.logger.info(f"Using unique index IDs in agent response: {listOfIndexes}")
    else:
        current_app.logger.info("No indexes provided for context retrieval")
        
    # Process message history if available
    formatted_history = []
    if lstMessageHistory and len(lstMessageHistory) > 0:
        try:
            # Process message history into ChatMessage objects
            for msg_str in lstMessageHistory:
                try:
                    # Each message should be in JSON format with 'role' and 'content'
                    msg_data = json.loads(msg_str)
                    role = msg_data.get('role', '').lower()
                    content = msg_data.get('content', '')
                    
                    if role == 'user':
                        formatted_history.append(ChatMessage(role=MessageRole.USER, content=content))
                    elif role == 'assistant':
                        formatted_history.append(ChatMessage(role=MessageRole.ASSISTANT, content=content))
                except json.JSONDecodeError:
                    current_app.logger.warning(f"Could not parse message history item: {msg_str}")
                    continue
            
            current_app.logger.info(f"Formatted {len(formatted_history)} messages from history")
        except Exception as e:
            current_app.logger.error(f"Error processing message history: {str(e)}")
            formatted_history = []

    try:
        current_app.logger.info("Creating MainAgentWorflow instance...")
        workflow = MainAgentWorflow(timeout=120, verbose=True)
        
        current_app.logger.info("Starting workflow execution...")
        current_app.logger.info("Passing agents to workflow: QueryAgent, WriteAgent, ReviewAgent")
        
        handler = await workflow.run(
            prompt=message,
            query_agent=query_agent,
            write_agent=write_agent,
            review_agent=review_agent,
            index_ids=listOfIndexes,
            message_history=formatted_history,
        )

        current_app.logger.info("Workflow execution completed")
        current_app.logger.info(f"Result type: {type(handler)}")
        
        final_result = handler
        current_app.logger.info("==== The report ====")
        current_app.logger.info(f"Result: {str(final_result)[:100]}...")
        current_app.logger.info("=" * 50)
        
        return final_result
    except Exception as e:
        print(f"Error in agent workflow: {str(e)}")
        print(traceback.format_exc())
        return {"error": str(e)}