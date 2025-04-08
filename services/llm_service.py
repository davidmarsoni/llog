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

__all__ = [
    'refresh_file_index_cache',
    'get_available_indexes',
    'query_content',
    'get_content_metadata',
    'get_recommender_system',
    'get_llm_response'
]