"""
Content recommendation functionality for LLM services
"""
from flask import current_app
from typing import Dict, Any
from services.llm.cache import get_available_indexes
from services.llm.content import query_content

def get_recommender_system(query: str = None, include_metadata: bool = True) -> Dict[str, Any]:
    """
    Create content recommendations based on themes, topics, and metadata.
    
    Args:
        query (str, optional): Optional query to find related content
        include_metadata (bool): Whether to include detailed metadata in response
        
    Returns:
        dict: Recommended content grouped by themes/topics
    """
    try:
        # Get all available indexes with metadata
        all_indexes = get_available_indexes()
        
        if not all_indexes:
            return {"error": "No cached content available for recommendations"}
            
        # If query is provided, use it to find similar content
        if query:
            # Simple semantic similarity for recommendation
            results = query_content(query, use_metadata_filtering=True)
            if "error" in results:
                return {"error": results["error"]}
                
            # Get IDs of top results
            relevant_ids = [r["source"].split(":")[-1] for r in results["results"][:5]]
            
            # Filter indexes to those that are related to query results
            filtered_indexes = [idx for idx in all_indexes if idx["id"] in relevant_ids]
            
            # Add some recommended content based on themes of results
            result_themes = set()
            for r in results["results"][:5]:
                result_themes.update(r.get("themes", []))
                
            # Find content with similar themes
            if result_themes:
                for idx in all_indexes:
                    if idx["id"] not in relevant_ids:  # Don't duplicate
                        idx_themes = set(idx.get('themes', []))
                        if idx_themes.intersection(result_themes):
                            filtered_indexes.append(idx)
            
            # Use filtered indexes for recommendations            
            if filtered_indexes:
                all_indexes = filtered_indexes
        
        # Group content by themes for organization
        theme_groups = {}
        
        # Process each index to extract themes and group content
        for idx in all_indexes:
            for theme in idx.get('themes', []):
                if theme not in theme_groups:
                    theme_groups[theme] = []
                    
                # Add content to this theme group
                content_item = {
                    'id': idx['id'],
                    'title': idx['title'],
                    'type': idx['type']
                }
                
                # Include additional metadata if requested
                if include_metadata:
                    content_item['themes'] = idx.get('themes', [])
                    content_item['keywords'] = idx.get('keywords', [])
                    
                theme_groups[theme].append(content_item)
        
        # Create the recommendations response
        recommendations = {
            'query': query,
            'theme_groups': [],
            'total_items': len(all_indexes)
        }
        
        # Convert theme groups to list for the response
        for theme, items in theme_groups.items():
            recommendations['theme_groups'].append({
                'theme': theme,
                'items': items,
                'count': len(items)
            })
            
        # Sort groups by number of items descending
        recommendations['theme_groups'].sort(key=lambda x: x['count'], reverse=True)
        
        return recommendations
        
    except Exception as e:
        current_app.logger.error(f"Error generating recommendations: {str(e)}")
        return {"error": str(e)}