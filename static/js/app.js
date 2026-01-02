// Global state
let locations = [];
let searchTimeout = null;
let map = null;
let markers = [];
let routeLine = null;

// Constants
const KM_TO_MILES = 0.621371;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    displayTodayDate();
    initializeMap();
    loadTodaysLocations();
    setupEventListeners();
});

// Display today's date
function displayTodayDate() {
    const dateElement = document.getElementById('todayDate');
    const today = new Date();
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateElement.textContent = today.toLocaleDateString('en-US', options);
}

// Setup event listeners
function setupEventListeners() {
    const input = document.getElementById('locationInput');
    input.addEventListener('input', handleSearchInput);
    input.addEventListener('blur', () => {
        // Delay hiding to allow click events on dropdown items
        setTimeout(() => hideAutocomplete(), 200);
    });
}

// Initialize map
function initializeMap() {
    // Create map centered on a default location
    map = L.map('map').setView([0, 0], 2);

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors',
        maxZoom: 19
    }).addTo(map);
}

// Handle search input with debouncing
function handleSearchInput(event) {
    const query = event.target.value.trim();

    // Clear previous timeout
    clearTimeout(searchTimeout);

    // Hide dropdown if query is too short
    if (query.length < 3) {
        hideAutocomplete();
        return;
    }

    // Show loading state
    showAutocompleteLoading();

    // Debounce the search
    searchTimeout = setTimeout(() => {
        searchLocations(query);
    }, 300);
}

// Search locations via API
async function searchLocations(query) {
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const results = await response.json();

        displayAutocompleteResults(results);
    } catch (error) {
        console.error('Search error:', error);
        hideAutocomplete();
    }
}

// Show autocomplete loading state
function showAutocompleteLoading() {
    const dropdown = document.getElementById('autocompleteDropdown');
    dropdown.innerHTML = '<div class="autocomplete-loading">Searching...</div>';
    dropdown.classList.remove('hidden');
}

// Display autocomplete results
function displayAutocompleteResults(results) {
    const dropdown = document.getElementById('autocompleteDropdown');

    if (results.length === 0) {
        dropdown.innerHTML = '<div class="autocomplete-loading">No results found</div>';
        return;
    }

    dropdown.innerHTML = '';

    results.forEach(result => {
        const item = document.createElement('div');
        item.className = 'autocomplete-item';

        item.innerHTML = `
            <div class="autocomplete-item-name">${escapeHtml(result.name)}</div>
            <div class="autocomplete-item-address">${escapeHtml(result.display_name)}</div>
        `;

        item.addEventListener('click', () => selectLocation(result));

        dropdown.appendChild(item);
    });

    dropdown.classList.remove('hidden');
}

// Hide autocomplete dropdown
function hideAutocomplete() {
    const dropdown = document.getElementById('autocompleteDropdown');
    dropdown.classList.add('hidden');
}

// Select a location from autocomplete
async function selectLocation(location) {
    hideAutocomplete();

    // Clear input
    document.getElementById('locationInput').value = '';

    // Add location via API
    await addLocation(location);
}

// Add location via API
async function addLocation(location) {
    try {
        const response = await fetch('/api/locations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(location)
        });

        const result = await response.json();

        if (result.success) {
            // Reload locations to get updated list and distance
            await loadTodaysLocations();
        }
    } catch (error) {
        console.error('Add location error:', error);
    }
}

// Load today's locations
async function loadTodaysLocations() {
    try {
        const response = await fetch('/api/locations/today');
        const data = await response.json();

        locations = data.locations;
        displayLocations(locations);
        displayDistance(data.total_distance);
        updateMap(locations, data.route_geometry);
    } catch (error) {
        console.error('Load locations error:', error);
    }
}

// Display locations list
function displayLocations(locations) {
    const listElement = document.getElementById('locationsList');

    if (locations.length === 0) {
        listElement.classList.add('empty');
        listElement.innerHTML = '<p class="empty-message">No locations added yet. Start by searching for a location above.</p>';
        return;
    }

    listElement.classList.remove('empty');
    listElement.innerHTML = '';

    locations.forEach((location, index) => {
        const item = document.createElement('div');
        item.className = 'location-item';

        item.innerHTML = `
            <div class="location-info">
                <span class="location-number">${index + 1}</span>
                <div style="display: inline-block; vertical-align: middle;">
                    <div class="location-name">${escapeHtml(location.name)}</div>
                    <div class="location-address">${escapeHtml(location.display_name)}</div>
                </div>
            </div>
            <button class="delete-btn" onclick="deleteLocation(${location.id})">Delete</button>
        `;

        listElement.appendChild(item);
    });
}

// Display total distance (convert km to miles)
function displayDistance(distanceKm) {
    const distanceElement = document.getElementById('totalDistance');
    const distanceMiles = distanceKm * KM_TO_MILES;
    distanceElement.textContent = distanceMiles.toFixed(2);
}

// Update map with locations and route
function updateMap(locations, routeGeometry) {
    // Clear existing markers and route
    markers.forEach(marker => map.removeLayer(marker));
    markers = [];
    if (routeLine) {
        map.removeLayer(routeLine);
        routeLine = null;
    }

    // If no locations, reset map
    if (locations.length === 0) {
        map.setView([0, 0], 2);
        return;
    }

    // Add markers for each location
    const latLngs = [];
    locations.forEach((location, index) => {
        const latLng = [location.latitude, location.longitude];
        latLngs.push(latLng);

        // Create marker with custom icon showing number
        const marker = L.marker(latLng).addTo(map);
        marker.bindPopup(`<b>${index + 1}. ${escapeHtml(location.name)}</b><br>${escapeHtml(location.display_name)}`);
        markers.push(marker);
    });

    // Draw actual walking route from OSRM geometry
    if (routeGeometry && routeGeometry.coordinates) {
        // Convert GeoJSON coordinates [lon, lat] to Leaflet format [lat, lon]
        const routeLatLngs = routeGeometry.coordinates.map(coord => [coord[1], coord[0]]);

        routeLine = L.polyline(routeLatLngs, {
            color: '#667eea',
            weight: 4,
            opacity: 0.7
        }).addTo(map);

        // Fit map bounds to show the route
        const bounds = routeLine.getBounds();
        map.fitBounds(bounds, { padding: [50, 50] });
    } else if (latLngs.length > 1) {
        // Fallback: draw straight lines if no route geometry available
        routeLine = L.polyline(latLngs, {
            color: '#667eea',
            weight: 4,
            opacity: 0.7,
            dashArray: '5, 10'  // Dashed to indicate it's not the actual route
        }).addTo(map);

        const bounds = L.latLngBounds(latLngs);
        map.fitBounds(bounds, { padding: [50, 50] });
    } else if (latLngs.length === 1) {
        // Single location, just center on it
        map.setView(latLngs[0], 13);
    }
}

// Delete location
async function deleteLocation(locationId) {
    try {
        const response = await fetch(`/api/locations/${locationId}`, {
            method: 'DELETE'
        });

        const result = await response.json();

        if (result.success) {
            // Reload locations to get updated list and distance
            await loadTodaysLocations();
        }
    } catch (error) {
        console.error('Delete location error:', error);
    }
}

// Utility function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
