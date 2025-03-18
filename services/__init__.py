"""
Services package for the application.
This package contains service modules for external integrations.
"""

# Keep importing the document_service for backward compatibility
from services.document_service import extract_auto_metadata, process_pdf_file, process_text_file

# Import other services
from services.llm_service import *
from services.notion_service import *
from services.storage_service import *

# Define what's available when using "from services import *"
__all__ = [
    # Document processing functions
    'extract_auto_metadata',
    'process_pdf_file',
    'process_text_file',
    # Other services
    'get_storage_client'
]