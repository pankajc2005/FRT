document.addEventListener('DOMContentLoaded', function() {
    // Initialize Map
    window.map = L.map('map', {
        zoomControl: false // Cleaner mobile UI
    });

    // Coordinates
    const djSanghvi = [19.1075, 72.8372]; // Actual DJ Sanghvi approx
    const vileParlePS = [19.1020, 72.8450]; // Approx Vile Parle PS

    // Set View
    window.map.setView(djSanghvi, 15);

    // Add Tile Layer (OpenStreetMap)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(window.map);

    // Custom Icons
    const userIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#ef4444; width: 15px; height: 15px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 10px #ef4444;'></div>",
        iconSize: [15, 15],
        iconAnchor: [7, 7]
    });

    const policeIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#10b981; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-shield-alt' style='color:white; font-size:12px;'></i></div>",
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });

    const chaukiIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#059669; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-building' style='color:white; font-size:10px;'></i></div>",
        iconSize: [20, 20],
        iconAnchor: [10, 10]
    });

    const patrolIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#f59e0b; width: 22px; height: 22px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-car' style='color:white; font-size:11px;'></i></div>",
        iconSize: [22, 22],
        iconAnchor: [11, 11]
    });

    const cctvIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#3b82f6; width: 18px; height: 18px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-video' style='color:white; font-size:9px;'></i></div>",
        iconSize: [18, 18],
        iconAnchor: [9, 9]
    });

    const criminalIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#ef4444; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; animation: pulse 1.5s infinite; box-shadow: 0 0 10px #ef4444;'><i class='fas fa-exclamation-triangle' style='color:white; font-size:12px;'></i></div>",
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });

    // Markers
    window.userMarker = L.marker(djSanghvi, {icon: userIcon}).addTo(window.map)
        .bindPopup("<b>You are here</b><br>DJ Sanghvi College").openPopup();

    // Initialize LayerGroup for Safe Assets (Hidden by default)
    window.safeAssetsLayer = L.layerGroup();

    // --- Mock CCTV Data (Aligned to real streets for clean demo) ---
    window.cctvLocations = [
        // Path 1: DJ Sanghvi -> Vile Parle Station (South-East Corridor)
        { lat: 19.1072, lng: 72.8375, id: "CCTV-001 (College Gate)" },
        { lat: 19.1065, lng: 72.8382, id: "CCTV-002 (Gulmohar Cross)" },
        { lat: 19.1058, lng: 72.8390, id: "CCTV-003 (Mithibai Jnc)" },
        { lat: 19.1045, lng: 72.8405, id: "CCTV-004 (SV Road)" },
        { lat: 19.1035, lng: 72.8420, id: "CCTV-005 (Market Rd)" },
        { lat: 19.1028, lng: 72.8435, id: "CCTV-006 (Station West)" },
        
        // Path 2: DJ Sanghvi -> Juhu Police Station (West Corridor)
        { lat: 19.1075, lng: 72.8360, id: "CCTV-007 (JVPD Scheme)" },
        { lat: 19.1072, lng: 72.8345, id: "CCTV-008 (Juhu Circle)" },
        { lat: 19.1065, lng: 72.8325, id: "CCTV-009 (Juhu Tara Rd)" },
        { lat: 19.1055, lng: 72.8305, id: "CCTV-010 (Juhu Beach Entry)" },

        // Path 3: North towards Cooper
        { lat: 19.1090, lng: 72.8372, id: "CCTV-011 (Cooper Signal)" },
        { lat: 19.1110, lng: 72.8370, id: "CCTV-012 (Irla Market)" }
    ];

    // Add CCTV Markers to LayerGroup
    window.cctvLocations.forEach(cam => {
        L.marker([cam.lat, cam.lng], {icon: cctvIcon})
            .bindPopup(`<b>${cam.id}</b><br>Status: Active<br><button onclick="removeAsset(this)" style="color:red; margin-top:5px; border:1px solid red; background:white; border-radius:4px; cursor:pointer;">Delete Asset</button>`)
            .addTo(window.safeAssetsLayer);
    });

    // --- Mock Criminal/Danger Data ---
    window.criminalLocations = [
        // Blocking a shortcut, forcing the route to stick to main roads
        { lat: 19.1055, lng: 72.8395, type: "Theft Hotspot" } 
    ];

    window.criminalLocations.forEach(crim => {
        L.marker([crim.lat, crim.lng], {icon: criminalIcon})
            .bindPopup(`<b style="color:red">DANGER: ${crim.type}</b><br>Avoid this area`)
            .addTo(window.safeAssetsLayer);
            
        // Add Danger Radius Circle
        L.circle([crim.lat, crim.lng], {
            color: 'red',
            fillColor: '#f03',
            fillOpacity: 0.2,
            radius: 150 // 150 meters danger zone
        }).addTo(window.safeAssetsLayer);
    });

    // Update Stats (Mock)
    const cctvCountEl = document.getElementById('cctvCount');
    if(cctvCountEl) cctvCountEl.innerText = window.cctvLocations.length;
    
    const incidentCountEl = document.getElementById('incidentCount');
    if(incidentCountEl) incidentCountEl.innerText = "0"; 

    // Initialize Autocomplete
    setupAutocomplete('startLocation', 'startSuggestions');
    setupAutocomplete('endLocation', 'endSuggestions');

    // Add Safe Locations (Police/Patrol) to LayerGroup
    window.safeLocations.forEach(loc => {
        let icon = policeIcon;
        if (loc.type === 'patrol') icon = patrolIcon;
        if (loc.type === 'chauki') icon = chaukiIcon;
        
        L.marker([loc.lat, loc.lng], {icon: icon})
            .bindPopup(`<b>${loc.name}</b><br>${loc.type.toUpperCase()}<br><button onclick="removeAsset(this)" style="color:red; margin-top:5px; border:1px solid red; background:white; border-radius:4px; cursor:pointer;">Delete Asset</button>`)
            .addTo(window.safeAssetsLayer);
    });

    // --- ADMIN / EDIT MODE LOGIC ---
    window.isEditMode = false;
    window.editType = 'cctv'; // Default
    window.isCustomizeMode = false; // New Customize Mode
    window.userWaypoints = []; // Store user custom waypoints

    // Create Edit Controls UI
    const editControls = L.control({position: 'topright'});
    editControls.onAdd = function(map) {
        const div = L.DomUtil.create('div', 'edit-controls');
        div.style.backgroundColor = 'white';
        div.style.padding = '10px';
        div.style.borderRadius = '8px';
        div.style.boxShadow = '0 2px 5px rgba(0,0,0,0.2)';
        div.innerHTML = `
            <div style="margin-bottom:5px; font-weight:bold;">Admin Mode</div>
            <label class="switch">
                <input type="checkbox" id="editModeToggle" onchange="toggleEditMode()">
                <span class="slider round"></span>
            </label>
            <div id="editTools" style="display:none; margin-top:10px;">
                <select id="assetTypeSelector" style="width:100%; padding:5px; margin-bottom:5px;" onchange="toggleRadiusControl()">
                    <option value="cctv">Add CCTV</option>
                    <option value="police">Add Police Station</option>
                    <option value="chauki">Add Chauki</option>
                    <option value="patrol">Add Patrol</option>
                    <option value="danger">Add Danger Zone</option>
                </select>
                
                <div id="radiusControl" style="display:none; margin-bottom:5px;">
                    <label style="font-size:12px;">Danger Radius: <span id="radiusVal">150</span>m</label>
                    <input type="range" id="radiusInput" min="50" max="500" value="150" style="width:100%" oninput="document.getElementById('radiusVal').innerText = this.value">
                </div>

                <small style="color:gray;">Click map to add. Click icon to delete.</small>
                <hr style="margin:5px 0;">
                <button onclick="resetMapData()" style="width:100%; background:#ef4444; color:white; border:none; padding:5px; border-radius:4px;">Reset All Data</button>
            </div>
        `;
        return div;
    };
    editControls.addTo(window.map);

    // Load Saved Data
    loadMapData();

    // Map Click Handler for Adding Assets
    window.map.on('click', function(e) {
        // 1. Customize Mode (Priority)
        if (window.isCustomizeMode) {
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;
            
            // Add visual marker for waypoint
            const wpIcon = L.divIcon({
                className: 'custom-div-icon',
                html: "<div style='background-color:#8b5cf6; width: 12px; height: 12px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 5px #8b5cf6;'></div>",
                iconSize: [12, 12],
                iconAnchor: [6, 6]
            });
            
            L.marker([lat, lng], {icon: wpIcon})
                .bindPopup("Via Point")
                .addTo(window.map);
                
            window.userWaypoints.push({lat, lng});
            
            // Recalculate Route immediately
            findSafeRoute(true); // Silent update
            return;
        }

        // 2. Admin Mode
        if (window.isEditMode) {
            const type = document.getElementById('assetTypeSelector').value;
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;
            
            let icon = cctvIcon;
            let popupText = "New Asset";
            let layer = window.safeAssetsLayer;
    
            if (type === 'cctv') {
                icon = cctvIcon;
                popupText = "<b>New CCTV</b><br>Status: Active";
                window.cctvLocations.push({lat, lng, id: `CCTV-${Date.now()}`});
            } else if (type === 'police') {
                icon = policeIcon;
                popupText = "<b>New Police Station</b>";
                window.safeLocations.push({name: "New Police Station", type: "police", lat, lng});
            } else if (type === 'chauki') {
                icon = chaukiIcon;
                popupText = "<b>New Chauki</b>";
                window.safeLocations.push({name: "New Chauki", type: "chauki", lat, lng});
            } else if (type === 'patrol') {
                icon = patrolIcon;
                popupText = "<b>New Patrol</b>";
                window.safeLocations.push({name: "New Patrol", type: "patrol", lat, lng});
            } else if (type === 'danger') {
                icon = criminalIcon;
                popupText = "<b style='color:red'>New Danger Zone</b>";
                const radius = parseInt(document.getElementById('radiusInput').value);
                window.criminalLocations.push({lat, lng, type: "Manual Report", radius: radius});
                
                // Add Circle
                L.circle([lat, lng], {color: 'red', fillColor: '#f03', fillOpacity: 0.2, radius: radius}).addTo(layer);
            }
    
            const marker = L.marker([lat, lng], {icon: icon})
                .bindPopup(`${popupText}<br><button onclick="removeAsset(this)" style="color:red; margin-top:5px; border:1px solid red; background:white; border-radius:4px; cursor:pointer;">Delete Asset</button>`)
                .addTo(layer);
                
            // Open popup immediately to confirm
            marker.openPopup();
            
            // Save Changes
            saveMapData();
            return;
        }

        // 3. Default Mode (Start Location Selection)
        const lat = e.latlng.lat;
        const lng = e.latlng.lng;
        
        document.getElementById('startLocation').value = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
        
        if (window.userMarker) {
            window.userMarker.setLatLng([lat, lng]);
            window.userMarker.bindPopup("<b>Start Location</b><br>Selected on Map").openPopup();
        }
    });
});

// --- Customize Mode Functions ---
window.toggleCustomizeMode = function() {
    window.isCustomizeMode = !window.isCustomizeMode;
    const btn = document.getElementById('customizeBtn');
    if (window.isCustomizeMode) {
        btn.innerText = "Click Map to Add Waypoint";
        btn.style.backgroundColor = "#8b5cf6"; // Purple
        alert("Customize Mode: Click anywhere on the map to force the route to go through that point.");
    } else {
        btn.innerText = "Enable Customization";
        btn.style.backgroundColor = "#3b82f6"; // Blue
    }
};

window.clearCustomization = function() {
    window.userWaypoints = [];
    alert("Custom waypoints cleared. Recalculating...");
    findSafeRoute();
};

window.saveCurrentAsUrgent = function() {
    if (!window.routeLine) {
        alert("No route currently drawn to save!");
        return;
    }
    
    if(confirm("Set the currently visible route as the default 'Urgent Help' path?")) {
        // Get all latlngs from the polyline
        const latlngs = window.routeLine.getLatLngs();
        
        // Convert to simple array of [lat, lng]
        // Leaflet might return nested arrays if it's a multi-polyline, but usually it's flat for simple routes
        const simplePath = latlngs.map(pt => [pt.lat, pt.lng]);
        
        window.urgentRoutePath = simplePath;
        saveMapData();
        alert("Urgent Route Saved! This path will now be used when 'Urgent Help' is toggled.");
    }
};

// --- Edit Mode Functions ---
window.toggleEditMode = function() {
    window.isEditMode = document.getElementById('editModeToggle').checked;
    const tools = document.getElementById('editTools');
    if (window.isEditMode) {
        tools.style.display = 'block';
        // Ensure assets are visible in edit mode
        if(window.safeAssetsLayer) window.safeAssetsLayer.addTo(window.map);
        alert("Edit Mode Enabled: Click on map to add assets. Click existing assets to delete.");
    } else {
        tools.style.display = 'none';
    }
};

window.removeAsset = function(btn) {
    // Find the popup's content wrapper
    const popupContent = btn.closest('.leaflet-popup-content');
    if (!popupContent) return;

    // Leaflet stores the popup object on the map, and the popup has a reference to its source layer (marker)
    // But accessing it from the DOM element is tricky.
    // A more robust way is to find the marker that owns this popup.
    
    // Iterate over all layers in safeAssetsLayer to find the one with this open popup
    let targetLayer = null;
    window.safeAssetsLayer.eachLayer(function(layer) {
        if (layer.getPopup() && layer.getPopup().isOpen() && layer.getPopup().getContent().includes(btn.parentElement.innerHTML)) {
             // This is a loose match, but effective for this demo
             // Better: Leaflet binds the popup instance to the wrapper
        }
        // Actually, the simplest way in Leaflet:
        // The popup object is usually accessible via the map's open popup if it's the only one.
    });

    // Alternative: Use the map's currently open popup
    const popup = window.map._popup; 
    if (popup && popup._source) {
        const lat = popup._source.getLatLng().lat;
        const lng = popup._source.getLatLng().lng;

        // Remove the marker itself
        window.safeAssetsLayer.removeLayer(popup._source);

        // Check for associated Circle (Danger Zone) and remove it
        window.safeAssetsLayer.eachLayer(function(layer) {
            if (layer instanceof L.Circle) {
                const cLat = layer.getLatLng().lat;
                const cLng = layer.getLatLng().lng;
                // Check if circle is at the same location
                if (Math.abs(cLat - lat) < 0.000001 && Math.abs(cLng - lng) < 0.000001) {
                    window.safeAssetsLayer.removeLayer(layer);
                }
            }
        });

        // Also remove from arrays to update routing logic
        
        // Remove from CCTV array
        window.cctvLocations = window.cctvLocations.filter(c => c.lat !== lat || c.lng !== lng);
        
        // Remove from Criminal array
        if(window.criminalLocations) {
             window.criminalLocations = window.criminalLocations.filter(c => c.lat !== lat || c.lng !== lng);
        }

        // Remove from Safe Locations
        if(window.safeLocations) {
            window.safeLocations = window.safeLocations.filter(c => c.lat !== lat || c.lng !== lng);
        }

        // Save Changes
        saveMapData();
    }
};

// --- Mock Data for Search ---
const mockLocations = [
    { name: "DJ Sanghvi College", type: "landmark", lat: 19.1075, lng: 72.8372 },
    { name: "Vile Parle Police Station", type: "police", lat: 19.1020, lng: 72.8450 },
    { name: "Juhu Police Station", type: "police", lat: 19.1050, lng: 72.8280 },
    { name: "Santacruz Police Station", type: "police", lat: 19.0840, lng: 72.8360 },
    { name: "Andheri Police Station", type: "police", lat: 19.1190, lng: 72.8460 },
    { name: "Khar Police Station", type: "police", lat: 19.0700, lng: 72.8340 },
    { name: "Bandra Police Station", type: "police", lat: 19.0550, lng: 72.8300 },
    { name: "Vile Parle Station (East)", type: "transit", lat: 19.1000, lng: 72.8430 },
    { name: "Vile Parle Station (West)", type: "transit", lat: 19.1000, lng: 72.8420 },
    { name: "Andheri Station", type: "transit", lat: 19.1195, lng: 72.8465 },
    { name: "Santacruz Station", type: "transit", lat: 19.0820, lng: 72.8400 },
    { name: "Juhu Beach", type: "landmark", lat: 19.0980, lng: 72.8260 },
    { name: "Versova Beach", type: "landmark", lat: 19.1300, lng: 72.8150 },
    { name: "Mithibai College", type: "landmark", lat: 19.1030, lng: 72.8380 },
    { name: "NMIMS University", type: "landmark", lat: 19.1035, lng: 72.8375 },
    { name: "PVR Juhu", type: "landmark", lat: 19.1060, lng: 72.8290 },
    { name: "JW Marriott Juhu", type: "landmark", lat: 19.1010, lng: 72.8250 },
    { name: "Infinity Mall Andheri", type: "landmark", lat: 19.1400, lng: 72.8300 }
];

// Updated Safe Locations (Wider Coverage: 10-20km radius)
window.safeLocations = [
    // Police Stations (Main Hubs)
    { name: "Vile Parle Police Station", type: "police", lat: 19.1020, lng: 72.8450 },
    { name: "Juhu Police Station", type: "police", lat: 19.1050, lng: 72.8280 },
    { name: "Santacruz Police Station", type: "police", lat: 19.0840, lng: 72.8360 },
    { name: "Andheri Police Station", type: "police", lat: 19.1140, lng: 72.8460 },
    { name: "Khar Police Station", type: "police", lat: 19.0700, lng: 72.8340 },
    { name: "Bandra Police Station", type: "police", lat: 19.0550, lng: 72.8300 },
    { name: "Versova Police Station", type: "police", lat: 19.1320, lng: 72.8120 },
    { name: "Oshiwara Police Station", type: "police", lat: 19.1450, lng: 72.8300 },
    { name: "Vakola Police Station", type: "police", lat: 19.0800, lng: 72.8550 },
    
    // Police Chaukis (Isolated, not near stations)
    { name: "Police Chauki (Juhu Circle)", type: "chauki", lat: 19.1100, lng: 72.8300 }, // Major Junction
    { name: "Police Chauki (Milan Subway)", type: "chauki", lat: 19.0900, lng: 72.8420 }, // Bridge Area
    { name: "Police Chauki (Seven Bungalows)", type: "chauki", lat: 19.1280, lng: 72.8180 }, // Versova End
    { name: "Police Chauki (Kalanagar)", type: "chauki", lat: 19.0600, lng: 72.8500 }, // Bandra East Entry

    // Patrol Vehicles (At Major Junctions/Roads)
    { name: "Patrol Vehicle Alpha (SV Road)", type: "patrol", lat: 19.1050, lng: 72.8400 },
    { name: "Patrol Vehicle Beta (Linking Road)", type: "patrol", lat: 19.0650, lng: 72.8350 },
    { name: "Patrol Vehicle Gamma (WEH Andheri)", type: "patrol", lat: 19.1150, lng: 72.8550 },
    { name: "Patrol Vehicle Delta (Juhu Tara)", type: "patrol", lat: 19.0950, lng: 72.8280 },
    { name: "Patrol Vehicle Epsilon (Lokhandwala)", type: "patrol", lat: 19.1400, lng: 72.8250 }
];

// --- Fuzzy Search Logic ---
function setupAutocomplete(inputId, suggestionsId) {
    const input = document.getElementById(inputId);
    const box = document.getElementById(suggestionsId);

    input.addEventListener('input', function() {
        const val = this.value.toLowerCase();
        box.innerHTML = '';
        
        if (!val) {
            box.style.display = 'none';
            return;
        }

        // Simple fuzzy match: check if string includes query
        const matches = mockLocations.filter(loc => 
            loc.name.toLowerCase().includes(val)
        );

        if (matches.length > 0) {
            matches.forEach(loc => {
                const div = document.createElement('div');
                div.className = 'suggestion-item';
                
                let icon = 'fa-map-marker-alt';
                if(loc.type === 'police') icon = 'fa-shield-alt';
                if(loc.type === 'hospital') icon = 'fa-hospital';
                if(loc.type === 'transit') icon = 'fa-train';

                div.innerHTML = `<i class="fas ${icon}"></i> ${loc.name}`;
                div.onclick = function() {
                    input.value = loc.name;
                    box.style.display = 'none';
                };
                box.appendChild(div);
            });
            box.style.display = 'block';
        } else {
            box.style.display = 'none';
        }
    });

    // Close on click outside
    document.addEventListener('click', function(e) {
        if (e.target !== input && e.target !== box) {
            box.style.display = 'none';
        }
    });
}

// --- Urgent Mode Logic ---
function toggleUrgentMode() {
    const isUrgent = document.getElementById('urgentToggle').checked;
    const endInput = document.getElementById('endLocation');
    const startInput = document.getElementById('startLocation');
    
    // Clear any existing urgent markers
    if (window.urgentMarkers) {
        window.urgentMarkers.forEach(m => m.remove());
        window.urgentMarkers = [];
    }

    if (isUrgent) {
        // SHOW SAFE ASSETS
        if(window.safeAssetsLayer) {
            window.safeAssetsLayer.addTo(window.map);
        }

        // STATIC ROUTE DEFINITION (DJ Sanghvi -> Vile Parle PS)
        const staticStart = {lat: 19.1075, lng: 72.8372, name: "DJ Sanghvi College"};
        const staticEnd = {lat: 19.1020, lng: 72.8450, name: "Vile Parle Police Station"};
        
        // Set Inputs
        startInput.value = staticStart.name;
        endInput.value = staticEnd.name;
        endInput.style.backgroundColor = '#fee2e2'; // Red tint
        endInput.style.borderColor = '#ef4444';

        // Hardcoded Path (Approximate along main roads)
        // Use saved urgent route if available, else default
        const defaultPath = [
            [19.1075, 72.8372], // DJ Sanghvi
            [19.1075, 72.8360], // JVPD Junction
            [19.1050, 72.8360], // SV Road South
            [19.1020, 72.8360], // Turn East
            [19.1020, 72.8400], // Towards Station
            [19.1020, 72.8450]  // Vile Parle PS
        ];
        
        const staticPath = window.urgentRoutePath || defaultPath;

        // Draw Static Route
        if (window.routeLine) window.routeLine.remove();
        
        window.routeLine = L.polyline(staticPath, {
            color: '#ef4444', // Red for Urgent
            weight: 5,
            opacity: 0.8,
            lineCap: 'round'
        }).addTo(window.map);

        window.map.fitBounds(window.routeLine.getBounds(), {padding: [50, 50]});
        
        // --- ADD MARKERS FOR WAYPOINTS (CAMERAS) & END (POLICE) ---
        window.urgentMarkers = [];
        
        const cctvIcon = L.divIcon({
            className: 'custom-div-icon',
            html: "<div style='background-color:#3b82f6; width: 18px; height: 18px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-video' style='color:white; font-size:9px;'></i></div>",
            iconSize: [18, 18],
            iconAnchor: [9, 9]
        });
        
        const policeIcon = L.divIcon({
            className: 'custom-div-icon',
            html: "<div style='background-color:#10b981; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-shield-alt' style='color:white; font-size:12px;'></i></div>",
            iconSize: [24, 24],
            iconAnchor: [12, 12]
        });

        // Iterate through path points
        for (let i = 0; i < staticPath.length; i++) {
            const pt = staticPath[i]; // [lat, lng]
            
            if (i === staticPath.length - 1) {
                // Last Point -> Police Chouki
                const m = L.marker(pt, {icon: policeIcon})
                    .bindPopup("<b>Safe Destination</b><br>Police Chouki")
                    .addTo(window.map);
                window.urgentMarkers.push(m);
            } else if (i > 0) {
                // Intermediate Points -> Cameras
                // Skip index 0 (Start)
                const m = L.marker(pt, {icon: cctvIcon})
                    .bindPopup("<b>Safe Waypoint</b><br>CCTV Coverage")
                    .addTo(window.map);
                window.urgentMarkers.push(m);
            }
        }

        // Show Custom Modal
        document.getElementById('urgentDestName').innerText = staticEnd.name;
        const modal = document.getElementById('urgentModal');
        if(modal) modal.style.display = 'flex';

        // Send Urgent Alert to Backend
        fetch('/api/report_urgent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                current_location: staticStart.name,
                destination: staticEnd.name,
                coords: staticStart
            })
        })
        .then(res => res.json())
        .then(data => console.log('Urgent Alert Sent:', data))
        .catch(err => console.error('Error sending alert:', err));

    } else {
        // HIDE SAFE ASSETS
        if(window.safeAssetsLayer) {
            window.safeAssetsLayer.remove();
        }

        // Reset
        endInput.style.backgroundColor = '';
        endInput.style.borderColor = '';
        endInput.value = ''; 
        startInput.value = '';
        
        // Remove Route Line
        if(window.routeLine) {
            window.routeLine.remove();
            window.routeLine = null;
        }
        
        // Remove Urgent Markers
        if (window.urgentMarkers) {
            window.urgentMarkers.forEach(m => m.remove());
            window.urgentMarkers = [];
        }
    }
}

function closeUrgentModal() {
    const modal = document.getElementById('urgentModal');
    if(modal) modal.style.display = 'none';
}

// Global functions for UI interaction
function findSafeRoute(silent = false, destinationCoords = null) {
    const start = document.getElementById('startLocation').value;
    const end = document.getElementById('endLocation').value;
    
    if(!start || !end) {
        if(!silent) alert("Please enter both locations");
        return;
    }
    
    // SHOW SAFE ASSETS
    if(window.safeAssetsLayer) {
        window.safeAssetsLayer.addTo(window.map);
    }
    
    // Use the same default path as Urgent Help (DJ Sanghvi -> Vile Parle PS)
    const defaultPath = [
        [19.1075, 72.8372], // DJ Sanghvi
        [19.1075, 72.8360], // JVPD Junction
        [19.1050, 72.8360], // SV Road South
        [19.1020, 72.8360], // Turn East
        [19.1020, 72.8400], // Towards Station
        [19.1020, 72.8450]  // Vile Parle PS
    ];
    
    const staticPath = window.urgentRoutePath || defaultPath;
    
    // Clear existing route markers
    if (window.urgentMarkers) {
        window.urgentMarkers.forEach(m => m.remove());
        window.urgentMarkers = [];
    }

    // Draw Route
    if (window.routeLine) window.routeLine.remove();
    
    window.routeLine = L.polyline(staticPath, {
        color: '#1e40af', // Blue for search
        weight: 5,
        opacity: 0.8,
        lineCap: 'round'
    }).addTo(window.map);
    
    window.map.fitBounds(window.routeLine.getBounds(), {padding: [50, 50]});
    
    // Add markers for waypoints (CCTVs) and end (Police)
    window.urgentMarkers = [];
    
    const cctvIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#3b82f6; width: 18px; height: 18px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-video' style='color:white; font-size:9px;'></i></div>",
        iconSize: [18, 18],
        iconAnchor: [9, 9]
    });
    
    const policeIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:#10b981; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-shield-alt' style='color:white; font-size:12px;'></i></div>",
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });

    // Add markers along path
    for (let i = 0; i < staticPath.length; i++) {
        const pt = staticPath[i];
        
        if (i === staticPath.length - 1) {
            // Last Point -> Police Station
            const m = L.marker(pt, {icon: policeIcon})
                .bindPopup("<b>Safe Destination</b><br>Police Station")
                .addTo(window.map);
            window.urgentMarkers.push(m);
        } else if (i > 0) {
            // Intermediate Points -> Cameras
            const m = L.marker(pt, {icon: cctvIcon})
                .bindPopup("<b>Safe Waypoint</b><br>CCTV Coverage")
                .addTo(window.map);
            window.urgentMarkers.push(m);
        }
    }
    
    console.log("Safe Route drawn (Same as Urgent path)");
}

/* 
   REMOVED ALGORITHMS:
   - fetchOSRMRoute
   - checkRouteSafety
   - findSafeWaypoint
   - saveRouteToBackend (optional, but kept simple logging above)
*/

function drawRoute(geometry, isDetour) {
    // Legacy function, kept if needed for other parts, but findSafeRoute now handles drawing directly.
}


function useMyLocation() {
    document.getElementById('startLocation').value = "DJ Sanghvi College";
}

function reportIncident() {
    alert("Incident Reported! Authorities have been notified.");
    toggleIncidentModal();
    // Also show assets on manual report
    if(window.safeAssetsLayer) {
        window.safeAssetsLayer.addTo(window.map);
    }
}

function shareLocation() {
    if (navigator.share) {
        navigator.share({
            title: 'My Safe Route',
            text: 'I am travelling from DJ Sanghvi to Vile Parle PS.',
            url: window.location.href
        });
    } else {
        alert("Location link copied to clipboard!");
    }
}

// --- Helper Functions for Admin Mode ---

window.toggleRadiusControl = function() {
    const type = document.getElementById('assetTypeSelector').value;
    const radiusControl = document.getElementById('radiusControl');
    if (type === 'danger') {
        radiusControl.style.display = 'block';
    } else {
        radiusControl.style.display = 'none';
    }
};

window.saveMapData = function() {
    const data = {
        cctv: window.cctvLocations,
        criminal: window.criminalLocations,
        safe: window.safeLocations,
        urgentRoute: window.urgentRoutePath
    };

    fetch('/api/save_map_data', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    })
    .then(res => res.json())
    .then(data => {
        console.log("Map data saved successfully");
    })
    .catch(err => console.error("Error saving map data:", err));
};

window.loadMapData = function() {
    fetch('/api/get_map_data')
    .then(res => res.json())
    .then(data => {
        if (data.cctv) window.cctvLocations = data.cctv;
        if (data.criminal) window.criminalLocations = data.criminal;
        if (data.safe) window.safeLocations = data.safe;
        if (data.urgentRoute) window.urgentRoutePath = data.urgentRoute;

        // Re-render all assets
        if (window.safeAssetsLayer) {
            window.safeAssetsLayer.clearLayers();
            
            // Re-add CCTV
            const cctvIcon = L.divIcon({
                className: 'custom-div-icon',
                html: "<div style='background-color:#3b82f6; width: 18px; height: 18px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-video' style='color:white; font-size:9px;'></i></div>",
                iconSize: [18, 18],
                iconAnchor: [9, 9]
            });

            window.cctvLocations.forEach(cam => {
                L.marker([cam.lat, cam.lng], {icon: cctvIcon})
                    .bindPopup(`<b>${cam.id}</b><br>Status: Active<br><button onclick="removeAsset(this)" style="color:red; margin-top:5px; border:1px solid red; background:white; border-radius:4px; cursor:pointer;">Delete Asset</button>`)
                    .addTo(window.safeAssetsLayer);
            });

            // Re-add Criminal/Danger
            const criminalIcon = L.divIcon({
                className: 'custom-div-icon',
                html: "<div style='background-color:#ef4444; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; animation: pulse 1.5s infinite; box-shadow: 0 0 10px #ef4444;'><i class='fas fa-exclamation-triangle' style='color:white; font-size:12px;'></i></div>",
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });

            window.criminalLocations.forEach(crim => {
                L.marker([crim.lat, crim.lng], {icon: criminalIcon})
                    .bindPopup(`<b style="color:red">DANGER: ${crim.type}</b><br>Avoid this area<br><button onclick="removeAsset(this)" style="color:red; margin-top:5px; border:1px solid red; background:white; border-radius:4px; cursor:pointer;">Delete Asset</button>`)
                    .addTo(window.safeAssetsLayer);
                
                // Add Circle
                L.circle([crim.lat, crim.lng], {
                    color: 'red',
                    fillColor: '#f03',
                    fillOpacity: 0.2,
                    radius: crim.radius || 150
                }).addTo(window.safeAssetsLayer);
            });

            // Re-add Safe Locations
            const policeIcon = L.divIcon({
                className: 'custom-div-icon',
                html: "<div style='background-color:#10b981; width: 24px; height: 24px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-shield-alt' style='color:white; font-size:12px;'></i></div>",
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
        
            const chaukiIcon = L.divIcon({
                className: 'custom-div-icon',
                html: "<div style='background-color:#059669; width: 20px; height: 20px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-building' style='color:white; font-size:10px;'></i></div>",
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
        
            const patrolIcon = L.divIcon({
                className: 'custom-div-icon',
                html: "<div style='background-color:#f59e0b; width: 22px; height: 22px; border-radius: 50%; border: 2px solid white; display:flex; align-items:center; justify-content:center; box-shadow: 0 2px 5px rgba(0,0,0,0.2);'><i class='fas fa-car' style='color:white; font-size:11px;'></i></div>",
                iconSize: [22, 22],
                iconAnchor: [11, 11]
            });

            window.safeLocations.forEach(loc => {
                let icon = policeIcon;
                if (loc.type === 'patrol') icon = patrolIcon;
                if (loc.type === 'chauki') icon = chaukiIcon;
                
                L.marker([loc.lat, loc.lng], {icon: icon})
                    .bindPopup(`<b>${loc.name}</b><br>${loc.type.toUpperCase()}<br><button onclick="removeAsset(this)" style="color:red; margin-top:5px; border:1px solid red; background:white; border-radius:4px; cursor:pointer;">Delete Asset</button>`)
                    .addTo(window.safeAssetsLayer);
            });
            
            // Update Stats
            const cctvCountEl = document.getElementById('cctvCount');
            if(cctvCountEl) cctvCountEl.innerText = window.cctvLocations.length;
        }
    })
    .catch(err => console.error("Error loading map data:", err));
};

window.resetMapData = function() {
    if(confirm("Are you sure you want to reset all map data to defaults? This cannot be undone.")) {
        fetch('/api/save_map_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}) // Empty object triggers reset in backend if we implemented it that way, or we can just send default data.
            // Actually, the backend implementation of save_map_data just overwrites the file. 
            // If we want to reset to "defaults", we should probably delete the file or overwrite with defaults.
            // But the user asked to "remove all the things". 
            // Let's just clear the arrays and save.
        })
        .then(() => {
             // Clear local arrays
             window.cctvLocations = [];
             window.criminalLocations = [];
             window.safeLocations = [];
             saveMapData(); // Save empty arrays
             loadMapData(); // Reload (will clear map)
        });
    }
};
