"""
Document processing service for handling various document formats
"""
# Re-export functionality from specialized modules in the document package
from services.document import extract_auto_metadata, process_pdf_file, process_text_file

# Export all necessary functions
__all__ = ['extract_auto_metadata', 'process_pdf_file', 'process_text_file']