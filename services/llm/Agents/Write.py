"""
Write Agent for generating structured written content
"""
from flask import current_app
import os
from typing import List, Dict, Any, Optional
import logging
import re
from services.llm.chat import get_llm_response
from services.llm.content import query_content
from services.llm.Agents.agent_logger import log_agent_use

class Write:
    """
    Write agent that generates high-quality structured text content based on user requirements.
    Supports various formats and can incorporate research from existing content.
    """
    
    def __init__(self, logger=None):
        """Initialize the write agent with optional custom logger"""
        self.logger = logger or current_app.logger
        self.formats = {
            "article": self._format_article,
            "blog": self._format_blog,
            "report": self._format_report,
            "summary": self._format_summary,
            "outline": self._format_outline,
            "email": self._format_email
        }
    
    def _format_article(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as a structured article"""
        structured = {
            "type": "article",
            "title": content.get("title", "Untitled Article"),
            "sections": []
        }
        
        # Process the main content
        main_content = content.get("content", "")
        
        # Extract sections based on headings
        sections = re.split(r'(?m)^#{1,3} ', main_content)
        
        # Process each section (skip empty first split if it exists)
        for section in (sections[1:] if sections[0].strip() == "" else sections):
            if not section.strip():
                continue
                
            # Extract heading and content
            section_parts = section.strip().split('\n', 1)
            heading = section_parts[0].strip()
            body = section_parts[1].strip() if len(section_parts) > 1 else ""
            
            structured["sections"].append({
                "heading": heading,
                "content": body
            })
            
        return structured
    
    def _format_blog(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as a blog post"""
        # Similar to article but with blog-specific formatting
        article_format = self._format_article(content)
        
        # Convert to blog format
        blog_format = {
            "type": "blog",
            "title": article_format.get("title", "Untitled Blog Post"),
            "intro": "",
            "sections": article_format.get("sections", []),
            "conclusion": "",
            "tags": content.get("tags", [])
        }
        
        # Extract intro and conclusion if they exist
        if blog_format["sections"]:
            first_section = blog_format["sections"][0]
            if first_section["heading"].lower() in ["introduction", "intro"]:
                blog_format["intro"] = first_section["content"]
                blog_format["sections"] = blog_format["sections"][1:]
                
            last_section = blog_format["sections"][-1]
            if last_section["heading"].lower() in ["conclusion", "summary", "final thoughts"]:
                blog_format["conclusion"] = last_section["content"]
                blog_format["sections"] = blog_format["sections"][:-1]
        
        return blog_format
    
    def _format_report(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as a formal report"""
        report = {
            "type": "report",
            "title": content.get("title", "Untitled Report"),
            "executive_summary": "",
            "sections": [],
            "recommendations": [],
            "appendices": []
        }
        
        # Process the main content
        main_content = content.get("content", "")
        
        # Extract sections based on headings
        sections = re.split(r'(?m)^#{1,3} ', main_content)
        
        # Process each section
        for section in (sections[1:] if sections[0].strip() == "" else sections):
            if not section.strip():
                continue
                
            # Extract heading and content
            section_parts = section.strip().split('\n', 1)
            heading = section_parts[0].strip()
            body = section_parts[1].strip() if len(section_parts) > 1 else ""
            
            # Categorize section based on heading
            heading_lower = heading.lower()
            if "executive summary" in heading_lower or "abstract" in heading_lower:
                report["executive_summary"] = body
            elif "recommendation" in heading_lower:
                # Extract bullet points as recommendations
                bullets = re.findall(r'(?m)^[\*\-\•]\s*(.+)$', body)
                report["recommendations"].extend(bullets if bullets else [body])
            elif "appendix" in heading_lower:
                report["appendices"].append({
                    "title": heading,
                    "content": body
                })
            else:
                report["sections"].append({
                    "heading": heading,
                    "content": body
                })
        
        return report
    
    def _format_summary(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as a concise summary"""
        return {
            "type": "summary",
            "title": content.get("title", "Summary"),
            "content": content.get("content", ""),
            "key_points": content.get("key_points", [])
        }
    
    def _format_outline(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as an outline with hierarchical structure"""
        outline = {
            "type": "outline",
            "title": content.get("title", "Outline"),
            "sections": []
        }
        
        # Process the main content
        main_content = content.get("content", "")
        
        # Split by lines and process hierarchical structure
        lines = main_content.strip().split("\n")
        current_path = []
        
        for line in lines:
            if not line.strip():
                continue
                
            # Calculate indentation level
            indent = len(line) - len(line.lstrip())
            level = indent // 2  # Assuming 2 spaces per level
            
            # Adjust current path based on indentation
            if level >= len(current_path):
                # Going deeper
                current_path.append({"title": line.strip(), "items": []})
            else:
                # Coming back to a higher level
                current_path = current_path[:level]
                current_path.append({"title": line.strip(), "items": []})
            
            # Update the outline structure
            if level == 0:
                outline["sections"].append(current_path[-1])
            else:
                current_path[level-1]["items"].append(current_path[level])
        
        return outline
    
    def _format_email(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Format content as an email with standard email components"""
        return {
            "type": "email",
            "subject": content.get("title", ""),
            "greeting": content.get("greeting", ""),
            "body": content.get("content", ""),
            "closing": content.get("closing", "Regards,"),
            "signature": content.get("signature", "")
        }
    
    def _prepare_prompt(self, request: Dict[str, Any]) -> str:
        """
        Prepare a detailed prompt for the LLM based on the writing request
        
        Args:
            request (Dict[str, Any]): The writing request parameters
            
        Returns:
            str: Formatted prompt for the LLM
        """
        content_type = request.get("type", "article").lower()
        topic = request.get("topic", "")
        keywords = request.get("keywords", [])
        tone = request.get("tone", "informative")
        audience = request.get("audience", "general")
        length = request.get("length", "medium")
        instructions = request.get("instructions", "")
        
        # Map length to word count expectations
        length_map = {
            "short": "300-500 words",
            "medium": "800-1200 words",
            "long": "1500-2500 words",
            "very long": "3000+ words"
        }
        word_count = length_map.get(length.lower(), "800-1200 words")
        
        # Build the prompt
        prompt = f"""Generate a {content_type} about '{topic}'. 

Details:
- Target length: {word_count}
- Target audience: {audience}
- Tone: {tone}
- Keywords to include: {', '.join(keywords) if keywords else 'No specific keywords required'}

Structure the {content_type} with appropriate headings and sections. Use markdown formatting.

{instructions}

Generate the complete {content_type} with a compelling title."""

        return prompt
    
    def write(self, 
              request: Dict[str, Any], 
              use_research: bool = False, 
              research_query: Optional[str] = None,
              index_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Generate written content based on the request parameters
        
        Args:
            request (Dict[str, Any]): Content request parameters including:
                - type: Content type (article, blog, report, etc.)
                - topic: Main topic to write about
                - keywords: List of keywords to include
                - tone: Desired tone (formal, casual, etc.)
                - audience: Target audience
                - length: Desired length (short, medium, long)
                - instructions: Additional writing instructions
            use_research (bool): Whether to incorporate research from content indexes
            research_query (str, optional): Custom query for research, defaults to topic
            index_ids (List[str], optional): Specific index IDs to search
            
        Returns:
            Dict[str, Any]: Generated content in structured format
        """
        try:
            self.logger.info(f"Starting write request for {request.get('type', 'content')} on {request.get('topic', 'unspecified topic')}")
            log_agent_use("Write", f"Generating {request.get('type', 'content')} about '{request.get('topic', 'unspecified topic')}'")
            
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
                prompt += f"\n\nUse the following research to inform your writing:\n{context}"
            
            # Get response from LLM
            self.logger.info("Generating content with LLM")
            response = get_llm_response(
                query=prompt,
                use_context=False  # We've already added context manually if needed
            )
            
            if "error" in response:
                raise ValueError(f"Error from LLM service: {response['error']}")
                
            content_text = response.get("answer", "")
            content_type = request.get("type", "article").lower()
            
            # Extract title from markdown content
            title_match = re.search(r'^#\s+(.+)$', content_text, re.MULTILINE)
            title = title_match.group(1) if title_match else request.get("topic", "Untitled")
            
            # Create base content object
            content = {
                "title": title,
                "content": content_text,
                "raw_text": content_text
            }
            
            # Add any specific request parameters
            for key in ["tone", "audience", "keywords"]:
                if key in request:
                    content[key] = request[key]
            
            # Format the content based on type
            if content_type in self.formats:
                formatted_content = self.formats[content_type](content)
            else:
                # Default to article format
                formatted_content = self._format_article(content)
                
            # Add raw text for debugging/storage
            formatted_content["raw_text"] = content_text
            
            self.logger.info(f"Write operation complete: Generated {content_type} '{title}'")
            log_agent_use("Write", f"Writing complete: Generated {content_type} '{title}'")
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