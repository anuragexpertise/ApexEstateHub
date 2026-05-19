self.addEventListener('push', function (event) {
    let data = {};
    if (event.data) {
        data = event.data.json();
    }
    const title = data.title || 'Test Notification';
    const options = {
        body: data.body || 'This is a test message from your server.',
        icon: data.icon || '/static/assets/EH_logo.png',
        badge: '/static/assets/badge.png',
        data: {
            url: data.url || '/'
        }
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    if (event.notification.data && event.notification.data.url) {
        event.waitUntil(clients.openWindow(event.notification.data.url));
    }
});