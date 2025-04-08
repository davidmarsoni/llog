"""
Reviewing Agent - Specialized agent for content analysis and feedback
"""
from flask import current_app
from typing import Dict, Any, Optional
import re
import json
from services.llm.chat import get_llm_response

class ReviewingAgent:
    """
    Reviewing Agent that specializes in evaluating content:
    - Quality assessment and feedback
    - Fact-checking and accuracy verification
    - Style and tone evaluation
    - Improvement suggestions
    """
    
    def __init__(self, logger=None):
        """Initialize the reviewing agent with optional custom logger"""
        self.logger = logger or current_app.logger
    
    def execute(self, instruction: str) -> str:
        """
        Execute a reviewing task based on the instruction
        
        Args:
            instruction: Specific instruction for the reviewing task
            
        Returns:
            The review feedback as text
        """
        print(f"\n======= ReviewingAgent START =======")
        print(f"Review task: {instruction[:100]}...")
        self.logger.info(f"Executing review task: {instruction[:100]}...")
        
        try:
            # Format the instruction to extract content to review if present
            content_to_review, review_instruction = self._parse_instruction(instruction)
            
            # Construct the review prompt based on what we need to review
            if content_to_review:
                review_prompt = f"""You are a professional content reviewer. Analyze and provide feedback on this content:

CONTENT TO REVIEW:
'''
{content_to_review}
'''

REVIEW INSTRUCTIONS: {review_instruction}

Provide specific, constructive feedback focusing on:
1. Content quality - Accuracy, clarity, and relevance
2. Organization - Structure, flow, and logical progression
3. Style and tone - Appropriateness for the intended audience
4. Specific improvements - Clear suggestions for enhancement

Format your review as constructive feedback with clear sections.
"""
            else:
                # No content provided, just instructions for the review
                review_prompt = f"""You are a professional content reviewer. Provide a framework for reviewing based on this instruction:

REVIEW INSTRUCTIONS: {instruction}

Outline a detailed approach to reviewing the content, including:
1. Key elements to look for
2. Important criteria to evaluate
3. Recommended improvements to suggest

Format your response as a structured review framework.
"""
            
            # Get the review from LLM
            response = get_llm_response(
                query=review_prompt,
                use_context=False
            )
            
            review = response.get("answer", "")
            
            print(f"Generated review (first 150 chars): {review[:150]}...")
            print("======= ReviewingAgent COMPLETE =======\n")
            self.logger.info(f"Review task complete. Generated {len(review)} chars")
            
            return review
        
        except Exception as e:
            self.logger.error(f"Error in review task: {str(e)}")
            print(f"Error in review task: {str(e)}")
            print("======= ReviewingAgent ERROR =======\n")
            return f"Error generating review: {str(e)}"
    
    def _parse_instruction(self, instruction: str) -> tuple:
        """
        Parse the instruction to separate content to review from instructions
        
        Args:
            instruction: The combined instruction string
            
        Returns:
            Tuple of (content_to_review, review_instruction)
        """
        # Look for content enclosed in triple backticks, triple quotes, or specific markers
        content_markers = [
            (r'```(.*?)```', r'```.*?```'),
            (r'"""(.*?)"""', r'""".*?"""'),
            (r"'''(.*?)'''", r"'''.*?'''"),
            (r'CONTENT:(.*?)ENDCONTENT', r'CONTENT:.*?ENDCONTENT'),
            (r'<content>(.*?)</content>', r'<content>.*?</content>')
        ]
        
        content_to_review = None
        review_instruction = instruction
        
        for marker_pattern, replace_pattern in content_markers:
            match = re.search(marker_pattern, instruction, re.DOTALL)
            if match:
                content_to_review = match.group(1).strip()
                review_instruction = re.sub(replace_pattern, '', instruction, flags=re.DOTALL).strip()
                break
        
        return content_to_review, review_instruction