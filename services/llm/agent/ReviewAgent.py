from services.llm_service import get_llm_response
class ReviewAgent:
    """Reviews and refines content."""
    def run(self, content):
        print(f"\n======= ReviewAgent AGENT START =======")
        print(f"Input content (first 100 chars): {content[:100]}...")
        
         # Use LLM to review and refine the content without additional context
        review_prompt = f"""Review and improve the following response for clarity, accuracy, 
        and completeness. Make sure it provides helpful information and is well-structured:

        CONTENT TO REVIEW:
        {content}

        Please return the improved version only without any explanation or additional comments.
        """
        try:
            # Call LLM to review content
            review_response = get_llm_response(
                query=review_prompt,
                chat_history=[],
                use_context=False
            )
            
            final_result = review_response.get("answer", "Failed to review content.")
            
        except Exception as e:
            print(f"Error in content review: {str(e)}")
            final_result = content  # Return original content if review fails
        

        # Log the final output
        print(f"Final reviewed content (first 150 chars): {final_result[:150]}...")
        print(f"======= ReviewAgent AGENT COMPLETE =======\n")
        return final_result