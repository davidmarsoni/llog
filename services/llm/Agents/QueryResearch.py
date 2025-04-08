"""
QueryResearch Agent for advanced research capabilities
"""
from flask import current_app
import os
from typing import List, Dict, Any, Optional
import logging
from collections import Counter
import re
from services.llm.content import query_content, get_content_metadata
from services.llm.cache import get_available_indexes

class QueryResearch:
    """
    Research agent that processes queries to extract themes, keywords, and organized information
    from available content sources.
    """
    
    # initialize the logger (object that creates log messages) for the agent : logging of events and errors
    # where are these logs stored? in the log file specified in the config file
    def __init__(self, logger=None):
        """Initialize the research agent with optional custom logger"""
        self.logger = logger or current_app.logger
        print("QueryResearch Agent has been initialized.")
    
    # Extract key themes from text content -> compare to metadata and other sources, 
    # pick out the most relevant index IDs and themes
    # -> return a list of themes and keywords
    # -> return a list of sources with metadata and content
    def _extract_themes(self, text: str, min_count: int = 1, max_themes: int = 10) -> List[Dict[str, Any]]:
        """        
        Args:
            text (str): The text content to analyze
            min_count (int): Minimum occurrence threshold, defaults to 1 to include unique insights
            max_themes (int): Maximum number of themes to return
            
        Returns:
            List[Dict[str, Any]]: List of theme objects with theme name and count
        """
        # Simple implementation - could be enhanced with NLP libraries
        # Look for sentence patterns that might indicate themes
        sentences = re.split(r'[.!?]', text)
        potential_themes = []
        
        for sentence in sentences:
            # Clean the sentence
            clean = sentence.strip().lower()
            if len(clean) < 10:  # Skip very short sentences
                continue
                
            # Look for key phrases that might indicate themes
            if any(marker in clean for marker in ['important', 'key', 'significant', 'essential', 'critical']):
                # Extract noun phrases (simplified approach)
                potential_themes.append(clean)
        
        # Count theme occurrences
        theme_counter = Counter()
        for theme in potential_themes:
            # Extract key phrases (simplified approach)
            words = theme.split()
            if len(words) >= 3:
                theme_phrase = ' '.join(words[:3])
                theme_counter[theme_phrase] += 1
        
        # Filter and format themes
        themes = [
            {"theme": theme, "count": count, "relevance": self._calculate_relevance(count, max(theme_counter.values()) if theme_counter else 1)}
            for theme, count in theme_counter.most_common(max_themes)
            if count >= min_count
        ]
        
        # If no themes detected with the threshold, adjust and try again
        if not themes and theme_counter:
            themes = [
                {"theme": theme, "count": count, "relevance": self._calculate_relevance(count, max(theme_counter.values()))}
                for theme, count in theme_counter.most_common(max_themes)
            ]
            
        return themes
    
    #  Calculate a relevance score (0.0-1.0) based on count relative to max count
    # -> this is used to determine the importance of a keyword or theme in the text
    # -> the higher the count, the more relevant it is
    def _calculate_relevance(self, count: int, max_count: int) -> float:
        """
        Args:
            count (int): The occurrence count
            max_count (int): The maximum count found
            
        Returns:
            float: Relevance score from 0.0 to 1.0
        """
        if max_count <= 0:
            return 0.0
        # Base relevance starts at 0.4 even for single occurrences
        # This ensures even unique items have reasonable relevance
        base_relevance = 0.4
        variable_portion = 0.6
        return base_relevance + variable_portion * (count / max_count)
    
    # Extract keywords from text content
    def _extract_keywords(self, text: str, min_count: int = 1, max_keywords: int = 15) -> List[Dict[str, Any]]:
        """
        Extract keywords from text content
        
        Args:
            text (str): The text content to analyze
            min_count (int): Minimum occurrence threshold, defaults to 1 to include unique terms
            max_keywords (int): Maximum number of keywords to return
            
        Returns:
            List[Dict[str, Any]]: List of keyword objects with keyword and count
        """
        # Remove common stop words (simplified approach)
        stop_words = {'the', 'a', 'an', 'and', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'of', 'is', 'are'}
        
        # Clean text and split into words
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        words = text.split()
        
        # Filter out stop words and short words
        filtered_words = [word for word in words if word not in stop_words and len(word) > 3]
        
        # Count occurrences
        word_counter = Counter(filtered_words)
        
        # Calculate max count for relevance scoring
        max_count = max(word_counter.values()) if word_counter else 1
        
        # Format keywords with relevance scores
        keywords = [
            {
                "keyword": word, 
                "count": count,
                "relevance": self._calculate_relevance(count, max_count)
            }
            for word, count in word_counter.most_common(max_keywords)
            if count >= min_count
        ]
        
        return keywords
    
    #  Process a single content source to extract themes and organize information
    def _process_source(self, source: Dict[str, Any]) -> Dict[str, Any]:
        """        
        Args:
            source (Dict[str, Any]): Source data from query_content
            
        Returns:
            Dict[str, Any]: Processed source with extracted themes and structured content
        """
        index_id = source.get('index_id')
        title = source.get('title', f'Content {index_id}')
        response_text = source.get('response', '')
        
        # Get themes for this specific source
        source_themes = self._extract_themes(response_text)
        source_theme_names = [t['theme'] for t in source_themes]
        
        # Structure the content (in real implementation, this could parse the content more intelligently)
        content = [{"text": response_text, "relevance": 1.0}]
        
        # Try to get additional metadata
        metadata = {}
        try:
            metadata = get_content_metadata(index_id)
        except Exception as e:
            self.logger.warning(f"Could not get metadata for {index_id}: {str(e)}")
        
        # Combine into processed source
        processed_source = {
            "id": index_id,
            "title": title,
            "themes": source_theme_names,
            "content": content,
            "metadata": metadata
        }
        
        return processed_source
    #  Perform comprehensive research on a query
    def research(self, query: str, index_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """        
        Args:
            query (str): The research query
            index_ids (List[str], optional): Specific index IDs to search, if any
            
        Returns:
            Dict[str, Any]: Research results including themes, keywords, and processed sources
        """
        print("\n======= QueryResearch AGENT START =======")
        print(f"Input query (first 100 chars): {query[:100]}")
        try:
            self.logger.info(f"Starting research query: {query}")
            
            # If no indexes specified, use all available
            if not index_ids:
                available_indexes = get_available_indexes()
                index_ids = [idx['id'] for idx in available_indexes if idx]
                
            # Query content from specified indexes
            query_results = query_content(query, index_ids)
            
            if not query_results.get('success'):
                raise ValueError("Query failed to return results")
                
            result_items = query_results.get('results', [])
            
            if not result_items:
                return {
                    "status": "error",
                    "message": "No results found for the research query",
                    "query": query,
                    "total_results": 0,
                    "themes": [],
                    "keywords": [],
                    "sources": []
                }
            
            # Combine all response texts for overall analysis
            all_text = ' '.join([result.get('response', '') for result in result_items])
            
            # Extract overall themes and keywords
            themes = self._extract_themes(all_text)
            keywords = self._extract_keywords(all_text)
            
            # Process individual sources
            sources = [self._process_source(source) for source in result_items]
            
            # Construct final research result
            research_result = {
                "status": "success",
                "query": query,
                "total_results": len(sources),
                "themes": themes,
                "keywords": keywords,
                "sources": sources
            }
            
            self.logger.info(f"Research complete. Found {len(sources)} sources, {len(themes)} themes, {len(keywords)} keywords")
            print(f"Extracted themes (first 150 chars): {str(themes)[:150]}")
            print("======= QueryResearch AGENT COMPLETE =======\n")
            return research_result
            
        except Exception as e:
            self.logger.error(f"Error in research query: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "query": query,
                "total_results": 0,
                "themes": [],
                "keywords": [],
                "sources": []
            }