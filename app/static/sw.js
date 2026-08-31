/* Nudnik service worker.
 *
 * Two jobs: keep the shell available offline, and make a notification
 * genuinely hard to ignore. Swiping a reminder away without acting is not a
 * decision, so it re-posts instead of disappearing.
 */

/* Replaced by the server on every request, so a front-end change produces
 * different worker bytes and the browser installs a fresh worker. */
const VERSION = '__VERSION__';
const CACHE = 'nudnik-' + VERSION;

/* Assets that may be served straight from cache because their contents never
 * change without the filename changing. Everything else goes network-first, so
 * a deploy is visible on the next load rather than whenever the cache version
 * happens to be bumped. */
const IMMUTABLE = /\/static\/(fonts|icons)\//;
/* Only unversioned entries are precached. CSS and JS carry a ?v= query that
 * changes with their contents, so listing them here would just pin one stale
 * revision; they are cached on demand by the network-first handler instead. */
const SHELL = ['/', '/static/icons/icon-192.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL).catch(() => undefined))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // API calls must never be served stale -- an out-of-date open-loop list is
  // worse than an error message.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request).catch(() => caches.match(request)));
    return;
  }

  // Fonts and icons are content-stable: cache-first is safe and fast.
  if (IMMUTABLE.test(url.pathname)) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((response) => {
            if (response.ok && response.type === 'basic') {
              const copy = response.clone();
              caches.open(CACHE).then((cache) => cache.put(request, copy));
            }
            return response;
          })
      )
    );
    return;
  }

  // The app shell (HTML, CSS, JS) is network-first. A stale service-worker
  // cache silently serving last week's stylesheet is a nasty class of bug;
  // the cache is a genuine offline fallback, not the primary source.
  event.respondWith(
    fetch(request, { cache: 'no-cache' })
      .then((response) => {
        if (response.ok && response.type === 'basic') {
          const copy = response.clone();
          caches.open(CACHE).then((cache) => cache.put(request, copy));
        }
        return response;
      })
      .catch(() => caches.match(request).then((cached) => cached || caches.match('/')))
  );
});

/* ---------------------------------------------------------------- push --- */

const LABELS = {
  he: { done: '✅ בוצע', snooze: '⏰ עוד שעה', call: '📞 חייג', open: 'פתח' },
  en: { done: '✅ Done', snooze: '⏰ In an hour', call: '📞 Call', open: 'Open' },
};

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (err) {
    data = { title: 'Nudnik', body: event.data ? event.data.text() : '' };
  }

  const lang = data.lang === 'en' ? 'en' : 'he';
  const L = LABELS[lang];
  const tier = data.tier || 0;

  const maxActions = (self.Notification && Notification.maxActions) || 2;
  const actions = [{ action: 'done', title: L.done }];
  if (data.phone) actions.push({ action: 'call', title: L.call });
  else actions.push({ action: 'snooze', title: L.snooze });
  actions.length = Math.min(actions.length, maxActions);

  const options = {
    body: data.body || '',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/badge.png',
    lang,
    dir: lang === 'he' ? 'rtl' : 'ltr',
    // The tag carries the attempt number, so every rung of the escalation
    // ladder is a genuinely NEW notification.
    //
    // Reusing one tag per occurrence seems tidier, but Android treats a repeat
    // of an existing tag as an in-place update: no banner, no sound, nothing.
    // Ignore rung 1 and leave it in the drawer, and rungs 2..9 would silently
    // overwrite it -- the ladder would look like it was escalating while
    // actually going quiet. Stacking is prevented by closing the previous one
    // explicitly below instead.
    tag: data.occurrence_id
      ? `occ-${data.occurrence_id}-${data.tally || 0}`
      : `nudnik-${Date.now()}`,
    renotify: true,
    requireInteraction: true,
    silent: false,
    timestamp: Date.now(),
    vibrate: tier >= 2 ? [300, 120, 300, 120, 300] : [200, 100, 200],
    actions,
    data,
  };

  event.waitUntil(
    (async () => {
      // Retire the previous rung for this same occurrence, so exactly one
      // notification per reminder is on screen without relying on tag-replace
      // (which would suppress the alert).
      // Close is done explicitly rather than by reusing a tag, because a
      // repeated tag is an in-place update that Android never alerts for.
      const prefix = data.occurrence_id ? `occ-${data.occurrence_id}-` : 'nudnik-';
      try {
        const open = await self.registration.getNotifications();
        open
          .filter((n) => (n.tag || '').startsWith(prefix))
          .forEach((n) => n.close());
      } catch (err) { /* not fatal */ }

      // showNotification rejects on some Android/Chrome combinations if any
      // option is unsupported -- and a rejection displays nothing, which looks
      // identical to the push never arriving. Degrade instead of vanishing.
      // Keep the taskbar/dock badge current even when no window is open.
      try {
        if (self.navigator && self.navigator.setAppBadge) {
          const res = await fetch('/api/dashboard', { cache: 'no-store' });
          if (res.ok) {
            const d = await res.json();
            const n = (d.overdue || []).length;
            if (n > 0) await self.navigator.setAppBadge(n);
            else if (self.navigator.clearAppBadge) await self.navigator.clearAppBadge();
          }
        }
      } catch (err) { /* badge is a nicety, never block the notification */ }

      try {
        await self.registration.showNotification(data.title || 'Nudnik', options);
      } catch (err) {
        try {
          await self.registration.showNotification(data.title || 'Nudnik', {
            body: data.body || '',
            icon: '/static/icons/icon-192.png',
            tag: options.tag,
            data,
          });
        } catch (err2) {
          await self.registration.showNotification(data.title || 'Nudnik');
        }
      }
    })()
  );
});

/* Swiping without acting is not an answer. Re-post shortly after, unless the
 * loop was closed in the meantime. */
self.addEventListener('notificationclose', (event) => {
  const data = event.notification.data || {};
  if (!data.occurrence_id) return;
  if (data.norepost) return;

  event.waitUntil(
    (async () => {
      await new Promise((resolve) => setTimeout(resolve, 25000));
      try {
        const res = await fetch(`/api/occurrences/${data.occurrence_id}`, {
          cache: 'no-store',
        });
        if (!res.ok) return;
        const occ = await res.json();
        if (['done', 'skipped', 'snoozed', 'missed'].includes(occ.status)) return;

        const lang = data.lang === 'en' ? 'en' : 'he';
        const L = LABELS[lang];
        const stillOpen = lang === 'he' ? 'עדיין לא סגרת את זה' : 'You still have not closed this';
        await self.registration.showNotification(data.title || 'Nudnik', {
          body: `${stillOpen}\n${data.body || ''}`,
          icon: '/static/icons/icon-192.png',
          badge: '/static/icons/badge.png',
          lang,
          dir: lang === 'he' ? 'rtl' : 'ltr',
          tag: `occ-${data.occurrence_id}-repost-${Date.now()}`,
          renotify: true,
          requireInteraction: true,
          vibrate: [400, 150, 400],
          actions: [
            { action: 'done', title: L.done },
            { action: 'snooze', title: L.snooze },
          ],
          // Do not loop forever; one reprise is a nudge, ten is malware.
          data: { ...data, norepost: true },
        });
      } catch (err) {
        /* offline: the escalation ladder will come back around anyway */
      }
    })()
  );
});

self.addEventListener('notificationclick', (event) => {
  const data = event.notification.data || {};
  const action = event.action;
  event.notification.close();

  if (action === 'call' && data.phone) {
    event.waitUntil(self.clients.openWindow(`tel:${data.phone}`));
    return;
  }

  if (action === 'done' && data.occurrence_id) {
    event.waitUntil(
      fetch(`/api/occurrences/${data.occurrence_id}/done`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      })
        .then(() => notifyClients({ type: 'occurrence-changed', id: data.occurrence_id }))
        .catch(() =>
          self.registration.showNotification('⚠️', {
            body: data.lang === 'en' ? 'Could not save. Open the app.' : 'לא הצלחתי לשמור. פתח את האפליקציה.',
            icon: '/static/icons/icon-192.png',
            data: { norepost: true },
          })
        )
    );
    return;
  }

  if (action === 'snooze' && data.occurrence_id) {
    event.waitUntil(
      fetch(`/api/occurrences/${data.occurrence_id}/snooze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ minutes: 60 }),
      })
        .then(() => notifyClients({ type: 'occurrence-changed', id: data.occurrence_id }))
        .catch(() => undefined)
    );
    return;
  }

  const target = data.occurrence_id ? `/#/occurrence/${data.occurrence_id}` : '/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((list) => {
      for (const client of list) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          client.navigate(target);
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    })
  );
});

async function notifyClients(message) {
  const list = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
  list.forEach((client) => client.postMessage(message));
}

self.addEventListener('message', (event) => {
  if (event.data === 'skip-waiting') self.skipWaiting();
});
