import traceback
import logging
from llama_index.core.workflow import Context
from llama_index.core.workflow import (
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from services.llm.agents.events import (
    QueryEvent,
    ReviewEvent,
    WriteEvent,
)
from services.llm.agents.utils import llm
from services.llm.agents.instruction_parser import analyze_prompt_requirements

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
    async def query(self, ctx: Context, ev: QueryEvent) -> ReviewEvent:
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
            
            # Now we go directly to the review step instead of write
            original_prompt = await ctx.get("prompt")
            research_info = str(result)
            
            logger.info("====== PREPARING FOR PRE-WRITING REVIEW ======")
            # No answer yet, but we'll review the requirements and research
            return ReviewEvent(answer="", is_pre_write_review=True)
        except Exception as e:
            logger.error(f"Error in query: {str(e)}\n{traceback.format_exc()}")
            raise

    @step
    async def review(self, ctx: Context, ev: ReviewEvent) -> WriteEvent | StopEvent:
        logger.info("====== REVIEW STEP STARTED ======")
        try:
            original_prompt = await ctx.get("prompt")
            research_info = await ctx.get("research")
            
            # Check if this is a pre-write review (happens before writing) or post-write review
            is_pre_write = getattr(ev, "is_pre_write_review", False)
            
            if is_pre_write:
                logger.info("This is a PRE-WRITE review to guide the writing process")
                
                # Get all requirements in one simple call (no await as it's not async)
                requirements = analyze_prompt_requirements(original_prompt)
                word_count_instruction = requirements.get('word_count_instruction')
                context_instruction = requirements.get('context_instruction')
                
                # Prepare a review prompt that will identify only issues with the research
                review_prompt = f"""Review the following research information and identify ONLY issues or problems:
                
                Original Prompt: {original_prompt}
                Research Information: {research_info}
                
                ONLY point out:
                1. Missing information needed to answer the question
                2. Factual errors or inconsistencies in the research
                3. Any critical context that is absent
                {f'4. Issues with meeting: {word_count_instruction}' if word_count_instruction else ''}
                {f'5. Issues with addressing: {context_instruction}' if context_instruction else ''}
                
                If the research is practically correct and sufficient AND directly answers the original prompt, respond with: 
                "DIRECT_ANSWER: [Insert refined research as complete answer]" 
                
                DO NOT waste time describing what is correct - focus only on problems that need fixing.
                """
                
                result = self.review_agent.chat(review_prompt)
                logger.info(f"Pre-writing review result received: {str(result)[:100]}...")
                
                # Check if the review agent is providing a direct answer
                if str(result).startswith("DIRECT_ANSWER:"):
                    direct_answer = str(result).replace("DIRECT_ANSWER:", "").strip()
                    logger.info("Review agent provided direct answer. Stopping workflow early.")
                    return StopEvent(result=direct_answer)
                
                # Store the review guidance for the writing step
                await ctx.set("review_guidance", str(result))
                
                # Now proceed to the write step
                logger.info("Proceeding to write step with review guidance")
                return WriteEvent(review_guidance=str(result))
            else:
                # This is a post-write review (after writing)
                logger.info(f"POST-WRITE review: Answer to review (first 100 chars): {ev.answer[:100]}...")
                
                rewrite_count = await ctx.get("rewrite_count", 0)
                rewrite_count += 1
                await ctx.set("rewrite_count", rewrite_count)
                
                # Log the current rewrite count for debugging
                logger.info(f"Current rewrite count: {rewrite_count}")
                
                # Get all requirements
                requirements = analyze_prompt_requirements(original_prompt)
                word_count_instruction = requirements.get('word_count_instruction')
                context_instruction = requirements.get('context_instruction')
                
                # Prepare a focused review prompt that identifies only issues
                review_prompt = f"""Review the following answer and ONLY identify issues or problems:
                
                Original Prompt: {original_prompt}
                Research Information: {research_info}
                Answer to Review: {ev.answer}
                
                ONLY point out:
                1. Content that does not match the research or original prompt
                2. Missing answers to parts of the original question
                3. Factual errors compared to the provided research
                {f'4. Issues with the requirement: {word_count_instruction}' if word_count_instruction else ''}
                
                If the answer is practically correct, make minor refinements if needed and approve it.
                DO NOT provide a comprehensive evaluation if the content is already acceptable.
                """
                
                result = self.review_agent.chat(review_prompt)
                logger.info(f"Post-write review result received: {str(result)}")
                
                # Check if we've already hit the max rewrite count
                if rewrite_count >= 2:
                    logger.info("Maximum rewrite attempts reached (2). Finishing the flow without further rewrites.")
                    return StopEvent(result=ev.answer)
                
                logger.info("Asking if we should retry based on the review...")
                
                try_again = llm.complete(
                    f"This is a review of an answer. If you think this review is bad enough "
                    f"that it should be rewritten, respond with just the word RETRY. If the review is good, reply "
                    f"with just the word CONTINUE. Here's the review: <review>{str(result)}</review>"
                )
                logger.info(f"Decision on whether to retry: {try_again.text}")
                
                if try_again.text == "RETRY":
                    logger.info("Starting rewrite process based on review feedback")
                    return WriteEvent(
                        review_feedback=f"{str(result)}\nOriginal prompt: {original_prompt}\nResearch info: {research_info}"
                    )
                else:
                    logger.info("Review is good! Finishing the flow.")
                    return StopEvent(result=ev.answer)
        except Exception as e:
            logger.error(f"Error in review: {str(e)}\n{traceback.format_exc()}")
            raise
    
    @step
    async def write(self, ctx: Context, ev: WriteEvent) -> ReviewEvent:
        logger.info("====== WRITE STEP STARTED ======")
        try:
            original_prompt = await ctx.get("prompt")
            research_info = await ctx.get("research")
            message_history = await ctx.get("message_history", [])
            
            logger.info(f"Retrieved from context: prompt='{original_prompt[:50]}...', research_info (first 100 chars): '{research_info[:100]}...'")
            logger.info(f"Message history available: {len(message_history) > 0} with {len(message_history)} messages")
            
            # Get review guidance if available (from pre-write review)
            review_guidance = getattr(ev, "review_guidance", None)
            # Get review feedback if this is a rewrite
            review_feedback = getattr(ev, "review_feedback", None)
            
            prompt = (
                f"Write a detailed, clear, and direct answer addressing the question: "
                f"<question>{original_prompt}</question>. Use the following research as supporting information: "
                f"<research>{research_info}</research>"
            )
            
            # Include pre-write review guidance if available
            if review_guidance:
                prompt += f"\n\nConsider this review guidance when writing your answer:\n<review_guidance>{review_guidance}</review_guidance>\n"
                logger.info("Including pre-write review guidance")
            
            # Include review feedback if this is a rewrite
            if review_feedback:
                prompt += f"\n\nThis answer has been reviewed and the reviewer provided the following feedback that should be taken into account:\n<review_feedback>{review_feedback}</review_feedback>\n"
                logger.info("Including post-write review feedback for rewrite")
            
            # Include conversation history if available
            if message_history and len(message_history) > 0:
                history_context = "\n".join([f"{msg.role}: {msg.content}" for msg in message_history])
                prompt += f"\n\nTake into account the following conversation history to ensure your response is contextually relevant:\n<conversation_history>\n{history_context}\n</conversation_history>\n"
                logger.info("Including conversation history in write prompt")
            
            logger.info("Sending prompt to write agent...")
            result = self.write_agent.chat(prompt)
            
            logger.info(f"Write result received (first 100 chars): {str(result)[:100]}...")
            logger.info("====== WRITE STEP COMPLETED ======")
            
            # Now proceed to the post-write review step
            return ReviewEvent(answer=str(result), is_pre_write_review=False)
        except Exception as e:
            logger.error(f"Error in write: {str(e)}\n{traceback.format_exc()}")
            raise