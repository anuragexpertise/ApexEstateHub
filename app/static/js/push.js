// Push notification setup
let swRegistration = null;
let isSubscribed = false;
let applicationServerPublicKey = null;

function showPushError(message) {
    // Non-blocking, user-visible notice: push is optional, but failures must not be silent.
    const existing = document.getElementById('pushError');
    if (existing) {
        existing.textContent = message;
        existing.classList.remove('hidden');
        return;
    }
    const el = document.createElement('div');
    el.id = 'pushError';
    el.className = 'conn-banner';
    el.style.background = '#b58900';
    el.style.fontSize = '13px';
    el.innerHTML = `<span>${message}</span>
        <button class="dismiss" onclick="this.parentElement.classList.add('hidden')">Dismiss</button>`;
    document.body.appendChild(el);
}

async function loadVapidPublicKey() {
    try {
        const response = await fetch('/api/push/vapid-public-key');
        if (!response.ok) {
            throw new Error(`Failed to fetch VAPID public key: ${response.status}`);
        }
        const data = await response.json();
        applicationServerPublicKey = data.publicKey;
        if (!applicationServerPublicKey) {
            throw new Error('VAPID public key is empty');
        }
        console.log('VAPID public key loaded');
        return true;
    } catch (error) {
        showPushError('Push notifications unavailable: could not load server key.');
        return false;
    }
}

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
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
        console.warn('Push notifications not supported');
        return;
    }

    const keyLoaded = await loadVapidPublicKey();
    if (!keyLoaded) {
        console.warn('Push notifications disabled: VAPID public key not available');
        return;
    }

    try {
        swRegistration = await navigator.serviceWorker.register('/static/sw.js');
        console.log('Service Worker registered');

        const subscription = await swRegistration.pushManager.getSubscription();
        isSubscribed = !(subscription === null);

        if (!isSubscribed) {
            await subscribeUser();
        } else {
            console.log('Already subscribed to push notifications');
        }
    } catch (error) {
        showPushError('Push notifications unavailable: ' + error.message);
    }
}

async function subscribeUser() {
    if (!applicationServerPublicKey) {
        console.error('Cannot subscribe: VAPID public key not loaded');
        return;
    }

    const auth = (JSON.parse(localStorage.getItem('auth-store') || '{}') || {});
    const token = auth.access_token || localStorage.getItem('jwt_token') || '';
    if (!token) {
        console.warn('Push subscribe skipped: no auth token available yet');
        return;
    }

    try {
        const applicationServerKey = urlBase64ToUint8Array(applicationServerPublicKey);
        const subscription = await swRegistration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: applicationServerKey
        });
        
        console.log('User is subscribed:', subscription);
        
        const headers = { 'Content-Type': 'application/json' };
        headers['Authorization'] = `Bearer ${token}`;
        
        const response = await fetch('/api/push/subscribe', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(subscription)
        });
        
        const data = await response.json();
        if (data.message || data.success) {
            console.log('Push subscription saved to server');
            isSubscribed = true;
        } else if (response.status === 401) {
            console.warn('Push subscribe failed: auth token expired or invalid');
        } else {
            console.warn('Push subscribe failed:', data);
        }
    } catch (error) {
        showPushError('Failed to subscribe to push notifications: ' + error.message);
    }
}

async function unsubscribeUser() {
    try {
        const subscription = await swRegistration.pushManager.getSubscription();
        if (subscription) {
            await subscription.unsubscribe();
            
            // Notify server
            const auth = (JSON.parse(localStorage.getItem('auth-store') || '{}') || {});
            const token = (auth.data && auth.data.access_token) ? auth.data.access_token : (auth.access_token || localStorage.getItem('jwt_token') || '');
            const headers = { 'Content-Type': 'application/json' };
            if (token) headers['Authorization'] = `Bearer ${token}`;
            
            await fetch('/api/push/subscription', {
                method: 'DELETE',
                headers: headers,
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