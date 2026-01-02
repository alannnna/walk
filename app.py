from flask import Flask, render_template, request, jsonify
import sqlite3
import requests
from datetime import date
from contextlib import closing

app = Flask(__name__)

# Database initialization
def init_db():
    """Initialize the SQLite database and create locations table if it doesn't exist"""
    with closing(sqlite3.connect('database.db')) as conn:
        with closing(conn.cursor()) as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    name TEXT NOT NULL,
                    display_name TEXT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    sequence_order INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

def get_db_connection():
    """Get a database connection"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_walking_distance(locations):
    """
    Calculate total walking distance using OSRM routing API.
    locations: list of {latitude, longitude} dicts in order
    Returns: tuple of (distance in km, route geometry)
    """
    if len(locations) < 2:
        return 0, None

    # Build coordinates string: lon1,lat1;lon2,lat2;...
    coords = ';'.join([f"{loc['longitude']},{loc['latitude']}" for loc in locations])

    # OSRM route endpoint (foot profile for walking)
    url = f"http://router.project-osrm.org/route/v1/foot/{coords}"
    params = {'overview': 'full', 'geometries': 'geojson'}

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get('code') == 'Ok':
            # Distance in meters, convert to km
            distance_meters = data['routes'][0]['distance']
            distance_km = round(distance_meters / 1000, 2)

            # Get route geometry (GeoJSON coordinates)
            geometry = data['routes'][0]['geometry']

            return distance_km, geometry
        else:
            return 0, None
    except:
        return 0, None

@app.route('/')
def index():
    """Serve the main HTML page"""
    return render_template('index.html')

@app.route('/api/search')
def search_locations():
    """Search locations via Nominatim API (autocomplete)"""
    query = request.args.get('q', '')

    if len(query) < 3:
        return jsonify([])

    # Call Nominatim API
    url = 'https://nominatim.openstreetmap.org/search'
    params = {
        'q': query,
        'format': 'json',
        'addressdetails': 1,
        'limit': 5
    }
    headers = {
        'User-Agent': 'WalkingDistanceTracker/1.0'
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        results = response.json()

        # Format results for frontend
        formatted_results = []
        for result in results:
            formatted_results.append({
                'name': result.get('name', result.get('display_name', '').split(',')[0]),
                'display_name': result.get('display_name', ''),
                'latitude': float(result.get('lat')),
                'longitude': float(result.get('lon'))
            })

        return jsonify(formatted_results)
    except:
        return jsonify([])

@app.route('/api/locations/today')
def get_todays_locations():
    """Get all locations for today with total walking distance"""
    today = date.today().isoformat()

    conn = get_db_connection()
    locations = conn.execute(
        'SELECT * FROM locations WHERE date = ? ORDER BY sequence_order',
        (today,)
    ).fetchall()
    conn.close()

    # Convert to list of dicts
    locations_list = []
    for loc in locations:
        locations_list.append({
            'id': loc['id'],
            'name': loc['name'],
            'display_name': loc['display_name'],
            'latitude': loc['latitude'],
            'longitude': loc['longitude'],
            'sequence_order': loc['sequence_order']
        })

    # Calculate total distance and route geometry using OSRM
    total_distance, route_geometry = calculate_walking_distance(locations_list)

    return jsonify({
        'locations': locations_list,
        'total_distance': total_distance,
        'route_geometry': route_geometry
    })

@app.route('/api/locations', methods=['POST'])
def add_location():
    """Add a new location for today"""
    data = request.json
    today = date.today().isoformat()

    # Get the next sequence order for today
    conn = get_db_connection()
    max_order = conn.execute(
        'SELECT MAX(sequence_order) as max_order FROM locations WHERE date = ?',
        (today,)
    ).fetchone()

    next_order = (max_order['max_order'] or -1) + 1

    # Insert the new location
    conn.execute('''
        INSERT INTO locations (date, name, display_name, latitude, longitude, sequence_order)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        today,
        data['name'],
        data.get('display_name', ''),
        data['latitude'],
        data['longitude'],
        next_order
    ))
    conn.commit()

    # Get the new location ID
    new_id = conn.execute('SELECT last_insert_rowid() as id').fetchone()['id']
    conn.close()

    return jsonify({
        'id': new_id,
        'success': True
    })

@app.route('/api/locations/<int:location_id>', methods=['DELETE'])
def delete_location(location_id):
    """Delete a location"""
    conn = get_db_connection()
    conn.execute('DELETE FROM locations WHERE id = ?', (location_id,))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
