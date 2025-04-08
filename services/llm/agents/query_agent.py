from llama_index.core.agent import FunctionCallingAgent as GenericFunctionCallingAgent
from llama_index.core.tools import FunctionTool
from services.llm.agents.utils import llm
from tavily import AsyncTavilyClient 
from dotenv import load_dotenv
import os

from services.llm.content import get_content_metadata

# Load environment variables from .env file
load_dotenv()

tavily_api_key = os.getenv("TAVILY_API_KEY") 


async def search_best_maching_index_based_on_metdata(
    query: str,
    index_ids: list = None,
) -> dict:
    """Find the most relevant index based on metadata.
    Use this FIRST when looking for information to determine which indexes are most relevant.
    
    Args:
        query: The user's original question/prompt to the AI
        index_ids: List of index IDs to search through
    """
    if not index_ids:
        print("ERROR: No index IDs provided")
        return {"error": "No index IDs provided"}
    
    matches = []
    query_terms = set(query.lower().split())
    print(f"[METADATA SEARCH] Query terms: {query_terms}")
    print(f"[METADATA SEARCH] Processing {len(index_ids)} index IDs")
    
    # Get available metadata indexes of the list of indexes
    for index_id in index_ids:
        try:
            print(f"[METADATA SEARCH] Fetching metadata for index: {index_id}")
            # The get_content_metadata function is not async, so we shouldn't await it
            metadata = get_content_metadata(index_id)
            print(f"[METADATA SEARCH] Metadata type: {type(metadata)}")
            print(f"[METADATA SEARCH] Metadata content: {metadata}")
            
            if not metadata:
                print(f"[METADATA SEARCH] WARNING: No metadata found for index: {index_id}")
                continue
                
            # Extract key fields from metadata and create a focused search text
            meta_text = ""
            important_fields = []
            
            if isinstance(metadata, dict):
                # Extract title and add to important fields
                title = metadata.get('title', '')
                if title:
                    important_fields.append(title.lower())
                
                # Extract auto_metadata fields if available
                auto_meta = metadata.get('auto_metadata', {})
                if auto_meta:
                    # Add summary with higher importance
                    summary = auto_meta.get('summary', '')
                    if summary:
                        important_fields.append(summary.lower())
                    
                    # Add keywords, themes, topics
                    for field in ['keywords', 'themes', 'topics', 'entities']:
                        values = auto_meta.get(field, [])
                        if values:
                            if isinstance(values, list):
                                for value in values:
                                    if value:
                                        important_fields.append(value.lower())
                            elif isinstance(values, str):
                                important_fields.append(values.lower())
                
                # Combine all important fields into a single text
                meta_text = ' '.join(important_fields)
                
                # If no important fields were found, fall back to the entire metadata as string
                if not meta_text:
                    meta_text = str(metadata).lower()
            else:
                meta_text = str(metadata).lower()
            
            print(f"[METADATA SEARCH] Processed metadata text length: {len(meta_text)}")
            print(f"[METADATA SEARCH] Extracted fields: {important_fields[:3]}...")
            
            # Calculate a more sophisticated relevance score
            # Count how many query terms appear in the metadata
            matched_terms = sum(1 for term in query_terms if term in meta_text)
            
            # Check for exact matches of the complete query
            exact_match = query.lower() in meta_text
            
            # Also check for partial phrase matches (at least 3 consecutive words)
            phrase_match = False
            if len(query_terms) >= 3:
                query_words = query.lower().split()
                for i in range(len(query_words) - 2):  # Need at least 3 words
                    phrase = ' '.join(query_words[i:i+3])
                    if phrase in meta_text:
                        phrase_match = True
                        break
            
            # Calculate a weighted score with bonuses for different match types
            score = matched_terms  # Base score from matched terms
            
            # Add bonuses for different types of matches
            if exact_match:
                score += 10  # Strong bonus for exact query match
            
            if phrase_match:
                score += 5   # Medium bonus for phrase matches
                
            # Add bonus based on percentage of query terms matched
            if query_terms:
                coverage = matched_terms / len(query_terms)
                coverage_bonus = int(coverage * 5)  # Up to 5 points based on coverage
                score += coverage_bonus
            
            print(f"[METADATA SEARCH] Match score for {index_id}: {score} (matched terms: {matched_terms}, exact match: {exact_match}, phrase match: {phrase_match})")
            
            # Only include matches with a minimum score
            if score > 0:
                matches.append({
                    "metadata": metadata,
                    "score": score,
                    "index_id": index_id,
                    "matched_fields": important_fields[:5]  # Include matched fields for debugging
                })
        except Exception as e:
            print(f"[METADATA SEARCH] ERROR processing index {index_id}: {str(e)}")
            continue

    # Sort matches by score (highest first)
    matches.sort(key=lambda x: x["score"], reverse=True)
    
    # Return the top 5 matches or an empty result
    if matches:
        top_matches = matches[:5]  # Get up to 3 best matches 
        return {
            "top_matches": [match["metadata"] for match in top_matches],
            "top_match_scores": [match["score"] for match in top_matches],
            "top_match_ids": [match["index_id"] for match in top_matches],
            "all_matches": matches,
            "total_matches": len(matches)
        }
    
    return {"error": "No matching metadata found", "matches": 0}
    
    
async def search_best_context(
    query: str,
    index_ids: list = None,
) -> dict:
    """Search within indexes for relevant context.
    Use this SECOND after finding relevant indexes with metadata search.
    
    Args:
        query: The user's original question/prompt to the AI
        index_ids: List of index IDs to search in, preferably from metadata search results or the complete 
                  result from search_best_maching_index_based_on_metdata
    """
    # Handle case where the complete result from first function is passed
    if isinstance(index_ids, dict) and "top_match_ids" in index_ids:
        index_ids = index_ids.get("top_match_ids")
        
    if not index_ids:
        return {"error": "No index IDs provided for context search"}
    
    results = []
    
    # For each index, perform a semantic search
    from services.llm.content import get_content_metadata
    from services.notion_service import download_blob_to_memory
    from services.storage_service import get_storage_client
    import os
    
    for index_id in index_ids:
        try:
            # Get search results directly from the vector index
            client = get_storage_client()
            bucket_name = os.getenv("GCS_BUCKET_NAME") or os.environ.get('GCS_BUCKET_NAME')
            bucket = client.bucket(bucket_name)
            
            # Path to the vector index
            vector_index_path = f"cache/vector_index_{index_id}.pkl"
            
            # Try to load the existing vector index
            if bucket.blob(vector_index_path).exists():
                # Load the vector index
                index = download_blob_to_memory(vector_index_path)
                if not index:
                    continue
                    
                # Create a query engine with similarity search
                query_engine = index.as_query_engine(similarity_top_k=5)
                
                # Get the response with similarity scores
                response = query_engine.query(query)
                
                # Extract the text and similarity scores from the source nodes
                result_text = str(response)
                
                # Extract similarity scores from source nodes if available
                similarity_score = 0.0
                source_nodes = getattr(response, 'source_nodes', [])
                if source_nodes and len(source_nodes) > 0:
                    # Get the highest similarity score from the source nodes
                    similarity_score = max((node.score or 0.0) for node in source_nodes)
                else:
                    # Fallback if no source nodes or scores
                    similarity_score = min(len(result_text) / 1000, 1.0)  # Normalize by length, max 1.0
                
                results.append({
                    "index_id": index_id,
                    "content": result_text,
                    "relevance_score": similarity_score,
                    "similarity": float(similarity_score)
                })
        except Exception as e:
            results.append({
                "index_id": index_id,
                "error": str(e)
            })
    
    # Sort results by relevance score
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    
    if results:
        # Take the 5 best results (or fewer if less available)
        top_results = results[:5]
        return {
            "best_result": results[0] if results else None,
            "top_results": top_results,  # Include top 5 results with similarity scores
            "all_results": results,
            "total_results": len(results)
        }
    
    return {"error": "No relevant context found in the provided indexes"}
    
async def search_web(
    query: str,
) -> dict:
    """Search the web for information.
    Use this as a LAST RESORT only if the information cannot be found in our indexes."""
    
    client = AsyncTavilyClient(api_key=tavily_api_key)
    return str(await client.search(query))
    
    
# Convert functions to FunctionTool objects
metadata_search_tool = FunctionTool.from_defaults(fn=search_best_maching_index_based_on_metdata)
context_search_tool = FunctionTool.from_defaults(fn=search_best_context)
web_search_tool = FunctionTool.from_defaults(fn=search_web)

print("[QUERY AGENT] Created function tools for agent")

query_agent = GenericFunctionCallingAgent.from_tools(
    tools=[metadata_search_tool, context_search_tool, web_search_tool],
    llm=llm,
    verbose=True,
    allow_parallel_tool_calls=False, 
    system_prompt="""You are an agent that retrieves information by following a specific process:
                1. FIRST, use search_best_maching_index_based_on_metdata to identify relevant indexes
                2. SECOND, use search_best_context to search within those indexes
                3. ONLY if you cannot find information in the indexes, use search_web as a last resort

                Always follow this exact sequence when searching. Do not skip steps or change the order.
                """
)