// Push notification setup
let swRegistration = null;
let isSubscribed = false;

const applicationServerPublicKey = 'YOUR_VAPID_PUBLIC_KEY';

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, '+')
        .replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function initializePushNotifications() {
    if ('serviceWorker' in navigator && 'PushManager' in window) {
        try {
            // Register service worker
            swRegistration = await navigator.serviceWorker.register('/sw.js');
            console.log('Service Worker registered');
            
            // Check if already subscribed
            const subscription = await swRegistration.pushManager.getSubscription();
            isSubscribed = !(subscription === null);
            
            if (!isSubscribed) {
                await subscribeUser();
            } else {
                console.log('Already subscribed to push notifications');
            }
        } catch (error) {
            console.error('Push notification error:', error);
        }
    } else {
        console.warn('Push notifications not supported');
    }
}

async function subscribeUser() {
    try {
        const applicationServerKey = urlBase64ToUint8Array(applicationServerPublicKey);
        const subscription = await swRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: applicationServerKey
        });
        
        console.log('User is subscribed:', subscription);
        
        // Send subscription to server
        const response = await fetch('/auth/subscribe-push', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(subscription)
        });
        
        const data = await response.json();
        if (data.success) {
            console.log('Push subscription saved to server');
            isSubscribed = true;
        }
    } catch (error) {
        console.error('Failed to subscribe user:', error);
    }
}

async function unsubscribeUser() {
    try {
        const subscription = await swRegistration.pushManager.getSubscription();
        if (subscription) {
            await subscription.unsubscribe();
            
            // Notify server
            await fetch('/auth/unsubscribe-push', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });
            
            console.log('User unsubscribed');
            isSubscribed = false;
        }
    } catch (error) {
        console.error('Failed to unsubscribe:', error);
    }
}

// Initialize on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePushNotifications);
} else {
    initializePushNotifications();
}