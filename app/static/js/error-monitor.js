// error-monitor.js
//
// Dash is pinned to <2.15.0 in requirements.txt, which predates the
// official on_error/set_props global error-handling API (added in Dash
// 2.17). Without this, an uncaught exception in any Python callback
// (e.g. route_page() hitting a dropped DB connection mid-navigation)
// fails the browser's request to Dash's internal "_dash-update-component"
// endpoint, and dash-renderer's default behaviour is to log to the
// console and leave the page exactly as it was — no visible feedback at
// all. The person just sees a click that silently did nothing.
//
// This wraps window.fetch once, at the browser level, so it works
// regardless of the installed Dash version and needs no Python-side
// changes. It only reacts to Dash's own callback endpoint; every other
// fetch (login, push, QR scan, etc.) already has its own handling and
// is left untouched.

(function () {
    var BANNER_ID = 'eh-connection-banner';
    var hideTimer = null;

    function ensureBanner() {
        var el = document.getElementById(BANNER_ID);
        if (el) return el;
        el = document.createElement('div');
        el.id = BANNER_ID;
        el.style.cssText = [
            'position:fixed', 'top:0', 'left:0', 'right:0', 'z-index:99999',
            'padding:10px 16px', 'text-align:center', 'font-size:14px',
            'font-family:-apple-system,Segoe UI,Roboto,sans-serif',
            'color:#fff', 'background:#dc3545',
            'transform:translateY(-100%)', 'transition:transform .25s ease',
        ].join(';');
        document.body.appendChild(el);
        return el;
    }

    function showBanner(message) {
        var el = ensureBanner();
        el.textContent = message;
        // next frame, so the transform transition actually runs
        requestAnimationFrame(function () {
            el.style.transform = 'translateY(0)';
        });
        if (hideTimer) clearTimeout(hideTimer);
        hideTimer = setTimeout(hideBanner, 6000);
    }

    function hideBanner() {
        var el = document.getElementById(BANNER_ID);
        if (el) el.style.transform = 'translateY(-100%)';
    }

    function isDashCallback(url) {
        return typeof url === 'string' && url.indexOf('_dash-update-component') !== -1;
    }

    var originalFetch = window.fetch;
    window.fetch = function (input, init) {
        var url = typeof input === 'string' ? input : (input && input.url);
        return originalFetch.apply(this, arguments).then(function (response) {
            if (isDashCallback(url)) {
                if (!response.ok) {
                    if (!navigator.onLine) {
                        showBanner('No network connection — changes may not have saved. Reconnecting…');
                    } else if (response.status >= 500) {
                        showBanner('Connection issue — that action may not have completed. Please retry.');
                    } else {
                        hideBanner();
                    }
                } else {
                    hideBanner();
                }
            }
            return response;
        }).catch(function (err) {
            if (isDashCallback(url)) {
                showBanner('No network connection — changes may not have saved. Reconnecting…');
            }
            throw err;
        });
    };

    window.addEventListener('online', hideBanner);
    window.addEventListener('offline', function () {
        showBanner('No network connection.');
    });
})();
