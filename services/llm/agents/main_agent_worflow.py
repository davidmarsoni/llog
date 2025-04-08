from llama_index.core.workflow import Context
from llama_index.llms.openai import OpenAI
from llama_index.core.workflow import (
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from services.llm.agents.events import (
    QueryEvent,
    ReviewEvent,
    RewriteEvent,
    WriteEvent,
)
from services.llm.agents.utils import llm

class MainAgentWorflow(Workflow):
    
    @step
    async def setup(self, ctx: Context, ev: StartEvent) -> QueryEvent:
        # Store the query_agent from the event
        self.query_agent = ev.query_agent
        
        # Initialize rewriting counter and store the original prompt
        await ctx.set("rewrite_count", 0)
        await ctx.set("prompt", ev.prompt)
        await ctx.set("index_ids", ev.index_ids)
        
        # Pass both prompt and index_ids to the QueryEvent
        return QueryEvent(prompt=ev.prompt, index_ids=ev.index_ids)

    @step
    async def query(self, ctx: Context, ev: QueryEvent) -> StopEvent:
        await ctx.set("prompt", ev.prompt)
        # Get available indexes from context if provided in the event
        index_ids = ev.index_ids
        
        # Debug print to check what indexes are available
        print(f"[MAIN AGENT] Using indexes: {index_ids}")
        
        # Adjust the query to include index_ids in a format the agent can understand
        result = self.query_agent.chat(
            f"Gather some information that another agent will use to write an answer about this topic: <topic>{ev.prompt}</topic>. "
            "Just include the facts without making it into a full answer. "
            f"Use these index IDs for searching: {index_ids}"
        )
        print("Research result:", result)
        await ctx.set("research", str(result))
        return StopEvent()

   