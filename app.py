"""
Main application module for Flask app
"""
from flask import Flask, jsonify
from dotenv import load_dotenv
import os
import logging

def create_app(test_config=None):
    """Create and configure the Flask application."""
    # Load environment variables
    load_dotenv()
    
    # Create Flask app
    app = Flask(__name__)
    
    # Configure logging to ensure all messages appear in the terminal
    if app.debug:
        # Set Flask logger to output all levels of messages
        app.logger.setLevel(logging.INFO)
        
        # Create a stream handler for terminal output
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        
        # Create a formatter and add it to the handler
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        
        # Add the handler to the logger
        app.logger.addHandler(handler)
        
        # Ensure propagation is enabled
        app.logger.propagate = True
    
    # Load configuration
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-key-for-testing")
    app.config["GCS_BUCKET_NAME"] = os.getenv("GCS_BUCKET_NAME")
    # Set maximum file size to 1GB
    app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1GB in bytes
    # Set request timeout
    app.config['TIMEOUT'] = 300  # 5 minutes timeout
    
    # Override config with test config if provided
    if test_config:
        app.config.update(test_config)
    
    # Register error handlers
    @app.errorhandler(413)
    def request_entity_too_large(error):
        return jsonify({"error": "File too large. Maximum allowed size is 1GB."}), 413
        
    @app.errorhandler(408)
    def request_timeout(error):
        return jsonify({"error": "Request timeout. Please try again with a smaller file or wait."}), 408
    
    # Register all routes using the centralized route registration function
    from routes import register_routes
    register_routes(app)
    
    return app

# Create a global app instance for 'flask run' to find automatically
app = create_app()
app.debug = True  # Set debug mode on by default

# For running the app directly
if __name__ == "__main__":
    app.run(debug=True)