"""
Document processing package for handling various document formats
"""
from services.document.pdf import process_pdf_file
from services.document.text import process_text_file

# Export all necessary functions
__all__ = [
    'process_pdf_file', 
    'process_text_file'
]