from flask import Blueprint, render_template, request, session, redirect, url_for, flash
from app import db # Importeer de db instantie
from app.models import Traveler, ActivityType, Itinerary # Importeer de modellen
from datetime import datetime, date
from sqlalchemy import func
import json 
import random 

# BELANGRIJKE OPMERKING: De foute import 'array_overlap' is verwijderd.
# De PostgreSQL array operator ('&&') wordt nu direct op de kolom gebruikt, wat de fout oplost.

main_bp = Blueprint("main", __name__)

# Functie om de start- en einddatum om te zetten van string (dd/mm/yyyy) naar Python Date object
def parse_date(date_str):
    try:
        return datetime.strptime(date_str, '%d/%m/%Y').date()
    except ValueError:
        return None
    except TypeError:
        return None

# Functie om het budgetbereik om te zetten naar een numerieke limiet
def get_max_budget(budget_range):
    """
    Vertaalt de string budget_range (low, medium, high, luxury) naar een prijslimiet.
    Dit is een schatting.
    """
    if budget_range == 'low':
        return 75 
    elif budget_range == 'medium':
        return 200 
    elif budget_range == 'high':
        return 450 
    elif budget_range == 'luxury':
        return 1000 
    return 9999 

# --- Algorithmic Component (Sectie 4): Priority Scoring ---
def generate_itinerary(traveler_data):
    """
    Genereert een reisplan (Itinerary) op basis van de voorkeuren van de reiziger 
    met behulp van een Priority Scoring algoritme.
    """
    
    # 1. Bepaal de belangrijkste interesses en duur
    interests = {
        'Culture': traveler_data.interest_culture or 0,
        'Food': traveler_data.interest_food or 0,
        'Wildlife': traveler_data.interest_wildlife or 0,
        'History': traveler_data.interest_history or 0,
        'Beach': traveler_data.interest_beach or 0
    }
    
    # Bepaal de totale duur van de reis
    if isinstance(traveler_data.start_date, date) and isinstance(traveler_data.end_date, date):
        duration_days = (traveler_data.end_date - traveler_data.start_date).days + 1
    else:
        duration_days = 3 
        
    if duration_days <= 0:
        duration_days = 1 

    # Bepaal de maximale prijs per dag/per persoon
    max_price = get_max_budget(traveler_data.budget_range)
    
    # 2. Query Activiteiten
    
    # We verzamelen de namen van alle categorieën met een score > 0
    chosen_categories = [k for k, v in interests.items() if v > 0]
    
    # We gebruiken de PostgreSQL array overlap operator ('&&') in de query.
    # Dit is de meest efficiënte methode om de filtering te doen.
    
    # Query: Filter op land en prijs. Gebruik array overlap ALS er interesses zijn gekozen.
    if chosen_categories:
        activities = ActivityType.query.filter(
            ActivityType.country == traveler_data.country,
            ActivityType.price_estimation <= max_price,
            ActivityType.interest_categ.op('&&')(chosen_categories) 
        ).all()
    else:
        # Als er geen interesses zijn, filter dan alleen op land en budget
        activities = ActivityType.query.filter(
            ActivityType.country == traveler_data.country,
            ActivityType.price_estimation <= max_price
        ).all()

    # 3. Priority Scoring (Kern van het Algoritme)
    scored_activities = []
    for activity in activities:
        score = 0
        
        # Zorg ervoor dat activity_categories een lijst is (nodig voor de Python logica)
        activity_categories = activity.interest_categ 
        
        # Roestvrij check: als de array uit de DB als string of None komt, maak er een lege lijst van
        if not activity_categories or not isinstance(activity_categories, list):
             # Als Supabase de array als een string opslaat (bv. '["Culture", "Food"]'), 
             # kunnen we deze niet direct gebruiken. We negeren deze voor de MVP 
             # of vullen een lege lijst in.
             activity_categories = []
        
        for category, interest_score in interests.items():
            if category in activity_categories:
                # Prioriteitsscore: verhoog de score op basis van hoe belangrijk de matchende categorie is
                score += interest_score 
        
        # Dynamic Pricing idee: Geef activiteiten met een lagere prijs een kleine boost
        price = activity.price_estimation or 0
        if max_price > 0 and price > 0:
            price_factor = (max_price - price) / max_price
            score += price_factor * 2 
        
        scored_activities.append({
            'activity': activity,
            'score': score
        })

    # Sorteer op de hoogste score (en random voor gelijke scores)
    random.shuffle(scored_activities)
    scored_activities.sort(key=lambda x: x['score'], reverse=True)
    
    # 4. Planning genereren
    itinerary_list = []
    current_day = 1
    
    # Vul de planning op met de top-scorende activiteiten
    for item in scored_activities:
        activity = item['activity']
        activity_duration = activity.duration_days or 1
        
        # Stop met plannen als de activiteit niet meer in de resterende dagen past
        if current_day <= duration_days and current_day + activity_duration - 1 <= duration_days:
            
            itinerary_list.append({
                "day": current_day, 
                "title": activity.name,
                "description": activity.description,
                "activity_type_id": activity.activity_type_id 
            })
            current_day += activity_duration
            
    # Vul resterende dagen op met een standaard activiteit (Moet ID 1 in de database zijn)
    # Zorg dat er een activiteit met ID 1 bestaat in Supabase (bv. "Aankomst / Vrije dag")
    while len(itinerary_list) < duration_days:
        day_num = len(itinerary_list) + 1
        itinerary_list.append({
            "day": day_num,
            "title": "Day {} – Local Exploration".format(day_num),
            "description": "Enjoy a free day to explore the local area, shop, or relax.",
            "activity_type_id": 1 
        })

    return itinerary_list[:duration_days] 

# --- Routes ---

@main_bp.route("/")
def index():
    # Wissen van de sessie bij de start om een nieuwe reis te garanderen
    session.clear() 
    return render_template("index.html")


@main_bp.route("/step1", methods=["GET", "POST"])
def step1_route():
    if request.method == "POST":
        # Sla de data van Step 1 op in de Flask Session
        session["start_date"] = request.form.get("start_date")
        session["end_date"] = request.form.get("end_date")
        session["budget_range"] = request.form.get("budget_range")
        session["country"] = request.form.get("country") 
        
        # Bereken de duur
        start_date = parse_date(session.get("start_date"))
        end_date = parse_date(session.get("end_date"))
        
        duration = (end_date - start_date).days + 1 if start_date and end_date and end_date >= start_date else "N/A"
        session["duration"] = duration
        
        # Ga naar de volgende stap
        return redirect(url_for("main.step2_route"))

    # Toon het formulier voor GET request
    return render_template("step1.html")


@main_bp.route("/step2", methods=["GET", "POST"])
def step2_route():
    if request.method == "POST":
        # Sla de data van Step 2 op in de Flask Session
        session["adults"] = request.form.get("adults", type=int)
        session["children"] = request.form.get("children", type=int)
        session["accommodation_type"] = request.form.get("accommodation_type")
        
        # Sla de interesses op
        session["interest_culture"] = request.form.get("culture", type=int)
        session["interest_food"] = request.form.get("food", type=int)
        session["interest_wildlife"] = request.form.get("wildlife", type=int)
        session["interest_history"] = request.form.get("history", type=int)
        session["interest_beach"] = request.form.get("beach", type=int)

        # De gegevens zijn compleet, sla ze op in de database en genereer het resultaat
        return redirect(url_for("main.result_route"))
        
    # Toon het formulier voor GET request (geeft gegevens van Step 1 door)
    return render_template(
        "step2.html",
        duration=session.get("duration", "N/A"),
        budget=session.get("budget_range", "N/A"),
        country=session.get("country", "N/A")
    )


@main_bp.route("/result")
def result_route():
    # 1. Opslaan van de Traveler data in Supabase
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
        # Val terug op sessiegegevens als de database mislukt
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
            # Sla het plan alleen op als er een geldige activity_type_id is
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
    data = {
        "start": session.get("start_date"),
        "end": session.get("end_date"),
        "budget": session.get("budget_range"),
        "adults": session.get("adults"),
        "children": session.get("children"),
        "accommodation": session.get("accommodation_type"),
        "itinerary": itinerary_list 
    }
    
    # Wis de sessie nadat het resultaat is getoond
    session.clear() 
    
    return render_template("result.html", **data)