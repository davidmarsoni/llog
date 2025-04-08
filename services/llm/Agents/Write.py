"""
Write Agent for generating structured content for questions, summaries, and quizzes
"""
from flask import current_app
import os
from typing import List, Dict, Any, Optional
import logging
import re
from services.llm.chat import get_llm_response
from services.llm.content import query_content

class Write:
    """
    Write agent that generates content for specific use cases:
    - Answering questions
    - Creating concise summaries
    - Generating interactive quizzes
    """
    
    def __init__(self, logger=None):
        """Initialize the write agent with optional custom logger"""
        self.logger = logger or current_app.logger
        self.formats = {
            "answer": self._format_answer,
            "summary": self._format_summary,
            "quiz": self._format_quiz
        }
    
    def _format_answer(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as a direct answer to a question"""
        return {
            "type": "answer",
            "question": content.get("title", ""),
            "answer": content.get("content", ""),
            "sources": content.get("sources", [])
        }
    
    def _format_summary(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as a concise summary"""
        # Extract key points from the content if present
        key_points = []
        content_text = content.get("content", "")
        
        # Look for bullet points or numbered lists
        matches = re.findall(r'(?m)^[\*\-\d\.\•]\s+(.+)$', content_text)
        if matches:
            key_points = matches
        
        return {
            "type": "summary",
            "title": content.get("title", "Summary"),
            "content": content_text,
            "key_points": key_points
        }
    
    def _format_quiz(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as an interactive quiz"""
        quiz = {
            "type": "quiz",
            "title": content.get("title", "Quiz"),
            "description": "",
            "questions": []
        }
        
        # Process the content to extract questions
        content_text = content.get("content", "")
        
        # Extract description (first paragraph)
        desc_match = re.search(r'^(.*?)(?=\n\s*\n|\n\s*#)', content_text, re.DOTALL)
        if desc_match:
            quiz["description"] = desc_match.group(1).strip()
        
        # Look for questions in the format "Q1: Question text"
        # and answers in the format "A: Answer text" or "Option A: Text"
        question_blocks = re.split(r'(?m)^(?:Q|Question|#)[\s\d\.:]+', content_text)
        
        for block in question_blocks[1:]:  # Skip the first split which is usually intro text
            question_match = re.search(r'^(.*?)(?=\n\s*(?:A|Option|Answer|Correct|Explanation)|\Z)', block, re.DOTALL)
            if question_match:
                question_text = question_match.group(1).strip()
                
                # Look for options/answers
                options = []
                correct_answer = None
                explanation = ""
                
                # Find options (A, B, C, D) or (1, 2, 3, 4)
                option_matches = re.findall(r'(?m)^(?:Option\s+)?([A-D\d])[\s\.:]+(.+)$', block)
                for opt_letter, opt_text in option_matches:
                    options.append({"letter": opt_letter, "text": opt_text.strip()})
                
                # Find correct answer and explanation
                correct_match = re.search(r'(?:Correct|Answer)[^\n]*?[:\s]\s*([A-D\d])', block)
                if correct_match:
                    correct_answer = correct_match.group(1)
                
                explanation_match = re.search(r'(?:Explanation|Reason)[^\n]*?[:\s]\s*(.+?)(?=\n\s*$|\Z)', block, re.DOTALL)
                if explanation_match:
                    explanation = explanation_match.group(1).strip()
                
                # Add question to quiz
                quiz["questions"].append({
                    "question": question_text,
                    "options": options,
                    "correct_answer": correct_answer,
                    "explanation": explanation
                })
        
        return quiz
    
    def _prepare_prompt(self, request: Dict[str, Any]) -> str:
        """
        Prepare a prompt for the LLM based on the writing request
        
        Args:
            request (Dict[str, Any]): The writing request parameters
            
        Returns:
            str: Formatted prompt for the LLM
        """
        content_type = request.get("type", "answer").lower()
        topic = request.get("topic", "")
        keywords = request.get("keywords", [])
        length = request.get("length", "medium")
        
        # Map length to word count expectations
        length_map = {
            "very short": "50-100 words",
            "short": "100-200 words",
            "medium": "200-400 words",
            "long": "500-800 words"
        }
        word_count = length_map.get(length.lower(), "200-400 words")
        
        # Customize prompt based on content type
        if content_type == "answer":
            prompt = f"""Answer the following question concisely: "{topic}"

Details:
- Keep it brief: {word_count}
- Focus on accuracy and clarity
- Use factual information
- Keywords to include: {', '.join(keywords) if keywords else 'None specified'}

Your answer should be direct and informative."""

        elif content_type == "summary":
            prompt = f"""Create a concise summary of '{topic}'.

Details:
- Keep it brief: {word_count}
- Focus on key points only
- Avoid unnecessary details
- Keywords to include: {', '.join(keywords) if keywords else 'None specified'}

Format your summary with bullet points for key takeaways."""

        elif content_type == "quiz":
            prompt = f"""Create an interactive quiz about '{topic}'.

Generate {3 if length == 'short' else (5 if length == 'medium' else 8)} multiple-choice questions.

For each question:
1. Write a clear question
2. Provide 4 options (label them A, B, C, D)
3. Indicate the correct answer
4. Include a brief explanation for the correct answer

Format each question as:
Question 1: [Question text]
Option A: [Option text]
Option B: [Option text]
Option C: [Option text]
Option D: [Option text]
Correct Answer: [Letter]
Explanation: [Brief explanation]

Start with a brief introduction to the quiz topic."""

        return prompt
    
    def write(self, 
              request: Dict[str, Any], 
              use_research: bool = False, 
              research_query: Optional[str] = None,
              index_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        print("\n======= Write AGENT START =======")
        print(f"Input request (first 100 chars): {str(request)[:100]}")
        try:
            self.logger.info(f"Starting write request for {request.get('type', 'content')} on {request.get('topic', 'unspecified topic')}")
            
            # Get research context if requested
            context = None
            if use_research and request.get("topic"):
                try:
                    query = research_query if research_query else request.get("topic")
                    self.logger.info(f"Performing research on: {query}")
                    
                    query_results = query_content(query, index_ids)
                    
                    if query_results and query_results.get("success") and query_results.get("results"):
                        # Format research context
                        context_parts = []
                        for result in query_results.get("results", []):
                            title = result.get("title", "")
                            content = result.get("response", "")
                            if content:
                                context_parts.append(f"Source: {title}\n{content}\n")
                        
                        context = "Research Context:\n" + "\n".join(context_parts)
                        self.logger.info(f"Retrieved research context: {len(context)} characters")
                except Exception as e:
                    self.logger.warning(f"Error retrieving research context: {str(e)}")
                    # Continue without context
            
            # Prepare the prompt for the LLM
            prompt = self._prepare_prompt(request)
            
            # Add research context if available
            if context:
                prompt += f"\n\nUse the following research to inform your response:\n{context}"
            
            # Get response from LLM
            self.logger.info("Generating content with LLM")
            response = get_llm_response(
                query=prompt,
                use_context=False  # We've already added context manually if needed
            )
            
            if "error" in response:
                raise ValueError(f"Error from LLM service: {response['error']}")
                
            content_text = response.get("answer", "")
            content_type = request.get("type", "answer").lower()
            
            # Extract title if present
            title_match = re.search(r'^#\s+(.+)$', content_text, re.MULTILINE)
            title = title_match.group(1) if title_match else request.get("topic", "")
            
            # Create base content object
            content = {
                "title": title,
                "content": content_text,
                "raw_text": content_text
            }
            
            # Format the content based on type
            if content_type in self.formats:
                formatted_content = self.formats[content_type](content)
            else:
                # Default to answer format
                formatted_content = self._format_answer(content)
                
            # Add raw text for debugging/storage
            formatted_content["raw_text"] = content_text
            
            self.logger.info(f"Write operation complete: Generated {content_type} '{title}'")
            print(f"Generated content (first 150 chars): {str(formatted_content)[:150]}")
            print("======= Write AGENT COMPLETE =======\n")
            return {
                "status": "success",
                "content": formatted_content
            }
            
        except Exception as e:
            self.logger.error(f"Error in write operation: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }