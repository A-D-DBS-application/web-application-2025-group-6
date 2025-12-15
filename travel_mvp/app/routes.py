from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app import db 
from app.models import Traveler, ActivityType, Itinerary, User
from datetime import datetime, date
from sqlalchemy import func, text, inspect
from app.optimizer import solve_travel_route
import json 
import random 

main_bp = Blueprint("main", __name__)

# Functie om de start- en einddatum om te zetten van string naar Python Date object
# Deze functie kan nu zowel dd/mm/yyyy (oude HTML) als yyyy-mm-dd (nieuwe HTML5 date input) verwerken
def parse_date(date_str):
    if not date_str:
        return None
    try:
        # Probeer het nieuwe HTML5 format (YYYY-MM-DD)
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        try:
            # Probeer het oude format (DD/MM/YYYY)
            return datetime.strptime(date_str, '%d/%m/%Y').date()
        except ValueError:
            return None
    except TypeError:
        return None

# Functie om het budgetbereik om te zetten naar een numerieke limiet (NIET MEER GEBRUIKT VOOR FILTERING)
def get_max_budget(budget_range):
    if budget_range == 'low':
        return 75 
    elif budget_range == 'medium':
        return 200 
    elif budget_range == 'high':
        return 450 
    elif budget_range == 'luxury':
        return 1000 
    return 9999 

# Shared function: Clear session while preserving Flask-Login data
def clear_session_preserve_login():
    """Wist alle sessie data behalve Flask-Login authenticatie data."""
    flask_login_keys = ['_user_id', '_fresh', '_id', '_remember_me']
    saved_login_data = {key: session.get(key) for key in flask_login_keys if key in session}
    session.clear()
    # Restore Flask-Login keys
    for key, value in saved_login_data.items():
        session[key] = value

# Shared function: Sla alle preferences data op uit sessie
def save_session_preferences():
    """Haalt alle preferences data uit de sessie en retourneert als dictionary."""
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

# Shared function: Herstel preferences data in sessie
def restore_session_preferences(saved_data):
    """Herstelt preferences data in de sessie."""
    if saved_data.get('country'):
        session["country"] = saved_data['country']
    if saved_data.get('start_date'):
        session["start_date"] = saved_data['start_date']
    if saved_data.get('end_date'):
        session["end_date"] = saved_data['end_date']
    if saved_data.get('budget_range'):
        session["budget_range"] = saved_data['budget_range']
    if saved_data.get('adults') is not None:
        session["adults"] = saved_data['adults']
    if saved_data.get('children') is not None:
        session["children"] = saved_data['children']
    if saved_data.get('accommodation_type'):
        session["accommodation_type"] = saved_data['accommodation_type']
    if saved_data.get('interest_culture') is not None:
        session["interest_culture"] = saved_data['interest_culture']
    if saved_data.get('interest_food') is not None:
        session["interest_food"] = saved_data['interest_food']
    if saved_data.get('interest_wildlife') is not None:
        session["interest_wildlife"] = saved_data['interest_wildlife']
    if saved_data.get('interest_history') is not None:
        session["interest_history"] = saved_data['interest_history']
    if saved_data.get('interest_beach') is not None:
        session["interest_beach"] = saved_data['interest_beach']
    if saved_data.get('duration'):
        session["duration"] = saved_data['duration']

# Shared function: Format date to DD-MM-YYYY
def format_date_for_display(date_str):
    """Formatteert een datum string naar DD-MM-YYYY formaat."""
    if not date_str:
        return "not set"
    try:
        date_obj = parse_date(date_str)
        if date_obj:
            return date_obj.strftime("%d-%m-%Y")
    except:
        pass
    return date_str

# Shared function: Check session requirements
def check_session_requirements(required_keys):
    """
    Controleert of alle vereiste session keys aanwezig zijn.
    Returns: (is_valid, redirect_response)
    """
    missing_keys = [key for key in required_keys if not session.get(key)]
    if missing_keys:
        if 'country' in missing_keys:
            flash("Please select a destination first.", "warning")
        return False, redirect(url_for("main.index"))
    return True, None

# Shared function: Create Traveler object from session data
def create_traveler_from_session():
    """
    Maakt een Traveler object aan op basis van session data.
    Returns: (traveler_object, error_message)
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
        return None, str(e)

# Shared function: Prepare result page data
def prepare_result_data(itinerary_list, country_from_traveler=None):
    """
    Bereidt de data voor die naar de result template wordt gestuurd.
    country_from_traveler: Optioneel land uit Traveler object als fallback.
    """
    start_date_formatted = format_date_for_display(session.get("start_date"))
    end_date_formatted = format_date_for_display(session.get("end_date"))
    
    # Bepaal de achtergrondfoto op basis van het gekozen land
    # Probeer eerst uit session, anders uit Traveler object
    country = (session.get("country") or country_from_traveler or "").lower()
    country_image_map = {
        "uganda": "/static/img/uganda.jpg",
        "rwanda": "/static/img/rwanda.jpg",
        "tanzania": "/static/img/tanzania.jpg"
    }
    background_image = country_image_map.get(country, "/static/img/tanzania.jpg")  # Default naar Tanzania
    
    return {
        "start": start_date_formatted,
        "end": end_date_formatted,
        "budget": session.get("budget_range"),
        "adults": session.get("adults"),
        "children": session.get("children"),
        "accommodation": session.get("accommodation_type"),
        "itinerary": itinerary_list,
        "background_image": background_image,
        "country": country  # Doorgeven van country voor specifieke styling
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
    # Check if is_child_friendly column exists in database
    if num_children > 0:
        try:
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('activity_type')]
            has_child_friendly_column = 'is_child_friendly' in columns
            
            if has_child_friendly_column:
                base_query = base_query.filter(ActivityType.is_child_friendly == True)
            else:
                print("Warning: is_child_friendly column does not exist yet. Skipping child-friendly filter.")
        except Exception as e:
            print(f"Warning: Could not check for is_child_friendly column: {e}. Skipping filter.")
    
    # Apply interest categories filter if any are selected
    try:
        if chosen_categories:
            # Filter op country, is_child_friendly (if applicable), EN interests in de database query
            activities = base_query.filter(
                ActivityType.interest_categ.op('&&')(chosen_categories) 
            ).all()
        else:
            # Filter alleen op country (en is_child_friendly if applicable) als er geen interests zijn gekozen
            activities = base_query.all()
    except Exception as e:
        # If query fails due to transaction error, rollback and retry
        db.session.rollback()
        db.session.expire_all()
        if chosen_categories:
            activities = base_query.filter(
                ActivityType.interest_categ.op('&&')(chosen_categories) 
        ).all()
        else:
            activities = base_query.all()

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
    
    # Optimaliseer route met TSP (alleen voor Uganda met coördinaten)
    if selected_activities and traveler_data.country and traveler_data.country.lower() == 'uganda':
        try:
            activity_ids = [a.activity_type_id for a in selected_activities]
            # Filter Entebbe Airport (ID 25) uit de lijst - wordt automatisch toegevoegd als startpunt
            activity_ids = [aid for aid in activity_ids if aid != 25]
            
            if len(activity_ids) >= 1:  # Minimaal 1 activiteit nodig (Entebbe wordt toegevoegd)
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
            
    # Vul resterende dagen op met een standaard activiteit (Vrije dag)
    try:
        placeholder_activity = ActivityType.query.get(1)
    except Exception as e:
        # If query fails due to transaction error, rollback and retry
        db.session.rollback()
        db.session.expire_all()
        try:
            placeholder_activity = ActivityType.query.get(1)
        except Exception:
            placeholder_activity = None
    placeholder_duration = (placeholder_activity.duration_days if placeholder_activity and placeholder_activity.duration_days else 1)
    
    while current_day <= duration_days:
        # Zorg dat we niet over duration_days heen gaan
        actual_duration = min(placeholder_duration, duration_days - current_day + 1)
        
        if placeholder_activity:
            title = f"Day {current_day} – Local Exploration"
            description = "Enjoy a free day to explore the local area, shop, or relax."
            placeholder_id = 1
        else:
            title = f"Day {current_day} – Free Day"
            description = "No activity found for this day."
            placeholder_id = None
        
        # Maak een wrapper object dat de duration kan overschrijven zonder de database te wijzigen
        class ActivityWrapper:
            def __init__(self, activity, duration):
                self._activity = activity
                self.duration_days = duration
                # Delegate andere attributen naar het originele object
                if activity:
                    self.name = activity.name
                    self.description = activity.description
                    self.images_url_text = getattr(activity, 'images_url_text', None)
                else:
                    self.name = title
                    self.description = description
                    self.images_url_text = None
            
            def __getattr__(self, name):
                # Stuur alle andere attributen door naar het originele activity object
                if self._activity:
                    return getattr(self._activity, name)
                raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        
        activity_obj = ActivityWrapper(placeholder_activity, actual_duration)
            
        itinerary_list.append({
            "day": current_day,
            "title": title,
            "description": description,
            "activity_type_id": placeholder_id,
            "activity": activity_obj
        })
        current_day += actual_duration

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
        
        # Bereken de duur
        start_date = parse_date(session.get("start_date"))
        end_date = parse_date(session.get("end_date"))
        
        duration = (end_date - start_date).days + 1 if start_date and end_date and end_date >= start_date else "N/A"
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
    
    # 4. Optimaliseer route VOORDAT items in database worden opgeslagen (alleen voor Uganda)
    # Verander de volgorde: Roep de optimizer aan voordat je de items voor het eerst in de database opslaat
    if country and country.lower() == 'uganda' and itinerary_list:
        try:
            # Extract activity IDs from itinerary_list
            activity_ids = [item.get("activity_type_id") for item in itinerary_list if item.get("activity_type_id") is not None]
            # Filter Entebbe Airport (ID 25) uit de lijst - wordt automatisch toegevoegd als startpunt
            activity_ids = [aid for aid in activity_ids if aid != 25]
            
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
    if not db_error_occurred and country and country.lower() == 'uganda' and itinerary_list and saved_itinerary_ids:
        try:
            # Check of user_id kolom betrouwbaar is
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('itinerary')]
            has_user_id_column = 'user_id' in columns
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


@main_bp.route("/login", methods=["GET", "POST"])
def login_route():
    """
    Login page. For MVP, this is a simple username entry.
    If user doesn't exist, they will be registered automatically.
    """
    if request.method == "POST":
        username = request.form.get("username")
        contact_email = request.form.get("contact_email", "")
        
        if username:
            # Check if user exists
            user = User.query.filter_by(username=username).first()
            
            if not user:
                # Create new user (simple MVP registration)
                user = User(
                    username=username,
                    contact_email=contact_email if contact_email else None,
                    role="traveller"
                )
                db.session.add(user)
                db.session.commit()
                flash(f"Account created! Welcome, {username}!", "success")
            else:
                flash(f"Welcome back, {username}!", "success")
            
            # Log in the user
            login_user(user)
            
            # Redirect to result page if user was in the middle of planning
            if session.get("country") and session.get("start_date"):
                return redirect(url_for("main.result_route"))
            return redirect(url_for("main.index"))
    
    return render_template("login.html")

@main_bp.route("/logout")
@login_required
def logout_route():
    """Log out the current user."""
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))

@main_bp.route("/my-trips")
@login_required
def my_trips_route():
    """Display all itineraries for the current logged-in user."""
    try:
        # Query all itineraries for the current user using ORM
        user_itineraries = Itinerary.query.filter_by(user_id=current_user.user_id).order_by(Itinerary.itinerary_id.desc()).all()
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
            # Get traveler info
            traveler = Traveler.query.get(traveler_id)
            trips_dict[traveler_id] = {
                'traveler': traveler,
                'itineraries': []
            }
        trips_dict[traveler_id]['itineraries'].append(itinerary)
    
    # Convert to list for template
    trips = list(trips_dict.values())
    
    return render_template("my_trips.html", trips=trips)


# API Routes for editing itinerary
@main_bp.route("/api/itinerary/<int:itinerary_id>/remove", methods=["POST"])
def remove_itinerary_item(itinerary_id):
    """Remove an itinerary item from the database and renumber remaining days."""
    try:
        itinerary_item = Itinerary.query.get_or_404(itinerary_id)
        traveler_id = itinerary_item.traveler_id
        removed_day = itinerary_item.day
        
        # Get activity duration to handle multi-day activities
        activity = itinerary_item.activity_type
        activity_duration = activity.duration_days if activity and activity.duration_days else 1
        
        # Optional: Check if user owns this itinerary (if logged in and user_id column exists)
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('itinerary')]
        has_user_id_column = 'user_id' in columns
        
        if has_user_id_column and current_user.is_authenticated:
            if itinerary_item.user_id != current_user.user_id:
                return jsonify({"success": False, "error": "Unauthorized"}), 403
        
        # Delete the item
        db.session.delete(itinerary_item)
        
        # Renumber all remaining items: decrease day by activity_duration for items after the removed day
        # This handles multi-day activities correctly - if we remove a 2-day activity starting on day 4,
        # we need to decrease all days after day 4 by 2 (since days 4-5 are removed)
        # Use raw SQL to avoid user_id column issues
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('itinerary')]
        has_user_id_column = 'user_id' in columns
        
        if has_user_id_column:
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
        else:
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
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/activities/<country>", methods=["GET"])
def get_activities_by_country(country):
    """Get all available activities for a specific country, excluding those already in the itinerary."""
    try:
        # Normalize country name - handle both lowercase and capitalized
        # Database stores: "Uganda", "Rwanda", "Tanzania"
        country_normalized = country.capitalize()
        
        # Get traveler_id from request parameters
        traveler_id = request.args.get('traveler_id', type=int)
        
        # Get number of children from request parameters (for child-friendly filtering)
        num_children = request.args.get('children', type=int, default=0)
        
        # Build base query with country filter
        base_query = ActivityType.query.filter_by(country=country_normalized)
        
        # Apply child-friendly filter if children are present
        # IF num_children > 0: only fetch activities where is_child_friendly is TRUE
        # ELSE: no filter (adults can do all activities)
        # Check if is_child_friendly column exists in database
        if num_children > 0:
            try:
                inspector = inspect(db.engine)
                columns = [col['name'] for col in inspector.get_columns('activity_type')]
                has_child_friendly_column = 'is_child_friendly' in columns
                
                if has_child_friendly_column:
                    base_query = base_query.filter(ActivityType.is_child_friendly == True)
                else:
                    print("Warning: is_child_friendly column does not exist yet. Skipping child-friendly filter.")
            except Exception as e:
                print(f"Warning: Could not check for is_child_friendly column: {e}. Skipping filter.")
        
        # Query activities for this country (with child-friendly filter if applicable)
        try:
            activities = base_query.all()
        except Exception as e:
            # If query fails due to transaction error, rollback and retry
            db.session.rollback()
            db.session.expire_all()
            activities = base_query.all()
        
        # Get already used activity_type_ids for this traveler
        used_activity_ids = set()
        if traveler_id:
            try:
                # Use raw SQL to avoid user_id column issues
                inspector = inspect(db.engine)
                columns = [col['name'] for col in inspector.get_columns('itinerary')]
                
                sql = text("SELECT day_activity_id FROM itinerary WHERE traveler_id = :traveler_id")
                result = db.session.execute(sql, {'traveler_id': traveler_id})
                used_activity_ids = {row[0] for row in result if row[0] is not None}
            except Exception as e:
                # If query fails, continue without filtering
                print(f"Warning: Could not filter existing activities: {e}")
        
        activities_list = []
        for activity in activities:
            # Only include activities that are not already in the itinerary
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
        return jsonify({"success": False, "error": str(e)}), 500


@main_bp.route("/api/itinerary/add", methods=["POST"])
def add_itinerary_item():
    """Add a new activity to an existing itinerary. Automatically determines the next available day."""
    try:
        data = request.get_json()
        
        traveler_id = data.get("traveler_id")
        activity_type_id = data.get("activity_type_id")
        
        if not all([traveler_id, activity_type_id]):
            return jsonify({"success": False, "error": "Missing required fields"}), 400
        
        # Get activity details
        try:
            activity = ActivityType.query.get_or_404(activity_type_id)
        except Exception as e:
            # If query fails due to transaction error, rollback and retry
            db.session.rollback()
            db.session.expire_all()
            activity = ActivityType.query.get_or_404(activity_type_id)
        
        # Find the maximum day number for this traveler to determine next day
        # New activities should not start on day 1, so minimum is day 2
        max_day_result = db.session.query(func.max(Itinerary.day)).filter_by(traveler_id=traveler_id).scalar()
        next_day = max((max_day_result or 0) + 1, 2)  # Minimum day 2 for new activities
        
        # Check if user_id column exists in itinerary table
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('itinerary')]
        has_user_id_column = 'user_id' in columns
        
        # Get user_id if logged in and column exists
        user_id = None
        if has_user_id_column and current_user.is_authenticated:
            user_id = current_user.user_id
        
        # Use raw SQL to insert, building query dynamically based on column existence
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
            # Insert without user_id column
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
        return jsonify({"success": False, "error": str(e)}), 500