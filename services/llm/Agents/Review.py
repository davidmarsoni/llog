"""
Review Agent for analyzing and providing feedback on content
"""
from flask import current_app
import logging
from typing import Dict, Any, List, Optional
from services.llm.llm_core import get_llm_response

class Review:
    """
    Review agent that analyzes content and provides structured feedback.
    Supports various review types including writing feedback, fact checking,
    and SEO optimization suggestions.
    """
    
    def __init__(self, logger=None):
        """Initialize the review agent with optional custom logger"""
        self.logger = logger or current_app.logger
        self.review_types = {
            "writing": self._review_writing,
            "fact_check": self._review_facts,
            "seo": self._review_seo,
            "comprehensive": self._review_comprehensive
        }
    
    def _validate_content(self, content: str) -> Dict[str, Any]:
        """
        Validate content to ensure it's reviewable
        
        Args:
            content: The content to validate
            
        Returns:
            Dict with validation result and message if invalid
        """
        if not content or not content.strip():
            return {
                "valid": False,
                "message": "Content is empty. Please provide text to review."
            }
            
        if len(content.strip()) < 50:
            return {
                "valid": False, 
                "message": "Content is too short for meaningful review. Please provide more text."
            }
            
        return {"valid": True}
    
    def _review_writing(self, content: str, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Review writing style, grammar, structure, and clarity
        
        Args:
            content: The text content to review
            criteria: Optional specific criteria to focus on
            
        Returns:
            Dict with structured writing feedback
        """
        writing_feedback = {
            "type": "writing",
            "summary": "",
            "strengths": [],
            "weaknesses": [],
            "suggestions": [],
            "grammar_issues": [],
            "style_score": 0
        }
        
        # Process LLM response into structured format
        result = self._get_review_from_llm(content, "writing", criteria)
        if not result:
            return writing_feedback
            
        # Extract information from LLM response
        writing_feedback["summary"] = result.get("summary", "")
        writing_feedback["strengths"] = result.get("strengths", [])
        writing_feedback["weaknesses"] = result.get("weaknesses", [])
        writing_feedback["suggestions"] = result.get("improvement_suggestions", [])
        writing_feedback["grammar_issues"] = result.get("grammar_issues", [])
        
        # Calculate style score (1-10) based on strengths vs weaknesses
        strengths_count = len(writing_feedback["strengths"])
        weaknesses_count = len(writing_feedback["weaknesses"])
        
        # Set a default minimum score if content exists but LLM didn't return much
        if len(content.strip()) > 200 and strengths_count + weaknesses_count == 0:
            writing_feedback["style_score"] = 1  # Minimum score for non-empty content
        elif strengths_count + weaknesses_count > 0:
            raw_score = min(10, max(1, round(10 * strengths_count / (strengths_count + weaknesses_count))))
            writing_feedback["style_score"] = raw_score
        
        return writing_feedback
    
    def _review_facts(self, content: str, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Review factual accuracy and identify potential inaccuracies
        
        Args:
            content: The text content to review
            criteria: Optional specific criteria to focus on
            
        Returns:
            Dict with structured fact checking results
        """
        fact_feedback = {
            "type": "fact_check",
            "summary": "",
            "accurate_statements": [],
            "questionable_statements": [],
            "incorrect_statements": [],
            "missing_context": [],
            "verification_suggestions": [],
            "accuracy_score": 0
        }
        
        # Process LLM response into structured format
        result = self._get_review_from_llm(content, "fact_check", criteria)
        if not result:
            return fact_feedback
            
        # Extract information from LLM response
        fact_feedback["summary"] = result.get("summary", "")
        fact_feedback["accurate_statements"] = result.get("accurate_statements", [])
        fact_feedback["questionable_statements"] = result.get("questionable_statements", [])
        fact_feedback["incorrect_statements"] = result.get("incorrect_statements", [])
        fact_feedback["missing_context"] = result.get("missing_context", [])
        fact_feedback["verification_suggestions"] = result.get("verification_suggestions", [])
        
        # Calculate accuracy score (1-10)
        accurate = len(fact_feedback["accurate_statements"])
        questionable = len(fact_feedback["questionable_statements"])
        incorrect = len(fact_feedback["incorrect_statements"])
        
        total_statements = accurate + questionable + incorrect
        
        # Set a default minimum score if content exists but LLM didn't return much
        if len(content.strip()) > 200 and total_statements == 0:
            fact_feedback["accuracy_score"] = 1  # Minimum score for non-empty content
        elif total_statements > 0:
            # Weight accurate fully, questionable statements half
            weighted_score = (accurate + (questionable * 0.5)) / total_statements
            fact_feedback["accuracy_score"] = round(weighted_score * 10)
        
        return fact_feedback
    
    def _review_seo(self, content: str, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Review content for SEO optimization opportunities
        
        Args:
            content: The text content to review
            criteria: Optional specific criteria like target keywords
            
        Returns:
            Dict with structured SEO feedback
        """
        seo_feedback = {
            "type": "seo",
            "summary": "",
            "keyword_analysis": {},
            "content_suggestions": [],
            "structure_suggestions": [],
            "meta_suggestions": [],
            "seo_score": 0
        }
        
        # Process LLM response into structured format
        result = self._get_review_from_llm(content, "seo", criteria)
        if not result:
            return seo_feedback
            
        # Extract information from LLM response
        seo_feedback["summary"] = result.get("summary", "")
        seo_feedback["keyword_analysis"] = result.get("keyword_analysis", {})
        seo_feedback["content_suggestions"] = result.get("content_suggestions", [])
        seo_feedback["structure_suggestions"] = result.get("structure_suggestions", [])
        seo_feedback["meta_suggestions"] = result.get("meta_suggestions", [])
        
        # Extract or calculate SEO score if available
        seo_score = result.get("seo_score", 0)
        
        # Set a default minimum score if content exists but LLM didn't return a score
        if len(content.strip()) > 200 and seo_score == 0:
            seo_feedback["seo_score"] = 1  # Minimum score for non-empty content
        else:
            seo_feedback["seo_score"] = seo_score
        
        return seo_feedback
    
    def _review_comprehensive(self, content: str, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Perform a comprehensive review covering writing quality, factual accuracy, and SEO
        
        Args:
            content: The text content to review
            criteria: Optional specific criteria to focus on
            
        Returns:
            Dict with comprehensive review results from all categories
        """
        # Get individual reviews
        writing_review = self._review_writing(content, criteria)
        fact_review = self._review_facts(content, criteria)
        seo_review = self._review_seo(content, criteria)
        
        # Combine into comprehensive review
        comprehensive = {
            "type": "comprehensive",
            "summary": "",
            "writing": {
                "strengths": writing_review.get("strengths", []),
                "weaknesses": writing_review.get("weaknesses", []),
                "suggestions": writing_review.get("suggestions", []),
                "style_score": writing_review.get("style_score", 0)
            },
            "facts": {
                "questionable_statements": fact_review.get("questionable_statements", []),
                "incorrect_statements": fact_review.get("incorrect_statements", []),
                "verification_suggestions": fact_review.get("verification_suggestions", []),
                "accuracy_score": fact_review.get("accuracy_score", 0)
            },
            "seo": {
                "keyword_analysis": seo_review.get("keyword_analysis", {}),
                "content_suggestions": seo_review.get("content_suggestions", []),
                "structure_suggestions": seo_review.get("structure_suggestions", []),
                "seo_score": seo_review.get("seo_score", 0)
            },
            "overall_score": 0,
            "priority_improvements": []
        }
        
        # Calculate overall score (average of the three scores)
        style_score = writing_review.get("style_score", 0)
        accuracy_score = fact_review.get("accuracy_score", 0)
        seo_score = seo_review.get("seo_score", 0)
        
        # Set overall score, ensuring non-zero if content exists
        if len(content.strip()) > 200 and style_score + accuracy_score + seo_score == 0:
            comprehensive["overall_score"] = 1  # Minimum score for non-empty content
        elif style_score > 0 or accuracy_score > 0 or seo_score > 0:
            # Average of non-zero scores
            non_zero_scores = [s for s in [style_score, accuracy_score, seo_score] if s > 0]
            if non_zero_scores:
                overall = sum(non_zero_scores) / len(non_zero_scores)
                comprehensive["overall_score"] = round(overall)
        
        # Generate a summary combining insights from all reviews
        try:
            summary_prompt = f"""Provide a brief summary of this content's overall quality based on:
            - Writing style score: {style_score}/10
            - Factual accuracy score: {accuracy_score}/10
            - SEO optimization score: {seo_score}/10
            
            Key writing strengths: {', '.join(writing_review.get('strengths', [])[:2])}
            Key factual issues: {len(fact_review.get('questionable_statements', [])) + len(fact_review.get('incorrect_statements', []))} found
            
            Provide 2-3 sentences that capture the most important aspects.
            """
            
            summary_response = get_llm_response(
                query=summary_prompt,
                use_context=False
            )
            
            if "answer" in summary_response:
                comprehensive["summary"] = summary_response["answer"]
        except Exception as e:
            self.logger.warning(f"Error generating comprehensive summary: {str(e)}")
            # Use basic summary if there's an error
            comprehensive["summary"] = f"Overall score: {comprehensive['overall_score']}/10. Several areas for improvement identified."
        
        # Identify priority improvements
        all_suggestions = []
        
        # Add writing suggestions if score is low
        if style_score < 7 and writing_review.get("suggestions"):
            all_suggestions.extend([f"[Writing] {s}" for s in writing_review.get("suggestions", [])[:2]])
            
        # Add fact checking suggestions if score is low
        if accuracy_score < 7 and fact_review.get("verification_suggestions"):
            all_suggestions.extend([f"[Fact] {s}" for s in fact_review.get("verification_suggestions", [])[:2]])
            
        # Add SEO suggestions
        if seo_review.get("content_suggestions"):
            all_suggestions.extend([f"[SEO] {s}" for s in seo_review.get("content_suggestions", [])[:2]])
            
        # Prioritize suggestions (take top 5)
        comprehensive["priority_improvements"] = all_suggestions[:5]
        
        return comprehensive
    
    def _prepare_review_prompt(self, content: str, review_type: str, criteria: Optional[Dict[str, Any]] = None) -> str:
        """
        Prepare a detailed prompt for the LLM based on the review type
        
        Args:
            content: The content to review
            review_type: Type of review (writing, fact_check, seo, etc.)
            criteria: Optional specific criteria to focus on
            
        Returns:
            str: Formatted prompt for the LLM
        """
        # Limit content length for review to ensure faster, more focused feedback
        max_review_chars = 4000
        if len(content) > max_review_chars:
            truncated_content = content[:max_review_chars] + "...[truncated for length]"
        else:
            truncated_content = content
            
        base_prompt = f"""Review the following content and provide concise, actionable feedback.
        
Content to review:
'''
{truncated_content}
'''
        """
        
        if review_type == "writing":
            prompt = base_prompt + """
Focus on providing practical writing feedback:
1. Identify what works well
2. Note 2-3 specific areas for improvement
3. Evaluate readability and engagement

Return your analysis as JSON with these fields:
- summary: Brief overall assessment (1-2 sentences)
- strengths: List of 2-3 key strengths
- weaknesses: List of 2-3 key areas for improvement
- improvement_suggestions: List of 2-3 specific, actionable suggestions
- grammar_issues: List of major grammar or clarity issues (if any)
"""

        elif review_type == "fact_check":
            prompt = base_prompt + """
Focus on accuracy and reliability. Analyze:
1. Identify any questionable claims or statements
2. Note any missing context or nuance
3. Highlight areas of strong factual support

Return your analysis as JSON with these fields:
- summary: Brief assessment of factual reliability (1-2 sentences)
- accurate_statements: List of well-supported claims (max 3)
- questionable_statements: List of statements requiring verification (if any)
- incorrect_statements: List of likely inaccurate claims (if any)
- missing_context: Key information that would improve accuracy (if applicable)
- verification_suggestions: Specific ways to verify questionable information
"""

        elif review_type == "seo":
            prompt = base_prompt + """
Focus on practical SEO improvements:
1. Identify strongest keywords and search potential
2. Note 2-3 specific SEO improvements with high impact
3. Suggest title and structure optimizations

Return your analysis as JSON with these fields:
- summary: Brief SEO assessment (1-2 sentences)
- keyword_analysis: Object with 2-3 primary keywords and brief usage analysis
- content_suggestions: List of 2-3 specific content improvements for SEO
- structure_suggestions: List of 1-2 structural changes to improve search visibility
- meta_suggestions: Brief title and meta description improvement (if needed)
- seo_score: Numerical score from 1-10 rating current SEO optimization
"""

        # Add any custom criteria to the prompt
        if criteria:
            criteria_str = "\nAdditional criteria to consider:\n"
            for key, value in criteria.items():
                criteria_str += f"- {key}: {value}\n"
            prompt += criteria_str
            
        # Add instruction for conciseness
        prompt += "\nImportant: Keep your feedback concise, practical and actionable. Focus on the most important points rather than exhaustive analysis."
        
        return prompt
    
    def _get_review_from_llm(self, content: str, review_type: str, criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get review feedback from LLM service
        
        Args:
            content: Content to review
            review_type: Type of review
            criteria: Optional specific criteria
            
        Returns:
            Dict with LLM response parsed as JSON (or empty dict on error)
        """
        try:
            # Add a safeguard for extremely short content
            if len(content.strip()) < 100:
                return {
                    "summary": f"Content is too short ({len(content.strip())} chars) for a meaningful {review_type} review.",
                    "note": "Please provide more content for a thorough analysis."
                }
                
            prompt = self._prepare_review_prompt(content, review_type, criteria)
            
            self.logger.info(f"Requesting {review_type} review from LLM")
            response = get_llm_response(
                query=prompt,
                use_context=False
            )
            
            if "error" in response:
                self.logger.error(f"Error from LLM: {response['error']}")
                return {
                    "summary": f"Error reviewing content: {response.get('error', 'Unknown error')}",
                    "error": True
                }
                
            if "answer" in response:
                result = response["answer"]
                if isinstance(result, str):
                    # If the result is a string, it might be JSON in string form or plain text
                    try:
                        # Look for JSON content in the response
                        import re
                        import json
                        # Try to find JSON content within the string (between { and })
                        json_match = re.search(r'(\{.*\})', result, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(1)
                            parsed_result = json.loads(json_str)
                            return parsed_result
                        else:
                            # If no JSON format found, try to parse the whole string
                            try:
                                parsed_result = json.loads(result)
                                return parsed_result
                            except json.JSONDecodeError:
                                # If parsing fails, wrap the text in a basic structure
                                return {"summary": result}
                    except Exception as e:
                        self.logger.warning(f"Error parsing JSON from LLM response: {str(e)}")
                        return {"summary": result}
                else:
                    # Result is already parsed JSON
                    return result
            
            return {"summary": "No valid response received from LLM."}
            
        except Exception as e:
            self.logger.error(f"Error getting review from LLM: {str(e)}")
            return {"summary": f"Error during review process: {str(e)}"}
    
    def review(self, 
               content: str,
               review_type: str = "comprehensive", 
               criteria: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Review content and provide structured feedback
        
        Args:
            content (str): Content to review
            review_type (str): Type of review (writing, fact_check, seo, comprehensive)
            criteria (Dict, optional): Specific criteria for the review
            
        Returns:
            Dict[str, Any]: Review results in structured format
        """
        try:
            print("\n======= Review AGENT START =======")
            print(f"Input content (first 100 chars): {content[:100]}")
            self.logger.info(f"Starting {review_type} review")
            
            # First validate the content
            validation = self._validate_content(content)
            if not validation["valid"]:
                self.logger.warning(f"Content validation failed: {validation['message']}")
                return {
                    "status": "error",
                    "message": validation["message"]
                }
            
            # Default to comprehensive if type not recognized
            if review_type not in self.review_types:
                self.logger.warning(f"Review type '{review_type}' not recognized, using comprehensive")
                review_type = "comprehensive"
                
            # Perform the review
            review_method = self.review_types[review_type]
            result = review_method(content, criteria)
            
            print(f"Final reviewed content (first 150 chars): {str(result)[:150]}")
            print("======= Review AGENT COMPLETE =======\n")
            self.logger.info(f"Review completed: {review_type}")
            
            return {
                "status": "success",
                "review": result
            }
            
        except Exception as e:
            self.logger.error(f"Error in review operation: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }