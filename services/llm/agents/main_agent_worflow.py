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
from llama_index.core.llms import ChatMessage, MessageRole
import traceback
import logging
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainAgentWorkflow")

class MainAgentWorflow(Workflow):
    
    @step
    async def setup(self, ctx: Context, ev: StartEvent) -> QueryEvent:
        logger.info("====== SETUP STEP STARTED ======")
        try:
            # Store the query_agent from the event
            self.query_agent = ev.query_agent
            self.write_agent = ev.write_agent
            self.review_agent = ev.review_agent
            
            logger.info(f"Agents initialized: query_agent={self.query_agent.__class__.__name__}, write_agent={self.write_agent.__class__.__name__}, review_agent={self.review_agent.__class__.__name__}")
            
            # Initialize rewriting counter and store the original prompt
            await ctx.set("rewrite_count", 0)
            await ctx.set("prompt", ev.prompt)
            await ctx.set("index_ids", ev.index_ids)
            
            # Process message history if available
            message_history = getattr(ev, "message_history", [])
            await ctx.set("message_history", message_history)
            
            logger.info(f"Context set: prompt='{ev.prompt[:50]}...', index_ids={ev.index_ids}")
            logger.info(f"Message history available: {len(message_history) > 0}")
            logger.info("====== SETUP STEP COMPLETED ======")
            
            # Pass both prompt and index_ids to the QueryEvent
            return QueryEvent(prompt=ev.prompt, index_ids=ev.index_ids)
        except Exception as e:
            logger.error(f"Error in setup: {str(e)}\n{traceback.format_exc()}")
            raise

    @step
    async def query(self, ctx: Context, ev: QueryEvent) -> WriteEvent:
        logger.info("====== QUERY STEP STARTED ======")
        try:
            await ctx.set("prompt", ev.prompt)
            # Get available indexes from context if provided in the event
            index_ids = ev.index_ids
            
            # Retrieve message history if available
            message_history = await ctx.get("message_history", [])
            
            # Debug print to check what indexes are available
            logger.info(f"[MAIN AGENT] Using indexes: {index_ids}")
            logger.info(f"[MAIN AGENT] Message history available: {len(message_history) > 0} with {len(message_history)} messages")
            
            # Create query with conversation context if history exists
            query_prompt = f"Gather some information that another agent will use to write an answer about this topic: <topic>{ev.prompt}</topic>. "
            
            # Include conversation history if available
            if message_history and len(message_history) > 0:
                history_context = "\n".join([f"{msg.role}: {msg.content}" for msg in message_history])
                query_prompt += f"\n\nTake into account the following conversation history:\n<conversation_history>\n{history_context}\n</conversation_history>\n"
                logger.info("Including conversation history in query")
            
            query_prompt += "Just include the facts without making it into a full answer. " + \
                f"Use these index IDs for searching: {index_ids}"
            
            logger.info("Sending query to query agent...")
            # Adjust the query to include index_ids in a format the agent can understand
            result = self.query_agent.chat(query_prompt)
            
            logger.info(f"Research result received (first 100 chars): {str(result)[:100]}...")
            await ctx.set("research", str(result))
            logger.info("====== QUERY STEP COMPLETED ======")
            return WriteEvent()
        except Exception as e:
            logger.error(f"Error in query: {str(e)}\n{traceback.format_exc()}")
            raise

    @step
    async def write(self, ctx: Context, ev: WriteEvent | RewriteEvent) -> ReviewEvent:
        logger.info("====== WRITE STEP STARTED ======")
        try:
            original_prompt = await ctx.get("prompt")
            research_info = await ctx.get("research")
            message_history = await ctx.get("message_history", [])
            
            logger.info(f"Retrieved from context: prompt='{original_prompt[:50]}...', research_info (first 100 chars): '{research_info[:100]}...'")
            logger.info(f"Message history available: {len(message_history) > 0} with {len(message_history)} messages")
            
            prompt = (
                f"Write a detailed, clear, and direct answer addressing the question: "
                f"<question>{original_prompt}</question>. Use the following research as supporting information: "
                f"<research>{research_info}</research>"
            )
            
            # Include conversation history if available
            if message_history and len(message_history) > 0:
                history_context = "\n".join([f"{msg.role}: {msg.content}" for msg in message_history])
                prompt += f"\n\nTake into account the following conversation history to ensure your response is contextually relevant:\n<conversation_history>\n{history_context}\n</conversation_history>\n"
                logger.info("Including conversation history in write prompt")
            
            if isinstance(ev, RewriteEvent):
                logger.info("Rewrite event detected, adding review feedback to prompt")
                prompt += (
                    f" Note: This answer has been reviewed and the reviewer provided the following feedback that "
                    f"should be taken into account: <review>{ev.review}</review>"
                )
            
            logger.info("Sending prompt to write agent...")
            result = self.write_agent.chat(prompt)
            
            logger.info(f"Write result received (first 100 chars): {str(result)[:100]}...")
            logger.info("====== WRITE STEP COMPLETED ======")
            return ReviewEvent(answer=str(result))
        except Exception as e:
            logger.error(f"Error in write: {str(e)}\n{traceback.format_exc()}")
            raise

    @step
    async def review(self, ctx: Context, ev: ReviewEvent) -> StopEvent | RewriteEvent:
        logger.info("====== REVIEW STEP STARTED ======")
        try:
            logger.info(f"Answer to review (first 100 chars): {ev.answer[:100]}...")
            logger.info("Sending answer to review agent...")
            
            original_prompt = await ctx.get("prompt")
            research_info = await ctx.get("research")
            rewrite_count = await ctx.get("rewrite_count")
            rewrite_count += 1
            await ctx.set("rewrite_count", rewrite_count)
            
            # Log the current rewrite count for debugging
            logger.info(f"Current rewrite count: {rewrite_count}")
            
            # Use LLM to detect special instructions in the prompt in any language
            from services.llm.agents.instruction_parser import analyze_prompt_requirements
            
            # Get all requirements in one simple call (no await as it's not async)
            requirements = analyze_prompt_requirements(original_prompt)
            word_count_instruction = requirements.get('word_count_instruction')
            context_instruction = requirements.get('context_instruction')
            
            # Prepare a comprehensive review prompt
            review_prompt = f"""Review the following answer based on the original prompt and research information:
            
            Original Prompt: {original_prompt}

            Research Information: {research_info}

            Answer to Review: {ev.answer}

            Please evaluate:
            1. Does the answer preserve the context from the original prompt and research?
            2. Does the answer directly address the question asked?
            3. Is the information accurate based on the research provided?
            {f'4. {word_count_instruction}' if word_count_instruction else ''}

            """
            result = self.review_agent.chat(review_prompt)
            logger.info(f"Review result received: {str(result)}")
            
            # Check if we've already hit the max rewrite count BEFORE asking for another review
            if rewrite_count >= 2:  # Changed from > 2 to >= 2 to limit to exactly 1 rewrite
                logger.info("Maximum rewrite attempts reached (2). Finishing the flow without further rewrites.")
                logger.info("====== REVIEW STEP COMPLETED (MAX REWRITES) ======")
                return StopEvent(result=ev.answer)
                
            logger.info("Asking if we should retry based on the review...")
            
            try_again = llm.complete(
                f"This is a review of an answer written by an agent. If you think this review is bad enough "
                f"that the agent should try again, respond with just the word RETRY. If the review is good, reply "
                f"with just the word CONTINUE. Here's the review: <review>{str(result)}</review>"
            )
            logger.info(f"Decision on whether to retry: {try_again.text}")
            
            if try_again.text == "RETRY":
                logger.info("Reviewer said try again - starting rewrite process")
                logger.info("====== REVIEW STEP COMPLETED (RETRY) ======")
                return RewriteEvent(
                    review=(
                        f"{str(result)}\n"
                        f"Original prompt: {original_prompt}\n"
                        f"Research info: {research_info}"
                    )
                )
            else:
                logger.info("Reviewer thought it was good! Finishing the flow.")
                logger.info("====== REVIEW STEP COMPLETED (SUCCESS) ======")
                return StopEvent(result=ev.answer)
        except Exception as e:
            logger.error(f"Error in review: {str(e)}\n{traceback.format_exc()}")
            raise