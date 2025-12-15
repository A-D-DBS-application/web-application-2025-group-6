"""
API routes for the travel MVP application.

Handles AJAX requests for dynamic itinerary editing:
- Removing activities from itinerary
- Adding activities to itinerary
- Fetching available activities by country
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import ActivityType, Itinerary
from sqlalchemy import func, text
from app.utils import safe_db_query, check_column_exists

api_bp = Blueprint("api", __name__)


@api_bp.route("/api/itinerary/<int:itinerary_id>/remove", methods=["POST"])
def remove_itinerary_item(itinerary_id):
    """
    Remove an activity from an itinerary.
    
    Automatically renumbers remaining days and updates the database.
    """
    try:
        itinerary_item = safe_db_query(Itinerary.query.get_or_404, itinerary_id)
        traveler_id = itinerary_item.traveler_id
        removed_day = itinerary_item.day

        activity = safe_db_query(ActivityType.query.get, itinerary_item.day_activity_id)
        activity_duration = activity.duration_days if activity and activity.duration_days else 1

        # Check authorization if user_id column exists
        has_user_id_column = check_column_exists('itinerary', 'user_id')
        if has_user_id_column and current_user.is_authenticated:
            if itinerary_item.user_id != current_user.user_id:
                return jsonify({"success": False, "error": "Unauthorized"}), 403

        db.session.delete(itinerary_item)

        # Update day numbers for remaining activities
        sql = text("""
            UPDATE itinerary
            SET day = day - :decrease_by
            WHERE traveler_id = :traveler_id AND day > :removed_day
        """)
        db.session.execute(sql, {
            'traveler_id': traveler_id,
            'removed_day': removed_day,
            'decrease_by': activity_duration
        })

        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Activity removed successfully",
            "removed_day": removed_day,
            "duration": activity_duration
        })
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/activities/<country>", methods=["GET"])
def get_activities_by_country(country):
    """
    Get available activities for a country, filtered by child-friendly status.
    
    Only returns activities not already in the itinerary.
    """
    try:
        country_normalized = country.capitalize()
        traveler_id = request.args.get('traveler_id', type=int)
        num_children = request.args.get('children', type=int, default=0)

        base_query = ActivityType.query.filter_by(country=country_normalized)

        # Apply child-friendly filter if children are present
        if num_children > 0:
            has_child_friendly_column = check_column_exists('activity_type', 'is_child_friendly')
            if has_child_friendly_column:
                base_query = base_query.filter(ActivityType.is_child_friendly == True)
            else:
                print("Warning: is_child_friendly column does not exist yet. Skipping child-friendly filter in API.")

        # Execute query with retry logic
        activities = safe_db_query(lambda: base_query.all())

        # Get already used activity IDs for this traveler
        used_activity_ids = set()
        if traveler_id:
            try:
                sql = text("SELECT day_activity_id FROM itinerary WHERE traveler_id = :traveler_id")
                result = db.session.execute(sql, {'traveler_id': traveler_id})
                used_activity_ids = {row[0] for row in result if row[0] is not None}
            except Exception as e:
                print(f"Warning: Could not filter existing activities: {e}")

        # Build response with only unused activities
        activities_list = []
        for activity in activities:
            if activity.activity_type_id not in used_activity_ids:
                activities_list.append({
                    "activity_type_id": activity.activity_type_id,
                    "name": activity.name,
                    "description": activity.description,
                    "duration_days": activity.duration_days or 1,
                    "price_estimation": float(activity.price_estimation) if activity.price_estimation else None,
                    "images_url_text": activity.images_url_text,
                    "interest_categ": activity.interest_categ or []
                })

        return jsonify({"success": True, "activities": activities_list})
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/itinerary/add", methods=["POST"])
def add_itinerary_item():
    """
    Add a new activity to an existing itinerary.
    
    Automatically determines the next available day (minimum day 2).
    """
    try:
        data = request.get_json()
        traveler_id = data.get("traveler_id")
        activity_type_id = data.get("activity_type_id")

        if not all([traveler_id, activity_type_id]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Get activity details with retry logic
        activity = safe_db_query(ActivityType.query.get_or_404, activity_type_id)

        # Find the maximum day number for this traveler to determine next day
        max_day_result = db.session.query(func.max(Itinerary.day)).filter_by(traveler_id=traveler_id).scalar()
        next_day = max((max_day_result or 0) + 1, 2)  # Minimum day 2 for new activities

        # Check if user_id column exists and get user_id if logged in
        has_user_id_column = check_column_exists('itinerary', 'user_id')
        user_id = None
        if has_user_id_column and current_user.is_authenticated:
            user_id = current_user.user_id

        # Build SQL query dynamically based on column existence
        if has_user_id_column:
            sql = text("""
                INSERT INTO itinerary (traveler_id, user_id, day, day_activity_id, title, description)
                VALUES (:traveler_id, :user_id, :day, :day_activity_id, :title, :description)
                RETURNING itinerary_id
            """)
            result = db.session.execute(sql, {
                'traveler_id': traveler_id,
                'user_id': user_id,
                'day': next_day,
                'day_activity_id': activity_type_id,
                'title': activity.name,
                'description': activity.description
            })
        else:
            sql = text("""
                INSERT INTO itinerary (traveler_id, day, day_activity_id, title, description)
                VALUES (:traveler_id, :day, :day_activity_id, :title, :description)
                RETURNING itinerary_id
            """)
            result = db.session.execute(sql, {
                'traveler_id': traveler_id,
                'day': next_day,
                'day_activity_id': activity_type_id,
                'title': activity.name,
                'description': activity.description
            })

        itinerary_id = result.scalar()
        db.session.commit()

        return jsonify({
            "success": True,
            "message": "Activity added successfully",
            "itinerary_id": itinerary_id,
            "activity": {
                "itinerary_id": itinerary_id,
                "day": next_day,
                "title": activity.name,
                "description": activity.description,
                "duration_days": activity.duration_days or 1,
                "images_url_text": activity.images_url_text,
                "activity_type_id": activity_type_id,
                "price_estimation": float(activity.price_estimation) if activity.price_estimation else 0
            }
        })
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error adding activity: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

