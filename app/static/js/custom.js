// Custom JavaScript for ApexEstateHub
console.log('ApexEstateHub - Custom JS loaded');

// Handle sidebar toggle for mobile
function initSidebarToggle() {
    const sidebar = document.querySelector('.glass-sidebar');
    const toggleBtn = document.getElementById('sidebar-toggle');
    
    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener('click', () => {
            sidebar.classList.toggle('show');
        });
    }
}

// Handle notifications
function initNotifications() {
    if ('Notification' in window && Notification.permission === 'granted') {
        console.log('Notifications enabled');
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initSidebarToggle();
    initNotifications();
});