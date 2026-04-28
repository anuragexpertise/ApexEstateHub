document.addEventListener("DOMContentLoaded", function () {
    function syncBodyState() {
        const sidebar = document.getElementById("app-sidebar");
        const mobileOpen = !!sidebar &&
            sidebar.classList.contains("sidebar-open") &&
            window.innerWidth <= 767;

        document.body.classList.toggle("sidebar-visible-mobile", mobileOpen);
    }

    function attachSidebarObserver() {
        const sidebar = document.getElementById("app-sidebar");
        if (!sidebar || sidebar.dataset.layoutObserverAttached === "true") {
            return !!sidebar;
        }

        const observer = new MutationObserver(syncBodyState);
        observer.observe(sidebar, {
            attributes: true,
            attributeFilter: ["class"],
        });

        sidebar.dataset.layoutObserverAttached = "true";
        syncBodyState();
        return true;
    }

    if (!attachSidebarObserver()) {
        const intervalId = window.setInterval(function () {
            if (attachSidebarObserver()) {
                window.clearInterval(intervalId);
            }
        }, 250);

        window.setTimeout(function () {
            window.clearInterval(intervalId);
        }, 5000);
    }

    window.addEventListener("resize", syncBodyState);
    syncBodyState();
});
