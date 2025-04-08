"""
Structural Agent - Specialized agent for formatting and organizing content
"""
from flask import current_app
from typing import Dict, Any, Optional
import re
from services.llm.chat import get_llm_response

class StructuralAgent:
    """
    Structural Agent that specializes in organizing and formatting content:
    - Creating clear document structures
    - Formatting content for readability
    - Enhancing layout and organization
    - Converting between different formats
    """
    
    def __init__(self, logger=None):
        """Initialize the structural agent with optional custom logger"""
        self.logger = logger or current_app.logger
    
    def execute(self, instruction: str) -> str:
        """
        Execute a structural formatting task based on the instruction
        
        Args:
            instruction: Specific instruction for the formatting task
            
        Returns:
            The structured content as text
        """
        print(f"\n======= StructuralAgent START =======")
        print(f"Structure task: {instruction[:100]}...")
        self.logger.info(f"Executing structure task: {instruction[:100]}...")
        
        try:
            # Format the instruction to extract content to structure if present
            content_to_structure, structure_instruction = self._parse_instruction(instruction)
            
            # Construct the formatting prompt based on what we need to structure
            if content_to_structure:
                structure_prompt = f"""You are a professional document formatter and organizer. Format and structure this content:

CONTENT TO STRUCTURE:
'''
{content_to_structure}
'''

STRUCTURE INSTRUCTIONS: {structure_instruction}

Focus on:
1. Creating a clear, logical structure with appropriate headings and sections
2. Formatting text for readability (lists, paragraphs, emphasis)
3. Ensuring consistency in style and organization
4. Optimizing the flow and presentation of information

Provide only the structured content, with no explanations or meta-commentary.
"""
            else:
                # No content provided, just create a structure template
                structure_prompt = f"""You are a professional document formatter and organizer. Create a document structure based on this instruction:

STRUCTURE INSTRUCTIONS: {instruction}

Design a clear, logical document structure that includes:
1. Appropriate section headings and organization
2. Placeholder text indicating what content should go in each section
3. Formatting guidelines for the document

Provide a complete, ready-to-use structure that addresses the instructions.
"""
            
            # Get the structured content from LLM
            response = get_llm_response(
                query=structure_prompt,
                use_context=False
            )
            
            structured_content = response.get("answer", "")
            
            # Clean up the content 
            structured_content = self._clean_content(structured_content)
            
            print(f"Generated structure (first 150 chars): {structured_content[:150]}...")
            print("======= StructuralAgent COMPLETE =======\n")
            self.logger.info(f"Structure task complete. Generated {len(structured_content)} chars")
            
            return structured_content
        
        except Exception as e:
            self.logger.error(f"Error in structure task: {str(e)}")
            print(f"Error in structure task: {str(e)}")
            print("======= StructuralAgent ERROR =======\n")
            return f"Error structuring content: {str(e)}"
    
    def _parse_instruction(self, instruction: str) -> tuple:
        """
        Parse the instruction to separate content to structure from instructions
        
        Args:
            instruction: The combined instruction string
            
        Returns:
            Tuple of (content_to_structure, structure_instruction)
        """
        # Look for content enclosed in triple backticks, triple quotes, or specific markers
        content_markers = [
            (r'```(.*?)```', r'```.*?```'),
            (r'"""(.*?)"""', r'""".*?"""'),
            (r"'''(.*?)'''", r"'''.*?'''"),
            (r'CONTENT:(.*?)ENDCONTENT', r'CONTENT:.*?ENDCONTENT'),
            (r'<content>(.*?)</content>', r'<content>.*?</content>')
        ]
        
        content_to_structure = None
        structure_instruction = instruction
        
        for marker_pattern, replace_pattern in content_markers:
            match = re.search(marker_pattern, instruction, re.DOTALL)
            if match:
                content_to_structure = match.group(1).strip()
                structure_instruction = re.sub(replace_pattern, '', instruction, flags=re.DOTALL).strip()
                break
        
        return content_to_structure, structure_instruction
    
    def _clean_content(self, content: str) -> str:
        """
        Clean up generated content by removing meta-commentary
        
        Args:
            content: The raw content from the LLM
            
        Returns:
            Cleaned content
        """
        # Remove phrases like "Here's the structured content:" at the beginning
        content = re.sub(r'^(Here\'s|Here is).*?:\s*', '', content)
        
        # Remove any "I hope this helps" or similar at the end
        content = re.sub(r'(I hope this (helps|is helpful|meets your needs)|Let me know if you need.*?)$', '', content)
        
        # Clean up any excess whitespace
        content = re.sub(r'\n{3,}', '\n\n', content.strip())
        
        return content