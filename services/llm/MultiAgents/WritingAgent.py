"""
Writing Agent - Specialized agent for content creation
"""
from flask import current_app
from typing import Dict, Any, Optional
import re
from services.llm.chat import get_llm_response

class WritingAgent:
    """
    Writing Agent that specializes in generating various types of content:
    - Articles and blog posts
    - Summaries and briefs
    - Creative content and ideas
    - Explanations and educational content
    """
    
    def __init__(self, logger=None):
        """Initialize the writing agent with optional custom logger"""
        self.logger = logger or current_app.logger
    
    def execute(self, instruction: str) -> str:
        """
        Execute a writing task based on the instruction
        
        Args:
            instruction: Specific instruction for the writing task
            
        Returns:
            The generated content as text
        """
        print(f"\n======= WritingAgent START =======")
        print(f"Writing task: {instruction[:100]}...")
        self.logger.info(f"Executing writing task: {instruction[:100]}...")
        
        try:
            # Analyze the writing instruction to determine the best approach
            writing_prompt = f"""You are a professional content creator. Write content based on this instruction:

INSTRUCTION: {instruction}

Focus on creating markdown-formatted content that is clear, engaging, and informative.

Provide only the content itself, with no explanations or meta-commentary.
"""
            
            # Get the written content from LLM
            response = get_llm_response(
                query=writing_prompt,
                use_context=False
            )
            
            content = response.get("answer", "")
            
            # Clean up the content (remove any meta commentary)
            content = self._clean_content(content)
            
            print(f"Generated content (first 150 chars): {content[:150]}...")
            print("======= WritingAgent COMPLETE =======\n")
            self.logger.info(f"Writing task complete. Generated {len(content)} chars")
            
            return content
        
        except Exception as e:
            self.logger.error(f"Error in writing task: {str(e)}")
            print(f"Error in writing task: {str(e)}")
            print("======= WritingAgent ERROR =======\n")
            return f"Error generating content: {str(e)}"
    
    def _clean_content(self, content: str) -> str:
        """
        Clean up generated content by removing meta-commentary
        
        Args:
            content: The raw content from the LLM
            
        Returns:
            Cleaned content
        """
        # Remove phrases like "Here's the content:" at the beginning
        content = re.sub(r'^(Here\'s|Here is).*?:\s*', '', content)
        
        # Remove any "I hope this helps" or similar at the end
        content = re.sub(r'(I hope this (helps|is helpful|meets your needs)|Let me know if you need.*?)$', '', content)
        
        # Clean up any excess whitespace
        content = re.sub(r'\n{3,}', '\n\n', content.strip())
        
        return content