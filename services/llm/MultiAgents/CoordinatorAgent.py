"""
Coordinator Agent - Manages and orchestrates multiple specialized agents
"""
from flask import current_app
from typing import Dict, Any, List, Optional
import json
import re
from services.llm.chat import get_llm_response

class CoordinatorAgent:
    """
    Coordinator Agent that analyzes user requests and delegates to specialized agents:
    - WritingAgent: Handles content creation tasks
    - ReviewingAgent: Provides critical analysis and feedback
    - StructuralAgent: Organizes and formats information
    """
    
    def __init__(self, logger=None):
        """Initialize the coordinator agent with optional custom logger"""
        self.logger = logger or current_app.logger
        self.agents = {}  # Will be populated with agent instances
    
    def register_agent(self, agent_type: str, agent_instance: Any) -> None:
        """
        Register a specialized agent with the coordinator
        
        Args:
            agent_type: The type identifier for the agent
            agent_instance: The agent instance to register
        """
        self.logger.info(f"Registering agent: {agent_type}")
        self.agents[agent_type] = agent_instance
    
    def _analyze_request(self, request: str) -> Dict[str, Any]:
        """
        Analyze the user request to determine required agents and tasks
        
        Args:
            request: The user's request string
            
        Returns:
            Dict containing the analysis results and task breakdown
        """
        self.logger.info(f"Analyzing request: {request[:50]}...")
        
        # Ask LLM to analyze the request and determine which agents should handle it
        analysis_prompt = f"""Analyze this user request and determine which specialized agents should handle it:
        
USER REQUEST: {request}

Break down the request into specific tasks that can be assigned to specialized agents.
Consider these agents and their capabilities:

1. WritingAgent: Creates original content, drafts texts, generates ideas
2. ReviewingAgent: Evaluates content quality, checks facts, provides feedback  
3. StructuralAgent: Formats content, creates structure, organizes information

For each identified task, specify:
- Which agent should handle it
- What specific instruction this agent needs
- The priority/order of this task (what needs to happen first)

Return your analysis as JSON with this structure:
{{
  "primary_intent": "brief description of the main user goal",
  "tasks": [
    {{
      "agent": "agent_name",
      "instruction": "specific instruction for the agent",
      "priority": number (lower is higher priority),
      "depends_on": ["task_ids of dependencies"] or null
    }}
  ]
}}

Be specific and practical in the instructions. Think about how the tasks connect to each other.
"""
        
        try:
            # Get analysis from LLM
            response = get_llm_response(
                query=analysis_prompt,
                use_context=False
            )
            
            analysis_text = response.get("answer", "")
            
            # Extract JSON from response
            json_match = re.search(r'(\{.*\})', analysis_text, re.DOTALL)
            if json_match:
                analysis = json.loads(json_match.group(1))
                self.logger.info(f"Request analysis complete. Primary intent: {analysis.get('primary_intent', 'Unknown')}")
                return analysis
            else:
                self.logger.warning("Could not extract JSON analysis from LLM response")
                # Create a simple default analysis
                return {
                    "primary_intent": "Process user request",
                    "tasks": [
                        {
                            "agent": "WritingAgent",
                            "instruction": request,
                            "priority": 1,
                            "depends_on": None
                        }
                    ]
                }
                
        except Exception as e:
            self.logger.error(f"Error analyzing request: {str(e)}")
            # Return default analysis on error
            return {
                "primary_intent": "Process user request (error in analysis)",
                "tasks": [
                    {
                        "agent": "WritingAgent",
                        "instruction": request,
                        "priority": 1,
                        "depends_on": None
                    }
                ]
            }
    
    def _execute_task(self, task: Dict[str, Any], results_so_far: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single task using the appropriate agent
        
        Args:
            task: The task specification
            results_so_far: Results from previous tasks
            
        Returns:
            Dict containing the task execution results
        """
        agent_type = task.get("agent")
        instruction = task.get("instruction", "")
        task_id = task.get("id", "unknown")
        
        self.logger.info(f"Executing task {task_id} with {agent_type}")
        
        # Check if we have this agent registered
        if agent_type not in self.agents:
            self.logger.warning(f"Agent {agent_type} not found for task {task_id}")
            return {
                "status": "error",
                "message": f"Agent {agent_type} not registered",
                "task_id": task_id
            }
            
        # Check for dependencies in the instruction
        dependency_pattern = r'\{([a-zA-Z0-9_]+)\}'
        for match in re.finditer(dependency_pattern, instruction):
            dep_key = match.group(1)
            if dep_key in results_so_far:
                # Replace the placeholder with the actual result
                instruction = instruction.replace(f"{{{dep_key}}}", str(results_so_far.get(dep_key, "")))
        
        # Execute the task with the appropriate agent
        agent = self.agents[agent_type]
        try:
            result = agent.execute(instruction)
            self.logger.info(f"Task {task_id} completed successfully")
            return {
                "status": "success",
                "result": result,
                "task_id": task_id
            }
        except Exception as e:
            self.logger.error(f"Error executing task {task_id}: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "task_id": task_id
            }
    
    def process_request(self, request: str) -> Dict[str, Any]:
        """
        Process a user request by coordinating multiple agents
        
        Args:
            request: The user's request string
            
        Returns:
            Dict containing the combined results from all agents
        """
        print(f"\n======= CoordinatorAgent START =======")
        print(f"Processing request: {request[:100]}...")
        
        try:
            # Step 1: Analyze the request
            analysis = self._analyze_request(request)
            
            # Step 2: Sort tasks by priority
            tasks = sorted(analysis.get("tasks", []), key=lambda x: x.get("priority", 999))
            
            # Add task IDs if not present
            for i, task in enumerate(tasks):
                if "id" not in task:
                    task["id"] = f"task_{i+1}"
            
            # Step 3: Execute tasks in order, tracking dependencies
            results = {}
            task_results = {}
            
            for task in tasks:
                task_id = task.get("id")
                dependencies = task.get("depends_on", [])
                
                # Check if all dependencies are satisfied
                dependencies_met = True
                if dependencies:
                    for dep in dependencies:
                        if dep not in task_results or task_results[dep].get("status") != "success":
                            dependencies_met = False
                            break
                
                if dependencies_met:
                    # Execute this task
                    result = self._execute_task(task, results)
                    task_results[task_id] = result
                    
                    # Store the main result for dependency resolution
                    if result.get("status") == "success":
                        results[task_id] = result.get("result")
                else:
                    self.logger.warning(f"Skipping task {task_id} - dependencies not met")
                    task_results[task_id] = {
                        "status": "skipped",
                        "message": "Dependencies not satisfied",
                        "task_id": task_id
                    }
            
            # Step 4: Combine results into a final response
            final_result = self._combine_results(analysis, task_results, results)
            
            print(f"Request processing complete. Generated {len(str(final_result))} chars of output")
            print("======= CoordinatorAgent COMPLETE =======\n")
            
            return {
                "status": "success",
                "result": final_result,
                "analysis": analysis
            }
            
        except Exception as e:
            self.logger.error(f"Error processing request: {str(e)}")
            print(f"Error processing request: {str(e)}")
            print("======= CoordinatorAgent ERROR =======\n")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _combine_results(self, analysis: Dict[str, Any], task_results: Dict[str, Any], results: Dict[str, Any]) -> Any:
        """
        Combine results from multiple tasks into a coherent final result
        
        Args:
            analysis: The original request analysis
            task_results: The results of each task with status
            results: The successful results by task_id
            
        Returns:
            A combined final result
        """
        # Start with the highest priority successful result
        primary_intent = analysis.get("primary_intent", "")
        
        # Use the final task's result as the main output
        final_task_id = None
        for task in sorted(analysis.get("tasks", []), key=lambda x: x.get("priority", 999), reverse=True):
            task_id = task.get("id")
            if task_id in task_results and task_results[task_id].get("status") == "success":
                final_task_id = task_id
                break
        
        if final_task_id and final_task_id in results:
            final_output = results[final_task_id]
        else:
            # If no successful final task, combine available results
            final_output = "The system was unable to process your request completely."
            successful_results = []
            for task_id, result in task_results.items():
                if result.get("status") == "success":
                    successful_results.append(result.get("result", ""))
            
            if successful_results:
                final_output = "\n\n".join(successful_results)
        
        return final_output