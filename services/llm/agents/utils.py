from llama_index.llms.openai import OpenAI
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY") 

llm = OpenAI(model="gpt-4o-mini", api_key=api_key)
