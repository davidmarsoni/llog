"""
Simple agent logger to show when agents are used
"""
from flask import current_app
import sys

def log_agent_use(agent_type, operation):
    """
    Print a simple message when an agent is used and log to Flask logger
    
    Args:
        agent_type: The type of agent (Research, Write, Review)
        operation: What the agent is doing
    """
    message = f"--- {agent_type.upper()} AGENT: {operation} ---"
    
    # Print to stdout (terminal)
    print(message, flush=True)
    sys.stdout.flush()
    
    # Also log to Flask's logger if we're in a Flask app context
    try:
        if current_app:
            current_app.logger.info(message)
    except:
        # If we're not in a Flask app context, just continue
        pass