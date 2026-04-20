// Mobile responsiveness handlers
(function() {
    'use strict';
    
    // Handle window resize
    function handleResize() {
        const sidebar = document.getElementById('main-sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (window.innerWidth > 768) {
            if (sidebar) sidebar.classList.remove('sidebar-open');
            if (overlay) overlay.classList.remove('active');
        }
    }
    
    // Handle touch events for sidebar
    function initTouchEvents() {
        let touchStartX = 0;
        let touchEndX = 0;
        
        document.addEventListener('touchstart', function(e) {
            touchStartX = e.changedTouches[0].screenX;
        });
        
        document.addEventListener('touchend', function(e) {
            touchEndX = e.changedTouches[0].screenX;
            handleSwipe();
        });
        
        function handleSwipe() {
            const sidebar = document.getElementById('main-sidebar');
            if (!sidebar) return;
            
            // Swipe right to open sidebar
            if (touchEndX - touchStartX > 100 && touchStartX < 50) {
                sidebar.classList.add('sidebar-open');
                document.querySelector('.sidebar-overlay')?.classList.add('active');
            }
            
            // Swipe left to close sidebar
            if (touchStartX - touchEndX > 100) {
                sidebar.classList.remove('sidebar-open');
                document.querySelector('.sidebar-overlay')?.classList.remove('active');
            }
        }
    }
    
    // Add overlay element if not exists
    function addOverlay() {
        if (!document.querySelector('.sidebar-overlay')) {
            const overlay = document.createElement('div');
            overlay.className = 'sidebar-overlay';
            overlay.id = 'sidebar-overlay';
            document.body.appendChild(overlay);
            
            overlay.addEventListener('click', function() {
                document.getElementById('main-sidebar')?.classList.remove('sidebar-open');
                overlay.classList.remove('active');
            });
        }
    }
    
    // Handle body scroll when sidebar is open
    function handleBodyScroll() {
        const sidebar = document.getElementById('main-sidebar');
        if (!sidebar) return;
        
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'class') {
                    if (sidebar.classList.contains('sidebar-open')) {
                        document.body.style.overflow = 'hidden';
                    } else {
                        document.body.style.overflow = '';
                    }
                }
            });
        });
        
        observer.observe(sidebar, { attributes: true });
    }
    
    // Initialize
    window.addEventListener('DOMContentLoaded', function() {
        addOverlay();
        handleResize();
        initTouchEvents();
        handleBodyScroll();
        window.addEventListener('resize', handleResize);
    });
})();

// Clientside callback handlers
window.clientside = window.clientside || {};
window.clientside.handleMobileMenu = function(n_clicks, current_style) {
    if (n_clicks) {
        const sidebar = document.getElementById('main-sidebar');
        const overlay = document.querySelector('.sidebar-overlay');
        
        if (sidebar) {
            if (sidebar.classList.contains('sidebar-open')) {
                sidebar.classList.remove('sidebar-open');
                if (overlay) overlay.classList.remove('active');
                return { ...current_style, transform: 'translateX(-100%)' };
            } else {
                sidebar.classList.add('sidebar-open');
                if (overlay) overlay.classList.add('active');
                return { ...current_style, transform: 'translateX(0)' };
            }
        }
    }
    return current_style;
};