document.addEventListener("DOMContentLoaded", function () {
    function syncThemeState() {
        const root = document.getElementById("app-root");
        const themeClasses = Array.from(document.body.classList).filter(function (className) {
            return className.indexOf("theme-") === 0;
        });

        themeClasses.forEach(function (className) {
            document.body.classList.remove(className);
        });

        if (!root) {
            return;
        }

        Array.from(root.classList).forEach(function (className) {
            if (className.indexOf("theme-") === 0) {
                document.body.classList.add(className);
            }
        });
    }

    function syncBodyState() {
        const sidebar = document.getElementById("app-sidebar");
        const mobileOpen = !!sidebar &&
            sidebar.classList.contains("sidebar-open") &&
            window.innerWidth <= 767;

        document.body.classList.toggle("sidebar-visible-mobile", mobileOpen);
        syncThemeState();
    }

    function attachObservers() {
        const sidebar = document.getElementById("app-sidebar");
        const root = document.getElementById("app-root");

        if (sidebar && sidebar.dataset.layoutObserverAttached !== "true") {
            const sidebarObserver = new MutationObserver(syncBodyState);
            sidebarObserver.observe(sidebar, {
                attributes: true,
                attributeFilter: ["class"],
            });

            sidebar.dataset.layoutObserverAttached = "true";
        }

        if (root && root.dataset.themeObserverAttached !== "true") {
            const rootObserver = new MutationObserver(syncThemeState);
            rootObserver.observe(root, {
                attributes: true,
                attributeFilter: ["class"],
            });

            root.dataset.themeObserverAttached = "true";
        }

        syncBodyState();
        return !!(sidebar && root);
    }

    if (!attachObservers()) {
        const intervalId = window.setInterval(function () {
            if (attachObservers()) {
                window.clearInterval(intervalId);
            }
        }, 250);

        window.setTimeout(function () {
            window.clearInterval(intervalId);
        }, 5000);
    }

    // On small screens, close the sidebar drawer as soon as a sidebar tab is tapped.
    // Sidebar tabs are dcc.Link (History API, no page reload), so without this the
    // drawer stays open over the page the user just navigated to.
    // We click the overlay instead of editing classes by hand: the toggle_sidebar
    // callback owns the sidebar class + sidebar-open-store, and routing the close
    // through it keeps the next hamburger tap in sync. Delegated on document so it
    // survives Dash re-rendering the nav list on every route change.
    document.addEventListener("click", function (event) {
        if (!window.matchMedia("(max-width: 767px)").matches) {
            return;
        }

        const target = event.target;
        if (!target || !target.closest) {
            return;
        }

        // Tabs, plus the "+" quick-action buttons that sit on the same rows.
        if (!target.closest('#app-sidebar .snav-link, #app-sidebar [id*="btn-new-sidebar"]')) {
            return;
        }

        const sidebar = document.getElementById("app-sidebar");
        const overlay = document.getElementById("sb-overlay");
        if (sidebar && overlay && sidebar.classList.contains("sidebar-open")) {
            overlay.click();
        }
    });

    window.addEventListener("resize", syncBodyState);
    syncBodyState();
    syncThemeState();
});
