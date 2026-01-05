// Global state
let locations = [];
let map = null;
let markers = [];
let routeLine = null;
let selectedDate = null;
let tempMarker = null;  // Temporary marker for map clicks

// Constants
const KM_TO_MILES = 0.621371;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Set selected date to today by default
    selectedDate = formatDate(new Date());

    initializeMap();
    renderDaySelector();
    updateSelectedDateDisplay();
    loadLocationsForDate(selectedDate);
    setupEventListeners();
});

// Format date as YYYY-MM-DD
function formatDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// Get last N days including today
function getLastNDays(n) {
    const days = [];
    for (let i = n - 1; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        days.push(date);
    }
    return days;
}

// Render day selector buttons
function renderDaySelector() {
    const daySelector = document.getElementById('daySelector');
    const last7Days = getLastNDays(7);

    daySelector.innerHTML = '';

    last7Days.forEach(date => {
        const dateStr = formatDate(date);
        const button = document.createElement('button');
        button.className = 'day-button';
        if (dateStr === selectedDate) {
            button.classList.add('active');
        }

        const weekday = date.toLocaleDateString('en-US', { weekday: 'short' });
        const dayNum = date.getDate();
        const month = date.toLocaleDateString('en-US', { month: 'short' });

        button.innerHTML = `
            <div class="day-button-weekday">${weekday}</div>
            <div class="day-button-date">${dayNum}</div>
            <div class="day-button-month">${month}</div>
        `;

        button.addEventListener('click', () => selectDate(dateStr));
        daySelector.appendChild(button);
    });
}

// Select a date
function selectDate(dateStr) {
    selectedDate = dateStr;
    renderDaySelector(); // Re-render to update active state
    updateSelectedDateDisplay();
    loadLocationsForDate(dateStr);
}

// Update the selected date display in header
function updateSelectedDateDisplay() {
    const dateElement = document.getElementById('selectedDate');
    const date = new Date(selectedDate + 'T00:00:00');
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateElement.textContent = date.toLocaleDateString('en-US', options);
}

// Setup event listeners
function setupEventListeners() {
    const input = document.getElementById('locationInput');
    const searchButton = document.getElementById('searchButton');

    // Search on Enter key
    input.addEventListener('keypress', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            triggerSearch();
        }
    });

    // Search on button click
    searchButton.addEventListener('click', () => {
        triggerSearch();
    });

    // Hide autocomplete when clicking outside
    input.addEventListener('blur', () => {
        // Delay hiding to allow click events on dropdown items
        setTimeout(() => hideAutocomplete(), 200);
    });
}

// Trigger search
function triggerSearch() {
    const input = document.getElementById('locationInput');
    const query = input.value.trim();

    // Check minimum length
    if (query.length < 3) {
        displayAutocompleteError('Please enter at least 3 characters');
        return;
    }

    // Show loading state
    showAutocompleteLoading();

    // Search
    searchLocations(query);
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

    // Add click handler for adding locations by clicking on map
    map.on('click', onMapClick);
}

// Handle map click to add location
async function onMapClick(e) {
    const lat = e.latlng.lat;
    const lon = e.latlng.lng;

    // Remove previous temporary marker if it exists
    if (tempMarker) {
        map.removeLayer(tempMarker);
        tempMarker = null;
    }

    // Create temporary marker
    tempMarker = L.marker([lat, lon]).addTo(map);
    tempMarker.bindPopup('<div class="map-popup-loading">Looking up location...</div>').openPopup();

    // Reverse geocode to get location name
    try {
        const location = await reverseGeocode(lat, lon);

        // Update popup with location info and add button
        const popupContent = `
            <div class="map-popup-content">
                <div class="map-popup-name">${escapeHtml(location.name)}</div>
                <div class="map-popup-address">${escapeHtml(location.display_name)}</div>
                <button class="map-popup-add-btn" onclick="addLocationFromMap(${lat}, ${lon}, '${escapeHtml(location.name).replace(/'/g, "\\'")}', '${escapeHtml(location.display_name).replace(/'/g, "\\'")}')">
                    Add Location
                </button>
            </div>
        `;
        tempMarker.setPopupContent(popupContent);
    } catch (error) {
        console.error('Reverse geocode error:', error);
        tempMarker.setPopupContent('<div class="map-popup-error">Could not find location information</div>');
    }
}

// Reverse geocode coordinates to get location name
async function reverseGeocode(lat, lon) {
    const response = await fetch(`/api/reverse-geocode?lat=${lat}&lon=${lon}`);

    if (!response.ok) {
        throw new Error('Reverse geocode failed');
    }

    return await response.json();
}

// Add location from map click
async function addLocationFromMap(lat, lon, name, displayName) {
    const location = {
        latitude: lat,
        longitude: lon,
        name: name,
        display_name: displayName
    };

    // Remove temporary marker
    if (tempMarker) {
        map.removeLayer(tempMarker);
        tempMarker = null;
    }

    // Add the location
    await addLocation(location);
}

// Search locations via API
async function searchLocations(query) {
    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        const results = await response.json();

        // Check if response is an error
        if (results.error) {
            displayAutocompleteError(results.error);
        } else {
            displayAutocompleteResults(results);
        }
    } catch (error) {
        console.error('Search error:', error);
        displayAutocompleteError('Network error - please try again');
    }
}

// Show autocomplete loading state
function showAutocompleteLoading() {
    const dropdown = document.getElementById('autocompleteDropdown');
    dropdown.innerHTML = '<div class="autocomplete-loading">Searching...</div>';
    dropdown.classList.remove('hidden');
}

// Display autocomplete error
function displayAutocompleteError(errorMessage) {
    const dropdown = document.getElementById('autocompleteDropdown');
    dropdown.innerHTML = `<div class="autocomplete-error">Error: ${escapeHtml(errorMessage)}</div>`;
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
        // Include the selected date in the request
        const locationData = {
            ...location,
            date: selectedDate
        };

        const response = await fetch('/api/locations', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(locationData)
        });

        const result = await response.json();

        if (result.success) {
            // Reload locations to get updated list and distance
            await loadLocationsForDate(selectedDate);
        }
    } catch (error) {
        console.error('Add location error:', error);
    }
}

// Load locations for a specific date
async function loadLocationsForDate(dateStr) {
    try {
        const response = await fetch(`/api/locations/${dateStr}`);
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
            await loadLocationsForDate(selectedDate);
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
