"""
Notion service for handling Notion API operations and caching.
This module provides a simplified interface to the Notion services.
"""
from services.notion import (
    get_notion_client,
    extract_notion_page_title,
    extract_notion_content_as_text,
    download_blob_to_memory,
    cache_notion_page,
    cache_notion_database,
    query_cached_notion
)

# Re-export all the functions for backward compatibility
__all__ = [
    'get_notion_client',
    'extract_notion_page_title',
    'extract_notion_content_as_text',
    'download_blob_to_memory',
    'cache_notion_page',
    'cache_notion_database',
    'query_cached_notion'
]