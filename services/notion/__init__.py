"""
Notion service for handling Notion API operations and caching.
This module provides functions to interact with Notion API and cache the results.
"""
from services.notion.utils import (
    get_notion_client,
    extract_notion_page_title,
    extract_notion_content_as_text,
    download_blob_to_memory
)

from services.notion.cache import (
    cache_notion_page,
    cache_notion_database,
    query_cached_notion
)

__all__ = [
    'get_notion_client',
    'extract_notion_page_title',
    'extract_notion_content_as_text',
    'download_blob_to_memory',
    'cache_notion_page',
    'cache_notion_database',
    'query_cached_notion'
]