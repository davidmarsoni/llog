from llama_index.core.agent import FunctionCallingAgent as GenericFunctionCallingAgent
from llama_index.core.tools import FunctionTool
from services.llm.agents.utils import llm
import re

# Define review functions
def check_context_preservation(original_prompt: str, research_info: str, answer: str) -> str:
    """
    Check if the answer preserves the context from the original prompt and research information.
    
    Args:
        original_prompt: The original question or prompt
        research_info: The research information that was used to write the answer
        answer: The final answer that needs to be reviewed
        
    Returns:
        A review of whether the context is preserved in the answer
    """
    return "This function will be executed by the LLM"

def check_instruction_compliance(answer: str, instruction_type: str, instruction_value: str) -> str:
    """
    Check if the answer follows specific instructions like word count limits.
    
    Args:
        answer: The final answer that needs to be reviewed
        instruction_type: Type of instruction (e.g., "word_count", "format_type")
        instruction_value: The expected value for the instruction (e.g., "5", "bullet_points")
        
    Returns:
        A review of whether the instruction was followed
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
review_system_prompt = """You are an expert review agent that carefully evaluates answers written by other agents.
Your job is to:

1. Check if the answer preserves the context from the original prompt and research information
2. Verify that all specific instructions in the prompt were followed (e.g., word limits, formatting)
3. Identify any factual errors or inconsistencies with the provided research
4. Evaluate if the answer directly addresses the original question

When reviewing answers, pay special attention to:
- Word count requirements (e.g., "write in 5 words", "summarize in 10 words")
- Formatting instructions (e.g., "use bullet points", "write in paragraphs")
- Completeness of the answer relative to the original question
- Accuracy of information compared to the research provided

Provide a clear, objective assessment with specific examples of what needs improvement.
"""

# Define the review agent with enhanced tools and system prompt
review_agent = GenericFunctionCallingAgent.from_tools(
    tools=[context_tool, instruction_tool, word_count_tool],
    llm=llm,
    verbose=True,
    allow_parallel_tool_calls=True,
    system_prompt=review_system_prompt
)

