"""
LLM service for handling interactions with language models and related functionality.
This module re-exports the core functionality from the modular llm package.
"""

from services.llm import (
    refresh_file_index_cache,
    get_available_indexes,
    query_content,
    get_content_metadata,
    get_recommender_system,
    get_llm_response
)

__all__ = [
    'refresh_file_index_cache',
    'get_available_indexes',
    'query_content',
    'get_content_metadata',
    'get_recommender_system',
    'get_llm_response'
]