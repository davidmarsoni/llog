"""
Main application module for Flask app
"""
from flask import Flask
from dotenv import load_dotenv
import os

def create_app(test_config=None):
    """Create and configure the Flask application."""
    # Load environment variables
    load_dotenv()
    
    # Create Flask app
    app = Flask(__name__)
    
    # Load configuration
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-key-for-testing")
    app.config["GCS_BUCKET_NAME"] = os.getenv("GCS_BUCKET_NAME")
    
    # Override config with test config if provided
    if test_config:
        app.config.update(test_config)
    
    # Register blueprints
    from routes.main_routes import main_bp
    from routes.chatbot_routes import chatbot_bp
    from routes.file_storage_routes import file_storage_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(chatbot_bp)
    app.register_blueprint(file_storage_bp)
    
    return app

# Create a global app instance for 'flask run' to find automatically
app = create_app()
app.debug = True  # Set debug mode on by default

# For running the app directly
if __name__ == "__main__":
    app.run(debug=True)