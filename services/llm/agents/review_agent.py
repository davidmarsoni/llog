from llama_index.core.agent import FunctionCallingAgent as GenericFunctionCallingAgent
from llama_index.core.tools import FunctionTool
from services.llm.agents.utils import llm
from tavily import AsyncTavilyClient 
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()
tavily_api_key = os.getenv("TAVILY_API_KEY") 

# Define the review agent 
review_agent = GenericFunctionCallingAgent.from_tools(
    tools=[],
    llm=llm,
    verbose=False,
    allow_parallel_tool_calls=True,
    system_prompt="You are an agent that reviews a answer written by a different agent."
)

# Get the returned answer from the write agent
# "Evaluate" the following answer and give a feedback on it.
# If ok -> validate it and return the answer.
# If not ok -> give a feedback to the write agent to improve the answer.

async def review_and_feedback(write_agent, initial_prompt: str) -> str:
    max_retries = 3
    retries = 0
    current_prompt = initial_prompt

    while retries < max_retries:
        # Get the response from the write agent
        write_response = write_agent.chat(current_prompt)
        
        # Review the response
        review_prompt = (f"Evaluate the following answer:\n\n"
            f"Initial Prompt:\n{initial_prompt}\n\n"
            f"{write_response}\n\n"
            f"If the answer is acceptable, respond with 'VALIDATE'."
            f"If the answer is not acceptable, respond with 'IMPROVE' and provide feedback on how to improve it."
        )
        review_result = review_agent.chat(review_prompt)
        
        if "VALIDATE" in review_result:
            # If validated, return the response
            return write_response
        elif "IMPROVE" in review_result:
            # If rewrite is needed, update the prompt with feedback
            feedback = review_result.replace("IMPROVE", "").strip()
            print(f"Feedback from review agent: {feedback}")

            # Use the feedback to rewrite the response
            current_prompt = (
                f"Rewrite the following answer based on this feedback:\n\n"
                f"Initial Prompt:\n{initial_prompt}\n\n"
                f"Answer:\n{write_response}\n\n"
                f"Feedback:\n{feedback}"
            )
            retries += 1
        else:
            # Handle unexpected errors
            raise Exception(f"Unexpected response from review agent: {review_result}")
    
    raise Exception("Maximum retries reached. Unable to validate the response.")