# Walking Distance Tracker - Development Documentation

## Project Overview

A simple web application for tracking daily walking distances. Users can add locations they've visited each day, and the app calculates total walking distance using actual pedestrian routes (not straight-line distance).

**Target Users**: Personal use on phone and laptop
**Status**: Functional MVP with core features complete

## Tech Stack

### Backend
- **Python Flask** (3.0.0) - Web framework
- **SQLite** - Database (single file, zero config)
- **Mapbox Directions API** - Walking route calculations (primary)
- **Mapbox Geocoding API** - Location search with proximity biasing
- **ipapi.co** - IP-based geolocation for search biasing (free tier)
- Fallback: OSRM for routing, Nominatim for geocoding (slower)

### Frontend
- **Plain HTML/CSS/JavaScript** - No build process
- **Leaflet.js** - Interactive maps
- **Responsive design** - Works on mobile and desktop

### Environment Management
- **uv** - Python package manager
- **python-dotenv** - Environment variable management
- **.env** file for configuration (gitignored)

## Key Features Implemented

### 1. Day Selector (Last 7 Days)
- Row of selectable day buttons
- Shows weekday, date, and month
- Active day highlighted
- Each day maintains separate locations and notes

### 2. Location Management
- **Search**: Mapbox geocoding with IP-based proximity biasing
  - Searches when Enter pressed or Search button clicked
  - Shows autocomplete dropdown with top 5 results
  - Results biased toward user's location (via IP geolocation)
- **Add from search**: Click result to add to current day
- **Add from map**: Click anywhere on map, shows popup with "Add Location" button
  - Uses reverse geocoding to get location name
- **Delete**: Each location has delete button
- **Ordering**: Locations maintain sequence_order for routing

### 3. Route Visualization
- **Map**: Leaflet.js shows all locations as numbered markers
- **Route Lines**: Displays actual walking routes (from Mapbox Directions API)
- **Multiple Segments**: Supports breaks in routes (see "Break After" feature)
- Auto-fits map bounds to show all locations

### 4. Distance Calculation
- Uses **Mapbox Directions API** with `walking` profile
- Considers sidewalks, crosswalks, pedestrian paths
- Displays in **miles** (converted from km)
- Handles multiple route segments when breaks are present

### 5. Break After Feature
- Button on each location (except last) to mark "break after this location"
- Use case: Walk to office → **BREAK** (took subway) → Walk from gym
- Distance only counts walking segments, excludes breaks
- Map shows separate route lines for each segment
- Visual indicator: "- - - Break - - -" between broken segments

### 6. Day Notes
- Text area (200 char limit) for daily notes
- Per-day storage (e.g., "went climbing", "physical therapy")
- Auto-saves 500ms after user stops typing
- Loads when switching days

### 7. IP-Based Geolocation
- Backend detects user's location from IP address
- On localhost, queries ipapi.co to get public IP, then geolocates
- In-memory caching to avoid repeated lookups
- Passes lat/lon to Mapbox as `proximity` parameter
- Makes search results more relevant (e.g., "Central Park" shows NYC first)

## Project Structure

```
walk/
├── app.py                          # Flask backend (all routes and logic)
├── database.db                     # SQLite database (auto-created)
├── requirements.txt                # Python dependencies
├── .env                           # Environment config (GITIGNORED)
├── .env.example                   # Template for .env
├── .gitignore                     # Git ignore rules
├── static/
│   ├── css/
│   │   └── style.css              # All styling (responsive)
│   └── js/
│       └── app.js                 # All frontend JavaScript
├── templates/
│   └── index.html                 # Main page HTML
└── claude.md                      # This file
```

## Database Schema

### `locations` table
```sql
CREATE TABLE locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,                    -- YYYY-MM-DD format
    name TEXT NOT NULL,                    -- Location name
    display_name TEXT,                     -- Full address
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    sequence_order INTEGER NOT NULL,        -- Order visited
    break_after INTEGER DEFAULT 0,          -- 1 = break after this location
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### `day_notes` table
```sql
CREATE TABLE day_notes (
    date TEXT PRIMARY KEY,                 -- YYYY-MM-DD format
    note TEXT,                             -- Daily note (200 chars max)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## API Endpoints

### Locations
- `GET /` - Serve main HTML page
- `GET /api/search?q={query}` - Search locations (Mapbox/Nominatim)
- `GET /api/reverse-geocode?lat={lat}&lon={lon}` - Reverse geocode coordinates
- `GET /api/locations/{date}` - Get all locations + distance for date
- `POST /api/locations` - Add new location
  - Body: `{name, display_name, latitude, longitude, date}`
- `DELETE /api/locations/{id}` - Delete location
- `PUT /api/locations/{id}/break` - Toggle break_after flag
  - Body: `{break_after: 0|1}`

### Notes
- `GET /api/notes/{date}` - Get note for date
- `PUT /api/notes/{date}` - Save/update note
  - Body: `{note: "text"}`

## Configuration (.env file)

```bash
# Geocoding provider: 'mapbox' or 'nominatim'
GEOCODING_PROVIDER=mapbox

# Mapbox API token (required for mapbox provider)
MAPBOX_TOKEN=pk.eyJ1IjoiYWxhbm5ubmEiLCJhIjoiVFZsall4YyJ9.RFSBAGS9tk46-PwoFeQxAQ
```

**Switching providers**: Change `GEOCODING_PROVIDER` to `nominatim` to use free OSM services (slower, no token needed)

## Key Implementation Details

### Distance Calculation with Breaks
```python
def calculate_walking_distance_with_breaks(locations):
    # Splits locations into segments based on break_after flags
    # Calculates distance for each segment separately
    # Returns: (total_distance, list_of_route_geometries)
```

- Iterates through locations, builds segments
- When `break_after=1` is encountered, ends current segment
- Calls `calculate_walking_distance()` for each segment
- Sums distances, collects all route geometries

### IP Geolocation Flow
1. User searches for location
2. Backend gets `request.remote_addr`
3. If localhost (127.0.0.1), queries ipapi.org for public IP
4. Calls ipapi.co with IP to get lat/lon
5. In-memory cache stores result
6. Passes lat/lon to Mapbox as `proximity` parameter
7. Mapbox biases results toward that location

### Frontend Auto-Save Pattern
```javascript
let saveNoteTimeout = null;

noteInput.addEventListener('input', () => {
    clearTimeout(saveNoteTimeout);
    saveNoteTimeout = setTimeout(() => {
        saveDayNote(noteInput.value);
    }, 500); // Debounce
});
```

## Design Decisions

### Why SQLite?
- Zero configuration, single file
- Perfect for single-user personal app
- Can handle decades of data (<1GB for 10+ years)
- Easy backup (copy file)
- Switch to Postgres only if deploying as multi-user service

### Why Mapbox over OSRM?
- OSRM's `foot` profile gives driving-like routes
- Mapbox `walking` profile considers:
  - Sidewalks and crosswalks
  - Pedestrian-only paths
  - Parks and shortcuts
- Much more realistic walking distances

### Why Plain JS over React?
- User preference for simplicity
- No build step needed
- Fast development for MVP
- Easy to understand and modify

### Why Miles instead of Kilometers?
- User preference (US-based)
- Conversion: `miles = km × 0.621371`
- Backend returns km, frontend converts for display

## Common Operations

### Running the App
```bash
# Development server (auto-reloads on file changes)
python app.py

# Access at:
# http://127.0.0.1:5001 (localhost)
# http://192.168.1.152:5001 (from phone on same network)
```

### Installing Dependencies
```bash
uv pip install -r requirements.txt
```

### Database Migrations
- Database auto-migrates on startup (`init_db()`)
- Uses `ALTER TABLE` with try/except for new columns
- Safe to run on existing databases

### Viewing Logs
Flask debug mode outputs to console. For background tasks:
```bash
tail -f /tmp/claude/tasks/{task_id}.output
```

## Known Issues & Limitations

### Nominatim Performance
- Searches can take 20+ seconds
- Proximity biasing doesn't work well
- Use Mapbox instead (default)

### Localhost IP Geolocation
- On localhost, requires extra API call to get public IP
- Works fine in production (real client IPs)
- Cached to minimize API calls

### Route Quality
- Mapbox Directions API is good but not perfect
- Very short walks (<100m) may have odd routing
- Walking through buildings/private property not detected

## Future Enhancement Ideas

(Not implemented, but noted for later)

- **Edit locations**: Currently can only delete/re-add
- **Reorder locations**: Drag-and-drop to change sequence
- **Export data**: CSV/JSON export for backup
- **Statistics**: Weekly/monthly totals, charts
- **Photos**: Attach photos to locations
- **Multi-user**: Authentication, separate users
- **Offline mode**: Service worker, local storage
- **Better mobile UX**: Native app wrapper (React Native/Flutter)

## Testing Notes

### Testing Reverse Geocoding
```bash
curl -s "http://127.0.0.1:5001/api/reverse-geocode?lat=40.7580&lon=-73.9855" | python3 -m json.tool
```

### Testing Distance Calculation
```bash
curl -s "http://127.0.0.1:5001/api/locations/2026-01-08" | python3 -m json.tool
```

### Testing Day Notes
```bash
# Save note
curl -X PUT -H "Content-Type: application/json" \
  -d '{"note":"Went climbing today"}' \
  http://127.0.0.1:5001/api/notes/2026-01-08

# Get note
curl -s http://127.0.0.1:5001/api/notes/2026-01-08 | python3 -m json.tool
```

## Performance Characteristics

- **Database size**: ~3.6 MB/year, ~36 MB/10 years
- **API calls per search**: 2-3 (IP geolocation + Mapbox search)
- **API calls per map click**: 1 (reverse geocode)
- **API calls per route**: 1 per segment (Mapbox Directions)
- **Page load time**: <500ms on good connection
- **Map rendering**: Instant for <100 locations

## Dependencies & API Limits

### Mapbox Free Tier
- 100,000 requests/month for Geocoding
- 100,000 requests/month for Directions
- Your usage: ~10-20 requests/day = ~300-600/month (well within limits)

### ipapi.co Free Tier
- 1,000 requests/day
- Your usage: ~1-2/day (cached per IP)

### No Rate Limiting Implemented
- Relies on frontend debouncing (search, notes)
- Could add rate limiting if needed (flask-limiter)

## Security Notes

- `.env` file is gitignored (contains Mapbox token)
- No authentication implemented (personal use only)
- SQL injection: Protected by parameterized queries
- XSS: Frontend uses `escapeHtml()` for user content
- CORS: Not needed (same-origin)

## Development Tips

### Debugging
- Flask debug mode shows stack traces in browser
- Check browser console for JavaScript errors
- Database: `sqlite3 database.db` to inspect

### Making Changes
- Backend changes auto-reload (Flask debug mode)
- Frontend changes: just refresh browser
- Database schema changes: Add migration in `init_db()`

### Git Workflow
- `.gitignore` properly configured
- Ignores: `.env`, `.venv/`, `database.db`, `__pycache__/`
- Commit often, small changes

## Contact & Attribution

Built as a personal project with assistance from Claude (Anthropic).

**Key Resources:**
- Mapbox API Docs: https://docs.mapbox.com/
- Leaflet.js Docs: https://leafletjs.com/
- Flask Docs: https://flask.palletsprojects.com/
- SQLite Docs: https://www.sqlite.org/docs.html
