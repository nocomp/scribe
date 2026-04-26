// ───────────────────────────────────────────────────────────────────────
//  SCRIBE Service Worker — Gestion des Web Push notifications
// ───────────────────────────────────────────────────────────────────────
//  Ce SW est enregistré par scribe.js au chargement. Il reçoit les push
//  depuis le navigateur (Chrome/Firefox/Safari) même quand l'onglet
//  SCRIBE est fermé.
//
//  NE PAS modifier ce fichier sans bumper la version cache (force reinstall
//  auto sur tous les navigateurs).
// ───────────────────────────────────────────────────────────────────────

const SW_VERSION = 'scribe-sw-v1.0.0';

self.addEventListener('install', (event) => {
  // Active immédiatement le nouveau SW (sans attendre la fermeture de tous les onglets)
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

// ── Réception d'un push ──────────────────────────────────────────────────
self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'SCRIBE', body: event.data ? event.data.text() : '' };
  }

  const title = data.title || '🔔 SCRIBE';
  const body  = data.body  || '';
  const urgency = data.urgency || 2;
  const tag     = data.tag || 'scribe-default';

  const options = {
    body: body,
    icon: '/static/icon-192.png',  // à fournir, sinon fallback browser
    badge: '/static/badge-72.png',
    tag: tag,                      // dedup : remplace notif existante même tag
    renotify: urgency >= 3,        // re-vibre si même tag remplacé
    requireInteraction: urgency >= 3,
    vibrate: urgency >= 3 ? [300, 100, 300, 100, 600] : [200],
    data: {
      url: data.url || '/',
      urgency: urgency,
      event_type: data.event_type || '',
      timestamp: data.timestamp || Date.now(),
    },
    actions: urgency >= 3 ? [
      { action: 'open', title: 'Consulter' },
      { action: 'dismiss', title: 'Fermer' },
    ] : [],
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

// ── Clic sur la notification → ouvre SCRIBE sur la bonne page ──────────────
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  if (event.action === 'dismiss') return;

  const url = event.notification.data.url || '/';
  const fullUrl = new URL(url, self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Si un onglet SCRIBE est déjà ouvert, on le focus
        for (const client of clientList) {
          if (client.url.startsWith(self.location.origin) && 'focus' in client) {
            client.navigate(fullUrl);
            return client.focus();
          }
        }
        // Sinon on ouvre un nouvel onglet
        if (self.clients.openWindow) {
          return self.clients.openWindow(fullUrl);
        }
      })
  );
});

// ── Fermeture de la notification (pour télémétrie optionnelle) ──────────────
self.addEventListener('notificationclose', (event) => {
  // Noop pour l'instant. Pourrait poster vers /api/v1/notifications/dismissed.
});
