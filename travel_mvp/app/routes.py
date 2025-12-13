from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app import db 
from app.models import Traveler, ActivityType, Itinerary 
from datetime import datetime, date
from sqlalchemy import func
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
    
    # Query Activiteiten (FILTER ALLEEN OP LAND EN INTERESSES)
    chosen_categories = [k for k, v in interests.items() if v > 0]
    
    if chosen_categories:
        activities = ActivityType.query.filter(
            ActivityType.country == traveler_data.country,
            ActivityType.interest_categ.op('&&')(chosen_categories) 
        ).all()
    else:
        activities = ActivityType.query.filter(
            ActivityType.country == traveler_data.country,
        ).all()

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
    
    # Planning genereren
    itinerary_list = []
    current_day = 1
    
    for item in scored_activities:
        activity = item['activity']
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
    placeholder_activity = ActivityType.query.get(1)
    
    while len(itinerary_list) < duration_days:
        day_num = len(itinerary_list) + 1
        
        if placeholder_activity:
            title = f"Day {day_num} – Local Exploration"
            description = "Enjoy a free day to explore the local area, shop, or relax."
            placeholder_id = 1
        else:
            title = f"Day {day_num} – Free Day"
            description = "No activity found for this day."
            placeholder_id = None
            
        itinerary_list.append({
            "day": day_num,
            "title": title,
            "description": description,
            "activity_type_id": placeholder_id,
            "activity": placeholder_activity
        })

    return itinerary_list[:duration_days] 

# --- Routes ---

@main_bp.route("/")
def index():
    """Toont de bestemmingskeuze (wordt nu afgehandeld door index.html)."""
    # Only clear country when coming from Home button, keep other preferences
    # Check if this is a full reset (from "Start a new planning" button)
    reset_all = request.args.get('reset') == 'all'
    
    if reset_all:
        # Full reset - clear everything
        session.clear()
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
    if not session.get("country"):
        flash("Please select a destination first.", "warning")
        return redirect(url_for("main.index"))
    
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
        
    if not session.get("country"):
        return redirect(url_for("main.index"))

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
    # 1. Opslaan van de Traveler data in Supabase
    if not session.get("country") or not session.get("start_date"):
         return redirect(url_for("main.index"))
         
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
        
        traveler_id = new_traveler.traveler_id
        
    except Exception as e:
        flash(f"Fout bij het opslaan van reizigersgegevens in de database.", "danger")
        print(f"DATABASE FOUT: {e}")
        data = {
            "start": session.get("start_date"), "end": session.get("end_date"),
            "budget": session.get("budget_range"), "adults": session.get("adults"),
            "children": session.get("children"), "accommodation": session.get("accommodation_type"),
            "itinerary": [] 
        }
        return render_template("result.html", **data)
        
    # 2. Het Algoritme draaien
    itinerary_list = generate_itinerary(new_traveler)
    
    # 3. Opslaan van het gegenereerde reisplan in Supabase
    try:
        for item in itinerary_list:
            if item.get("activity_type_id") is not None:
                new_itinerary_item = Itinerary(
                    traveler_id=traveler_id,
                    day=item["day"],
                    day_activity_id=item["activity_type_id"],
                    title=item["title"],
                    description=item["description"]
                )
                db.session.add(new_itinerary_item)
        
        db.session.commit()
        
    except Exception as e:
        flash(f"Fout bij het opslaan van de reisplan.", "danger")
        print(f"DATABASE FOUT BIJ ITINERARY: {e}")

    # 4. Resultaten tonen
    # Format dates to DD-MM-YYYY using shared function
    start_date_formatted = format_date_for_display(session.get("start_date"))
    end_date_formatted = format_date_for_display(session.get("end_date"))
    
    # Save all preferences data before clearing session using shared function
    saved_preferences = save_session_preferences()
    
    data = {
        "start": start_date_formatted,
        "end": end_date_formatted,
        "budget": session.get("budget_range"),
        "adults": session.get("adults"),
        "children": session.get("children"),
        "accommodation": session.get("accommodation_type"),
        "itinerary": itinerary_list 
    }
    
    session.clear()
    # Restore all preferences data so they're available when clicking Preferences from result page
    restore_session_preferences(saved_preferences)
    
    return render_template("result.html", **data)