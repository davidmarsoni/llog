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

def get_chat_response(
    query: str,
    context: Optional[str] = None,
    stream: bool = False,
    temperature: float = 0.7
) -> Iterator[str]:
    """
    Get a streaming response from the LLM.
    
    Args:
        query (str): The user's query
        context (str, optional): Context to use for the response
        stream (bool): Whether to stream the response
        temperature (float): Model temperature setting (0.0 to 1.0)
        
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
            temperature=temperature,
            api_key=api_key
        )
        
        # Set LlamaIndex settings
        Settings.llm = llm
        
        # Create system prompt with context if provided
        if context:
            system_prompt = f"""You are a helpful AI assistant. Use the following context 
            to help answer the user's question, but also draw on your general knowledge when needed. 
            If the context doesn't contain relevant information, just answer based on what you know.
            
            Context:
            {context}"""
        else:
            system_prompt = "You are a helpful AI assistant."
            
        # Create messages list
        messages = [
            ChatMessage(role=MessageRole.SYSTEM, content=system_prompt),
            ChatMessage(role=MessageRole.USER, content=query)
        ]
        
        if stream:
            # Stream the response
            response_iter = llm.stream_chat(messages)
            for chunk in response_iter:
                if chunk.delta and chunk.delta.content:
                    yield chunk.delta.content
        else:
            # Get complete response
            response = llm.chat(messages)
            yield response.message.content
            
    except Exception as e:
        current_app.logger.error(f"Error in chat response: {str(e)}")
        yield f"Error: {str(e)}"