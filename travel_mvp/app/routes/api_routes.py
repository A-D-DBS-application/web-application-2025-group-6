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
    
    Automatically renumbers remaining days, updates the database, and adjusts end_date.
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
            if itinerary_item.user_id and itinerary_item.user_id != current_user.user_id:
                return jsonify({"success": False, "error": "Unauthorized"}), 403

        # Get traveler to adjust end_date
        from app.models import Traveler
        traveler = safe_db_query(Traveler.query.get, traveler_id)
        
        # Calculate current total duration before removal
        current_duration_sql = text("""
            SELECT SUM(COALESCE(at.duration_days, 1))
            FROM itinerary i
            LEFT JOIN activity_type at ON i.day_activity_id = at.activity_type_id
            WHERE i.traveler_id = :traveler_id
        """)
        current_duration_result = db.session.execute(current_duration_sql, {'traveler_id': traveler_id})
        current_total_duration = current_duration_result.scalar() or 0
        
        # Delete the itinerary item
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
        
        # Adjust end_date if traveler exists and has dates
        date_adjusted = False
        new_end_date = None
        if traveler and traveler.start_date and traveler.end_date:
            # Calculate new total duration after removal
            new_total_duration = current_total_duration - activity_duration
            
            # Calculate planned duration
            total_trip_days = (traveler.end_date - traveler.start_date).days + 1
            
            # If new duration is less than planned, adjust end_date
            if new_total_duration < total_trip_days:
                from datetime import timedelta
                days_to_remove = total_trip_days - new_total_duration
                new_end_date = traveler.end_date - timedelta(days=days_to_remove)
                traveler.end_date = new_end_date
                db.session.commit()
                date_adjusted = True

        return jsonify({
            "success": True,
            "message": "Activity removed successfully",
            "removed_day": removed_day,
            "duration": activity_duration,
            "days_removed": activity_duration,
            "date_adjusted": date_adjusted,
            "new_end_date": new_end_date.strftime('%Y-%m-%d') if new_end_date else None
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
        
        # Exclude Rest Day activities from available activities list
        base_query = base_query.filter(ActivityType.name != "Rest Day")

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
    Checks if adding this activity exceeds the planned trip duration and adjusts end_date if needed.
    """
    try:
        data = request.get_json()
        traveler_id = data.get("traveler_id")
        activity_type_id = data.get("activity_type_id")

        if not all([traveler_id, activity_type_id]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        # Get traveler to check total trip duration
        from app.models import Traveler
        traveler = safe_db_query(Traveler.query.get, traveler_id)
        if not traveler:
            return jsonify({"success": False, "error": "Traveler not found"}), 404

        # Get activity details with retry logic
        activity = safe_db_query(ActivityType.query.get_or_404, activity_type_id)
        activity_duration = activity.duration_days if activity.duration_days else 1

        # Calculate total trip duration from start_date and end_date
        if traveler.start_date and traveler.end_date:
            total_trip_days = (traveler.end_date - traveler.start_date).days + 1
        else:
            total_trip_days = None

        # Calculate current total duration of all activities
        current_duration_sql = text("""
            SELECT SUM(COALESCE(at.duration_days, 1))
            FROM itinerary i
            LEFT JOIN activity_type at ON i.day_activity_id = at.activity_type_id
            WHERE i.traveler_id = :traveler_id
        """)
        current_duration_result = db.session.execute(current_duration_sql, {'traveler_id': traveler_id})
        current_total_duration = current_duration_result.scalar() or 0

        # Calculate new total duration after adding activity
        new_total_duration = current_total_duration + activity_duration

        # Check if we exceed the planned trip duration
        exceeds_duration = False
        warning_message = None
        date_adjusted = False
        new_end_date = None

        if total_trip_days and new_total_duration > total_trip_days:
            exceeds_duration = True
            # Calculate how many extra days we need
            extra_days = new_total_duration - total_trip_days
            
            # Automatically adjust end_date
            from datetime import timedelta
            if traveler.end_date:
                new_end_date = traveler.end_date + timedelta(days=extra_days)
                traveler.end_date = new_end_date
                db.session.commit()
                date_adjusted = True
                warning_message = f"Warning: Adding this activity increases your trip to {new_total_duration} days (exceeds your planned {total_trip_days} days). Your trip end date has been automatically adjusted to {new_end_date.strftime('%Y-%m-%d')}."
            else:
                warning_message = f"Warning: Adding this activity increases your trip to {new_total_duration} days, which exceeds your planned {total_trip_days} days."

        # Find the maximum day number for this traveler to determine next day
        max_day_result = db.session.query(func.max(Itinerary.day)).filter_by(traveler_id=traveler_id).scalar()
        next_day = max((max_day_result or 0) + 1, 2)  # Minimum day 2 for new activities

        # Don't set user_id automatically - only save when user clicks "Save Trip" button
        # This keeps consistency with result_route behavior
        has_user_id_column = check_column_exists('itinerary', 'user_id')
        user_id = None  # Will be set when user clicks "Save Trip"

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
                "duration_days": activity_duration,
                "images_url_text": activity.images_url_text,
                "activity_type_id": activity_type_id,
                "price_estimation": float(activity.price_estimation) if activity.price_estimation else 0
            },
            "warning": warning_message,
            "exceeds_duration": exceeds_duration,
            "date_adjusted": date_adjusted,
            "new_end_date": new_end_date.strftime('%Y-%m-%d') if new_end_date else None,
            "new_total_days": new_total_duration,
            "planned_days": total_trip_days
        })
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error adding activity: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def get_or_create_rest_day_activity(country):
    """
    Get or create a 'Rest Day' activity for the given country.
    
    Since day_activity_id cannot be NULL, we use a special Rest Day activity.
    """
    try:
        # Normalize country name
        country_normalized = country.capitalize() if country else None
        
        # Try to find existing Rest Day activity for this country
        rest_day = safe_db_query(
            lambda: ActivityType.query.filter_by(
                name="Rest Day",
                country=country_normalized
            ).first()
        )
        
        if rest_day:
            # Update image if it doesn't have one
            if not rest_day.images_url_text:
                rest_day_image_url = "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?w=800&h=600&fit=crop&auto=format"
                rest_day.images_url_text = rest_day_image_url
                db.session.commit()
            return rest_day.activity_type_id
        
        # If not found, create one using ORM
        # Check which columns exist to build the activity correctly
        has_child_friendly = check_column_exists('activity_type', 'is_child_friendly')
        has_price = check_column_exists('activity_type', 'price_estimation')
        
        # Create new Rest Day activity with a beautiful relaxing image
        # Using a high-quality Unsplash image of a beautiful African landscape view
        rest_day_image_url = "https://images.unsplash.com/photo-1516026672322-bc52d61a55d5?w=800&h=600&fit=crop&auto=format"
        
        # Create new Rest Day activity
        new_rest_day = ActivityType(
            name="Rest Day",
            description="A relaxing day to unwind and enjoy the surroundings.",
            duration_days=1,
            country=country_normalized,
            price_estimation=0 if has_price else None,
            is_child_friendly=True if has_child_friendly else None,
            images_url_text=rest_day_image_url
        )
        
        db.session.add(new_rest_day)
        db.session.flush()  # Get the ID without committing
        rest_day_id = new_rest_day.activity_type_id
        db.session.commit()
        
        return rest_day_id
            
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error creating/getting rest day activity: {e}")
        import traceback
        traceback.print_exc()
        return None


@api_bp.route("/api/itinerary/<int:itinerary_id>/replace", methods=["POST"])
def replace_itinerary_item(itinerary_id):
    """
    Replace an activity in an itinerary with a new activity or rest day.
    
    Maintains the total trip duration by adding/removing rest days as needed.
    If activity_type_id is provided, replaces with that activity.
    If activity_type_id is None or "rest", replaces with a rest day activity.
    """
    try:
        data = request.get_json()
        new_activity_id = data.get("activity_type_id")  # None for rest day
        is_rest_day = data.get("is_rest_day", False) or new_activity_id is None
        
        itinerary_item = safe_db_query(Itinerary.query.get_or_404, itinerary_id)
        traveler_id = itinerary_item.traveler_id
        old_day = itinerary_item.day
        
        # Get traveler to determine country and total trip duration
        from app.models import Traveler
        traveler = safe_db_query(Traveler.query.get, traveler_id)
        if not traveler:
            return jsonify({"success": False, "error": "Traveler not found"}), 404
        
        country = traveler.country if traveler else None
        
        # Calculate total trip duration from start_date and end_date
        if traveler.start_date and traveler.end_date:
            total_trip_days = (traveler.end_date - traveler.start_date).days + 1
        else:
            # Fallback: calculate from current itinerary
            max_day_sql = text("""
                SELECT MAX(day) FROM itinerary WHERE traveler_id = :traveler_id
            """)
            max_day_result = db.session.execute(max_day_sql, {'traveler_id': traveler_id})
            max_day = max_day_result.scalar() or 0
            # Get duration of last activity
            last_activity_sql = text("""
                SELECT i.day_activity_id FROM itinerary i 
                WHERE i.traveler_id = :traveler_id AND i.day = :max_day
            """)
            last_result = db.session.execute(last_activity_sql, {
                'traveler_id': traveler_id,
                'max_day': max_day
            })
            last_row = last_result.fetchone()
            if last_row and last_row[0]:
                last_activity = safe_db_query(ActivityType.query.get, last_row[0])
                last_duration = last_activity.duration_days if last_activity and last_activity.duration_days else 1
                total_trip_days = max_day + last_duration - 1
            else:
                total_trip_days = max_day
        
        # Calculate current total duration of all activities
        current_duration_sql = text("""
            SELECT SUM(COALESCE(at.duration_days, 1))
            FROM itinerary i
            LEFT JOIN activity_type at ON i.day_activity_id = at.activity_type_id
            WHERE i.traveler_id = :traveler_id
        """)
        current_duration_result = db.session.execute(current_duration_sql, {'traveler_id': traveler_id})
        current_total_duration = current_duration_result.scalar() or 0
        
        # Get old activity duration
        old_activity = safe_db_query(ActivityType.query.get, itinerary_item.day_activity_id)
        old_duration = old_activity.duration_days if old_activity and old_activity.duration_days else 1
        
        # Check authorization if user_id column exists
        has_user_id_column = check_column_exists('itinerary', 'user_id')
        if has_user_id_column and current_user.is_authenticated:
            if itinerary_item.user_id and itinerary_item.user_id != current_user.user_id:
                return jsonify({"success": False, "error": "Unauthorized"}), 403
        
        if is_rest_day:
            # Get or create rest day activity (cannot use NULL for day_activity_id)
            rest_day_activity_id = get_or_create_rest_day_activity(country)
            if not rest_day_activity_id:
                return jsonify({
                    "success": False,
                    "error": "Could not create rest day activity. Please try again."
                }), 500
            
            # Replace with rest day activity on the same day
            # If original activity was multi-day, we'll add additional rest days on the following days
            itinerary_item.day_activity_id = rest_day_activity_id
            itinerary_item.title = "Rest Day"
            itinerary_item.description = "A relaxing day to unwind and enjoy the surroundings."
            new_duration = 1
            
            # If original activity was longer than 1 day, add additional rest days
            # on the following days to maintain the same position
            # First, check if there are any activities on those days that would conflict
            if old_duration > 1:
                # Check for conflicts on days old_day+1 to old_day+old_duration-1
                conflict_check_sql = text("""
                    SELECT COUNT(*) FROM itinerary
                    WHERE traveler_id = :traveler_id
                    AND day >= :start_day AND day < :end_day
                    AND itinerary_id != :exclude_id
                """)
                conflict_result = db.session.execute(conflict_check_sql, {
                    'traveler_id': traveler_id,
                    'start_day': old_day + 1,
                    'end_day': old_day + old_duration,
                    'exclude_id': itinerary_id
                })
                has_conflicts = conflict_result.scalar() > 0
                
                if not has_conflicts:
                    # No conflicts, add rest days on the following days
                    has_user_id_column = check_column_exists('itinerary', 'user_id')
                    for i in range(1, old_duration):  # Add rest days for days 2, 3, etc.
                        additional_rest_day = old_day + i
                        if has_user_id_column:
                            insert_sql = text("""
                                INSERT INTO itinerary (traveler_id, user_id, day, day_activity_id, title, description)
                                VALUES (:traveler_id, NULL, :day, :activity_id, 'Rest Day', 'A relaxing day to unwind and enjoy the surroundings.')
                            """)
                        else:
                            insert_sql = text("""
                                INSERT INTO itinerary (traveler_id, day, day_activity_id, title, description)
                                VALUES (:traveler_id, :day, :activity_id, 'Rest Day', 'A relaxing day to unwind and enjoy the surroundings.')
                            """)
                        db.session.execute(insert_sql, {
                            'traveler_id': traveler_id,
                            'day': additional_rest_day,
                            'activity_id': rest_day_activity_id
                        })
                    # Update new_duration to match old_duration for Rest Day replacement
                    # This prevents renumbering of later activities
                    new_duration = old_duration
                else:
                    # There are conflicts - we'll let the normal renumbering logic handle it
                    # The Rest Day will stay on old_day, and later activities will shift
                    pass
        else:
            # Replace with new activity
            new_activity = safe_db_query(ActivityType.query.get_or_404, new_activity_id)
            
            # Check if activity is already in itinerary (except the one being replaced)
            existing_check = text("""
                SELECT COUNT(*) FROM itinerary 
                WHERE traveler_id = :traveler_id 
                AND day_activity_id = :activity_id 
                AND itinerary_id != :exclude_id
            """)
            result = db.session.execute(existing_check, {
                'traveler_id': traveler_id,
                'activity_id': new_activity_id,
                'exclude_id': itinerary_id
            })
            if result.scalar() > 0:
                return jsonify({
                    "success": False, 
                    "error": "This activity is already in your itinerary"
                }), 400
            
            itinerary_item.day_activity_id = new_activity_id
            itinerary_item.title = new_activity.name
            itinerary_item.description = new_activity.description
            new_duration = new_activity.duration_days if new_activity.duration_days else 1
        
        db.session.commit()
        
        # Calculate new total duration after replacement
        new_total_duration = current_total_duration - old_duration + new_duration
        duration_diff = new_duration - old_duration
        
        # Renumber days if duration changed (do this first)
        if duration_diff != 0:
            # Update day numbers for remaining activities
            if duration_diff > 0:
                # New activity is longer, shift later activities forward
                sql = text("""
                    UPDATE itinerary
                    SET day = day + :increase_by
                    WHERE traveler_id = :traveler_id AND day > :old_day
                """)
                db.session.execute(sql, {
                    'traveler_id': traveler_id,
                    'old_day': old_day,
                    'increase_by': duration_diff
                })
            else:
                # New activity is shorter, shift later activities backward
                sql = text("""
                    UPDATE itinerary
                    SET day = day - :decrease_by
                    WHERE traveler_id = :traveler_id AND day > :old_day
                """)
                db.session.execute(sql, {
                    'traveler_id': traveler_id,
                    'old_day': old_day,
                    'decrease_by': abs(duration_diff)
                })
            db.session.commit()
        
        # After renumbering, check if we need to add rest days or show warning
        # Recalculate new total duration after renumbering
        new_total_duration = current_total_duration - old_duration + new_duration
        
        # Check if we exceed the planned trip duration
        exceeds_duration = new_total_duration > total_trip_days
        warning_message = None
        date_adjusted = False
        new_end_date = None
        
        if exceeds_duration:
            # Automatically adjust end_date
            from datetime import timedelta
            if traveler.end_date:
                extra_days = new_total_duration - total_trip_days
                new_end_date = traveler.end_date + timedelta(days=extra_days)
                traveler.end_date = new_end_date
                db.session.commit()
                date_adjusted = True
                warning_message = f"Warning: This change increases your trip to {new_total_duration} days (exceeds your planned {total_trip_days} days). Your trip end date has been automatically adjusted to {new_end_date.strftime('%Y-%m-%d')}."
            else:
                warning_message = f"Warning: This change increases your trip to {new_total_duration} days, which exceeds your planned {total_trip_days} days."
        
        # If new activity is shorter, add rest days to maintain total duration
        # But only if we're not exceeding the planned duration
        # NOTE: For Rest Day replacements, we already added rest days above if old_duration > 1
        # So we skip this section for Rest Day replacements
        if new_duration < old_duration and not is_rest_day:
            days_to_add = old_duration - new_duration
            
            # Check if adding rest days would exceed total trip duration
            if new_total_duration + days_to_add <= total_trip_days:
                # Find the last day in the itinerary (after renumbering)
                max_day_sql = text("""
                    SELECT MAX(day) FROM itinerary WHERE traveler_id = :traveler_id
                """)
                max_day_result = db.session.execute(max_day_sql, {'traveler_id': traveler_id})
                max_day = max_day_result.scalar() or old_day
                
                # Get the duration of the last activity to find where it ends
                last_activity_sql = text("""
                    SELECT i.day_activity_id, i.day FROM itinerary i 
                    WHERE i.traveler_id = :traveler_id AND i.day = :max_day
                """)
                last_result = db.session.execute(last_activity_sql, {
                    'traveler_id': traveler_id,
                    'max_day': max_day
                })
                last_row = last_result.fetchone()
                
                if last_row and last_row[0]:
                    last_activity = safe_db_query(ActivityType.query.get, last_row[0])
                    last_duration = last_activity.duration_days if last_activity and last_activity.duration_days else 1
                    # Calculate where to insert rest days (after the last activity ends)
                    insert_start_day = max_day + last_duration
                else:
                    insert_start_day = max_day + 1
                
                # Get rest day activity ID
                rest_day_activity_id = get_or_create_rest_day_activity(country)
                if rest_day_activity_id:
                    # Add rest days after the last activity
                    has_user_id_column = check_column_exists('itinerary', 'user_id')
                    for i in range(days_to_add):
                        insert_day = insert_start_day + i
                        if has_user_id_column:
                            insert_sql = text("""
                                INSERT INTO itinerary (traveler_id, user_id, day, day_activity_id, title, description)
                                VALUES (:traveler_id, NULL, :day, :activity_id, 'Rest Day', 'A relaxing day to unwind and enjoy the surroundings.')
                            """)
                        else:
                            insert_sql = text("""
                                INSERT INTO itinerary (traveler_id, day, day_activity_id, title, description)
                                VALUES (:traveler_id, :day, :activity_id, 'Rest Day', 'A relaxing day to unwind and enjoy the surroundings.')
                            """)
                        db.session.execute(insert_sql, {
                            'traveler_id': traveler_id,
                            'day': insert_day,
                            'activity_id': rest_day_activity_id
                        })
                    db.session.commit()
                    # Update new_total_duration to reflect added rest days
                    new_total_duration += days_to_add
        
        # Determine if regeneration is needed
        # For Rest Day replacements, we don't need to regenerate if duration is unchanged
        # (Rest Day should stay on the same day as the original activity)
        rest_days_added = 0
        if new_duration < old_duration and new_total_duration + (old_duration - new_duration) <= total_trip_days:
            rest_days_added = old_duration - new_duration
        
        # Only regenerate if:
        # 1. It's not a Rest Day replacement (new activities need optimization)
        # 2. Or if rest days were added at the end (to show them)
        # 3. Or if duration changed significantly (to renumber days correctly)
        needs_regeneration = not is_rest_day or rest_days_added > 0 or abs(duration_diff) > 0
        
        return jsonify({
            "success": True,
            "message": "Activity replaced successfully",
            "itinerary_id": itinerary_id,
            "needs_regeneration": needs_regeneration,
            "is_rest_day": is_rest_day,
            "day_unchanged": duration_diff == 0,
            "rest_days_added": rest_days_added,
            "warning": warning_message,
            "exceeds_duration": exceeds_duration,
            "date_adjusted": date_adjusted,
            "new_end_date": new_end_date.strftime('%Y-%m-%d') if new_end_date else None,
            "new_total_days": new_total_duration,
            "planned_days": total_trip_days
        })
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error replacing activity: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/itinerary/regenerate", methods=["POST"])
def regenerate_itinerary():
    """
    Regenerate the itinerary page after activity replacement.
    
    This endpoint regenerates the itinerary using the optimizer to maintain
    the route logic and correct day numbers.
    """
    try:
        data = request.get_json()
        traveler_id = data.get("traveler_id")
        
        if not traveler_id:
            return jsonify({"success": False, "error": "Missing traveler_id"}), 400
        
        # Get traveler info
        from app.models import Traveler
        traveler = safe_db_query(Traveler.query.get_or_404, traveler_id)
        
        # Get all itinerary items for this traveler
        itinerary_items = safe_db_query(
            lambda: Itinerary.query.filter_by(traveler_id=traveler_id)
            .order_by(Itinerary.day.asc())
            .all()
        )
        
        if not itinerary_items:
            return jsonify({"success": False, "error": "No itinerary found"}), 404
        
        # Get country
        country = traveler.country.lower() if traveler.country else ""
        
        # Extract activity IDs (excluding rest days where day_activity_id is NULL)
        activity_ids = [item.day_activity_id for item in itinerary_items if item.day_activity_id is not None]
        
        # Regenerate optimized route if we have activities
        if activity_ids and country:
            from app.optimizer import solve_travel_route
            try:
                optimized_activities = solve_travel_route(activity_ids, country=country)
                
                if optimized_activities:
                    # Create mapping of activity_id to itinerary item
                    activity_to_item = {}
                    rest_days = []  # Track rest days separately
                    
                    for item in itinerary_items:
                        # Check if this is a Rest Day activity
                        activity = safe_db_query(ActivityType.query.get, item.day_activity_id) if item.day_activity_id else None
                        is_rest_day = (
                            item.day_activity_id is None or
                            (activity and activity.name == "Rest Day")
                        )
                        
                        if is_rest_day:
                            # Rest day - keep original position info
                            rest_days.append({
                                'itinerary_id': item.itinerary_id,
                                'day': item.day,
                                'title': item.title or "Rest Day",
                                'description': item.description or "A relaxing day to unwind and enjoy the surroundings.",
                                'activity_type_id': item.day_activity_id,
                                'activity': activity
                            })
                        else:
                            activity_to_item[item.day_activity_id] = item
                    
                    # Rebuild itinerary in optimized order
                    new_itinerary_list = []
                    current_day = 1
                    
                    # Add optimized activities
                    for opt_activity in optimized_activities:
                        activity_id = opt_activity.activity_type_id
                        activity_duration = opt_activity.duration_days or 1
                        
                        if activity_id in activity_to_item:
                            item = activity_to_item[activity_id]
                            
                            # Update day in database
                            item.day = current_day
                            item.title = opt_activity.name
                            item.description = opt_activity.description
                            
                            new_itinerary_list.append({
                                "itinerary_id": item.itinerary_id,
                                "day": current_day,
                                "title": item.title,
                                "description": item.description,
                                "activity_type_id": activity_id,
                                "activity": opt_activity
                            })
                            
                            current_day += activity_duration
                    
                    # Add rest days back in their approximate positions
                    # (This is a simplified approach - you might want more sophisticated logic)
                    for rest_day in rest_days:
                        # Insert rest day at appropriate position
                        new_itinerary_list.append({
                            "itinerary_id": rest_day['itinerary_id'],
                            "day": current_day,
                            "title": rest_day['title'],
                            "description": rest_day['description'],
                            "activity_type_id": None,
                            "activity": None
                        })
                        current_day += 1
                    
                    # Sort by day
                    new_itinerary_list.sort(key=lambda x: x['day'])
                    
                    # Update database with new day numbers
                    for item_data in new_itinerary_list:
                        update_sql = text("""
                            UPDATE itinerary
                            SET day = :new_day
                            WHERE itinerary_id = :itinerary_id
                        """)
                        db.session.execute(update_sql, {
                            'new_day': item_data['day'],
                            'itinerary_id': item_data['itinerary_id']
                        })
                    
                    db.session.commit()
                    
                    # Return updated itinerary data
                    return jsonify({
                        "success": True,
                        "itinerary": new_itinerary_list,
                        "message": "Itinerary regenerated successfully"
                    })
            except Exception as opt_error:
                print(f"Warning: Route optimization failed during regeneration: {opt_error}")
                # Fall through to return current itinerary
        
        # Return current itinerary if optimization not needed or failed
        itinerary_list = []
        for item in itinerary_items:
            activity = None
            if item.day_activity_id:
                activity = safe_db_query(ActivityType.query.get, item.day_activity_id)
            
            itinerary_list.append({
                "itinerary_id": item.itinerary_id,
                "day": item.day,
                "title": item.title,
                "description": item.description,
                "activity_type_id": item.day_activity_id,
                "activity": activity
            })
        
        return jsonify({
            "success": True,
            "itinerary": itinerary_list,
            "message": "Itinerary retrieved successfully"
        })
        
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error regenerating itinerary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/api/itinerary/save", methods=["POST"])
@login_required
def save_itinerary():
    """
    Save an itinerary to the current user's account.
    
    Updates all itinerary items for a given traveler_id with the current user's user_id.
    This allows users to save trips that were created while not logged in.
    """
    try:
        data = request.get_json()
        traveler_id = data.get("traveler_id")
        
        if not traveler_id:
            return jsonify({"success": False, "error": "Missing traveler_id"}), 400
        
        # Check if user_id column exists
        has_user_id_column = check_column_exists('itinerary', 'user_id')
        if not has_user_id_column:
            # Try to add the column automatically
            try:
                print("Attempting to add user_id column automatically...")
                db.session.execute(text("""
                    ALTER TABLE itinerary 
                    ADD COLUMN IF NOT EXISTS user_id INTEGER
                """))
                
                # Try to add foreign key constraint
                try:
                    db.session.execute(text("""
                        DO $$
                        BEGIN
                            IF NOT EXISTS (
                                SELECT 1 FROM information_schema.table_constraints 
                                WHERE table_schema = 'public' 
                                AND table_name = 'itinerary' 
                                AND constraint_name = 'fk_itinerary_user'
                            ) THEN
                                ALTER TABLE itinerary 
                                ADD CONSTRAINT fk_itinerary_user 
                                FOREIGN KEY (user_id) REFERENCES users(user_id);
                            END IF;
                        END $$;
                    """))
                except Exception as fk_error:
                    # Foreign key might already exist or fail - that's okay
                    print(f"Note: Foreign key constraint handling: {fk_error}")
                
                db.session.commit()
                print("✓ Successfully added user_id column!")
                # Re-check after adding
                has_user_id_column = check_column_exists('itinerary', 'user_id')
            except Exception as auto_add_error:
                db.session.rollback()
                print(f"Could not auto-add column: {auto_add_error}")
                error_msg = (
                    "Database migration required. The user_id column does not exist in the itinerary table. "
                    "Please run one of the following commands:\n"
                    "1. flask db upgrade (recommended)\n"
                    "2. python run_migration.py\n"
                    "3. python add_user_id_column.py\n"
                    "This will add the user_id column to save trips to your account."
                )
                return jsonify({"success": False, "error": error_msg}), 500
        
        if not has_user_id_column:
            error_msg = (
                "Database migration required. The user_id column does not exist in the itinerary table. "
                "Please run one of the following commands:\n"
                "1. flask db upgrade (recommended)\n"
                "2. python run_migration.py\n"
                "3. python add_user_id_column.py\n"
                "This will add the user_id column to save trips to your account."
            )
            return jsonify({"success": False, "error": error_msg}), 500
        
        # Get current user_id
        user_id = current_user.user_id
        
        # Debug: Check what traveler_id we received
        print(f"DEBUG: Attempting to save trip for traveler_id={traveler_id}, user_id={user_id}")
        
        # Check if itinerary items exist for this traveler_id
        # Try multiple ways to find the items - include items that might already have a user_id
        itinerary_items = safe_db_query(
            lambda: Itinerary.query.filter_by(traveler_id=traveler_id).all()
        )
        
        # Also try to find items that might have been saved to this user already
        if not itinerary_items:
            # Check if items exist but are already saved to this user
            already_saved_items = safe_db_query(
                lambda: Itinerary.query.filter_by(traveler_id=traveler_id, user_id=user_id).all()
            )
            if already_saved_items:
                return jsonify({
                    "success": True,
                    "message": f"This trip is already saved to your account! ({len(already_saved_items)} items)",
                    "rows_updated": 0,
                    "already_saved": True
                })
        
        # If no items found, try with raw SQL to see what's in the database
        if not itinerary_items:
            print(f"DEBUG: No items found with ORM query for traveler_id={traveler_id}")
            # Try raw SQL query to see if items exist
            try:
                sql_check = text("""
                    SELECT itinerary_id, traveler_id, user_id, day, title 
                    FROM itinerary 
                    WHERE traveler_id = :traveler_id
                    LIMIT 5
                """)
                result = db.session.execute(sql_check, {'traveler_id': traveler_id})
                rows = result.fetchall()
                if rows:
                    print(f"DEBUG: Found {len(rows)} items with raw SQL:")
                    for row in rows:
                        print(f"  - itinerary_id={row[0]}, traveler_id={row[1]}, user_id={row[2]}, day={row[3]}, title={row[4]}")
                    # Convert to Itinerary objects
                    itinerary_ids = [row[0] for row in rows]
                    itinerary_items = safe_db_query(
                        lambda: Itinerary.query.filter(Itinerary.itinerary_id.in_(itinerary_ids)).all()
                    )
                else:
                    # Check if traveler_id exists at all
                    traveler_check = text("SELECT traveler_id FROM traveler WHERE traveler_id = :traveler_id")
                    traveler_result = db.session.execute(traveler_check, {'traveler_id': traveler_id})
                    if not traveler_result.fetchone():
                        return jsonify({
                            "success": False, 
                            "error": f"Traveler with ID {traveler_id} does not exist. Please generate a new trip."
                        }), 404
                    
                    # Check if there are any itinerary items at all
                    any_items_check = text("SELECT COUNT(*) FROM itinerary")
                    count_result = db.session.execute(any_items_check)
                    total_count = count_result.scalar()
                    print(f"DEBUG: Total itinerary items in database: {total_count}")
                    
                    return jsonify({
                        "success": False, 
                        "error": f"No itinerary items found for this trip. This might happen if:\n1. The trip was not fully generated\n2. You're trying to save a trip from a different session\n3. The trip data was cleared\n\nPlease generate a new trip and try saving again."
                    }), 404
            except Exception as debug_error:
                print(f"DEBUG: Error during debug query: {debug_error}")
        
        if not itinerary_items:
            return jsonify({
                "success": False, 
                "error": f"No itinerary items found for this trip. Please generate a new trip first, then try saving it."
            }), 404
        
        print(f"DEBUG: Found {len(itinerary_items)} itinerary items to save")
        
        # Check if any items already belong to another user
        for item in itinerary_items:
            if item.user_id is not None and item.user_id != user_id:
                return jsonify({"success": False, "error": "This trip already belongs to another user"}), 403
        
        # Update all itinerary items with the current user's user_id
        update_sql = text("""
            UPDATE itinerary 
            SET user_id = :user_id 
            WHERE traveler_id = :traveler_id AND (user_id IS NULL OR user_id = :user_id)
        """)
        result = db.session.execute(update_sql, {
            'user_id': user_id,
            'traveler_id': traveler_id
        })
        
        rows_updated = result.rowcount
        db.session.commit()
        
        if rows_updated > 0:
            return jsonify({
                "success": True,
                "message": f"Trip saved successfully! {rows_updated} itinerary items saved to your account.",
                "rows_updated": rows_updated
            })
        else:
            return jsonify({
                "success": False,
                "error": "No items were updated. The trip may already be saved."
            }), 400
            
    except Exception as e:
        db.session.rollback()
        db.session.expire_all()
        print(f"Error saving itinerary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

