
from services.llm_service import get_llm_response

class QueryResearch:
    """Researches information related to a query."""
    def run(self, query, use_content=False, content_ids=None):
        print(f"\n======= QueryResearch AGENT START =======")
        print(f"Query: {query}")
        print(f"Using content: {use_content}, Content IDs: {content_ids}")
    
        
        # Use the same LLM service but for research purposes
        if use_content and content_ids:
            try:
                # Call the same LLM service but with a research prompt
                research_prompt = f"Please research the following query: {query}"
                print(f"Research prompt: {research_prompt}")
            
                
                research_response = get_llm_response(
                    query=research_prompt,
                    chat_history=[],
                    index_ids=content_ids,
                    use_context=True
                )
                research_result = research_response.get("answer", "No research results found.")
            except Exception as e:
                print(f"Error in research: {str(e)}")
                research_result = f"Research error: {str(e)}"
        else:
            research_result = f"Research results for: {query} (without additional context)"
            
        # Log the full output so we can see exactly what this agent produces
        print(f"Research result (first 150 chars): {research_result[:150]}...")
        print(f"======= QueryResearch AGENT COMPLETE =======\n")
        return research_result