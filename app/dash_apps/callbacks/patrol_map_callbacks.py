from dash import clientside_callback, Input, Output, State

clientside_callback(
    """
    function(map_id, lat_val, lon_val) {
        if (!map_id) return window.dash_clientside.no_update;
        
        // Ensure Leaflet is loaded
        if (typeof L === 'undefined') {
            console.error("Leaflet JS is not loaded yet.");
            return window.dash_clientside.no_update;
        }

        // Give the modal a moment to display so the map container has dimensions
        setTimeout(function() {
            // Dash sorts dictionary keys alphabetically in the DOM id attribute
            var dashIdStr = '{"entity":"patrol_location","type":"patrol-map-container"}';
            var container = document.getElementById(dashIdStr);
            if (!container) {
                // Fallback to querySelector just in case
                container = document.querySelector('[id*="patrol-map-container"]');
                if (!container) {
                    console.error("Map container not found in DOM.");
                    return;
                }
            }

            // Prevent re-initialization if already initialized
            if (container._leaflet_id) {
                return;
            }

            var parsedLat = parseFloat(lat_val);
            var parsedLon = parseFloat(lon_val);
            var defaultLat = isNaN(parsedLat) ? 28.6139 : parsedLat;
            var defaultLon = isNaN(parsedLon) ? 77.2090 : parsedLon;

            var map = L.map(container).setView([defaultLat, defaultLon], 16);
            
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);

            var marker = null;
            if (!isNaN(parsedLat) && !isNaN(parsedLon)) {
                marker = L.marker([parsedLat, parsedLon]).addTo(map);
            }

            map.on('click', function(e) {
                var lat = e.latlng.lat;
                var lon = e.latlng.lng;
                
                if (marker) {
                    marker.setLatLng(e.latlng);
                } else {
                    marker = L.marker(e.latlng).addTo(map);
                }

                // Update the form fields
                var latInput = document.getElementById('{"entity":"patrol_location","field":"latitude","type":"form-field"}');
                var lonInput = document.getElementById('{"entity":"patrol_location","field":"longitude","type":"form-field"}');
                
                if (latInput && lonInput) {
                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(latInput, lat.toFixed(6));
                    latInput.dispatchEvent(new Event('input', { bubbles: true }));
                    
                    setter.call(lonInput, lon.toFixed(6));
                    lonInput.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });

            // Fix map rendering issues inside Dash modals
            setTimeout(function() { map.invalidateSize(); }, 500);
        }, 300);

        return window.dash_clientside.no_update;
    }
    """,
    Output({"type": "patrol-map-dummy", "entity": "patrol_location"}, "children"),
    Input({"type": "patrol-map-container", "entity": "patrol_location"}, "id"),
    State({"type": "form-field", "entity": "patrol_location", "field": "latitude"}, "value"),
    State({"type": "form-field", "entity": "patrol_location", "field": "longitude"}, "value"),
    prevent_initial_call=True
)
