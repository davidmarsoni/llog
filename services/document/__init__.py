"""
Document processing package for handling various document formats
"""
from services.document.metadata import extract_auto_metadata
from services.document.pdf import process_pdf_file
from services.document.text import process_text_file

# Export all necessary functions
__all__ = [
    'extract_auto_metadata', 
    'process_pdf_file', 
    'process_text_file'
]