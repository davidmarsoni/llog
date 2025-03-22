"""
LLM service for handling interactions with language models and related functionality.
This module re-exports the core functionality from the modular llm package.
"""

from flask import current_app
from services.llm import (
    refresh_file_index_cache,
    get_available_indexes,
    query_content,
    get_content_metadata,
    get_recommender_system,
    get_llm_response
)

# Add a global flag to track loading state
_cache_loading = False

def is_cache_loading():
    """Check if the cache is currently being loaded or refreshed."""
    global _cache_loading
    return _cache_loading

def get_available_indexes(folder_path=None):
    """Get all available cached content indexes."""
    global _cache_loading
    if _cache_loading:
        # If already loading, return empty list to prevent duplicate loading
        return []
    try:
        _cache_loading = True
        from services.llm.cache import get_available_indexes as get_indexes
        indexes = get_indexes(folder_path)
        return indexes if indexes is not None else []
    except Exception as e:
        current_app.logger.error(f"Error in llm_service.get_available_indexes: {str(e)}")
        return []
    finally:
        _cache_loading = False

def get_streaming_response(query, use_content=False, content_ids=None):
    """Get streaming response from the LLM service.
    
    Args:
        query (str): The user's query
        use_content (bool): Whether to use indexed content for context
        content_ids (list): List of specific content IDs to use
        
    Yields:
        str: Chunks of the response text
    """
    try:
        # Import necessary modules
        from services.llm.chat import get_chat_response
        from services.llm.content import get_content_context
        
        # Get content context if needed
        context = None
        if use_content:
            try:
                context = get_content_context(query, content_ids) if content_ids else get_content_context(query)
            except Exception as e:
                current_app.logger.error(f"Error getting content context: {str(e)}")
                yield "Error: Could not retrieve content context. "
                return
        
        # Get streaming response from chat service
        for chunk in get_chat_response(query, context=context, stream=True):
            yield chunk
            
    except Exception as e:
        current_app.logger.error(f"Error in streaming response: {str(e)}")
        yield f"Error: {str(e)}"

__all__ = [
    'refresh_file_index_cache',
    'get_available_indexes',
    'query_content',
    'get_content_metadata',
    'get_recommender_system',
    'get_llm_response',
    'get_streaming_response'
]