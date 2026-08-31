/* Thin fetch wrapper.
 *
 * Every call funnels through one place so offline handling and error toasts
 * behave identically everywhere.
 */
(function (global) {
  'use strict';

  let onError = null;

  async function request(path, options) {
    const opts = Object.assign({ headers: {} }, options || {});
    if (opts.body && typeof opts.body !== 'string') {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(opts.body);
    }
    const res = await fetch('/api' + path, opts);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch (e) { /* non-JSON error body */ }
      const err = new Error(detail);
      err.status = res.status;
      if (onError) onError(err);
      throw err;
    }
    if (res.status === 204) return null;
    const type = res.headers.get('content-type') || '';
    return type.includes('json') ? res.json() : res.text();
  }

  const get = (p) => request(p);
  const post = (p, body) => request(p, { method: 'POST', body: body || {} });
  const patch = (p, body) => request(p, { method: 'PATCH', body });
  const del = (p) => request(p, { method: 'DELETE' });

  global.API = {
    setErrorHandler(fn) { onError = fn; },

    dashboard: () => get('/dashboard'),
    health: () => get('/health'),

    reminders: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return get('/reminders' + (q ? '?' + q : ''));
    },
    reminder: (id) => get('/reminders/' + id),
    createReminder: (data) => post('/reminders', data),
    updateReminder: (id, data) => patch('/reminders/' + id, data),
    deleteReminder: (id) => del('/reminders/' + id),
    duplicateReminder: (id) => post('/reminders/' + id + '/duplicate'),

    occurrences: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return get('/occurrences' + (q ? '?' + q : ''));
    },
    occurrence: (id) => get('/occurrences/' + id),
    done: (id, answer) => post('/occurrences/' + id + '/done', { answer: answer || null }),
    skip: (id) => post('/occurrences/' + id + '/skip'),
    snooze: (id, opts) => post('/occurrences/' + id + '/snooze', opts),
    reopen: (id) => post('/occurrences/' + id + '/reopen'),
    nudge: (id) => post('/occurrences/' + id + '/nudge'),
    callAssist: (id) => post('/occurrences/' + id + '/call-assist'),

    quickAdd: (text, preset, dryRun, anchorAt) =>
      post('/quick-add', {
        text,
        preset: preset || null,
        dry_run: !!dryRun,
        anchor_at: anchorAt || null,
      }),

    presets: () => get('/presets'),
    analytics: (days) => get('/analytics?days=' + (days || 90)),
    events: (limit) => get('/events?limit=' + (limit || 100)),
    logs: (params) => {
      const q = new URLSearchParams(params || {}).toString();
      return get('/logs' + (q ? '?' + q : ''));
    },

    settings: () => get('/settings'),
    reveal: (key) => get('/settings/reveal?key=' + encodeURIComponent(key)),
    saveSettings: (values) => patch('/settings', { values }),
    channels: () => get('/channels'),
    testChannel: (channel) => post('/channels/test', { channel }),

    pushKey: () => get('/push/key'),
    subscribe: (sub, label) =>
      post('/push/subscribe', {
        endpoint: sub.endpoint,
        keys: sub.toJSON ? sub.toJSON().keys : sub.keys,
        label: label || null,
      }),
    unsubscribe: (endpoint) => post('/push/unsubscribe', { endpoint }),
    devices: () => get('/push/devices'),
    deleteDevice: (id) => del('/push/devices/' + id),

    briefPreview: () => get('/brief/preview'),
    sendBrief: () => post('/brief/send'),

    exportAll: () => get('/export'),
    importAll: (data) => post('/import', data),
  };
})(window);
