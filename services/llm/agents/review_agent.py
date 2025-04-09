from llama_index.core.agent import FunctionCallingAgent as GenericFunctionCallingAgent
from llama_index.core.tools import FunctionTool
from services.llm.agents.utils import llm
import re

# Define review functions
def check_context_preservation(original_prompt: str, research_info: str, answer: str) -> str:
    """
    Identify ONLY issues where the answer fails to preserve context from the original prompt and research.
    
    Args:
        original_prompt: The original question or prompt
        research_info: The research information that was used to write the answer
        answer: The final answer that needs to be reviewed
        
    Returns:
        ONLY issues found with context preservation, or a brief approval message if no issues
    """
    return "This function will be executed by the LLM"

def check_instruction_compliance(answer: str, instruction_type: str, instruction_value: str) -> str:
    """
    Identify ONLY issues where the answer fails to follow specific instructions.
    
    Args:
        answer: The final answer that needs to be reviewed
        instruction_type: Type of instruction (e.g., "word_count", "format_type")
        instruction_value: The expected value for the instruction (e.g., "5", "bullet_points")
        
    Returns:
        ONLY issues found with instruction compliance, or a brief approval message if no issues
    """
    return "This function will be executed by the LLM"

def count_words(text: str) -> int:
    """
    Count the number of words in the given text.
    
    Args:
        text: The text to count words in
        
    Returns:
        The number of words in the text
    """
    # Clean the text and split by whitespace
    words = re.findall(r'\b\w+\b', text.lower())
    return len(words)

# Create function tools
context_tool = FunctionTool.from_defaults(fn=check_context_preservation)
instruction_tool = FunctionTool.from_defaults(fn=check_instruction_compliance)
word_count_tool = FunctionTool.from_defaults(fn=count_words)

# Define detailed system prompt for the review agent
review_system_prompt = """You are an expert review agent that identifies only issues or problems with answers or research.
Your job is focused on:

1. ONLY point out things that are WRONG or missing - do not waste time describing what is correct
2. If the answer or research is practically correct, rephrase it slightly if needed and terminate
3. Only identify factual errors or inconsistencies with the provided research
4. Only highlight if critical instructions were not followed

Focus exclusively on problems:
- Word count requirements that were violated (e.g., exceeding specified limits)
- Critical formatting instructions that were ignored
- Missing answers to parts of the original question
- Factual errors compared to the provided research

Be concise and direct. If everything is sufficiently correct, just make minor improvements and approve it.
DO NOT provide a comprehensive evaluation if the content is already acceptable.
"""

# Define the review agent with enhanced tools and system prompt
review_agent = GenericFunctionCallingAgent.from_tools(
    tools=[context_tool, instruction_tool, word_count_tool],
    llm=llm,
    verbose=True,
    allow_parallel_tool_calls=False,
    system_prompt=review_system_prompt
)

