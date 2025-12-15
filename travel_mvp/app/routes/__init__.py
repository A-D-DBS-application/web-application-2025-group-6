"""
Routes package for the travel MVP application.

This package contains all route blueprints organized by functionality:
- main_routes: Core trip planning routes (index, step1, step2, result)
- auth_routes: Authentication routes (login, logout)
- itinerary_routes: Itinerary management routes (my-trips)
- api_routes: API endpoints for dynamic itinerary editing
"""

# Import main_bp from main_routes to make it available at package level
from app.routes.main_routes import main_bp

__all__ = ['main_bp']

