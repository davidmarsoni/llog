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
        print(f"[CONTEXT SEARCH] Extracted top_match_ids from dictionary: {index_ids}")
        
    if not index_ids:
        return {"error": "No index IDs provided for context search"}
    
    print(f"[CONTEXT SEARCH] Starting context search for query: '{query}'")
    print(f"[CONTEXT SEARCH] Searching through {len(index_ids)} indexes: {index_ids}")
    
    results = []
    
    # For each index, perform a semantic search
    from services.llm.content import get_content_metadata
    from services.notion_service import download_blob_to_memory
    from services.storage_service import get_storage_client
    import os
    
    for index_id in index_ids:
        try:
            print(f"[CONTEXT SEARCH] Processing index: {index_id}")
            # Get search results directly from the vector index
            client = get_storage_client()
            bucket_name = os.getenv("GCS_BUCKET_NAME") or os.environ.get('GCS_BUCKET_NAME')
            bucket = client.bucket(bucket_name)
            
            # Path to the vector index
            vector_index_path = f"cache/vector_index_{index_id}.pkl"
            print(f"[CONTEXT SEARCH] Looking for vector index at: {vector_index_path}")
            
            # Try to load the existing vector index
            if bucket.blob(vector_index_path).exists():
                print(f"[CONTEXT SEARCH] Vector index found for {index_id}")
                # Load the vector index
                index = download_blob_to_memory(vector_index_path)
                if not index:
                    print(f"[CONTEXT SEARCH] Failed to load vector index for {index_id}")
                    continue
                    
                print(f"[CONTEXT SEARCH] Creating query engine for {index_id}")
                # Create a query engine with similarity search
                query_engine = index.as_query_engine(similarity_top_k=5)
                
                print(f"[CONTEXT SEARCH] Executing query against {index_id}")
                # Get the response with similarity scores
                response = query_engine.query(query)
                
                # Extract the text and similarity scores from the source nodes
                result_text = str(response)
                print(f"[CONTEXT SEARCH] Got response for {index_id}, length: {len(result_text)}")
                
                # Extract similarity scores from source nodes if available
                similarity_score = 0.0
                source_nodes = getattr(response, 'source_nodes', [])
                if source_nodes and len(source_nodes) > 0:
                    # Get the highest similarity score from the source nodes
                    similarity_score = max((node.score or 0.0) for node in source_nodes)
                    print(f"[CONTEXT SEARCH] Found {len(source_nodes)} source nodes for {index_id}, best score: {similarity_score}")
                else:
                    # Fallback if no source nodes or scores
                    similarity_score = min(len(result_text) / 1000, 1.0)  # Normalize by length, max 1.0
                    print(f"[CONTEXT SEARCH] No source nodes for {index_id}, using fallback score: {similarity_score}")
                
                results.append({
                    "index_id": index_id,
                    "content": result_text,
                    "relevance_score": similarity_score,
                    "similarity": float(similarity_score)
                })
            else:
                print(f"[CONTEXT SEARCH] Vector index not found for {index_id}")
        except Exception as e:
            print(f"[CONTEXT SEARCH] ERROR processing index {index_id}: {str(e)}")
            results.append({
                "index_id": index_id,
                "error": str(e)
            })
    
    # Sort results by relevance score
    results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
    print(f"[CONTEXT SEARCH] Found {len(results)} results, sorted by relevance")
    
    if results:
        # Take the 5 best results (or fewer if less available)
        top_results = results[:5]
        print(f"[CONTEXT SEARCH] Returning top {len(top_results)} results")
        return {
            "best_result": results[0] if results else None,
            "top_results": top_results,  # Include top 5 results with similarity scores
            "all_results": results,
            "total_results": len(results)
        }
    
    print("[CONTEXT SEARCH] No relevant context found in any index")
    return {"error": "No relevant context found in the provided indexes"}
    
async def search_web(
    query: str,
) -> dict:
    """Search the web for information.
    Use this as a LAST RESORT only if the information cannot be found in our indexes."""
    
    print(f"[WEB SEARCH] Searching web for query: '{query}'")
    
    try:
        client = AsyncTavilyClient(api_key=tavily_api_key)
        if not tavily_api_key:
            print("[WEB SEARCH] ERROR: No Tavily API key found")
            return {"error": "No Tavily API key configured"}
            
        print("[WEB SEARCH] Sending request to Tavily API")
        search_results = await client.search(query)
        
        # Check if we got valid results
        if not search_results:
            print("[WEB SEARCH] No results returned from Tavily API")
            return {"error": "No web search results found"}
            
        result_count = len(search_results) if isinstance(search_results, list) else "N/A"
        print(f"[WEB SEARCH] Received {result_count} results from Tavily API")
        
        # Convert to string for returning to agent
        str_results = str(search_results)
        print(f"[WEB SEARCH] Result length: {len(str_results)} characters")
        
        return str_results
        
    except Exception as e:
        error_msg = str(e)
        print(f"[WEB SEARCH] ERROR during web search: {error_msg}")
        return {"error": f"Web search failed: {error_msg}"}


async def analyze_query_need_for_search(query: str, conversation_history: list = None) -> dict:
    """
    Analyze if we can answer based on history or if search is needed.
    
    Args:
        query: The user's question/prompt
        conversation_history: Previous conversation messages if available
    
    Returns:
        Dictionary with analysis result
    """
    print(f"[ANALYZE QUERY] Analyzing query: '{query}'")
    
    # If no conversation history, search is needed
    if not conversation_history or len(conversation_history) == 0:
        print("[ANALYZE QUERY] No conversation history available - search needed")
        return {
            "needs_search": True,
            "reason": "No conversation history available to answer the query"
        }
    
    print(f"[ANALYZE QUERY] Found conversation history with {conversation_history} messages")
  
    # Format conversation history for the LLM
    history_text = ""
    processed_messages = 0
    
    for msg in conversation_history:
        # Check if msg is a dict with 'role' and 'content' keys
        if isinstance(msg, dict) and 'role' in msg and 'content' in msg:
            history_text += f"{msg['role']}: {msg['content']}\n"
            processed_messages += 1
        # Otherwise check if it has roles and content attributes
        elif hasattr(msg, 'roles') and hasattr(msg, 'content'):
            history_text += f"{msg.roles}: {msg.content}\n"
            processed_messages += 1
        else:
            print(f"[ANALYZE QUERY] WARNING: Message format not recognized: {type(msg)}")
                
    print(f"[ANALYZE QUERY] Successfully processed {processed_messages} messages for history")
    print(f"[ANALYZE QUERY] Total history length: {history_text} characters")
    
    # Ask LLM if the history contains enough information to answer
    analysis_prompt = f"""Based on the conversation history below, determine if you can answer the user's query 
    without performing any additional search. 
    
    User query: {query}
    
    Conversation history:
    {history_text}
    
    Can you answer this query using the information in the conversation history event partially?
    Answer with YES or NO, followed by a brief explanation.
    """
    
    print(f"[ANALYZE QUERY] Sending LLM analysis prompt with {len(history_text)} chars of history")
    response = llm.complete(analysis_prompt)
    answer = response.text.strip()
    print(f"[ANALYZE QUERY] Received LLM response of {len(answer)} chars")
    print(f"[ANALYZE QUERY] Analysis result: {answer}")
    
    # Parse response
    needs_search = True
    if answer.startswith("YES"):
        needs_search = False
        print("[ANALYZE QUERY] LLM determined we CAN answer from history (needs_search=False)")
    else:
        print("[ANALYZE QUERY] LLM determined we CANNOT answer from history (needs_search=True)")
    
    result = {
        "needs_search": needs_search,
        "reason": answer,
        "history_available": True
    }
    print(f"[ANALYZE QUERY] Returning result: {result}")
    return result
    
# Convert functions to FunctionTool objects
analyze_query_need_for_search_tool = FunctionTool.from_defaults(fn=analyze_query_need_for_search)
metadata_search_tool = FunctionTool.from_defaults(fn=search_best_maching_index_based_on_metdata)
context_search_tool = FunctionTool.from_defaults(fn=search_best_context)
web_search_tool = FunctionTool.from_defaults(fn=search_web)


query_agent = GenericFunctionCallingAgent.from_tools(
    tools=[
        analyze_query_need_for_search_tool,
        metadata_search_tool, 
        context_search_tool, 
        web_search_tool
    ],
    llm=llm,
    verbose=False,
    allow_parallel_tool_calls=False, 
    system_prompt="""You are an agent that retrieves information by following these specific steps:
                
                1. FIRST, use analyze_query_need_for_search to determine if we can answer based on conversation history
                   - If the response shows needs_search=False, return the answer from history without searching
                   - If needs_search=True, continue to step 2
                
                2. Check if index_ids are provided in your input:
                   - If index_ids are provided, proceed to step 3
                   - If NO index_ids are provided, skip to step 5 (web search)
                
                3. If index_ids exist, use search_best_maching_index_based_on_metdata to identify relevant indexes
                
                4. Then use search_best_context to search within those indexes from step 3
                   - If this finds relevant information, return it
                   - If no relevant information is found, proceed to step 5
                
                5. ONLY as a LAST RESORT use search_web
                
                ALWAYS follow this decision flow. Do not skip steps or change the order.
                When returning information, summarize it clearly and concisely.
                """
)