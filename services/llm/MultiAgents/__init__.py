"""
Multi-Agent System - A coordinated system of specialized agents
"""
from flask import current_app
from typing import Dict, Any, Optional

from services.llm.MultiAgents.CoordinatorAgent import CoordinatorAgent
from services.llm.MultiAgents.WritingAgent import WritingAgent
from services.llm.MultiAgents.ReviewingAgent import ReviewingAgent
from services.llm.MultiAgents.StructuralAgent import StructuralAgent

class MultiAgentHandler:
    """
    Handler for the multi-agent system that initializes and coordinates specialized agents:
    - CoordinatorAgent: Analyzes requests and orchestrates other agents
    - WritingAgent: Creates content based on instructions
    - ReviewingAgent: Evaluates and provides feedback on content
    - StructuralAgent: Formats and organizes content
    """
    
    def __init__(self, logger=None):
        """Initialize the multi-agent handler with optional custom logger"""
        self.logger = logger or current_app.logger
        
        # Initialize all agents
        self.coordinator = CoordinatorAgent(logger)
        self.writing_agent = WritingAgent(logger)
        self.reviewing_agent = ReviewingAgent(logger)
        self.structural_agent = StructuralAgent(logger)
        
        # Register specialized agents with the coordinator
        self.coordinator.register_agent("WritingAgent", self.writing_agent)
        self.coordinator.register_agent("ReviewingAgent", self.reviewing_agent)
        self.coordinator.register_agent("StructuralAgent", self.structural_agent)
        
        self.logger.info("Multi-Agent system initialized")
    
    def process_request(self, request: str) -> Dict[str, Any]:
        """
        Process a user request through the multi-agent system
        
        Args:
            request: The user's request as a string
            
        Returns:
            Dict containing the results and analysis
        """
        self.logger.info(f"Processing request through multi-agent system: {request[:50]}...")
        
        # Pass the request to the coordinator, which will handle all agent orchestration
        result = self.coordinator.process_request(request)
        
        self.logger.info("Multi-agent processing complete")
        return result

# Create a function to get a multi-agent handler instance
def get_multi_agent_handler(logger=None):
    """Get a configured multi-agent handler instance"""
    return MultiAgentHandler(logger)