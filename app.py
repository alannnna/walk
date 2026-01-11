from flask import Flask, render_template, request, jsonify
import sqlite3
import requests
from datetime import date
from contextlib import closing
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Configuration
GEOCODING_PROVIDER = os.getenv('GEOCODING_PROVIDER', 'mapbox').lower()  # 'mapbox' or 'nominatim'
print("geocoding provider is ", GEOCODING_PROVIDER)
MAPBOX_TOKEN = os.getenv('MAPBOX_TOKEN', '')

# IP Geolocation cache (in-memory cache for IP -> lat/lon lookups)
ip_location_cache = {}

def get_public_ip():
    """Get the server's public IP address for development on localhost"""
    try:
        response = requests.get('https://api.ipify.org?format=json', timeout=2)
        if response.status_code == 200:
            return response.json()['ip']
    except:
        pass
    return None

def get_location_from_ip(ip_address):
    """
    Get approximate location (lat/lon) from IP address using ipapi.co
    Results are cached in memory to avoid repeated lookups
    Returns: (latitude, longitude) tuple or (None, None) if lookup fails
    """
    # Check cache first
    if ip_address in ip_location_cache:
        return ip_location_cache[ip_address]

    # Skip localhost and private IPs
    if ip_address in ['127.0.0.1', 'localhost'] or ip_address.startswith('192.168.'):
        return (None, None)

    try:
        # Use ipapi.co free service (1000 requests/day, no API key needed)
        response = requests.get(f'https://ipapi.co/{ip_address}/json/', timeout=2)
        if response.status_code == 200:
            data = response.json()
            lat = data.get('latitude')
            lon = data.get('longitude')

            if lat and lon:
                # Cache the result (keep in memory for this session)
                ip_location_cache[ip_address] = (lat, lon)
                return (lat, lon)
    except:
        # If geo lookup fails, continue without proximity
        pass

    # Cache the failure too (avoid repeated failed lookups)
    ip_location_cache[ip_address] = (None, None)
    return (None, None)

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
                    break_after INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Migrate existing database: add break_after column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE locations ADD COLUMN break_after INTEGER DEFAULT 0')
                conn.commit()
            except sqlite3.OperationalError:
                # Column already exists, ignore
                pass

            # Create day_notes table for daily notes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS day_notes (
                    date TEXT PRIMARY KEY,
                    note TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()

def get_db_connection():
    """Get a database connection"""
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_walking_distance_with_breaks(locations):
    """
    Calculate total walking distance handling break_after flags.
    Splits locations into segments and calculates distance for each.
    locations: list of {latitude, longitude, break_after} dicts in order
    Returns: tuple of (total distance in km, list of route geometries)
    """
    if len(locations) < 2:
        return 0, []

    # Split locations into segments based on break_after flags
    segments = []
    current_segment = []

    for i, loc in enumerate(locations):
        current_segment.append(loc)

        # If this location has break_after=1, or it's the last location, end the segment
        if loc.get('break_after', 0) == 1 or i == len(locations) - 1:
            if len(current_segment) >= 2:
                segments.append(current_segment)
            elif len(current_segment) == 1 and i == len(locations) - 1 and len(segments) > 0:
                # Single location at end - add to last segment if we have segments
                segments[-1].append(current_segment[0])
            current_segment = []

    # Calculate distance and geometry for each segment
    total_distance = 0
    route_geometries = []

    for segment in segments:
        if len(segment) >= 2:
            distance, geometry = calculate_walking_distance(segment)
            total_distance += distance
            if geometry:
                route_geometries.append(geometry)

    return total_distance, route_geometries

def calculate_walking_distance(locations):
    """
    Calculate total walking distance using Mapbox Directions API.
    locations: list of {latitude, longitude} dicts in order
    Returns: tuple of (distance in km, route geometry)
    """
    if len(locations) < 2:
        return 0, None

    if not MAPBOX_TOKEN:
        # Fallback to OSRM if no Mapbox token
        return calculate_walking_distance_osrm(locations)

    # Build coordinates string: lon1,lat1;lon2,lat2;...
    coords = ';'.join([f"{loc['longitude']},{loc['latitude']}" for loc in locations])

    # Mapbox Directions API endpoint (walking profile)
    url = f"https://api.mapbox.com/directions/v5/mapbox/walking/{coords}"
    params = {
        'access_token': MAPBOX_TOKEN,
        'overview': 'full',
        'geometries': 'geojson'
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        if data.get('code') == 'Ok' and data.get('routes'):
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

def calculate_walking_distance_osrm(locations):
    """
    Fallback: Calculate walking distance using OSRM routing API.
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

@app.route('/api/reverse-geocode')
def reverse_geocode():
    """Reverse geocode coordinates to get location name"""
    lat = request.args.get('lat')
    lon = request.args.get('lon')

    if not lat or not lon:
        return jsonify({'error': 'lat and lon parameters required'}), 400

    try:
        lat = float(lat)
        lon = float(lon)

        if GEOCODING_PROVIDER == 'mapbox':
            return reverse_geocode_mapbox(lon, lat)
        else:
            return reverse_geocode_nominatim(lon, lat)
    except ValueError:
        return jsonify({'error': 'Invalid lat/lon values'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/search')
def search_locations():
    """Search locations via configured geocoding provider (Mapbox or Nominatim)"""
    query = request.args.get('q', '')

    if len(query) < 3:
        return jsonify([])

    try:
        # Get user's approximate location from IP for proximity biasing
        client_ip = request.remote_addr

        # On localhost, get the actual public IP for development testing
        if client_ip in ['127.0.0.1', 'localhost', '::1']:
            public_ip = get_public_ip()
            if public_ip:
                client_ip = public_ip

        user_lat, user_lon = get_location_from_ip(client_ip)

        if GEOCODING_PROVIDER == 'mapbox':
            return search_mapbox(query, user_lat, user_lon)
        else:
            return search_nominatim(query, user_lat, user_lon)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def search_mapbox(query, user_lat=None, user_lon=None):
    """Search using Mapbox Geocoding API with optional proximity biasing"""
    if not MAPBOX_TOKEN:
        raise Exception('Mapbox token not configured. Set MAPBOX_TOKEN environment variable.')

    url = f'https://api.mapbox.com/geocoding/v5/mapbox.places/{query}.json'
    params = {
        'access_token': MAPBOX_TOKEN,
        'limit': 5,
        'autocomplete': True
    }

    # Add proximity parameter if user location is available (biases results toward user)
    if user_lat is not None and user_lon is not None:
        params['proximity'] = f"{user_lon},{user_lat}"  # Mapbox uses lon,lat order

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    # Format Mapbox results for frontend
    formatted_results = []
    for feature in data.get('features', []):
        # Get coordinates [longitude, latitude]
        coords = feature.get('geometry', {}).get('coordinates', [])
        if len(coords) >= 2:
            formatted_results.append({
                'name': feature.get('text', ''),
                'display_name': feature.get('place_name', ''),
                'latitude': coords[1],
                'longitude': coords[0]
            })

    return jsonify(formatted_results)

def search_nominatim(query, user_lat=None, user_lon=None):
    """Search using Nominatim API with optional proximity biasing"""
    url = 'https://nominatim.openstreetmap.org/search'
    params = {
        'q': query,
        'format': 'json',
        'addressdetails': 1,
        'limit': 5
    }

    # Add proximity biasing if user location is available
    # Note: this doesn't seem to make any difference in the search results
    if user_lat is not None and user_lon is not None:
        params['q'] += f" {user_lat},{user_lon}"

    headers = {
        'User-Agent': 'WalkingDistanceTracker/1.0'
    }

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    results = response.json()

    # Format Nominatim results for frontend
    formatted_results = []
    for result in results:
        formatted_results.append({
            'name': result.get('name', result.get('display_name', '').split(',')[0]),
            'display_name': result.get('display_name', ''),
            'latitude': float(result.get('lat')),
            'longitude': float(result.get('lon'))
        })

    return jsonify(formatted_results)

def reverse_geocode_mapbox(lon, lat):
    """Reverse geocode using Mapbox API"""
    if not MAPBOX_TOKEN:
        raise Exception('Mapbox token not configured. Set MAPBOX_TOKEN environment variable.')

    url = f'https://api.mapbox.com/geocoding/v5/mapbox.places/{lon},{lat}.json'
    params = {
        'access_token': MAPBOX_TOKEN,
        'limit': 1
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    features = data.get('features', [])
    if features:
        feature = features[0]
        coords = feature.get('geometry', {}).get('coordinates', [])
        if len(coords) >= 2:
            return jsonify({
                'name': feature.get('text', ''),
                'display_name': feature.get('place_name', ''),
                'latitude': coords[1],
                'longitude': coords[0]
            })

    return jsonify({'error': 'No location found'}), 404

def reverse_geocode_nominatim(lon, lat):
    """Reverse geocode using Nominatim API"""
    url = 'https://nominatim.openstreetmap.org/reverse'
    params = {
        'lat': lat,
        'lon': lon,
        'format': 'json',
        'addressdetails': 1
    }
    headers = {
        'User-Agent': 'WalkingDistanceTracker/1.0'
    }

    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    result = response.json()

    if 'error' not in result:
        return jsonify({
            'name': result.get('name', result.get('display_name', '').split(',')[0]),
            'display_name': result.get('display_name', ''),
            'latitude': float(result.get('lat')),
            'longitude': float(result.get('lon'))
        })

    return jsonify({'error': 'No location found'}), 404

@app.route('/api/locations/<date_str>')
def get_locations_by_date(date_str):
    """Get all locations for a specific date with total walking distance"""
    conn = get_db_connection()
    locations = conn.execute(
        'SELECT * FROM locations WHERE date = ? ORDER BY sequence_order',
        (date_str,)
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
            'sequence_order': loc['sequence_order'],
            'break_after': loc['break_after']
        })

    # Calculate total distance and route geometry (handling segments)
    total_distance, route_geometries = calculate_walking_distance_with_breaks(locations_list)

    return jsonify({
        'locations': locations_list,
        'total_distance': total_distance,
        'route_geometries': route_geometries
    })

@app.route('/api/locations', methods=['POST'])
def add_location():
    """Add a new location for a specific date"""
    data = request.json
    location_date = data.get('date', date.today().isoformat())

    # Get the next sequence order for this date
    conn = get_db_connection()
    max_order = conn.execute(
        'SELECT MAX(sequence_order) as max_order FROM locations WHERE date = ?',
        (location_date,)
    ).fetchone()

    next_order = (max_order['max_order'] or -1) + 1

    # Insert the new location
    conn.execute('''
        INSERT INTO locations (date, name, display_name, latitude, longitude, sequence_order)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (
        location_date,
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

@app.route('/api/locations/<int:location_id>/break', methods=['PUT'])
def toggle_break_after(location_id):
    """Toggle break_after flag for a location"""
    data = request.json
    break_after = data.get('break_after', 0)

    conn = get_db_connection()
    conn.execute('UPDATE locations SET break_after = ? WHERE id = ?', (break_after, location_id))
    conn.commit()
    conn.close()

    return jsonify({'success': True})

@app.route('/api/notes/<date_str>', methods=['GET'])
def get_day_note(date_str):
    """Get note for a specific date"""
    conn = get_db_connection()
    note_row = conn.execute(
        'SELECT note FROM day_notes WHERE date = ?',
        (date_str,)
    ).fetchone()
    conn.close()

    note = note_row['note'] if note_row else ''
    return jsonify({'note': note})

@app.route('/api/notes/<date_str>', methods=['PUT'])
def update_day_note(date_str):
    """Update note for a specific date"""
    data = request.json
    note = data.get('note', '')

    conn = get_db_connection()

    # Use INSERT OR REPLACE to handle both create and update
    conn.execute('''
        INSERT OR REPLACE INTO day_notes (date, note, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (date_str, note))

    conn.commit()
    conn.close()

    return jsonify({'success': True})

# Initialize database on startup
init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
