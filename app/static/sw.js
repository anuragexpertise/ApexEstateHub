self.addEventListener('push', function (event) {
    let data = {};
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data = { title: 'Notification', body: event.data.text() };
        }
    }

    const title = data.title || 'EsateHub';
    const options = {
        body: data.body || 'You have a new notification',
        icon: data.icon || '/static/assets/EH_logo.png',
        badge: '/static/assets/badge.png',
        vibrate: [200, 100, 200],
        data: {
            url: data.url || '/dashboard/',
            dateOfArrival: Date.now()
        },
        actions: [
            { action: 'open', title: 'Open' },
            { action: 'close', title: 'Close' }
        ]
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();

    if (event.action === 'open' || !event.action) {
        const urlToOpen = event.notification.data?.url || '/';
        event.waitUntil(
            clients.matchAll({ type: 'window', includeUncontrolled: true })
                .then(function (clientList) {
                    for (let i = 0; i < clientList.length; i++) {
                        const client = clientList[i];
                        if (client.url === urlToOpen && 'focus' in client) {
                            return client.focus();
                        }
                    }
                    if (clients.openWindow) {
                        return clients.openWindow(urlToOpen);
                    }
                })
        );
    }
});

self.addEventListener('install', function (event) {
    console.log('Service Worker installed');
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    console.log('Service Worker activated');
    event.waitUntil(clients.claim());
});
