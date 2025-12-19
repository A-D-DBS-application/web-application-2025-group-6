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
from typing import Optional, Dict, Any, List, Callable, Tuple


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
    Get the image URL for a given country from Supabase home_pictures table.
    Also supports "Home" for hero image.
    
    Args:
        country: Country name (case-insensitive) or "Home" for hero image
        
    Returns:
        Supabase URL for country image or default Tanzania image URL
    """
    if not country:
        country = "tanzania"
    
    country_lower = country.lower()
    # Map country names to database values
    country_map = {
        "uganda": "Uganda",
        "rwanda": "Rwanda",
        "tanzania": "Tanzania",
        "home": "Home"
    }
    country_db_value = country_map.get(country_lower, "Tanzania")
    
    try:
        from sqlalchemy import text
        # Use raw SQL query for table name with space and column name with slash
        query = text("""
            SELECT url 
            FROM "home pictures" 
            WHERE "country/type" = :country_type 
            LIMIT 1
        """)
        result = safe_db_query(
            lambda: db.session.execute(query, {"country_type": country_db_value}).fetchone()
        )
        
        if result and result[0]:
            return result[0]
    except Exception as e:
        print(f"Error fetching country image from database: {e}")
    
    # Fallback to default (Tanzania) if not found or error
    try:
        from sqlalchemy import text
        query = text("""
            SELECT url 
            FROM "home pictures" 
            WHERE "country/type" = 'Tanzania' 
            LIMIT 1
        """)
        result = safe_db_query(
            lambda: db.session.execute(query).fetchone()
        )
        if result and result[0]:
            return result[0]
    except Exception as e:
        print(f"Error fetching default image from database: {e}")
    
    # No fallback - return empty string if database fails
    return ""


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


def prepare_itinerary_list_from_items(itinerary_items, include_placeholder=True):
    """
    Convert database itinerary items to template-ready list format.
    
    Shared function used by both result_route and trip_detail_route to avoid duplication.
    
    Args:
        itinerary_items: List of Itinerary database objects
        include_placeholder: Whether to create placeholder activity objects for items without activity
        
    Returns:
        List of itinerary dictionaries ready for template rendering
    """
    from app.models import ActivityType
    from app.utils import safe_db_query
    
    itinerary_list = []
    
    for item in itinerary_items:
        activity = None
        if item.day_activity_id:
            activity = safe_db_query(ActivityType.query.get, item.day_activity_id)
        
        if activity:
            activity_obj = activity
        elif include_placeholder:
            # Placeholder activity (Local Exploration or Rest Day)
            class PlaceholderActivity:
                def __init__(self, title, description):
                    self.activity_type_id = None
                    self.name = title
                    self.description = description
                    self.duration_days = 1
                    self.price_estimation = 0
                    self.images_url_text = None
                    self.interest_categ = []
                    self.latitude = None
                    self.longitude = None
            activity_obj = PlaceholderActivity(item.title or "Rest Day", item.description or "A relaxing day to unwind.")
        else:
            activity_obj = None
        
        itinerary_list.append({
            "day": item.day,
            "title": item.title or (activity.name if activity else "Rest Day"),
            "description": item.description or (activity.description if activity else "A relaxing day to unwind."),
            "activity_type_id": activity.activity_type_id if activity else None,
            "itinerary_id": item.itinerary_id,
            "activity": activity_obj
        })
    
    return itinerary_list


def calculate_trip_prices(itinerary_list, adults, children):
    """
    Calculate total price and average price per person for a trip.
    
    Shared function used by both result_route and trip_detail_route to avoid duplication.
    
    Args:
        itinerary_list: List of itinerary items with activity objects
        adults: Number of adults
        children: Number of children
        
    Returns:
        Tuple of (total_price_per_person, total_price, average_price_per_person)
    """
    total_price_per_person = 0
    
    for item in itinerary_list:
        activity = item.get("activity")
        if activity and hasattr(activity, 'price_estimation') and activity.price_estimation:
            price = float(activity.price_estimation)
            total_price_per_person += price
    
    # Calculate total price: (prijs pp * adults) + (prijs pp * children * 0.5)
    adults = adults or 1
    children = children or 0
    total_price = (total_price_per_person * adults) + (total_price_per_person * children * 0.5)
    
    # Calculate average price per person
    total_travelers = adults + children
    average_price_per_person = total_price / total_travelers if total_travelers > 0 else 0
    
    return total_price_per_person, total_price, average_price_per_person


def prepare_trip_template_data(traveler, itinerary_list, total_price, average_price_per_person):
    """
    Prepare template data dictionary for trip display pages.
    
    Shared function used by both result_route and trip_detail_route to avoid duplication.
    
    Args:
        traveler: Traveler database object
        itinerary_list: List of itinerary items
        total_price: Total trip price
        average_price_per_person: Average price per person
        
    Returns:
        Dictionary with all data needed for trip template rendering
    """
    from app.utils import get_country_image_path, format_date_for_display, format_budget_range, format_accommodation_type
    
    country = traveler.country.lower() if traveler.country else ""
    background_image = get_country_image_path(country)
    
    adults = traveler.adults or 1
    children = traveler.children or 0
    
    return {
        "start": format_date_for_display(traveler.start_date.strftime('%Y-%m-%d') if traveler.start_date else ""),
        "end": format_date_for_display(traveler.end_date.strftime('%Y-%m-%d') if traveler.end_date else ""),
        "budget": format_budget_range(traveler.budget_range or "N/A"),
        "adults": adults,
        "children": children,
        "accommodation": format_accommodation_type(traveler.accommodation_type or "N/A"),
        "itinerary": itinerary_list,
        "background_image": background_image,
        "country": country,
        "traveler_id": traveler.traveler_id,
        "total_price": total_price,
        "average_price_per_person": average_price_per_person
    }


