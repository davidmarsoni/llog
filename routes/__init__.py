"""
Routes module for the application.
Contains all the route handlers for the application.
"""

def register_routes(app):
    """
    Register all application routes with the Flask app.
    
    Args:
        app: The Flask application
    """
    # Import the main routes module
    from routes.main_routes import main_bp
    
    # Import and register chatbot routes
    from routes.chatbot_routes import chatbot_bp
    
    # Import and register file routes using the new registration function
    from routes.file.file_routes import register_file_blueprints
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(chatbot_bp)
    
    # Register all file-related blueprints
    register_file_blueprints(app)