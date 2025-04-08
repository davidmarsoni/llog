from llama_index.core.agent import FunctionCallingAgent as GenericFunctionCallingAgent
from llama_index.core.tools import FunctionTool
from services.llm.agents.utils import llm
from tavily import AsyncTavilyClient 
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
tavily_api_key = os.getenv("TAVILY_API_KEY") 


async def write_agent(
    context: str,
    query: str,
    tavily_api_key: str = tavily_api_key,
) -> str:
    """Write agent function to generate content based on context and query."""
    
    # Initialize the Tavily client
    client = AsyncTavilyClient(api_key=tavily_api_key)

    # Fetch context
    context = await get_context(context)
    print("Fetched context:", context)
    # Organize context
    organized_context = await organize_context(context)
    print("Organized context:", organized_context)
    # Write prompt
    prompt = await write_prompt(organized_context)
    print("Generated prompt:", prompt)
    # Generate content using the LLM
    output = await llm(prompt)
    print("Generated output:", output)
    
    # Validate output
    is_valid = await validate_output(output)
    if not is_valid:
        output = await rewrite(output)
        print("Rewritting output:", output)
    

    return output

# python
async def get_context(context: str) -> dict:
    print("==STARTING WRITE AGENT==")
    print("Getting context:", context)
    return {"context": context, "metadata": {"source": "query_agent"}}

async def organize_context(context: dict) -> dict:
    print("Organizing context:", context)
    organized = {
        "key_points": context.get("context", "").split(". "),
        "metadata": context.get("metadata", {})
    }
    return organized

async def write_prompt(organized_context: dict) -> str:
    print("Writing prompt from organized context:", organized_context)
    key_points = organized_context.get("key_points", [])
    prompt = "Write an article based on the following points:\n"
    for i, point in enumerate(key_points, 1):
        prompt += f"{i}. {point}\n"
    return prompt

async def validate_output(output: str) -> bool:
    """Validate the generated content."""
    # Example: Check if the output meets basic criteria
    return len(output) > 50  # Ensure the output is not too short

async def rewrite(output: str) -> str:
    print("Rewriting output:", output)
    print("==END OF WRITE AGENT==")
    # Example: Add more details to the output
    return output + "\n\nPlease expand on the above points for more detail."