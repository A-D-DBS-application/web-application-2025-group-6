"""
Itinerary management routes for the travel MVP application.

Handles viewing saved trips and itinerary management.
"""

from flask import Blueprint, render_template, flash, redirect, url_for, session
from flask_login import login_required, current_user
from app import db
from app.models import Itinerary, Traveler
from app.utils import safe_db_query, format_accommodation_type, format_budget_range, restore_session_preferences, parse_date

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


@itinerary_bp.route("/trip/<int:traveler_id>")
@login_required
def trip_detail_route(traveler_id):
    """
    Display detailed view of a saved trip.
    
    Shows the full itinerary similar to the result page.
    """
    try:
        # Get traveler info
        traveler = safe_db_query(Traveler.query.get_or_404, traveler_id)
        
        # Get all itinerary items for this traveler and user
        itinerary_items = safe_db_query(
            lambda: Itinerary.query.filter_by(
                traveler_id=traveler_id,
                user_id=current_user.user_id
            )
            .order_by(Itinerary.day.asc())
            .all()
        )
        
        if not itinerary_items:
            flash("No itinerary found for this trip.", "warning")
            return redirect(url_for("itinerary.my_trips_route"))
        
        # Prepare itinerary list similar to result page
        from app.utils import get_country_image_path, format_date_for_display
        from app.models import ActivityType
        
        itinerary_list = []
        total_price_per_person = 0
        
        # Sort items by day
        sorted_items = sorted(itinerary_items, key=lambda x: x.day)
        
        for item in sorted_items:
            # Get activity details if it's a real activity (not placeholder)
            activity = None
            if item.day_activity_id:
                activity = safe_db_query(ActivityType.query.get, item.day_activity_id)
            
            # Create activity object similar to result page
            if activity:
                activity_obj = activity
                price = float(activity.price_estimation) if activity.price_estimation else 0
                total_price_per_person += price
            else:
                # Placeholder activity (Local Exploration)
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
                activity_obj = PlaceholderActivity(item.title, item.description)
                price = 0
            
            itinerary_list.append({
                "day": item.day,
                "title": item.title,
                "description": item.description,
                "activity_type_id": activity.activity_type_id if activity else None,
                "itinerary_id": item.itinerary_id,
                "activity": activity_obj
            })
        
        # Calculate total price: (prijs pp * adults) + (prijs pp * children * 0.5)
        adults = traveler.adults or 1
        children = traveler.children or 0
        total_price = (total_price_per_person * adults) + (total_price_per_person * children * 0.5)
        
        # Calculate average price per person
        total_travelers = adults + children
        average_price_per_person = total_price / total_travelers if total_travelers > 0 else 0
        
        # Prepare data for template (similar to result page)
        country = traveler.country.lower() if traveler.country else ""
        background_image = get_country_image_path(country)
        
        data = {
            "start": format_date_for_display(traveler.start_date.strftime('%Y-%m-%d') if traveler.start_date else ""),
            "end": format_date_for_display(traveler.end_date.strftime('%Y-%m-%d') if traveler.end_date else ""),
            "budget": format_budget_range(traveler.budget_range or "N/A"),
            "adults": adults,
            "children": children,
            "accommodation": format_accommodation_type(traveler.accommodation_type or "N/A"),
            "itinerary": itinerary_list,
            "background_image": background_image,
            "country": country,
            "traveler_id": traveler_id,
            "total_price": total_price,
            "average_price_per_person": average_price_per_person
        }
        
        return render_template("trip_detail.html", **data)
        
    except Exception as e:
        print(f"Error loading trip detail: {e}")
        flash("Error loading trip details.", "danger")
        return redirect(url_for("itinerary.my_trips_route"))


@itinerary_bp.route("/trip/<int:traveler_id>/delete", methods=["POST"])
@login_required
def delete_trip_route(traveler_id):
    """
    Delete a saved trip by removing user_id from all itinerary items.
    
    This doesn't delete the itinerary items themselves, just unlinks them from the user.
    """
    try:
        # Get all itinerary items for this traveler and user
        itinerary_items = safe_db_query(
            lambda: Itinerary.query.filter_by(
                traveler_id=traveler_id,
                user_id=current_user.user_id
            ).all()
        )
        
        if not itinerary_items:
            flash("Trip not found or you don't have permission to delete it.", "warning")
            return redirect(url_for("itinerary.my_trips_route"))
        
        # Remove user_id from all itinerary items (set to NULL)
        from sqlalchemy import text
        update_sql = text("""
            UPDATE itinerary 
            SET user_id = NULL 
            WHERE traveler_id = :traveler_id AND user_id = :user_id
        """)
        result = db.session.execute(update_sql, {
            'traveler_id': traveler_id,
            'user_id': current_user.user_id
        })
        
        rows_updated = result.rowcount
        db.session.commit()
        
        if rows_updated > 0:
            flash(f"Trip deleted successfully! {rows_updated} items removed from your account.", "success")
        else:
            flash("No items were deleted.", "warning")
        
        return redirect(url_for("itinerary.my_trips_route"))
        
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error deleting trip: {e}")
        flash("Error deleting trip. Please try again.", "danger")
        return redirect(url_for("itinerary.my_trips_route"))


@itinerary_bp.route("/trip/<int:traveler_id>/preferences")
@login_required
def restore_preferences_route(traveler_id):
    """
    Restore preferences from a saved trip to session and redirect to step2.
    
    This allows users to edit their preferences from a saved trip.
    """
    try:
        # Get traveler info
        traveler = safe_db_query(Traveler.query.get_or_404, traveler_id)
        
        # Verify that this trip belongs to the current user
        itinerary_items = safe_db_query(
            lambda: Itinerary.query.filter_by(
                traveler_id=traveler_id,
                user_id=current_user.user_id
            ).first()
        )
        
        if not itinerary_items:
            flash("Trip not found or you don't have permission to access it.", "warning")
            return redirect(url_for("itinerary.my_trips_route"))
        
        # Prepare preferences data from traveler
        preferences_data = {
            'country': traveler.country,
            'start_date': traveler.start_date.strftime('%Y-%m-%d') if traveler.start_date else None,
            'end_date': traveler.end_date.strftime('%Y-%m-%d') if traveler.end_date else None,
            'budget_range': traveler.budget_range,
            'adults': traveler.adults,
            'children': traveler.children,
            'accommodation_type': traveler.accommodation_type,
            'interest_culture': traveler.interest_culture,
            'interest_food': traveler.interest_food,
            'interest_wildlife': traveler.interest_wildlife,
            'interest_history': traveler.interest_history,
            'interest_beach': traveler.interest_beach
        }
        
        # Calculate duration
        if traveler.start_date and traveler.end_date:
            duration = (traveler.end_date - traveler.start_date).days + 1
            preferences_data['duration'] = str(duration)
        else:
            preferences_data['duration'] = "N/A"
        
        # Restore preferences to session
        restore_session_preferences(preferences_data)
        
        # Redirect to step2 to edit preferences
        return redirect(url_for("main.step2_route"))
        
    except Exception as e:
        print(f"Error restoring preferences: {e}")
        flash("Error restoring preferences. Please try again.", "danger")
        return redirect(url_for("itinerary.my_trips_route"))


