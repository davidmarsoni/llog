from services.llm_service import get_llm_response
class WriteAgent:
    """Generates content based on research."""
    def run(self, research_summary):
        print(f"\n======= WriteAgent AGENT START =======")
        print(f"Input research (first 100 chars): {research_summary[:100]}...")

        # Generate content based on research
        result = f"Generated content based on: {research_summary}"

         # Use LLM to generate well-structured content based on research without additional context
        write_prompt = f"""Based on the following research information, write a comprehensive, 
        well-structured response that directly answers the user's query:

        RESEARCH INFORMATION:
        {research_summary}

        Please provide a clear, concise, and helpful answer, return the current version only without any explanation or additional comments.
        """
        
        try:
            # Call LLM to generate content
            write_response = get_llm_response(
                query=write_prompt,
                chat_history=[],
                use_context=False  # We don't need additional context since research is already provided
            )
            
            result = write_response.get("answer", "Failed to generate content based on research.")
            
        except Exception as e:
            print(f"Error in content generation: {str(e)}")
            result = f"Error generating content: {str(e)}"
        

        # Log the generated content 
        print(f"Generated content (first 150 chars): {result[:150]}...")
        print(f"======= WriteAgent AGENT COMPLETE =======\n")
        return result