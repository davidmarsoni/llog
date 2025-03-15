"""
Main routes for the application (home, about)
"""
from flask import Blueprint, render_template

# Create a Blueprint for main routes
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """Render the home page."""
    return render_template('home.html')

@main_bp.route('/about')
def about():
    """Render the about page."""
    return render_template('about.html')