"""
TSP Route Optimizer voor Travel Itinerary
Gebruikt PySCIPOpt om de kortste route tussen activiteiten te berekenen.
Open TSP: start bij Entebbe Airport, eindigt bij laatste activiteit (geen terugkeer).
"""

import math
from pyscipopt import Model, quicksum
from app import db
from app.models import ActivityType
from sqlalchemy import text


def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Bereken de afstand tussen twee punten op aarde met de Haversine-formule.
    
    Args:
        lat1, lon1: Coördinaten van punt 1 (in graden)
        lat2, lon2: Coördinaten van punt 2 (in graden)
    
    Returns:
        Afstand in kilometers
    """
    # Converteer graden naar radialen
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formule
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    
    # Straal van de aarde in kilometers
    R = 6371.0
    
    return R * c


def solve_travel_route(activity_ids, country=None):
    """
    Los het Open Traveling Salesman Problem op voor de gegeven activiteiten.
    Gebruikt MTZ (Miller-Tucker-Zemlin) formulering voor subtour eliminatie.
    Start altijd bij Entebbe Airport (voor Uganda) en eindigt bij de laatste activiteit.
    
    Args:
        activity_ids: Lijst van activity_type_id's die geoptimaliseerd moeten worden
        country: Land naam (optioneel, voor filtering)
    
    Returns:
        Lijst van activity objects in optimale volgorde (zonder terugkeer naar start)
    """
    if not activity_ids or len(activity_ids) < 1:
        # Als er geen activiteiten zijn, retourneer lege lijst
        return []
    
    # Haal startpunt op uit starting_points tabel
    try:
        start_sql = text("""
            SELECT country, latitude, longitude
            FROM starting_points
            WHERE country = :country_name
            LIMIT 1
        """)
        start_result = db.session.execute(start_sql, {'country_name': country})
        start_row = start_result.fetchone()
        
        if start_row and start_row[1] is not None and start_row[2] is not None:
            # Gebruik startpunt uit database
            START_POINT = {
                'activity_type_id': None,
                'name': f'{country} Starting Point',
                'description': f'Starting point for {country}',
                'latitude': float(start_row[1]),
                'longitude': float(start_row[2]),
                'is_start': True
            }
            print(f"Starting point loaded from database for {country}: {START_POINT['latitude']}, {START_POINT['longitude']}")
        else:
            # Fallback: gebruik Entebbe coördinaten voor Uganda
            if country and country.lower() == 'uganda':
                START_POINT = {
                    'activity_type_id': None,
                    'name': 'Entebbe International Airport',
                    'description': 'Starting point: International airport',
                    'latitude': 0.063004056529198,  # Uit starting_points tabel
                    'longitude': 32.4460903472213,  # Uit starting_points tabel
                    'is_start': True
                }
            else:
                # Voor andere landen, gebruik eerste activiteit als startpunt
                START_POINT = None
            print(f"Warning: Starting point not found in database for {country}, using fallback")
    except Exception as e:
        print(f"Error fetching starting point: {e}")
        # Fallback: gebruik Entebbe coördinaten voor Uganda
        if country and country.lower() == 'uganda':
            START_POINT = {
                'activity_type_id': None,
                'name': 'Entebbe International Airport',
                'description': 'Starting point: International airport',
                'latitude': 0.063004056529198,
                'longitude': 32.4460903472213,
                'is_start': True
            }
        else:
            START_POINT = None
    
    # Haal activiteiten op met coördinaten
    # Gebruik SQLAlchemy's .in_() voor veiligere query
    try:
        activities_query = ActivityType.query.filter(ActivityType.activity_type_id.in_(activity_ids))
        activities_orm = activities_query.all()
        
        # Haal coördinaten op via raw SQL (mogelijk niet in ORM model)
        activity_ids_list = list(activity_ids)
        sql = text("""
            SELECT activity_type_id, latitude, longitude
            FROM activity_type
            WHERE activity_type_id = ANY(:activity_ids)
        """)
        result = db.session.execute(sql, {'activity_ids': activity_ids_list})
        coords_data = {row[0]: (row[1], row[2]) for row in result.fetchall() if row[1] is not None and row[2] is not None}
        
        print(f"Found {len(coords_data)} activities with coordinates")
        
    except Exception as e:
        print(f"Error fetching activities: {e}")
        # Fallback: gebruik ORM zonder coördinaten
        activities = ActivityType.query.filter(ActivityType.activity_type_id.in_(activity_ids)).all()
        return activities
    
    # Filter activiteiten met geldige coördinaten
    if country and country.lower() == 'uganda' and START_POINT:
        valid_activities = [START_POINT.copy()]  # Start met startpunt op index 0
        
        # Voeg alle activiteiten met coördinaten toe
        for activity in activities_orm:
            activity_id = activity.activity_type_id
            
            if activity_id in coords_data:
                lat, lon = coords_data[activity_id]
                valid_activities.append({
                    'activity_type_id': activity_id,
                    'name': activity.name,
                    'description': activity.description,
                    'duration_days': activity.duration_days,
                    'price_estimation': activity.price_estimation,
                    'country': activity.country,
                    'images_url_text': activity.images_url_text,
                    'interest_categ': activity.interest_categ,
                    'latitude': float(lat),
                    'longitude': float(lon),
                    'is_start': False
                })
    else:
        # Voor andere landen of als er geen startpunt is, gebruik originele volgorde (geen optimalisatie)
        return activities_orm
    
    # Als er minder dan 2 activiteiten zijn (alleen Entebbe), retourneer originele volgorde
    if len(valid_activities) < 2:
        print("Warning: Not enough activities with coordinates for optimization. Using original order.")
        return activities_orm
    
    n = len(valid_activities)
    
    # Bereken afstandsmatrix
    distance_matrix = []
    for i in range(n):
        row = []
        for j in range(n):
            if i == j:
                row.append(0.0)
            else:
                lat1 = valid_activities[i]['latitude']
                lon1 = valid_activities[i]['longitude']
                lat2 = valid_activities[j]['latitude']
                lon2 = valid_activities[j]['longitude']
                dist = haversine_distance(lat1, lon1, lat2, lon2)
                row.append(dist)
        distance_matrix.append(row)
    
    # Open TSP: maak terugkeer naar start "gratis" (0 kosten)
    # Dit voorkomt geforceerde terugkeer naar Entebbe
    # Maar zorg dat we WEL kunnen starten vanuit Entebbe (index 0)
    for i in range(1, n):  # Van elke activiteit terug naar start (index 0)
        distance_matrix[i][0] = 0.0
    
    # Debug: print afstandsmatrix voor verificatie
    print(f"\nDistance matrix size: {n}x{n}")
    print("Sample distances from starting point:")
    for i in range(1, min(n, 6)):  # Show first 5 activities
        dist = distance_matrix[0][i]
        print(f"  Start -> {valid_activities[i]['name']}: {dist:.2f} km")
    
    if n > 2:
        print("\nSample distances between activities:")
        for i in range(1, min(n, 4)):
            for j in range(i+1, min(n, 5)):
                dist = distance_matrix[i][j]
                print(f"  {valid_activities[i]['name']} -> {valid_activities[j]['name']}: {dist:.2f} km")
    
    # Maak TSP model met PySCIPOpt
    model = Model("OpenTSP")
    model.hideOutput()
    
    # Variabelen: x[i][j] = 1 als we van i naar j reizen
    x = {}
    for i in range(n):
        for j in range(n):
            if i != j:
                x[i, j] = model.addVar(vtype="B", name=f"x_{i}_{j}")
    
    # MTZ variabelen: u[i] = positie van stad i in de route
    u = {}
    for i in range(1, n):  # u[0] = 0 (startpunt)
        u[i] = model.addVar(vtype="I", lb=1, ub=n-1, name=f"u_{i}")
    
    # Doelfunctie: minimaliseer totale afstand
    model.setObjective(
        quicksum(distance_matrix[i][j] * x[i, j] for i in range(n) for j in range(n) if i != j),
        "minimize"
    )
    
    # Constraints: elke stad heeft precies één inkomende en één uitgaande boog
    for i in range(n):
        model.addCons(quicksum(x[i, j] for j in range(n) if i != j) == 1, name=f"outgoing_{i}")
        model.addCons(quicksum(x[j, i] for j in range(n) if i != j) == 1, name=f"incoming_{i}")
    
    # MTZ constraints: subtour eliminatie
    # u[i] - u[j] + n * x[i][j] <= n - 1 voor alle i, j waar i != j en i, j != 0
    for i in range(1, n):
        for j in range(1, n):
            if i != j:
                model.addCons(
                    u[i] - u[j] + n * x[i, j] <= n - 1,
                    name=f"mtz_{i}_{j}"
                )
    
    # Los het model op
    model.optimize()
    
    # Haal de oplossing op
    if model.getStatus() != 'optimal':
        # Als optimalisatie faalt, retourneer originele volgorde
        print(f"Warning: TSP optimization failed with status {model.getStatus()}. Using original order.")
        return activities_orm
    
    # Reconstruct route using MTZ u[i] variables (not edges)
    # This ensures we follow the solver's calculated sequence strictly
    # Step 1: Create a list of tuples (activity_index, u_value) for all activities where i > 0
    activity_order = []
    for i in range(1, n):  # Skip index 0 (starting point)
        try:
            u_value = model.getVal(u[i])
            activity_order.append((i, u_value))
            print(f"Activity {i} ({valid_activities[i]['name']}): u[{i}] = {u_value:.2f}")
        except Exception as e:
            print(f"Error: Could not get u[{i}] value: {e}")
            # Fallback: use index as order (should not happen if model solved correctly)
            activity_order.append((i, float(i)))
    
    # Step 2: Explicitly sort by u_value in ascending order
    activity_order.sort(key=lambda x: x[1])
    
    # Step 3: Build route - prepend starting point (index 0), then sorted activities
    route = [0] + [item[0] for item in activity_order]
    
    # Verify we have all activities
    if len(route) != n:
        print(f"Error: Route length {len(route)} does not match expected {n}. Using original order.")
        return activities_orm
    
    # Calculate total distance for verification
    total_distance = 0.0
    for i in range(len(route) - 1):
        from_idx = route[i]
        to_idx = route[i + 1]
        dist = distance_matrix[from_idx][to_idx]
        total_distance += dist
        print(f"  {valid_activities[from_idx]['name']} -> {valid_activities[to_idx]['name']}: {dist:.2f} km")
    
    # Debug output
    print(f"\nTSP Route Summary:")
    print(f"  Total nodes: {len(route)} (including start point)")
    print(f"  Total distance: {total_distance:.2f} km")
    print(f"  Route indices: {route}")
    if len(route) > 1:
        route_names = [valid_activities[idx]['name'] for idx in route]
        print(f"  Optimized Route: {' -> '.join(route_names)}")
        # Print u values for verification
        if activity_order:
            u_values_str = ", ".join([f"u[{item[0]}]={item[1]:.1f}" for item in activity_order])
            print(f"  MTZ u values (sorted): {u_values_str}")
    
    # Retourneer activiteiten in optimale volgorde (zonder Entebbe Airport in de lijst)
    optimized_activities = []
    for idx in route:
        activity_data = valid_activities[idx]
        
        # Skip Entebbe Airport (is_start = True) - alleen activiteiten toevoegen
        if activity_data.get('is_start', False):
            continue
        
        # Haal ActivityType object op via ORM
        activity = ActivityType.query.get(activity_data['activity_type_id'])
        if activity:
            optimized_activities.append(activity)
        else:
            # Fallback: maak een simpel object
            activity = ActivityType()
            activity.activity_type_id = activity_data['activity_type_id']
            activity.name = activity_data['name']
            activity.description = activity_data['description']
            activity.duration_days = activity_data['duration_days']
            activity.price_estimation = activity_data['price_estimation']
            activity.country = activity_data['country']
            activity.images_url_text = activity_data['images_url_text']
            activity.interest_categ = activity_data['interest_categ']
            optimized_activities.append(activity)
    
    return optimized_activities
