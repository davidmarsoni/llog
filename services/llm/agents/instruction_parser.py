"""
Simple instruction parser using LLM to detect requirements in prompts.
"""
from services.llm.agents.utils import llm
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InstructionParser")

def analyze_prompt_requirements(prompt: str) -> dict:
    """
    Uses the LLM to detect word count requirements and context preservation needs in any language.
    
    Args:
        prompt: The original prompt/query
        
    Returns:
        Dict with instructions for the review agent
    """
    try:
        # Simple prompt to detect requirements
        detection_prompt = f"""
        Analyze this prompt: "{prompt}"
        
        If it contains a word count requirement (like "write in 5 words", "respond in 10 words", etc.), 
        in ANY language, respond with:
        WORD_COUNT: [number]
        
        If it asks to preserve specific context or information, respond with:
        CONTEXT: [brief explanation]
        
        If it has both, include both lines.
        If it has neither, respond with:
        NONE
        """
        
        response = llm.complete(detection_prompt).text.strip()
        logger.info(f"Prompt analysis result: {response}")
        
        result = {}
        
        # Parse the simple response format
        if "WORD_COUNT:" in response:
            try:
                word_count_line = [line for line in response.split('\n') if "WORD_COUNT:" in line][0]
                count = word_count_line.split("WORD_COUNT:")[1].strip()
                if count.isdigit():
                    result["word_count_instruction"] = f"Ensure the answer is exactly {count} words long."
            except:
                pass
                
        if "CONTEXT:" in response:
            try:
                context_line = [line for line in response.split('\n') if "CONTEXT:" in line][0]
                context = context_line.split("CONTEXT:")[1].strip()
                result["context_instruction"] = f"Ensure the answer preserves this context: {context}"
            except:
                pass
                
        return result
        
    except Exception as e:
        logger.error(f"Error in prompt analysis: {str(e)}")
        return {}
