"""
Itinerary management routes for the travel MVP application.

Handles viewing saved trips and itinerary management.
"""

from flask import Blueprint, render_template, flash
from flask_login import login_required, current_user
from app import db
from app.models import Itinerary, Traveler
from app.utils import safe_db_query

itinerary_bp = Blueprint("itinerary", __name__)


@itinerary_bp.route("/my-trips")
@login_required
def my_trips_route():
    """
    Display all itineraries for the current logged-in user.
    
    Groups itineraries by traveler_id to show complete trips.
    """
    try:
        # Query all itineraries for the current user using ORM
        user_itineraries = safe_db_query(
            lambda: Itinerary.query.filter_by(user_id=current_user.user_id)
            .order_by(Itinerary.itinerary_id.desc())
            .all()
        )
    except Exception as e:
        # If user_id column doesn't exist yet, return empty list
        print(f"Error querying itineraries: {e}")
        flash("Please run database migration to add user_id column to itinerary table.", "warning")
        return render_template("my_trips.html", trips=[])
    
    # Group itineraries by traveler_id to show complete trips
    trips_dict = {}
    for itinerary in user_itineraries:
        traveler_id = itinerary.traveler_id
        if traveler_id not in trips_dict:
            # Get traveler info with retry logic
            traveler = safe_db_query(Traveler.query.get, traveler_id)
            trips_dict[traveler_id] = {
                'traveler': traveler,
                'itineraries': []
            }
        trips_dict[traveler_id]['itineraries'].append(itinerary)
    
    # Convert to list for template
    trips = list(trips_dict.values())
    
    return render_template("my_trips.html", trips=trips)


