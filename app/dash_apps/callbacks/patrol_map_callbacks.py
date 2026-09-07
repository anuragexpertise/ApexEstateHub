from dash import clientside_callback, Input, Output, State

# ── 1. Map init + pin drop ───────────────────────────────────────────────────
#
# This callback only INITIALIZES the Leaflet map and forwards click
# coordinates to a hidden trigger button (see #2 below). It deliberately does
# NOT try to write into the lat/lon form-field inputs directly — a previous
# version did that by manually poking the DOM (native value setter +
# dispatchEvent), bypassing Dash's own callback graph, which the app's own
# save handler could sometimes fail to see reflected in State by the time the
# form was submitted. Values are now synced through a real Dash
# Output(form-field, "value") in callback #2 instead — the same pattern
# already used successfully by qty_stepper_callbacks.py in this codebase.
clientside_callback(
    """
    function(map_id, lat_val, lon_val) {
        if (!map_id) return window.dash_clientside.no_update;

        if (typeof L === 'undefined') {
            console.error("[patrol-map] Leaflet JS is not loaded yet — check that " +
                          "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js loaded " +
                          "(open the Network tab: a blocked/failed request there " +
                          "means the map can never initialize).");
            return window.dash_clientside.no_update;
        }

        // Dash sorts dictionary keys alphabetically in the DOM id attribute
        var containerIdStr = '{"entity":"patrol_location","type":"patrol-map-container"}';
        var pickedBtnIdStr  = '{"entity":"patrol_location","type":"patrol-map-picked"}';

        function findContainer() {
            var el = document.getElementById(containerIdStr);
            if (!el) {
                el = document.querySelector('[id*="patrol-map-container"]');
            }
            return el;
        }

        function initMap(container) {
            if (container._leaflet_id) {
                return; // already initialized
            }

            var parsedLat = parseFloat(lat_val);
            var parsedLon = parseFloat(lon_val);
            var defaultLat = isNaN(parsedLat) ? 28.6139 : parsedLat;
            var defaultLon = isNaN(parsedLon) ? 77.2090 : parsedLon;

            var map = L.map(container).setView([defaultLat, defaultLon], 16);

            var tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors'
            }).addTo(map);

            tiles.on('tileerror', function() {
                console.error("[patrol-map] A map tile failed to load from " +
                              "tile.openstreetmap.org — if this repeats for every " +
                              "tile, the tile server is likely blocked by a " +
                              "firewall/proxy/ad-blocker in this environment " +
                              "rather than a bug in the app.");
            });

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

                // Forward the picked coordinates to the hidden trigger
                // button as plain data attributes, then fire a REAL native
                // click on it. Dash tracks n_clicks on a genuine click event
                // unambiguously (unlike a React-controlled "value" prop), so
                // callback #2 below reliably fires and writes the lat/lon
                // into the form fields via a normal Dash Output.
                var pickedBtn = document.getElementById(pickedBtnIdStr);
                if (pickedBtn) {
                    pickedBtn.setAttribute('data-lat', lat.toFixed(6));
                    pickedBtn.setAttribute('data-lon', lon.toFixed(6));
                    pickedBtn.click();
                } else {
                    console.error("[patrol-map] Pin trigger button not found — " +
                                  "picked coordinates were not sent to the form.");
                }
            });

            // Re-measure once the browser has committed a layout pass, and
            // again shortly after as a safety net for any late CSS/collapse
            // transition still resolving the container's final size.
            if (window.requestAnimationFrame) {
                requestAnimationFrame(function() { map.invalidateSize(); });
            }
            setTimeout(function() { map.invalidateSize(); }, 400);
        }

        // Poll for the container to exist AND have a real, non-zero size
        // before calling L.map() on it (initializing on a zero-size element
        // is the classic cause of a grey/blank Leaflet map), bounded so we
        // never poll forever.
        var attempts = 0;
        var maxAttempts = 40; // ~4s at 100ms intervals
        var poll = setInterval(function() {
            attempts += 1;
            var container = findContainer();

            if (container && container._leaflet_id) {
                clearInterval(poll);
                return;
            }

            if (container && container.offsetWidth > 0 && container.offsetHeight > 0) {
                clearInterval(poll);
                initMap(container);
                return;
            }

            if (attempts >= maxAttempts) {
                clearInterval(poll);
                if (!container) {
                    console.error("[patrol-map] Map container not found in DOM after " +
                                  maxAttempts + " attempts (" + (maxAttempts / 10) +
                                  "s) — the form may not have rendered this card at all.");
                } else {
                    console.error("[patrol-map] Map container still has zero size after " +
                                  maxAttempts + " attempts; initializing anyway (map may " +
                                  "look broken until the page is resized/scrolled).");
                    initMap(container);
                }
            }
        }, 100);

        return window.dash_clientside.no_update;
    }
    """,
    Output({"type": "patrol-map-dummy", "entity": "patrol_location"}, "children"),
    Input({"type": "patrol-map-container", "entity": "patrol_location"}, "id"),
    State({"type": "form-field", "entity": "patrol_location", "field": "latitude"}, "value"),
    State({"type": "form-field", "entity": "patrol_location", "field": "longitude"}, "value"),
    prevent_initial_call=True,
)

# ── 2. Coordinate sync — Dash-native Output, not a DOM hack ─────────────────
#
# Fires on a real click (n_clicks) on the hidden trigger button set up in
# renderers.py's render_form_card (entity == "patrol_location" branch) and
# populated by callback #1 above. Reads the coordinates back off that same
# button's data-lat/data-lon attributes and writes them straight into the
# lat/lon form-field "value" props via a normal Dash Output — guaranteed to
# be reflected in State by the time the form is submitted, since it goes
# through Dash's own callback graph rather than simulating DOM input events.
clientside_callback(
    """
    function(n_clicks) {
        if (!n_clicks) {
            return [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update];
        }

        var pickedBtnIdStr = '{"entity":"patrol_location","type":"patrol-map-picked"}';
        var readoutIdStr    = '{"entity":"patrol_location","type":"patrol-map-readout"}';

        var pickedBtn = document.getElementById(pickedBtnIdStr);
        if (!pickedBtn) {
            console.error("[patrol-map] Pin trigger button missing on sync — this should not happen.");
            return [window.dash_clientside.no_update, window.dash_clientside.no_update, window.dash_clientside.no_update];
        }

        var lat = pickedBtn.getAttribute('data-lat');
        var lon = pickedBtn.getAttribute('data-lon');

        var readout = document.getElementById(readoutIdStr);
        if (readout) {
            readout.textContent = (lat && lon) ? ("Selected: " + lat + ", " + lon) : "";
        }

        return [lat, lon, window.dash_clientside.no_update];
    }
    """,
    Output({"type": "form-field", "entity": "patrol_location", "field": "latitude"}, "value"),
    Output({"type": "form-field", "entity": "patrol_location", "field": "longitude"}, "value"),
    Output({"type": "patrol-map-readout", "entity": "patrol_location"}, "children"),
    Input({"type": "patrol-map-picked", "entity": "patrol_location"}, "n_clicks"),
    prevent_initial_call=True,
)
