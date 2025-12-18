"""
Main routes for the travel MVP application.

Handles core trip planning functionality:
- Home page and destination selection
- Step 1: Date and budget selection
- Step 2: Travel group and interest preferences
- Result: Generated itinerary display
"""

from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from flask_login import current_user
from app import db 
from app.models import Traveler, ActivityType, Itinerary 
from datetime import date
from sqlalchemy import text
from app.optimizer import solve_travel_route
from app.utils import (
    parse_date,
    format_date_for_display,
    clear_session_preserve_login,
    save_session_preferences,
    restore_session_preferences,
    get_country_image_path,
    check_column_exists,
    safe_db_query
)
import random 

main_bp = Blueprint("main", __name__)

def check_session_requirements(required_keys):
    """
    Check if all required session keys are present.
    
    Args:
        required_keys: List of required session key names
        
    Returns:
        Tuple of (is_valid, redirect_response)
    """
    missing_keys = [key for key in required_keys if not session.get(key)]
    if missing_keys:
        if 'country' in missing_keys:
            flash("Please select a destination first.", "warning")
        return False, redirect(url_for("main.index"))
    return True, None


def create_traveler_from_session():
    """
    Create a Traveler object from session data.
    
    Returns:
        Tuple of (traveler_object, error_message)
    """
    try:
        new_traveler = Traveler(
            start_date=parse_date(session.get("start_date")),
            end_date=parse_date(session.get("end_date")),
            budget_range=session.get("budget_range"),
            accommodation_type=session.get("accommodation_type"),
            country=session.get("country"),
            adults=session.get("adults"),
            children=session.get("children"),
            interest_culture=session.get("interest_culture"),
            interest_food=session.get("interest_food"),
            interest_wildlife=session.get("interest_wildlife"),
            interest_history=session.get("interest_history"),
            interest_beach=session.get("interest_beach")
        )
        db.session.add(new_traveler)
        db.session.commit()
        return new_traveler, None
    except Exception as e:
        db.session.rollback()
        return None, str(e)

def prepare_result_data(itinerary_list, country_from_traveler=None):
    """
    Prepare data for the result template.
    
    Args:
        itinerary_list: List of itinerary items
        country_from_traveler: Optional country from Traveler object as fallback
        
    Returns:
        Dictionary with all data needed for result template
    """
    start_date_formatted = format_date_for_display(session.get("start_date"))
    end_date_formatted = format_date_for_display(session.get("end_date"))
    
    # Determine background image based on selected country
    country = (session.get("country") or country_from_traveler or "").lower()
    background_image = get_country_image_path(country)
    
    return {
        "start": start_date_formatted,
        "end": end_date_formatted,
        "budget": session.get("budget_range"),
        "adults": session.get("adults"),
        "children": session.get("children"),
        "accommodation": session.get("accommodation_type"),
        "itinerary": itinerary_list,
        "background_image": background_image,
        "country": country
    } 

# --- Algorithmic Component (De logica blijft ONGEWIJZIGD) ---
def generate_itinerary(traveler_data):
    """
    Genereert een reisplan op basis van Priority Scoring, 
    waarbij Budgetfiltering in de Query wordt genegeerd.
    """
    
    interests = {
        'Culture': traveler_data.interest_culture or 0,
        'Food': traveler_data.interest_food or 0,
        'Wildlife': traveler_data.interest_wildlife or 0,
        'History': traveler_data.interest_history or 0,
        'Beach': traveler_data.interest_beach or 0
    }
    
    if isinstance(traveler_data.start_date, date) and isinstance(traveler_data.end_date, date):
        duration_days = (traveler_data.end_date - traveler_data.start_date).days + 1
    else:
        duration_days = 3 
        
    if duration_days <= 0:
        duration_days = 1 
    
    # Query Activiteiten via ORM (SQLAlchemy)
    # ORM voordelen: directe database connectie, minder code, automatische Python object conversie
    # BACKEND FILTERING: alleen benodigde data ophalen (security en efficiency)
    # Alleen activiteiten voor het gekozen land worden opgehaald
    chosen_categories = [k for k, v in interests.items() if v > 0]
    
    # Get number of children from traveler_data
    num_children = traveler_data.children or 0
    
    # Build base query with country filter
    base_query = ActivityType.query.filter(ActivityType.country == traveler_data.country)
    
    # Apply child-friendly filter if children are present
    # IF num_children > 0: only fetch activities where is_child_friendly is TRUE
    # ELSE: no filter (adults can do all activities)
    if num_children > 0:
        has_child_friendly_column = check_column_exists('activity_type', 'is_child_friendly')
        if has_child_friendly_column:
            base_query = base_query.filter(ActivityType.is_child_friendly == True)
        else:
            print("Warning: is_child_friendly column does not exist yet. Skipping child-friendly filter.")
    
    # Apply interest categories filter if any are selected
    # Use safe_db_query for automatic retry on transaction errors
    if chosen_categories:
        activities = safe_db_query(
            lambda: base_query.filter(ActivityType.interest_categ.op('&&')(chosen_categories)).all()
        )
    else:
        activities = safe_db_query(lambda: base_query.all())

    # Priority Scoring
    scored_activities = []
    for activity in activities:
        score = 0
        activity_categories = activity.interest_categ 
        
        if not activity_categories or not isinstance(activity_categories, list):
             activity_categories = []
        
        for category, interest_score in interests.items():
            if category in activity_categories:
                score += interest_score 
        
        scored_activities.append({
            'activity': activity,
            'score': score
        })

    # Sorteer op de hoogste score
    random.shuffle(scored_activities)
    scored_activities.sort(key=lambda x: x['score'], reverse=True)
    
    # Selecteer activiteiten die in de duur passen
    selected_activities = []
    current_day = 1
    
    for item in scored_activities:
        activity = item['activity']
        activity_duration = activity.duration_days or 1
        
        if current_day <= duration_days and current_day + activity_duration - 1 <= duration_days:
            selected_activities.append(activity)
            current_day += activity_duration
    
    # Optimaliseer route met TSP (voor alle landen met startpunt en coördinaten)
    if selected_activities and traveler_data.country:
        try:
            activity_ids = [a.activity_type_id for a in selected_activities]
            # Startpunt wordt automatisch toegevoegd uit starting_points tabel
            # Geen specifieke activiteit ID filter nodig
            
            if len(activity_ids) >= 1:  # Minimaal 1 activiteit nodig
                optimized_activities = solve_travel_route(activity_ids, country=traveler_data.country)
                # Als optimalisatie succesvol was en we activiteiten terugkrijgen, gebruik de geoptimaliseerde volgorde
                if optimized_activities and len(optimized_activities) > 0:
                    # Maak een mapping van activity_id naar activity object voor snelle lookup
                    activity_map = {a.activity_type_id: a for a in selected_activities}
                    
                    # Reorder selected_activities volgens optimized_activities
                    reordered_activities = []
                    for opt_activity in optimized_activities:
                        if opt_activity.activity_type_id in activity_map:
                            reordered_activities.append(activity_map[opt_activity.activity_type_id])
                    
                    # Voeg eventuele activiteiten toe die niet geoptimaliseerd werden (zonder coördinaten)
                    for orig_activity in selected_activities:
                        if orig_activity.activity_type_id not in [a.activity_type_id for a in optimized_activities]:
                            reordered_activities.append(orig_activity)
                    
                    if reordered_activities:
                        selected_activities = reordered_activities
                        print(f"Route optimized: {len(optimized_activities)} activities reordered")
        except Exception as e:
            # Als optimalisatie faalt, gebruik originele volgorde
            print(f"Warning: Route optimization failed: {e}. Using original order.")
            import traceback
            traceback.print_exc()
    
    # Planning genereren met geoptimaliseerde volgorde
    itinerary_list = []
    current_day = 1
    
    for activity in selected_activities:
        activity_duration = activity.duration_days or 1
        
        if current_day <= duration_days and current_day + activity_duration - 1 <= duration_days:
            itinerary_list.append({
                "day": current_day, 
                "title": activity.name,
                "description": activity.description,
                "activity_type_id": activity.activity_type_id,
                "activity": activity 
            })
            current_day += activity_duration
            
    # Fill remaining days with placeholder activity (Local Exploration - geen database link)
    # Dit is een dummy activiteit zonder database link, zodat echte activiteiten (zoals Gorilla Trekking ID 1) normaal kunnen functioneren
    while current_day <= duration_days:
        # Bereken hoeveel dagen er nog over zijn
        remaining_days = duration_days - current_day + 1
        
        # Bepaal de dag display tekst
        if remaining_days == 1:
            day_display = f"Day {current_day}"
            title = f"Day {current_day} – Local Exploration"
        else:
            end_day = current_day + remaining_days - 1
            day_display = f"Day {current_day} – {end_day}"
            title = f"Day {current_day} – {end_day} – Local Exploration"
        
        description = "Enjoy free days to explore the local area, shop, or relax."
        
        # Maak een volledig dummy activity object zonder database link
        # Dit voorkomt dat het wordt meegenomen in route optimalisatie of database opslag
        class LocalExplorationActivity:
            def __init__(self, start_day, duration):
                self.activity_type_id = None  # Geen database link - belangrijk!
                self.name = title
                self.description = description
                self.duration_days = duration
                self.price_estimation = 0
                self.country = traveler_data.country
                self.images_url_text = None
                self.interest_categ = []
                # Geen coördinaten - dit voorkomt dat het wordt meegenomen in route optimalisatie
                self.latitude = None
                self.longitude = None
        
        # Maak placeholder voor de resterende dagen
        placeholder_activity = LocalExplorationActivity(current_day, remaining_days)
        
        itinerary_list.append({
            "day": current_day,
            "title": title,
            "description": description,
            "activity_type_id": None,  # Geen database link - belangrijk!
            "activity": placeholder_activity
        })
        
        # Stop de loop - we hebben alle resterende dagen opgevuld
        break

    return itinerary_list[:duration_days] 

# --- Routes ---

@main_bp.route("/")
def index():
    """Toont de bestemmingskeuze (wordt nu afgehandeld door index.html)."""
    # Only clear country when coming from Home button, keep other preferences
    # Check if this is a full reset (from "Start a new planning" button)
    reset_all = request.args.get('reset') == 'all'
    
    # Flask-Login uses these keys in session - preserve them
    flask_login_keys = ['_user_id', '_fresh', '_id', '_remember_me']
    
    if reset_all:
        # Full reset - clear trip planning data but preserve Flask-Login session
        clear_session_preserve_login()
    else:
        # Only reset country, keep preferences
        if 'country' in session:
            del session['country']
        if 'duration' in session:
            del session['duration']
    
    return render_template("index.html")

# NIEUWE ROUTE: Verwerkt de klik op de 'Discover [Land]' knoppen
@main_bp.route("/start_trip/<country_name>", methods=["POST"])
def start_trip_route(country_name):
    """Slaat de gekozen bestemming op en leidt door naar Step 1."""
    # Only update country and reset duration, keep other preferences
    session["country"] = country_name
    session["duration"] = "N/A" # Reset duur
    return redirect(url_for("main.step1_route"))

@main_bp.route("/step1", methods=["GET", "POST"])
def step1_route():
    if request.method == "POST":
        # De data komt nu van de HTML5 date picker (YYYY-MM-DD)
        session["start_date"] = request.form.get("start_date")
        session["end_date"] = request.form.get("end_date")
        session["budget_range"] = request.form.get("budget_range")
        
        # Land komt al uit de sessie, maar wordt voor de zekerheid nogmaals gecontroleerd
        country_from_form = request.form.get("country")
        if country_from_form:
            session["country"] = country_from_form
        
        # Calculate trip duration
        start_date = parse_date(session.get("start_date"))
        end_date = parse_date(session.get("end_date"))
        
        if start_date and end_date and end_date >= start_date:
            duration = (end_date - start_date).days + 1
        else:
            duration = "N/A"
        session["duration"] = duration
        
        return redirect(url_for("main.step2_route"))

    # Toon het formulier voor GET request
    is_valid, redirect_response = check_session_requirements(["country"])
    if not is_valid:
        return redirect_response
    
    # Pass saved values to template
    return render_template(
        "step1.html",
        saved_start_date=session.get("start_date", ""),
        saved_end_date=session.get("end_date", ""),
        saved_budget=session.get("budget_range", "")
    )


@main_bp.route("/step2", methods=["GET", "POST"])
def step2_route():
    if request.method == "POST":
        session["adults"] = request.form.get("adults", type=int)
        session["children"] = request.form.get("children", type=int)
        session["accommodation_type"] = request.form.get("accommodation_type")
        
        session["interest_culture"] = request.form.get("culture", type=int)
        session["interest_food"] = request.form.get("food", type=int)
        session["interest_wildlife"] = request.form.get("wildlife", type=int)
        session["interest_history"] = request.form.get("history", type=int)
        session["interest_beach"] = request.form.get("beach", type=int)

        return redirect(url_for("main.result_route"))
        
    is_valid, redirect_response = check_session_requirements(["country"])
    if not is_valid:
        return redirect_response

    return render_template(
        "step2.html",
        duration=session.get("duration", "N/A"),
        budget=session.get("budget_range", "N/A"),
        country=session.get("country", "N/A"),
        # Pass saved preferences to template
        saved_adults=session.get("adults", 1),
        saved_children=session.get("children", 0),
        saved_accommodation=session.get("accommodation_type", ""),
        saved_culture=session.get("interest_culture", 0),
        saved_food=session.get("interest_food", 0),
        saved_wildlife=session.get("interest_wildlife", 0),
        saved_history=session.get("interest_history", 0),
        saved_beach=session.get("interest_beach", 0)
    )


@main_bp.route("/result")
def result_route():
    # 1. Check session requirements
    is_valid, redirect_response = check_session_requirements(["country", "start_date"])
    if not is_valid:
        return redirect_response
    
    # 2. Opslaan van de Traveler data via ORM (SQLAlchemy)
    # Gebruik ORM in plaats van Supabase client calls voor minder afhankelijkheid en minder code
    new_traveler, error = create_traveler_from_session()
    
    if error:
        flash(f"Fout bij het opslaan van reizigersgegevens in de database.", "danger")
        print(f"DATABASE FOUT: {error}")
        # Gebruik country uit session als fallback bij error
        data = prepare_result_data([], session.get("country"))
        return render_template("result.html", **data)
        
    traveler_id = new_traveler.traveler_id
    country = new_traveler.country if new_traveler else session.get("country", "")
    
    # 3. Het Algoritme draaien
    itinerary_list = generate_itinerary(new_traveler)
    
    # 4. Optimaliseer route VOORDAT items in database worden opgeslagen (voor alle landen met startpunt)
    # Verander de volgorde: Roep de optimizer aan voordat je de items voor het eerst in de database opslaat
    if country and itinerary_list:
        try:
            # Extract activity IDs from itinerary_list
            activity_ids = [item.get("activity_type_id") for item in itinerary_list if item.get("activity_type_id") is not None]
            # Startpunt wordt automatisch toegevoegd uit starting_points tabel
            # Geen specifieke activiteit ID filter nodig
            
            if len(activity_ids) >= 1:
                # Roep solve_travel_route aan om de lijst optimized_activities te verkrijgen
                print(f"Calling solve_travel_route with {len(activity_ids)} activity IDs BEFORE saving to database...")
                optimized_activities = solve_travel_route(activity_ids, country=country)
                print(f"solve_travel_route returned {len(optimized_activities) if optimized_activities else 0} activities")
                
                if optimized_activities and len(optimized_activities) > 0:
                    print(f"Optimizer returned {len(optimized_activities)} activities in optimized order")
                    
                    # Update de itinerary_list variabele direct nadat de optimizer klaar is
                    # Zorg dat de lijst die naar render_template gaat (itinerary=itinerary_list) de exacte volgorde heeft van optimized_activities
                    
                    # Maak een mapping van activity_id naar item in itinerary_list
                    activity_to_item = {}
                    for item in itinerary_list:
                        activity_id = item.get("activity_type_id")
                        if activity_id:
                            activity_to_item[activity_id] = item
                    
                    # Rebuild itinerary_list in de exacte volgorde van optimized_activities
                    # Zorg dat de dagnummers in de UI opnieuw worden berekend op basis van de nieuwe volgorde en duration_days
                    new_itinerary_list = []
                    current_day = 1
                    
                    # Loop door optimized_activities in de exacte volgorde
                    for opt_activity in optimized_activities:
                        activity_id = opt_activity.activity_type_id
                        activity_duration = opt_activity.duration_days or 1
                        
                        if activity_id in activity_to_item:
                            item = activity_to_item[activity_id].copy()
                            # Update day op basis van nieuwe volgorde en duration_days
                            item["day"] = current_day
                            item["activity"] = opt_activity  # Gebruik het geoptimaliseerde activity object
                            new_itinerary_list.append(item)
                            current_day += activity_duration
                    
                    # Voeg activiteiten toe die niet geoptimaliseerd werden (zonder coördinaten)
                    optimized_activity_ids = {a.activity_type_id for a in optimized_activities}
                    for item in itinerary_list:
                        activity_id = item.get("activity_type_id")
                        if activity_id and activity_id not in optimized_activity_ids:
                            activity = item.get("activity")
                            activity_duration = (activity.duration_days if activity and hasattr(activity, 'duration_days') else 1)
                            item["day"] = current_day
                            new_itinerary_list.append(item)
                            current_day += activity_duration
                    
                    # Vervang itinerary_list met de geoptimaliseerde versie
                    itinerary_list = new_itinerary_list
                    print(f"✓ itinerary_list updated with optimized order. Total items: {len(itinerary_list)}")
                    print(f"✓ Day numbers recalculated based on new order and duration_days")
                    
        except Exception as e:
            print(f"Warning: Route optimization failed: {e}. Using original order.")
            import traceback
            traceback.print_exc()
    
    # 5. Opslaan van het gegenereerde reisplan via ORM (SQLAlchemy)
    # Nu opslaan met de geoptimaliseerde volgorde
    saved_itinerary_ids = []
    db_error_occurred = False
    try:
        # Get current user_id if logged in
        user_id = current_user.user_id if current_user.is_authenticated else None
        
        for item in itinerary_list:
            if item.get("activity_type_id") is not None:
                new_itinerary_item = Itinerary(
                    traveler_id=traveler_id,
                    user_id=user_id,  # Link to user if logged in
                    day=item["day"],
                    day_activity_id=item["activity_type_id"],
                    title=item["title"],
                    description=item["description"]
                )
                db.session.add(new_itinerary_item)
                db.session.flush()  # Get the itinerary_id without committing
                saved_itinerary_ids.append(new_itinerary_item.itinerary_id)
                # Add itinerary_id to the item for template
                item["itinerary_id"] = new_itinerary_item.itinerary_id
        
        db.session.commit()
        
    except Exception as e:
        db.session.rollback()  # Rollback transaction on error
        db_error_occurred = True
        error_msg = str(e)
        if "user_id" in error_msg and "does not exist" in error_msg:
            flash("Database migration required. Please run: flask db upgrade", "warning")
        else:
            flash(f"Fout bij het opslaan van de reisplan.", "danger")
        print(f"DATABASE FOUT BIJ ITINERARY: {e}")
        # Reset de sessie na een rollback om verdere queries mogelijk te maken
        db.session.expire_all()
    
    # 6. Optionele verificatie: Update database met geoptimaliseerde volgorde (alleen als user_id onbetrouwbaar is, gebruik alleen traveler_id)
    # Fix de database update: Gebruik alleen traveler_id om te updaten als user_id onbetrouwbaar is in de itinerary tabel
    # OPMERKING: De optimizer is al aangeroepen in stap 4 en itinerary_list is al geüpdatet met de juiste volgorde
    # Deze stap is alleen voor verificatie/extra zekerheid dat de database correct is
    if not db_error_occurred and country and itinerary_list and saved_itinerary_ids:
        try:
            # Check if user_id column is reliable
            has_user_id_column = check_column_exists('itinerary', 'user_id')
            use_user_id_filter = has_user_id_column and current_user.is_authenticated
            
            if use_user_id_filter:
                current_user_id = current_user.get_id()
                print(f"Verifying database: Using user_id filter: user_id={current_user_id}")
            else:
                print(f"Verifying database: Using only traveler_id filter (user_id column missing or user not authenticated)")
            
            # Update database records met de geoptimaliseerde volgorde uit itinerary_list
            # Gebruik alleen traveler_id als user_id onbetrouwbaar is
            current_day = 1
            updated_count = 0
            
            print("Verifying/updating database records with optimized order:")
            for idx, item in enumerate(itinerary_list, 1):
                activity_id = item.get("activity_type_id")
                activity = item.get("activity")
                activity_duration = (activity.duration_days if activity and hasattr(activity, 'duration_days') else 1) if activity else 1
                
                if activity_id:
                    # UPDATE statement: gebruik alleen traveler_id als user_id onbetrouwbaar is
                    if use_user_id_filter:
                        update_sql = text("""
                            UPDATE itinerary 
                            SET day = :new_day 
                            WHERE traveler_id = :traveler_id AND user_id = :user_id AND day_activity_id = :act_id
                        """)
                        result = db.session.execute(update_sql, {
                            'new_day': current_day,
                            'traveler_id': traveler_id,
                            'user_id': int(current_user_id),
                            'act_id': activity_id
                        })
                    else:
                        # Gebruik alleen traveler_id om te updaten als user_id onbetrouwbaar is
                        update_sql = text("""
                            UPDATE itinerary 
                            SET day = :new_day 
                            WHERE traveler_id = :traveler_id AND day_activity_id = :act_id
                        """)
                        result = db.session.execute(update_sql, {
                            'new_day': current_day,
                            'traveler_id': traveler_id,
                            'act_id': activity_id
                        })
                    
                    rows_affected = result.rowcount
                    if rows_affected > 0:
                        updated_count += 1
                        print(f"  [{idx}] Verified/Updated day={current_day} for activity_id={activity_id} - duration: {activity_duration} days")
                    else:
                        print(f"  WARNING: No rows updated for traveler_id={traveler_id}, day_activity_id={activity_id}")
                    
                    current_day += activity_duration
            
            if updated_count > 0:
                db.session.commit()
                print(f"✓ Database verified/updated: {updated_count} itinerary records confirmed")
            else:
                print(f"⚠️  No records were updated. This may indicate a problem.")
        except Exception as e:
            db.session.rollback()
            db.session.expire_all()
            print(f"Warning: Database verification/update failed: {e}. Using saved order.")
            import traceback
            traceback.print_exc()
    
    # 6. Resultaten tonen
    # Save all preferences data before clearing session using shared function
    saved_preferences = save_session_preferences()
    
    # Prepare result data using shared function (country is nog beschikbaar in session)
    data = prepare_result_data(itinerary_list, new_traveler.country if new_traveler else None)
    
    # Add traveler_id and country for editing functionality
    data["traveler_id"] = traveler_id
    data["country"] = new_traveler.country if new_traveler else session.get("country", "")
    
    # Clear trip planning data but preserve Flask-Login session
    clear_session_preserve_login()
    
    # Restore all preferences data so they're available when clicking Preferences from result page
    restore_session_preferences(saved_preferences)
    
    return render_template("result.html", **data)


# Note: Authentication, API, and itinerary management routes have been moved to separate blueprints:
# - app/routes/auth_routes.py (login, logout)
# - app/routes/api_routes.py (remove, add activities)
# - app/routes/itinerary_routes.py (my-trips)

# All API routes have been moved to app/routes/api_routes.py