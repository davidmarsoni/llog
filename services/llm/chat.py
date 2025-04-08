"""
LLM chat interaction functionality using LlamaIndex
"""
import os
from flask import current_app
from llama_index.core.llms import ChatMessage, MessageRole
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
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
            model="gpt-4-turbo-preview",
            temperature=creativity,
            max_tokens=maxTokens,
            api_key=api_key
        )
          # Set LlamaIndex settings
        Settings.llm = llm
        
        context = getContext(query=message, listOfIndexes=listOfIndexes)
        
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
    print(f"get_agent_response: {message}, {lstMessageHistory}, {creativity}, {modules}, {maxTokens}, {useRag}, {mode}, {listOfIndexes}")

    try:
        workflow = MainAgentWorflow(timeout=120, verbose=True)
        handler = await workflow.run(
            prompt=message,
            query_agent=query_agent,
            index_ids=listOfIndexes,  # Pass the list of indexes to the workflow
        )

        final_result = handler
        print("==== The report ====")
        print(final_result)
        
        return final_result
    except Exception as e:
        import traceback
        print(f"Error in agent workflow: {str(e)}")
        print(traceback.format_exc())
        return {"error": str(e)}