"""
Utility functions for the travel MVP application.

This module contains reusable helper functions following DRY principles:
- Database error handling and retry logic
- Column existence checking
- Session management
- Date formatting
- Data validation
"""

from flask import session
from app import db
from sqlalchemy import inspect
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable


def parse_date(date_str: Optional[str]) -> Optional[datetime.date]:
    """
    Parse a date string into a Python date object.
    
    Supports multiple date formats:
    - HTML5 format: YYYY-MM-DD
    - Legacy format: DD/MM/YYYY
    
    Args:
        date_str: Date string to parse
        
    Returns:
        Parsed date object or None if parsing fails
    """
    if not date_str:
        return None
    try:
        # Try HTML5 format (YYYY-MM-DD)
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        try:
            # Try legacy format (DD/MM/YYYY)
            return datetime.strptime(date_str, '%d/%m/%Y').date()
        except ValueError:
            return None
    except TypeError:
        return None


def format_date_for_display(date_str: Optional[str]) -> str:
    """
    Format a date string to DD-MM-YYYY format for display.
    
    Args:
        date_str: Date string to format
        
    Returns:
        Formatted date string or "not set" if invalid
    """
    if not date_str:
        return "not set"
    try:
        date_obj = parse_date(date_str)
        if date_obj:
            return date_obj.strftime("%d-%m-%Y")
    except Exception:
        pass
    return date_str


def get_max_budget(budget_range: Optional[str]) -> int:
    """
    Convert budget range string to numeric limit.
    
    Note: This function is currently not used for filtering,
    but kept for potential future use.
    
    Args:
        budget_range: Budget range string ('low', 'medium', 'high', 'luxury')
        
    Returns:
        Numeric budget limit
    """
    budget_map = {
        'low': 75,
        'medium': 200,
        'high': 450,
        'luxury': 1000
    }
    return budget_map.get(budget_range, 9999)


def check_column_exists(table_name: str, column_name: str) -> bool:
    """
    Check if a column exists in a database table.
    
    This is useful for handling database migrations gracefully,
    allowing code to work with or without certain columns.
    
    Args:
        table_name: Name of the database table
        column_name: Name of the column to check
        
    Returns:
        True if column exists, False otherwise
    """
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception as e:
        print(f"Warning: Could not check for column {column_name} in {table_name}: {e}")
        return False


def safe_db_query(query_func: Callable, *args, **kwargs) -> Any:
    """
    Execute a database query with automatic retry on transaction errors.
    
    This handles common database transaction errors by rolling back
    and retrying the query once. This is useful when dealing with
    Supabase/PostgreSQL connection issues.
    
    Args:
        query_func: Function that executes the database query
        *args: Positional arguments to pass to query_func
        **kwargs: Keyword arguments to pass to query_func
        
    Returns:
        Result of the query function
        
    Example:
        activity = safe_db_query(ActivityType.query.get, activity_id)
    """
    try:
        return query_func(*args, **kwargs)
    except Exception as e:
        # If query fails due to transaction error, rollback and retry
        db.session.rollback()
        db.session.expire_all()
        try:
            return query_func(*args, **kwargs)
        except Exception as retry_error:
            print(f"Database query failed after retry: {retry_error}")
            raise retry_error


def clear_session_preserve_login():
    """
    Clear all session data while preserving Flask-Login authentication data.
    
    This ensures users remain logged in when clearing trip planning data.
    """
    flask_login_keys = ['_user_id', '_fresh', '_id', '_remember_me']
    saved_login_data = {key: session.get(key) for key in flask_login_keys if key in session}
    session.clear()
    # Restore Flask-Login keys
    for key, value in saved_login_data.items():
        session[key] = value


def save_session_preferences() -> Dict[str, Any]:
    """
    Extract all trip planning preferences from session.
    
    Returns:
        Dictionary containing all preference data
    """
    return {
        'country': session.get("country"),
        'start_date': session.get("start_date"),
        'end_date': session.get("end_date"),
        'budget_range': session.get("budget_range"),
        'adults': session.get("adults"),
        'children': session.get("children"),
        'accommodation_type': session.get("accommodation_type"),
        'interest_culture': session.get("interest_culture"),
        'interest_food': session.get("interest_food"),
        'interest_wildlife': session.get("interest_wildlife"),
        'interest_history': session.get("interest_history"),
        'interest_beach': session.get("interest_beach"),
        'duration': session.get("duration")
    }


def restore_session_preferences(saved_data: Dict[str, Any]):
    """
    Restore trip planning preferences to session.
    
    Args:
        saved_data: Dictionary containing preference data
    """
    preference_keys = {
        'country': str,
        'start_date': str,
        'end_date': str,
        'budget_range': str,
        'adults': int,
        'children': int,
        'accommodation_type': str,
        'interest_culture': int,
        'interest_food': int,
        'interest_wildlife': int,
        'interest_history': int,
        'interest_beach': int,
        'duration': str
    }
    
    for key, value_type in preference_keys.items():
        if key in saved_data:
            value = saved_data[key]
            # Only restore if value is not None (for int types) or not empty (for str types)
            if value_type == int and value is not None:
                session[key] = value
            elif value_type == str and value:
                session[key] = value


def get_country_image_path(country: Optional[str]) -> str:
    """
    Get the image path for a given country.
    
    Args:
        country: Country name (case-insensitive)
        
    Returns:
        Path to country image or default Tanzania image
    """
    if not country:
        return "/static/img/tanzania.jpg"
    
    country_lower = country.lower()
    country_image_map = {
        "uganda": "/static/img/uganda.jpg",
        "rwanda": "/static/img/rwanda.jpg",
        "tanzania": "/static/img/tanzania.jpg"
    }
    return country_image_map.get(country_lower, "/static/img/tanzania.jpg")


def format_accommodation_type(accommodation_type: Optional[str]) -> str:
    """
    Format accommodation type value to a user-friendly display name.
    
    Converts database values like 'hotel5', 'hotel4', 'hotel3' to 
    readable format like 'Hotel (5 Star)', 'Hotel (4 Star)', 'Hotel (3 Star)'.
    
    Args:
        accommodation_type: Raw accommodation type value (e.g., 'hotel5', 'airbnb')
        
    Returns:
        Formatted display name (e.g., 'Hotel (5 Star)', 'Apartment / Airbnb')
    """
    if not accommodation_type:
        return "N/A"
    
    accommodation_map = {
        'hostel': 'Hostel',
        'airbnb': 'Apartment / Airbnb',
        'hotel3': 'Hotel (3 Star)',
        'hotel4': 'Hotel (4 Star)',
        'hotel5': 'Hotel (5 Star)',
        'resort': 'Resort',
        'boutique': 'Boutique Hotel'
    }
    
    return accommodation_map.get(accommodation_type.lower(), accommodation_type)


def format_budget_range(budget_range: Optional[str]) -> str:
    """
    Format budget range value to a user-friendly display name.
    
    Converts database values like 'low', 'medium', 'high', 'luxury' to 
    readable format like 'Budget', 'Moderate', 'Comfort', 'Luxury'.
    
    Handles both old and new database values for backward compatibility.
    
    Args:
        budget_range: Raw budget range value (e.g., 'low', 'high', 'luxury')
        
    Returns:
        Formatted display name (e.g., 'Budget', 'Comfort', 'Luxury')
    """
    if not budget_range:
        return "N/A"
    
    budget_map = {
        'low': 'Budget',
        'medium': 'Moderate',
        'high': 'Comfort',
        'luxury': 'Luxury'
    }
    
    # Convert to lowercase for case-insensitive matching
    budget_lower = budget_range.lower()
    
    # Return formatted name if found, otherwise return original with first letter capitalized
    return budget_map.get(budget_lower, budget_range.capitalize())


