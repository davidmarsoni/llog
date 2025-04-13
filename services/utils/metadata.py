"""
Metadata extraction functionality for documents
"""
import os
import json
import httpx
import re
from flask import current_app
from openai import OpenAI
   

def extract_auto_metadata(text_content):
    """
    Extract metadata automatically from document content using AI.
    Returns a dictionary with theme, topics, and other important information.
    """
    try:
        # Check if OpenAI API key is available
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            current_app.logger.warning("OpenAI API key not available. Skipping automatic metadata extraction.")
            return {
                "auto_generated": False,
                "themes": [],
                "topics": [],
                "entities": [],
                "keywords": []
            }
        
        # Create OpenAI client
        client = OpenAI(
            api_key=openai_api_key,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=10.0)
        )
        
        # Prepare a sample of the text (first 4000 chars is usually enough for metadata)
        text_sample = text_content[:4000] if len(text_content) > 4000 else text_content
        
        # Create the prompt for metadata extraction
        prompt = f"""
        Analyze the following document content and extract key metadata.
        The first element of each list should be the most important.
        Return ONLY a JSON object with these fields:
        - themes: List of 3-5 main themes
        - topics: List of 5-10 specific topics covered
        - entities: List of important entities mentioned (people, organizations, products)
        - keywords: List of 10-15 relevant keywords for search
        - summary: A 2-3 sentence summary of the content
        - language: The detected language of the content
        - contentType: The likely type of the content (article, report, tutorial, etc.)
        
        Document content:
        {text_sample}
        
        Return ONLY the JSON object with the extracted metadata.
        """
        
        # Call OpenAI API
        current_app.logger.info("Extracting automatic metadata using OpenAI")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            timeout=25,
        )
        
        result_text = response.choices[0].message.content
        
        # Extract the JSON content from the response
        try:
            # Try to parse the entire response as JSON directly
            metadata = json.loads(result_text)
        except json.JSONDecodeError:
            # If that fails, try to find JSON within the text
            try:
                json_match = re.search(r'\{[\s\S]*\}', result_text)
                if json_match:
                    metadata = json.loads(json_match.group(0))
                else:
                    raise ValueError("No valid JSON found in the response")
            except Exception as e:
                current_app.logger.error(f"Error extracting JSON from OpenAI response: {str(e)}")
                return {
                    "auto_generated": True,
                    "error": "Failed to parse metadata",
                    "themes": [],
                    "topics": [],
                    "entities": [],
                    "keywords": []
                }
        
        # Add auto_generated flag
        metadata["auto_generated"] = True
        
        current_app.logger.info(f"Successfully extracted automatic metadata: {len(metadata['topics'])} topics, {len(metadata['keywords'])} keywords")
        return metadata
        
    except Exception as e:
        current_app.logger.error(f"Error in automatic metadata extraction: {str(e)}")
        return {
            "auto_generated": False,
            "error": str(e),
            "themes": [],
            "topics": [],
            "entities": [],
            "keywords": []
        }