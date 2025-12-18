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

