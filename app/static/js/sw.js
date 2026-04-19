self.addEventListener('push', function(event) {
    console.log('Push received:', event);
    
    let data = {
        title: 'ApexEstateHub',
        body: 'You have a new notification',
        icon: '/static/assets/logo.png',
        url: '/dashboard'
    };
    
    if (event.data) {
        try {
            data = event.data.json();
        } catch (e) {
            data.body = event.data.text();
        }
    }
    
    const options = {
        body: data.body,
        icon: data.icon,
        badge: data.icon,
        vibrate: [200, 100, 200],
        data: {
            url: data.url,
            dateOfArrival: Date.now()
        },
        actions: [
            {
                action: 'open',
                title: 'Open',
                icon: '/static/assets/logo.png'
            },
            {
                action: 'close',
                title: 'Close',
                icon: '/static/assets/logo.png'
            }
        ]
    };
    
    event.waitUntil(
        self.registration.showNotification(data.title, options)
    );
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    
    if (event.action === 'open' || !event.action) {
        const urlToOpen = event.notification.data?.url || '/dashboard';
        
        event.waitUntil(
            clients.matchAll({type: 'window', includeUncontrolled: true})
                .then(windowClients => {
                    for (let client of windowClients) {
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

self.addEventListener('install', function(event) {
    console.log('Service Worker installed');
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    console.log('Service Worker activated');
    event.waitUntil(clients.claim());
});