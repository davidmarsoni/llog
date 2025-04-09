from llama_index.core.agent import FunctionCallingAgent as GenericFunctionCallingAgent
from llama_index.core.tools import FunctionTool
from services.llm.agents.utils import llm
from tavily import AsyncTavilyClient 
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

write_agent = GenericFunctionCallingAgent.from_tools(
    tools=[],
    llm=llm,
    verbose=False,
    allow_parallel_tool_calls=False,
    system_prompt="""You are an agent that writes structured, well-organized answers based on research provided by another agent.
                Instructions:
                1. Structure your response using proper Markdown formatting
                2. Use headings (## and ###) to organize content logically
                3. Use bullet points or numbered lists where appropriate
                4. Highlight important concepts using **bold** or *italic* text
                5. Use code blocks with syntax highlighting when presenting code or technical snippets
                6. Include relevant quotes from research using > blockquotes
                7. Keep paragraphs concise and focused on one idea
                8. Adapt your structure based on the context and type of question
                9. Always provide a brief introduction and conclusion
                10. Maintain a clear and professional tone throughout

                Always analyze the context and research data thoroughly before structuring your response, and ensure your answer directly addresses the original question.
                """
)