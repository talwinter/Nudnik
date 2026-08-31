/* Nudnik app controller.
 *
 * Hash routing, one delegated click handler, and the sheets. State is kept
 * deliberately small: views re-fetch rather than trying to stay in sync.
 */
(function () {
  'use strict';

  const t = (k, v) => I18n.t(k, v);
  const esc = Views.esc;
  const $ = (sel) => document.querySelector(sel);

  const NAV = [
    { id: 'now', ico: '◎', label: 'nav_now', hint: 'nav_now_hint', tab: true },
    { id: 'timeline', ico: '▤', label: 'nav_timeline', hint: 'nav_timeline_hint', tab: true },
    { id: 'reminders', ico: '☰', label: 'nav_reminders', hint: 'nav_reminders_hint', tab: true },
    { id: 'insights', ico: '◔', label: 'nav_insights', hint: 'nav_insights_hint', tab: true },
    { id: 'channels', ico: '⇄', label: 'nav_channels', tab: false },
    { id: 'activity', ico: '⋯', label: 'nav_activity', tab: false },
    { id: 'settings', ico: '⚙', label: 'nav_settings', tab: true },
  ];

  const state = {
    view: 'now',
    param: null,
    counts: { overdue: 0 },
    presets: null,
    settings: null,
    filters: { search: '', include_inactive: false },
    deferredInstall: null,
  };

  /* Ambient, always-visible count of open loops.
   *
   * On an installed desktop PWA this paints a number on the taskbar/dock icon
   * and in the window title. Unlike a notification it cannot be missed,
   * throttled, or covered by another app -- it simply sits there while
   * something is unclosed, which is exactly the behaviour this app is for. */
  function setAmbientCount(n) {
    const base = I18n.t('app_name');
    document.title = n > 0 ? `(${n}) ${base}` : base;
    try {
      if (n > 0 && navigator.setAppBadge) navigator.setAppBadge(n);
      else if (navigator.clearAppBadge) navigator.clearAppBadge();
    } catch (err) { /* unsupported browser; the title still updates */ }
  }

  /* ------------------------------------------------------------- toasts */

  function toast(message, tone) {
    const el = document.createElement('div');
    el.className = 'toast ' + (tone || '');
    el.textContent = message;
    $('#toasts').appendChild(el);
    setTimeout(() => el.remove(), 3200);
  }

  API.setErrorHandler((err) => toast(err.message || t('error'), 'bad'));

  /* ------------------------------------------------------------- sheets */

  // A sheet holding a form is not dismissible by clicking away from it. Only
  // an explicit X, Cancel or Save closes it. Lightweight pickers (snooze) stay
  // dismissible, because there is nothing there to lose.
  let sheetDismissible = false;
  let draftKey = null;

  function openSheet(html, opts) {
    // Default to non-dismissible: most sheets here hold a form.
    sheetDismissible = !!(opts && opts.dismissible);
    const sheet = $('#sheet');
    sheet.innerHTML = '<div class="sheet-grip"></div>' + html;
    sheet.hidden = false;
    $('#backdrop').hidden = false;
    document.body.style.overflow = 'hidden';
    draftKey = null;
    sheet.addEventListener('input', markDirty);
    sheet.addEventListener('change', markDirty);
    // Typing is not the only way to fill a form. Choosing an intensity, adding
    // a stage or picking a template are all clicks that fire neither input nor
    // change -- without this, a form built entirely by clicking still counts as
    // untouched and a stray tap discards it.
    sheet.addEventListener('click', (e) => {
      const el = e.target.closest('button, input, select, textarea, .chip-toggle');
      if (!el) return;
      const act = el.dataset ? el.dataset.act : null;
      if (act === 'close-sheet' || act === 'discard-sheet') return;
      markDirty();
    });
    const focusable = sheet.querySelector('input,select,textarea,button');
    if (focusable && window.innerWidth > 760) focusable.focus();
  }

  function markDirty() {
    saveDraft();
  }

  /* `discard: true` throws the saved draft away -- that is Cancel and Save.
     A plain close (the ✕) keeps it, so a mis-tap costs nothing: reopening the
     editor offers the work straight back. */
  function closeSheet(opts) {
    const discard = !!(opts && opts.discard);
    if (discard) clearDraft();
    else draftKey = null;
    $('#sheet').hidden = true;
    $('#backdrop').hidden = true;
    document.body.style.overflow = '';
  }

  $('#backdrop').addEventListener('click', () => {
    if (sheetDismissible) { closeSheet({ discard: true }); return; }
    // Silence here would read as a broken tap, so say which controls do close.
    toast(t('close_with_button'));
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || $('#sheet').hidden) return;
    if (sheetDismissible) closeSheet({ discard: true });
    else toast(t('close_with_button'));
  });

  /* A second safety net. Confirmation covers accidental taps, but a phone can
     kill a backgrounded page with no close event at all -- so the form is also
     mirrored to localStorage and offered back next time. */
  /* Reads the editor into the same shape the submit handler builds, so a
     restored draft is identical to what would have been saved -- including
     stage rows, which have no ids and would be lost by a DOM scrape. */
  function collectEditor() {
    if (!$('#editorForm')) return null;
    const stages = [];
    $('#fStages').querySelectorAll('.stage-row').forEach((row) => {
      stages.push({
        offset: stageOffsetMinutes(row),
        label: row.querySelector('.stage-label').value,
        main: !row.querySelector('.stage-days'),
        intensity: stageIntensity(row),
        at_time: stageTime(row),
      });
    });
    const val = (id) => { const el = $('#' + id); return el ? el.value : ''; };
    const chk = (id) => { const el = $('#' + id); return el ? el.checked : false; };
    const on = $('#fIntensity') && $('#fIntensity').querySelector('.on');
    return {
      title: val('fTitle'), when: val('fWhen'), notes: val('fNotes'),
      category: val('fCategory'), priority: val('fPriority'),
      repeat: val('fRepeat'), interval: val('fInterval'), phone: val('fPhone'),
      anchorDone: chk('fAnchorDone'), confirm: chk('fConfirm'), buddy: chk('fBuddy'),
      intensity: on ? on.dataset.val : null,
      stages,
    };
  }

  function applyEditor(d) {
    const set = (id, v) => { const el = $('#' + id); if (el && v !== undefined) el.value = v; };
    const tick = (id, v) => { const el = $('#' + id); if (el) el.checked = !!v; };
    set('fTitle', d.title); set('fWhen', d.when); set('fNotes', d.notes);
    set('fCategory', d.category); set('fPriority', d.priority);
    set('fRepeat', d.repeat); set('fInterval', d.interval); set('fPhone', d.phone);
    tick('fAnchorDone', d.anchorDone); tick('fConfirm', d.confirm); tick('fBuddy', d.buddy);

    if (d.intensity && $('#fIntensity')) {
      $('#fIntensity').querySelectorAll('button').forEach((b) => {
        b.classList.toggle('on', b.dataset.val === d.intensity);
      });
    }

    if (Array.isArray(d.stages) && d.stages.length) {
      const host = $('#fStages');
      host.innerHTML = d.stages.map((st, i) => stageRow({
        offset_minutes: st.main ? 0 : (st.offset || 0),
        label: st.label,
        intensity: st.intensity || undefined,
        at_time: st.at_time || '',
        kind: st.main ? 'main' : ((st.offset || 0) < 0 ? 'prep' : 'followup'),
      }, i)).join('');
    }
  }

  function saveDraft() {
    if (!draftKey) return;
    try {
      const data = collectEditor();
      if (!data || !data.title) return;   // nothing worth keeping yet
      localStorage.setItem(draftKey, JSON.stringify({ at: Date.now(), data }));
    } catch (err) { /* private mode, or storage full */ }
  }

  function clearDraft() {
    try { if (draftKey) localStorage.removeItem(draftKey); } catch (err) { /* */ }
    draftKey = null;
  }

  function restoreDraft() {
    if (!draftKey) return false;
    try {
      const raw = localStorage.getItem(draftKey);
      if (!raw) return false;
      const { at, data } = JSON.parse(raw);
      // A week-old draft is noise, not a rescue.
      if (!at || Date.now() - at > 7 * 24 * 3600 * 1000) { clearDraft(); return false; }
      if (!data || !data.title) return false;
      applyEditor(data);
      return true;
    } catch (err) {
      return false;
    }
  }

  /* ---------------------------------------------------------- navigation */

  function renderNav() {
    $('#railNav').innerHTML = NAV.map((n) => `
      <button class="nav-item ${state.view === n.id ? 'active' : ''}" data-act="go" data-view="${n.id}"
              title="${n.hint ? esc(t(n.hint)) : ''}">
        <span class="nav-ico" aria-hidden="true">${n.ico}</span>
        <span>${esc(t(n.label))}</span>
        ${n.id === 'now' && state.counts.overdue
          ? `<span class="nav-count hot">${state.counts.overdue}</span>` : ''}
      </button>`).join('');

    $('#tabbar').innerHTML = NAV.filter((n) => n.tab).map((n) => `
      <button class="${state.view === n.id ? 'active' : ''}" data-act="go" data-view="${n.id}">
        <span class="tab-ico" aria-hidden="true">${n.ico}</span>
        <span>${esc(t(n.label))}</span>
        ${n.id === 'now' && state.counts.overdue
          ? `<span class="tab-badge">${state.counts.overdue}</span>` : ''}
      </button>`).join('');

    const current = NAV.find((n) => n.id === state.view);
    $('#viewTitle').textContent = current ? t(current.label) : t('app_name');
  }

  function go(view, param) {
    const hash = '#/' + view + (param ? '/' + param : '');
    if (location.hash !== hash) { location.hash = hash; return; }
    render();
  }

  function readHash() {
    const parts = (location.hash || '#/now').replace(/^#\/?/, '').split('/');
    let view = parts[0] || 'now';
    let param = parts[1] || null;
    if (view === 'occurrence') { state.view = 'occurrence'; state.param = param; return; }
    if (view === 'add') { state.view = 'now'; state.param = null; setTimeout(quickAddSheet, 60); return; }
    if (view === 'open') view = 'now';
    if (!NAV.some((n) => n.id === view) && view !== 'reminder') view = 'now';
    state.view = view;
    state.param = param;
  }

  window.addEventListener('hashchange', () => { readHash(); render(); });

  /* ------------------------------------------------------------ rendering */

  async function render() {
    renderNav();
    const view = $('#view');
    view.innerHTML = `<p class="muted">${esc(t('loading'))}</p>`;
    $('#rail').classList.remove('open');

    try {
      switch (state.view) {
        case 'now': {
          const data = await API.dashboard();
          state.counts.overdue = data.overdue.length;
          setAmbientCount(data.overdue.length);
          view.innerHTML = Views.now(data);
          renderNav();
          break;
        }
        case 'timeline': {
          const items = await API.occurrences({ status: 'all', days: 120, limit: 300 });
          const open = items.filter((o) => !['done', 'skipped', 'missed'].includes(o.status));
          view.innerHTML = Views.timeline(open);
          break;
        }
        case 'reminders': {
          const list = await API.reminders(state.filters);
          view.innerHTML = Views.reminders(list, state.filters);
          bindReminderFilters();
          break;
        }
        case 'reminder': {
          const rem = await API.reminder(state.param);
          $('#viewTitle').textContent = rem.title;
          view.innerHTML = Views.reminderDetail(rem);
          break;
        }
        case 'occurrence': {
          const occ = await API.occurrence(state.param);
          $('#viewTitle').textContent = occ.stage_label || occ.title;
          view.innerHTML = Views.occurrenceDetail(occ);
          break;
        }
        case 'insights': {
          view.innerHTML = Views.insights(await API.analytics(90));
          break;
        }
        case 'channels': {
          view.innerHTML = Views.channelsView(await API.channels());
          break;
        }
        case 'activity': {
          view.innerHTML = Views.activity(await API.events(120));
          break;
        }
        case 'settings': {
          state.settings = await API.settings();
          view.innerHTML = settingsView(state.settings);
          bindSettings();
          break;
        }
        default:
          view.innerHTML = Views.emptyState('404', '', '?');
      }
    } catch (err) {
      view.innerHTML = Views.emptyState(t('error'), err.message || '', '⚠');
    }
  }

  function bindReminderFilters() {
    const search = $('#remSearch');
    if (search) {
      let timer;
      search.addEventListener('input', () => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          state.filters.search = search.value.trim();
          render();
        }, 320);
      });
    }
    const inactive = $('#showInactive');
    if (inactive) {
      inactive.addEventListener('change', () => {
        state.filters.include_inactive = inactive.checked;
        render();
      });
    }
  }

  /* ------------------------------------------------------------ snoozing */

  const SNOOZE_OPTIONS = [
    { key: 'snooze_10m', minutes: 10 },
    { key: 'snooze_1h', minutes: 60 },
    { key: 'snooze_3h', minutes: 180 },
    { key: 'snooze_evening', preset: 'evening' },
    { key: 'snooze_tomorrow', preset: 'tomorrow' },
    { key: 'snooze_weekend', preset: 'weekend' },
    { key: 'snooze_next_week', preset: 'next_week' },
  ];

  function snoozeSheet(id) {
    openSheet(`
      <div class="sheet-head"><h2>${esc(t('snooze_title'))}</h2>
        <button class="icon-btn" data-act="close-sheet">✕</button></div>
      <div class="chip-row" style="gap:9px">
        ${SNOOZE_OPTIONS.map((o) => `
          <button class="btn" style="flex:1 1 44%" data-act="do-snooze" data-id="${id}"
            ${o.minutes ? `data-minutes="${o.minutes}"` : `data-preset="${o.preset}"`}>
            ${esc(t(o.key))}
          </button>`).join('')}
      </div>
      <p class="hint" style="margin-top:15px">${esc(t('snooze_warning'))}</p>`,
      { dismissible: true });
  }

  /* ---------------------------------------------------------- quick add */

  async function quickAddSheet() {
    if (!state.presets) state.presets = await API.presets();

    openSheet(`
      <div class="sheet-head"><h2>${esc(t('quick_add'))}</h2>
        <button class="icon-btn" data-act="close-sheet">✕</button></div>

      <div class="field">
        <label for="qaText">${esc(t('title_label'))}</label>
        <input type="text" id="qaText" placeholder="${esc(t('quick_add_ph'))}" autocomplete="off">
        <div class="hint">${esc(t('quick_add_hint'))}</div>
      </div>

      <div id="qaPreview" class="hint mono" style="min-height:20px;color:var(--violet)"></div>

      <div class="field" style="margin-top:13px">
        <label for="qaWhen">${esc(t('qa_when'))}</label>
        <input type="datetime-local" id="qaWhen">
        <div class="hint">${esc(t('qa_when_hint'))}</div>
      </div>

      <div class="field" style="margin-top:15px">
        <label>${esc(t('pick_template'))}</label>
        <div class="hint" style="margin:0 0 9px">${esc(t('template_hint'))}</div>
        <div class="chip-row" id="qaPresets">
          ${state.presets.presets.map((p) => `
            <button type="button" class="chip-toggle" data-preset="${esc(p.key)}"
              title="${esc(p.description)}">${esc(p.emoji)} ${esc(p.name)}</button>`).join('')}
        </div>
      </div>

      <div class="row" style="margin-top:18px">
        <button class="btn btn-primary" data-act="qa-save">${esc(t('save'))}</button>
        <button class="btn" data-act="full-editor">${esc(t('details'))}…</button>
      </div>`);

    const input = $('#qaText');
    const preview = $('#qaPreview');
    let timer;

    input.addEventListener('input', () => {
      clearTimeout(timer);
      const text = input.value.trim();
      if (text.length < 3) { preview.textContent = ''; return; }
      timer = setTimeout(async () => {
        try {
          const parsed = await API.quickAdd(text, null, true);
          preview.textContent = parsed.title
            ? `→ ${parsed.title} · ${I18n.fmtDateTime(parsed.anchor_at)}`
            : '';
          // Only prefill an untouched field: never overwrite a date the user
          // typed in themselves.
          const when = $('#qaWhen');
          if (when && !when.value && parsed.anchor_local) {
            when.value = parsed.anchor_local.slice(0, 16);
          }
        } catch (e) { preview.textContent = ''; }
      }, 380);
    });

    $('#qaPresets').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-preset]');
      if (!btn) return;
      const on = btn.classList.contains('on');
      $('#qaPresets').querySelectorAll('.chip-toggle').forEach((b) => b.classList.remove('on'));
      if (!on) btn.classList.add('on');
    });
  }

  /* -------------------------------------------------------- full editor */

  /* A stage row reads as a phrase: "[14] [days before] [do this]".
     Direction is a choice, not a minus sign -- nobody thinks of an errand as
     happening at "negative seven days". */
  function stageRow(stage, index) {
    const offset = stage.offset_minutes || 0;
    const isMain = offset === 0;
    const days = Math.abs(Math.round(offset / 1440));
    const after = offset > 0;

    const intensitySelect = `
      <select class="stage-intensity" aria-label="${esc(t('intensity_label'))}">
        <option value="">${esc(t('stage_inherit'))}</option>
        ${['gentle', 'normal', 'relentless'].map((k) => `
          <option value="${k}" ${stage.intensity === k ? 'selected' : ''}>${esc(t('intensity_' + k))}</option>
        `).join('')}
      </select>`;

    if (isMain) {
      return `<div class="stage-row is-main" data-stage="${index}">
        <span class="stage-anchor stage-anchor-main">◆ ${esc(t('at_event'))}</span>
        <span></span>
        <input type="text" class="stage-label" value="${esc(stage.label || '')}"
               placeholder="${esc(t('title_ph'))}">
        ${intensitySelect}
      </div>`;
    }

    return `<div class="stage-row" data-stage="${index}">
      <input type="number" class="stage-days" min="0" step="1" value="${days}"
             aria-label="${esc(t('days_before'))}">
      <select class="stage-dir" aria-label="${esc(t('days_before'))}">
        <option value="before" ${after ? '' : 'selected'}>${esc(t('dir_before'))}</option>
        <option value="after" ${after ? 'selected' : ''}>${esc(t('dir_after'))}</option>
      </select>
      <input type="time" class="stage-time" value="${esc(stage.at_time || '')}"
             aria-label="${esc(t('stage_time_hint'))}">
      <button type="button" class="icon-btn" data-act="rm-stage" data-index="${index}"
              style="width:38px;height:38px">✕</button>
      <input type="text" class="stage-label" value="${esc(stage.label || '')}"
             placeholder="${esc(t('stage_label_ph'))}">
      ${intensitySelect}
    </div>`;
  }

  function stageTime(row) {
    const el = row.querySelector('.stage-time');
    return el && el.value ? el.value : null;
  }

  function stageIntensity(row) {
    const el = row.querySelector('.stage-intensity');
    return el && el.value ? el.value : null;
  }

  /* Signed offset in minutes for one row. The sign lives here and nowhere in
     the UI. */
  function stageOffsetMinutes(row) {
    const daysInput = row.querySelector('.stage-days');
    if (!daysInput) return 0;                       // the main stage
    const days = Math.abs(parseInt(daysInput.value || '0', 10));
    const dir = row.querySelector('.stage-dir');
    const after = dir && dir.value === 'after';
    return (after ? days : -days) * 1440;
  }

  async function editorSheet(reminder) {
    if (!state.presets) state.presets = await API.presets();
    const rem = reminder || {
      title: '', notes: '', category: 'general', emoji: '', priority: 'normal',
      anchor_at: null, repeat_kind: 'none', repeat_interval: 1,
      anchor_to_completion: false, stages: [{ offset_minutes: 0, label: '', kind: 'main' }],
      intensity: 'relentless', channels: [], contact_phone: '', contact_url: '',
      require_confirmation: false, escalate_to_buddy: false, active: true,
    };

    // datetime-local wants local wall time, the API speaks UTC.
    let localValue = '';
    if (rem.anchor_at) {
      const d = I18n.toDate(rem.anchor_at);
      const pad = (n) => String(n).padStart(2, '0');
      localValue = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    openSheet(`
      <div class="sheet-head">
        <h2>${esc(rem.id ? t('edit_reminder') : t('new_reminder'))}</h2>
        <button class="icon-btn" data-act="close-sheet">✕</button>
      </div>
      <form id="editorForm" data-id="${rem.id || ''}">

        <div class="field">
          <label for="fTitle">${esc(t('title_label'))}</label>
          <input type="text" id="fTitle" value="${esc(rem.title)}" placeholder="${esc(t('title_ph'))}" required>
        </div>

        <div class="row">
          <div class="field">
            <label for="fWhen">${esc(t('when_label'))}</label>
            <input type="datetime-local" id="fWhen" value="${localValue}" required>
            <div class="hint">${esc(t('when_hint'))}</div>
          </div>
          <div class="field">
            <label for="fEmoji">${esc(t('category_label'))}</label>
            <select id="fCategory">
              ${state.presets.categories.map((c) => `
                <option value="${esc(c.key)}" ${rem.category === c.key ? 'selected' : ''}>
                  ${esc(c.emoji)} ${esc(c[I18n.getLang()] || c.en)}
                </option>`).join('')}
            </select>
          </div>
        </div>

        <div class="field">
          <label>${esc(t('intensity_label'))}</label>
          <div class="seg" id="fIntensity">
            ${['gentle', 'normal', 'relentless'].map((k) => `
              <button type="button" data-val="${k}" class="${rem.intensity === k ? 'on' : ''}">
                ${esc(t('intensity_' + k))}
              </button>`).join('')}
          </div>
          <div class="hint" id="intensityHint">${esc(t('intensity_' + rem.intensity + '_hint'))}</div>
        </div>

        <div class="field">
          <label>${esc(t('stages_label'))}</label>
          <div class="hint" style="margin:0 0 9px">${esc(t('stages_hint'))}</div>
          <div class="hint" style="margin:0 0 9px">${esc(t('stage_intensity_hint'))}</div>
          <div class="hint" style="margin:0 0 9px">${esc(t('stage_time_hint'))}</div>
          <div class="stages" id="fStages">
            ${(rem.stages || []).map(stageRow).join('')}
          </div>
          <button type="button" class="ghost-btn" data-act="add-stage" style="margin-top:9px">
            ${esc(t('add_stage'))}
          </button>
        </div>

        <div class="field">
          <label>${esc(t('repeat_label'))}</label>
          <!-- Reads as one sentence: "every [8] [weeks]" -- the two halves are
               meaningless apart, and split labels made 'every 8 weeks' look
               impossible. -->
          <div class="row" style="align-items:center;gap:8px">
            <span style="flex:0 0 auto;color:var(--muted)">${esc(t('every_n'))}</span>
            <input type="number" id="fInterval" min="1" max="99"
                   style="flex:0 0 84px" value="${rem.repeat_interval || 1}">
            <select id="fRepeat" style="flex:1 1 130px">
              ${['none', 'daily', 'weekly', 'monthly', 'yearly'].map((k) => `
                <option value="${k}" ${rem.repeat_kind === k ? 'selected' : ''}>${
                  esc(k === 'none' ? t('repeat_none') : t('unit_' + {
                    daily: 'days', weekly: 'weeks', monthly: 'months', yearly: 'years',
                  }[k]))}</option>
              `).join('')}
            </select>
          </div>
          <div class="hint">${esc(t('repeat_hint_weeks'))}</div>
          <div class="hint mono" id="repeatPreview" style="color:var(--violet)"></div>
        </div>

        <label class="switch">
          <input type="checkbox" id="fAnchorDone" ${rem.anchor_to_completion ? 'checked' : ''}>
          <span class="switch-text">${esc(t('anchor_completion'))}
            <small>${esc(t('anchor_completion_hint'))}</small></span>
        </label>

        <div class="field" style="margin-top:15px">
          <label for="fPhone">${esc(t('contact_label'))}</label>
          <input type="tel" id="fPhone" value="${esc(rem.contact_phone || '')}" inputmode="tel"
                 placeholder="03-1234567">
          <div class="hint">${esc(t('contact_hint'))}</div>
        </div>

        <div class="field">
          <label for="fNotes">${esc(t('notes_label'))}</label>
          <textarea id="fNotes" placeholder="${esc(t('notes_ph'))}">${esc(rem.notes || '')}</textarea>
        </div>

        <div class="field">
          <label for="fPriority">${esc(t('priority_label'))}</label>
          <select id="fPriority">
            ${['low', 'normal', 'high', 'critical'].map((k) => `
              <option value="${k}" ${rem.priority === k ? 'selected' : ''}>${esc(t('prio_' + k))}</option>
            `).join('')}
          </select>
          <div class="hint">${esc(t('prio_critical_hint'))}</div>
        </div>

        <label class="switch">
          <input type="checkbox" id="fConfirm" ${rem.require_confirmation ? 'checked' : ''}>
          <span class="switch-text">${esc(t('confirm_label'))}</span>
        </label>
        <label class="switch">
          <input type="checkbox" id="fBuddy" ${rem.escalate_to_buddy ? 'checked' : ''}>
          <span class="switch-text">${esc(t('buddy_label'))}</span>
        </label>

        <div class="row" style="margin-top:20px">
          <button type="submit" class="btn btn-primary">${esc(t('save'))}</button>
          <button type="button" class="btn" data-act="discard-sheet">${esc(t('cancel'))}</button>
        </div>
      </form>`);

    const form = $('#editorForm');

    // Set after openSheet, which clears it -- the draft belongs to the editor.
    draftKey = 'nudnik_draft_' + (rem.id || 'new');

    // Offer back anything left from a session that ended without a close.
    if (restoreDraft()) toast(t('draft_restored'), 'ok');

    /* Live preview of the next few dates.
     *
     * "every 8 weeks" and "every 2 months" look interchangeable in a dropdown
     * and are not: 56 days versus 59-62. Showing the actual dates removes the
     * guesswork entirely.
     */
    function updateRepeatPreview() {
      const out = $('#repeatPreview');
      if (!out) return;
      const kind = $('#fRepeat').value;
      const n = Math.max(1, parseInt($('#fInterval').value || '1', 10));
      const startRaw = $('#fWhen').value;
      if (!startRaw || kind === 'none') { out.textContent = ''; return; }

      const start = new Date(startRaw);
      if (isNaN(start)) { out.textContent = ''; return; }

      const dates = [];
      for (let i = 0; i < 4; i += 1) {
        const d = new Date(start);
        if (kind === 'daily') d.setDate(d.getDate() + n * i);
        else if (kind === 'weekly') d.setDate(d.getDate() + n * 7 * i);
        else if (kind === 'yearly') d.setFullYear(d.getFullYear() + n * i);
        else if (kind === 'monthly') {
          // Clamp like the server does: 31 Jan + 1 month is 28/29 Feb, not 3 Mar.
          const day = start.getDate();
          d.setDate(1);
          d.setMonth(d.getMonth() + n * i);
          const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
          d.setDate(Math.min(day, last));
        }
        dates.push(d);
      }

      const fmt = (d) => d.toLocaleDateString(I18n.locale(), {
        day: '2-digit', month: '2-digit', year: '2-digit',
      });
      const gap = Math.round((dates[1] - dates[0]) / 86400000);
      out.textContent =
        t('next_dates') + ': ' + dates.map(fmt).join('  ·  ') +
        '   (' + gap + ' ' + t('unit_days') + ')';
    }

    ['fRepeat', 'fInterval', 'fWhen'].forEach((id) => {
      const el = $('#' + id);
      if (el) el.addEventListener('change', updateRepeatPreview);
      if (el) el.addEventListener('input', updateRepeatPreview);
    });
    updateRepeatPreview();

    $('#fIntensity').addEventListener('click', (e) => {
      const btn = e.target.closest('[data-val]');
      if (!btn) return;
      $('#fIntensity').querySelectorAll('button').forEach((b) => b.classList.remove('on'));
      btn.classList.add('on');
      $('#intensityHint').textContent = t('intensity_' + btn.dataset.val + '_hint');
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const stages = [];
      $('#fStages').querySelectorAll('.stage-row').forEach((row) => {
        const offset = stageOffsetMinutes(row);
        const stage = {
          offset_minutes: offset,
          label: row.querySelector('.stage-label').value.trim(),
          kind: offset === 0 ? 'main' : (offset < 0 ? 'prep' : 'followup'),
        };
        const si = stageIntensity(row);
        if (si) stage.intensity = si;
        const st = stageTime(row);
        if (st) stage.at_time = st;
        stages.push(stage);
      });

      const payload = {
        title: $('#fTitle').value.trim(),
        notes: $('#fNotes').value.trim() || null,
        category: $('#fCategory').value,
        priority: $('#fPriority').value,
        anchor_at: new Date($('#fWhen').value).toISOString(),
        repeat_kind: $('#fRepeat').value,
        repeat_interval: parseInt($('#fInterval').value || '1', 10),
        anchor_to_completion: $('#fAnchorDone').checked,
        stages,
        intensity: $('#fIntensity').querySelector('.on').dataset.val,
        contact_phone: $('#fPhone').value.trim() || null,
        require_confirmation: $('#fConfirm').checked,
        escalate_to_buddy: $('#fBuddy').checked,
      };

      try {
        if (form.dataset.id) await API.updateReminder(form.dataset.id, payload);
        else await API.createReminder(payload);
        closeSheet({ discard: true });
        toast(t('saved'), 'ok');
        render();
      } catch (err) { /* handler already toasted */ }
    });
  }

  /* ------------------------------------------------------------ settings */

  function settingsView(s) {
    const origin = location.origin;
    // Filled in asynchronously by revealFeedUrls(); the token is deliberately
    // not part of the masked settings payload.
    const icsUrl = '';
    const hookUrl = `${origin}/hooks/telegram/…`;

    const authBanner = s.auth_enabled
      ? `<div class="banner" style="border-color:rgba(95,211,168,.4)">
           <div class="banner-mark">🔒</div>
           <div class="banner-body">
             <strong>${esc(t('auth_on'))}</strong>
             <a class="btn btn-sm" href="/logout" style="margin-top:9px">${esc(t('logout'))}</a>
           </div>
         </div>`
      : `<div class="banner hot">
           <div class="banner-mark">🔓</div>
           <div class="banner-body">
             <strong>${esc(t('auth_off_title'))}</strong>
             <p>${esc(t('auth_off_body'))}</p>
           </div>
         </div>`;

    return `
    ${authBanner}
    <section class="section">
      <div class="section-head"><h2>${esc(t('set_general'))}</h2></div>
      <div class="card">
        <div class="row">
          <div class="field">
            <label for="sLang">${esc(t('lang_label'))}</label>
            <select id="sLang" data-key="lang">
              <option value="he" ${s.lang === 'he' ? 'selected' : ''}>עברית</option>
              <option value="en" ${s.lang === 'en' ? 'selected' : ''}>English</option>
            </select>
          </div>
          <div class="field">
            <label for="sTz">${esc(t('tz_label'))}</label>
            <input type="text" id="sTz" data-key="timezone" value="${esc(s.timezone || '')}">
          </div>
        </div>
        <div class="field">
          <label for="sUrl">${esc(t('public_url_label'))}</label>
          <input type="url" id="sUrl" data-key="public_url" value="${esc(s.public_url || '')}">
          <div class="hint">${esc(t('public_url_hint'))}</div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head">
        <h2>${esc(t('enable_push'))}</h2>
        <span class="chip ${(s.channels_ready || {}).push ? 'chip-done' : 'chip-missed'}">
          ${esc((s.channels_ready || {}).push ? t('ch_ready') : t('ch_not_ready'))}</span>
        <span class="spacer"></span>
        <button class="ghost-btn" data-act="test-ch" data-ch="push">${esc(t('test'))}</button>
      </div>
      <div class="card">
        <div class="hint" style="margin-bottom:11px">${esc(t('push_is_a_channel'))}</div>
        <div id="pushStatus" class="hint" style="margin-bottom:11px"></div>
        <div class="row">
          <button class="btn btn-primary" id="pushBtn">${esc(t('enable_push'))}</button>
          <button class="btn" data-act="local-test">${esc(t('local_test'))}</button>
          <button class="btn" data-act="diagnose">${esc(t('diagnose'))}</button>
          <button class="btn" id="installBtn" hidden>${esc(t('install_app'))}</button>
        </div>
        <div class="hint" style="margin-top:9px">${esc(t('local_test_hint'))}</div>
        <pre id="diagOut" class="hint mono" style="white-space:pre-wrap;margin-top:9px"></pre>
        <div class="hint" style="margin-top:11px">${esc(t('install_hint'))}</div>
        <div class="hint" style="margin-top:13px">${esc(t('devices'))}:
          <span class="mono">${s.push_device_count || 0}</span></div>
        <div id="deviceList" style="margin-top:6px"></div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>${esc(t('set_quiet'))}</h2></div>
      <div class="card">
        <div class="hint" style="margin-bottom:12px">${esc(t('set_quiet_hint'))}</div>
        <label class="switch">
          <input type="checkbox" data-key="quiet_hours_enabled" ${s.quiet_hours_enabled ? 'checked' : ''}>
          <span class="switch-text">${esc(t('set_quiet'))}</span>
        </label>
        <div class="row">
          <div class="field"><label>${esc(I18n.getLang() === 'he' ? 'מ' : 'From')}</label>
            <input type="time" data-key="quiet_start" value="${esc(s.quiet_start || '23:00')}"></div>
          <div class="field"><label>${esc(I18n.getLang() === 'he' ? 'עד' : 'Until')}</label>
            <input type="time" data-key="quiet_end" value="${esc(s.quiet_end || '07:30')}"></div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>${esc(t('set_brief'))}</h2></div>
      <div class="card">
        <div class="hint" style="margin-bottom:12px">${esc(t('set_brief_hint'))}</div>
        <label class="switch">
          <input type="checkbox" data-key="brief_enabled" ${s.brief_enabled ? 'checked' : ''}>
          <span class="switch-text">${esc(t('set_brief'))}</span>
        </label>
        <div class="field" style="max-width:180px">
          <input type="time" data-key="brief_time" value="${esc(s.brief_time || '08:30')}">
        </div>
        <button class="btn btn-sm" data-act="send-brief">${esc(t('send_brief_now'))}</button>
      </div>
    </section>

    ${channelSection('ntfy', s, [
      ['ntfy_url', 'URL', 'text'], ['ntfy_topic', 'Topic', 'text'], ['ntfy_token', 'Token', 'password'],
    ])}
    ${channelSection('telegram', s, [
      ['telegram_token', 'Bot token', 'password'], ['telegram_chat_id', 'Chat ID', 'text'],
    ], t('telegram_hook_hint'))}
    ${channelSection('email', s, [
      ['smtp_host', 'SMTP host', 'text'], ['smtp_port', 'Port', 'number'],
      ['smtp_user', 'User', 'text'], ['smtp_pass', 'Password', 'password'],
      ['email_to', 'Send to', 'text'],
    ])}
    ${channelSection('gotify', s, [['gotify_url', 'URL', 'text'], ['gotify_token', 'Token', 'password']])}
    ${channelSection('matrix', s, [
      ['matrix_homeserver', 'Homeserver', 'text'], ['matrix_token', 'Access token', 'password'],
      ['matrix_room', 'Room ID', 'text'],
    ])}
    ${channelSection('webhook', s, [
      ['webhook_url', 'URL', 'text'],
      ['webhook_template', 'Body template (JSON, optional)', 'text'],
    ],
      I18n.getLang() === 'he'
        ? 'עובד ישירות עם Discord, Slack, Home Assistant, n8n — הגוף כולל גם content וגם text.'
        : 'Works directly with Discord, Slack, Home Assistant, n8n — the body carries both content and text.')}

    <section class="section">
      <div class="section-head">
        <h2>${esc(t('call_assist'))}</h2>
        <span class="chip ${s.callassist_enabled && s.callassist_url ? 'chip-done' : 'chip-missed'}">
          ${esc(s.callassist_enabled && s.callassist_url ? t('ch_ready') : t('ch_not_ready'))}</span>
      </div>
      <div class="card">
        <div class="hint" style="margin-bottom:12px">${esc(t('call_assist_hint'))}</div>
        <label class="switch">
          <input type="checkbox" data-key="callassist_enabled" ${s.callassist_enabled ? 'checked' : ''}>
          <span class="switch-text">${esc(I18n.getLang() === 'he' ? 'פעיל' : 'Enabled')}</span>
        </label>
        <div class="row">
          <div class="field"><label>Provider URL</label>
            <input type="text" data-key="callassist_url" value="${esc(s.callassist_url || '')}"
                   placeholder="https://api.bland.ai/v1/calls"></div>
          <div class="field"><label>Token</label>
            <input type="password" data-key="callassist_token" value="${esc(s.callassist_token || '')}"></div>
          <div class="field"><label>${esc(t('call_assist_my_number'))}</label>
            <input type="tel" data-key="callassist_my_number" value="${esc(s.callassist_my_number || '')}"
                   placeholder="+9725..."></div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>${esc(t('set_buddy'))}</h2></div>
      <div class="card">
        <div class="hint" style="margin-bottom:12px">${esc(t('set_buddy_hint'))}</div>
        <label class="switch">
          <input type="checkbox" data-key="buddy_enabled" ${s.buddy_enabled ? 'checked' : ''}>
          <span class="switch-text">${esc(t('set_buddy'))}</span>
        </label>
        <div class="row">
          <div class="field"><label>${esc(I18n.getLang() === 'he' ? 'שם' : 'Name')}</label>
            <input type="text" data-key="buddy_name" value="${esc(s.buddy_name || '')}"></div>
          <div class="field"><label>Telegram chat ID</label>
            <input type="text" data-key="buddy_telegram_chat_id" value="${esc(s.buddy_telegram_chat_id || '')}"></div>
          <div class="field"><label>Email</label>
            <input type="text" data-key="buddy_email" value="${esc(s.buddy_email || '')}"></div>
        </div>
        <div class="field" style="max-width:220px">
          <label>${esc(I18n.getLang() === 'he' ? 'אחרי כמה תזכורות' : 'After how many reminders')}</label>
          <input type="number" min="2" max="50" data-key="buddy_after_attempts" value="${s.buddy_after_attempts || 8}">
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>${esc(t('set_integrations'))}</h2></div>
      <div class="card">
        <div class="field">
          <label>${esc(t('calendar_feed'))}</label>
          <div class="hint" style="margin-bottom:8px">${esc(t('calendar_feed_hint'))}</div>
          <div class="copy-row">
            <input type="text" id="icsUrl" readonly value="${esc(icsUrl)}">
            <button class="btn btn-sm" data-act="copy" data-target="icsUrl">${esc(t('copy'))}</button>
          </div>
        </div>
        <div class="field">
          <label>${esc(t('api_key_label'))}</label>
          <div class="hint" style="margin-bottom:8px">${esc(t('api_key_hint'))}</div>
          <div class="copy-row">
            <input type="text" id="apiKey" readonly value="${esc(s.api_key || '')}">
            <button class="btn btn-sm" data-act="reveal-key">${esc(t('details'))}</button>
          </div>
        </div>
        <div class="field">
          <label>Telegram webhook</label>
          <div class="hint" style="margin-bottom:8px">${esc(t('telegram_hook_hint'))}</div>
          <div class="copy-row">
            <input type="text" id="hookUrl" readonly value="${esc(hookUrl)}" class="mono">
            <button class="btn btn-sm" data-act="copy" data-target="hookUrl">${esc(t('copy'))}</button>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="section-head"><h2>${esc(t('set_danger'))}</h2></div>
      <div class="card">
        <div class="row">
          <button class="btn" data-act="export">${esc(t('export_data'))}</button>
          <button class="btn" data-act="import">${esc(t('import_data'))}</button>
          <button class="btn" data-act="run-tick">${esc(t('run_engine_now'))}</button>
          <button class="btn" data-act="force-refresh">${esc(t('force_refresh'))}</button>
        </div>
        <div class="hint" style="margin-top:11px">${esc(t('force_refresh_hint'))}</div>
        <div class="hint mono" style="margin-top:13px">
          ${esc(JSON.stringify(s.scheduler && s.scheduler.jobs ? { running: s.scheduler.running, tick: s.scheduler.tick_seconds } : {}))}
        </div>
      </div>
    </section>`;
  }

  function channelSection(name, s, fields, hint) {
    const enabledKey = name + '_enabled';
    const ready = (s.channels_ready || {})[name];
    return `<section class="section">
      <div class="section-head">
        <h2>${esc(t('ch_' + name) !== 'ch_' + name ? t('ch_' + name) : name)}</h2>
        <span class="chip ${ready ? 'chip-done' : 'chip-missed'}">
          ${esc(ready ? t('ch_ready') : t('ch_not_ready'))}</span>
        <span class="spacer"></span>
        <button class="ghost-btn" data-act="test-ch" data-ch="${name}">${esc(t('test'))}</button>
      </div>
      <div class="card">
        ${hint ? `<div class="hint" style="margin-bottom:12px">${esc(hint)}</div>` : ''}
        <label class="switch">
          <input type="checkbox" data-key="${enabledKey}" ${s[enabledKey] ? 'checked' : ''}>
          <span class="switch-text">${esc(I18n.getLang() === 'he' ? 'פעיל' : 'Enabled')}</span>
        </label>
        <div class="row">
          ${fields.map(([key, label, type]) => `
            <div class="field">
              <label>${esc(label)}</label>
              <input type="${type}" data-key="${key}" value="${esc(s[key] === null || s[key] === undefined ? '' : s[key])}"
                     autocomplete="off">
            </div>`).join('')}
        </div>
      </div>
    </section>`;
  }

  function bindSettings() {
    let timer;
    const collect = () => {
      const values = {};
      document.querySelectorAll('[data-key]').forEach((el) => {
        const key = el.dataset.key;
        if (el.type === 'checkbox') values[key] = el.checked;
        else if (el.type === 'number') values[key] = parseInt(el.value || '0', 10);
        else values[key] = el.value;
      });
      return values;
    };

    document.querySelectorAll('[data-key]').forEach((el) => {
      el.addEventListener('change', () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
          const values = collect();
          await API.saveSettings(values);
          toast(t('saved'), 'ok');
          if (values.lang && values.lang !== I18n.getLang()) {
            I18n.setLang(values.lang);
            render();
          }
        }, 260);
      });
    });

    refreshPushUI();
    renderDevices();
    revealFeedUrls();
    const pushBtn = $('#pushBtn');
    if (pushBtn) pushBtn.addEventListener('click', enablePush);

    const installBtn = $('#installBtn');
    if (installBtn && state.deferredInstall) {
      installBtn.hidden = false;
      installBtn.addEventListener('click', async () => {
        state.deferredInstall.prompt();
        await state.deferredInstall.userChoice;
        state.deferredInstall = null;
        installBtn.hidden = true;
      });
    }
  }

  /* Feed URLs carry secrets, so they are fetched separately rather than
     riding along in the settings payload. */
  async function revealFeedUrls() {
    const ics = $('#icsUrl');
    if (!ics) return;
    try {
      const [icsTok, apiKey] = await Promise.all([
        API.reveal('ics_token'),
        API.reveal('api_key'),
      ]);
      ics.value = `${location.origin}/api/calendar.ics?token=${encodeURIComponent(icsTok.value)}`;
      const hook = $('#hookUrl');
      if (hook) hook.value = `${location.origin}/hooks/telegram/${apiKey.value}`;
      state.apiKey = apiKey.value;
    } catch (err) { /* leave the placeholders */ }
  }

  /* ---------------------------------------------------------- web push */

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
  }

  async function thisDeviceSubscribed() {
    try {
      if (!('serviceWorker' in navigator) || !window.isSecureContext) return false;
      const reg = await navigator.serviceWorker.getRegistration();
      if (!reg) return false;
      return !!(await reg.pushManager.getSubscription());
    } catch (err) {
      return false;
    }
  }

  async function currentEndpointTail() {
    try {
      const reg = await navigator.serviceWorker.getRegistration();
      const sub = reg && (await reg.pushManager.getSubscription());
      return sub ? sub.endpoint.slice(-16) : null;
    } catch (err) {
      return null;
    }
  }

  /* The registered-device list, with THIS device marked. When push "works"
     but nothing arrives, this is the screen that tells you why. */
  async function renderDevices() {
    const host = $('#deviceList');
    if (!host) return;
    try {
      const [devices, tail] = await Promise.all([API.devices(), currentEndpointTail()]);
      if (!devices.length) {
        host.innerHTML = `<p class="hint" style="color:var(--rose)">${esc(t('no_devices'))}</p>`;
        return;
      }
      host.innerHTML = devices.map((d) => {
        const isThis = tail && d.endpoint_tail === tail;
        return `<div class="log-line ${isThis ? 'ok' : ''}">
          <span class="log-ch">${isThis ? '★' : '•'}</span>
          <span class="log-detail">
            ${isThis ? `<strong>${esc(t('this_device'))}</strong> · ` : ''}
            ${esc((d.user_agent || '').slice(0, 48) || d.endpoint_host)}
          </span>
          <button class="ghost-btn" data-act="del-device" data-id="${d.id}"
            style="margin-inline-start:auto">${esc(t('remove_device'))}</button>
        </div>`;
      }).join('');
      if (tail && !devices.some((d) => d.endpoint_tail === tail)) {
        host.innerHTML += `<p class="hint" style="color:var(--rose);margin-top:9px">${
          esc(t('this_device_not_subscribed'))}</p>`;
      }
    } catch (err) { /* offline */ }
  }

  async function refreshPushUI() {
    const el = $('#pushStatus');
    if (!el) return;

    if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
      el.textContent = t('push_needs_https');
      return;
    }
    if (!window.isSecureContext) { el.textContent = t('push_needs_https'); return; }
    if (Notification.permission === 'denied') { el.textContent = t('push_blocked'); return; }

    const reg = await navigator.serviceWorker.getRegistration();
    const sub = reg && (await reg.pushManager.getSubscription());
    el.textContent = sub ? '✅ ' + t('push_on') : t('install_hint');
  }

  async function enablePush() {
    try {
      if (!window.isSecureContext) { toast(t('push_needs_https'), 'bad'); return; }
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') { toast(t('push_blocked'), 'bad'); return; }

      const { publicKey } = await API.pushKey();
      if (!publicKey) { toast('VAPID', 'bad'); return; }

      // navigator.serviceWorker.ready never rejects -- if registration failed
      // it simply hangs forever, which looks exactly like "the button does
      // nothing". Race it so the failure is reported instead of swallowed.
      const reg = await Promise.race([
        navigator.serviceWorker.ready,
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('service worker not ready')), 8000)
        ),
      ]);
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(publicKey),
        });
      }
      await API.subscribe(sub, navigator.userAgent.slice(0, 60));
      toast(t('push_on'), 'ok');
      refreshPushUI();
      renderDevices();
    } catch (err) {
      toast(err.message || t('error'), 'bad');
    }
  }

  /* ------------------------------------------------- delegated actions */

  document.addEventListener('click', async (e) => {
    const el = e.target.closest('[data-act]');
    if (!el) return;
    const act = el.dataset.act;
    const id = el.dataset.id;

    switch (act) {
      case 'go':
        e.preventDefault();
        go(el.dataset.view);
        break;

      // The X keeps the draft, so a mis-tap loses nothing.
      case 'close-sheet': closeSheet(); break;
      // Cancel is an explicit decision to throw the work away.
      case 'discard-sheet': closeSheet({ discard: true }); break;

      case 'done':
        await API.done(id);
        toast(t('saved'), 'ok');
        render();
        break;

      case 'skip':
        await API.skip(id);
        render();
        break;

      case 'snooze': snoozeSheet(id); break;

      case 'do-snooze': {
        const opts = el.dataset.minutes
          ? { minutes: parseInt(el.dataset.minutes, 10) }
          : { preset: el.dataset.preset };
        await API.snooze(id, opts);
        closeSheet({ discard: true });
        toast(t('saved'), 'ok');
        render();
        break;
      }

      case 'reopen': await API.reopen(id); render(); break;

      case 'call-assist': {
        el.disabled = true;
        try {
          await API.callAssist(id);
          toast(t('call_placed'), 'ok');
        } finally { el.disabled = false; }
        break;
      }
      case 'detail': go('occurrence', id); break;
      case 'view-rem': go('reminder', id); break;

      case 'edit-rem': {
        const rem = await API.reminder(id);
        editorSheet(rem);
        break;
      }

      case 'del-rem':
        if (confirm(t('confirm_delete'))) {
          await API.deleteReminder(id);
          toast(t('deleted'), 'ok');
          render();
        }
        break;

      case 'nudge':
        await API.nudge(id);
        toast(t('saved'), 'ok');
        render();
        break;

      case 'add-stage': {
        const container = $('#fStages');
        const index = container.children.length;
        container.insertAdjacentHTML('beforeend',
          stageRow({ offset_minutes: -7 * 1440, label: '', kind: 'prep' }, index));
        // Keep the event itself last, so the list reads in chronological order.
        const mainRow = container.querySelector('.stage-row.is-main');
        if (mainRow) container.appendChild(mainRow);
        break;
      }

      case 'rm-stage':
        el.closest('.stage-row').remove();
        break;

      case 'qa-save': {
        const text = $('#qaText').value.trim();
        if (!text) return;
        const chosen = $('#qaPresets').querySelector('.chip-toggle.on');
        const when = $('#qaWhen').value;
        await API.quickAdd(
          text,
          chosen ? chosen.dataset.preset : null,
          false,
          when ? new Date(when).toISOString() : null
        );
        closeSheet({ discard: true });
        toast(t('saved'), 'ok');
        render();
        break;
      }

      case 'full-editor': closeSheet(); editorSheet(null); break;

      case 'test-ch': {
        // Push is sent to every registered device, so a "success" here can
        // easily mean "your other computer got it". Check this device first,
        // or the result is actively misleading.
        if (el.dataset.ch === 'push' && !(await thisDeviceSubscribed())) {
          toast(t('this_device_not_subscribed'), 'bad');
          break;
        }
        el.disabled = true;
        const res = await API.testChannel(el.dataset.ch);
        el.disabled = false;
        // Report what actually happened, not a generic "saved".
        toast(res.detail || (res.ok ? t('saved') : t('error')), res.ok ? 'ok' : 'bad');
        break;
      }

      /* Fires a notification from the device itself, skipping the server and
         the push service entirely. This splits one confusing symptom into two
         separate answers: if nothing appears here, the problem is Android
         (permissions, DND, per-app notification settings). If this appears but
         a pushed one does not, the problem is the push pipeline. */
      case 'local-test': {
        try {
          if (Notification.permission !== 'granted') {
            const p = await Notification.requestPermission();
            if (p !== 'granted') { toast(t('push_blocked'), 'bad'); break; }
          }
          const reg = await navigator.serviceWorker.getRegistration();
          if (!reg) { toast('no service worker', 'bad'); break; }
          await reg.showNotification(t('test_local_title') || 'נודניק', {
            body: t('local_test_sent'),
            icon: '/static/icons/icon-192.png',
            badge: '/static/icons/badge.png',
            // Unique per tap: a repeated tag is treated as an in-place
            // update by Android and would not alert the second time.
            tag: 'nudnik-local-test-' + Date.now(),
            renotify: true,
            data: { norepost: true },
          });
          // Ask the registration whether the notification actually exists.
          // This is the decisive check: if it is listed here but you cannot
          // see it, the OS accepted the call and then suppressed the display,
          // which no amount of app-side code can fix.
          await new Promise((r) => setTimeout(r, 400));
          const shown = (await reg.getNotifications()).filter((n) =>
            (n.tag || '').startsWith('nudnik-local-test')
          );
          const out = $('#diagOut');
          if (out) {
            out.textContent =
              'showNotification  resolved' + String.fromCharCode(10) +
              'registration has  ' + shown.length + ' notification(s)' +
              String.fromCharCode(10) +
              (shown.length
                ? '=> Delivered. If you only see it in the notification drawer and'
                  + String.fromCharCode(10)
                  + '   not as a pop-up banner, that is Android importance:'
                  + String.fromCharCode(10)
                  + '   enable Floating notifications for this app.'
                : '=> The notification was dropped before display.');
          }
          toast(t('local_test_sent'), 'ok');
        } catch (err) {
          toast(String(err && err.message ? err.message : err), 'bad');
        }
        break;
      }

      case 'diagnose': {
        const out = $('#diagOut');
        const reg = ('serviceWorker' in navigator)
          ? await navigator.serviceWorker.getRegistration() : null;
        let sub = null;
        try { sub = reg && (await reg.pushManager.getSubscription()); } catch (e) { /* */ }
        const lines = [
          `permission      ${typeof Notification !== 'undefined' ? Notification.permission : 'n/a'}`,
          `secure context  ${window.isSecureContext}`,
          `standalone      ${window.matchMedia('(display-mode: standalone)').matches}`,
          `sw registered   ${!!reg}`,
          `sw controlling  ${!!navigator.serviceWorker.controller}`,
          `sw state        ${reg && reg.active ? reg.active.state : 'none'}`,
          `subscribed      ${!!sub}`,
          `max actions     ${typeof Notification !== 'undefined' ? (Notification.maxActions || '?') : 'n/a'}`,
          `origin          ${location.origin}`,
        ];
        out.textContent = lines.join(String.fromCharCode(10));
        break;
      }

      case 'del-device': {
        await API.deleteDevice(id);
        render();
        break;
      }

      case 'send-brief':
        await API.sendBrief();
        toast(t('saved'), 'ok');
        break;

      case 'run-tick': {
        const res = await fetch('/api/tick?key=' + encodeURIComponent(state.apiKey || ''), {
          method: 'POST',
        });
        toast(res.ok ? t('saved') : t('error'), res.ok ? 'ok' : 'bad');
        render();
        break;
      }

      case 'force-refresh': {
        // The in-app escape hatch, so a stuck version never means digging
        // through browser settings. Scoped to this app's cache and worker
        // only: reminders live on the server and the push subscription is
        // untouched.
        toast(t('refreshing'), 'ok');
        try {
          if ('serviceWorker' in navigator) {
            const regs = await navigator.serviceWorker.getRegistrations();
            await Promise.all(regs.map((r) => r.unregister()));
          }
          if (window.caches) {
            const keys = await caches.keys();
            await Promise.all(keys.map((k) => caches.delete(k)));
          }
        } catch (err) { /* clear whatever we can, then reload regardless */ }
        // Cache-busting query so even the HTTP cache cannot serve the old shell.
        location.replace(location.pathname + '?r=' + Date.now() + location.hash);
        break;
      }

      case 'copy': {
        const input = document.getElementById(el.dataset.target);
        input.select();
        try {
          await navigator.clipboard.writeText(input.value);
          toast(t('copied'), 'ok');
        } catch (err) { document.execCommand('copy'); }
        break;
      }

      case 'reveal-key': {
        const res = await API.reveal('api_key');
        $('#apiKey').value = res.value || '';
        el.textContent = t('copy');
        el.dataset.act = 'copy';
        el.dataset.target = 'apiKey';
        break;
      }

      case 'export': {
        const data = await API.exportAll();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `nudnik-${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
        break;
      }

      case 'import': {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'application/json';
        input.onchange = async () => {
          const file = input.files[0];
          if (!file) return;
          const data = JSON.parse(await file.text());
          const res = await API.importAll(data);
          toast(`${t('saved')} (${res.created})`, 'ok');
          render();
        };
        input.click();
        break;
      }

      default: break;
    }
  });

  /* ------------------------------------------------------------- chrome */

  $('#addBtn').addEventListener('click', quickAddSheet);
  $('#refreshBtn').addEventListener('click', render);
  $('#menuBtn').addEventListener('click', () => $('#rail').classList.toggle('open'));

  $('#langToggle').addEventListener('click', () => {
    const next = I18n.getLang() === 'he' ? 'en' : 'he';
    I18n.setLang(next);
    $('#langToggle').textContent = next === 'he' ? 'EN' : 'עב';
    document.querySelectorAll('[data-t]').forEach((el) => {
      el.textContent = t(el.dataset.t);
    });
    render();
  });

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    state.deferredInstall = e;
    const btn = $('#installBtn');
    if (btn) btn.hidden = false;
  });

  /* Service worker registration, with a self-healing update path.
   *
   * A PWA that silently runs last week's code is the single most common way
   * these apps go wrong, so the update is automatic rather than something you
   * have to know to force. sw.js carries a server-injected version, so any
   * front-end change makes it new bytes; the browser then installs the new
   * worker, it claims the page, and controllerchange fires -- at which point we
   * reload exactly once to pick up the new assets.
   */
  if ('serviceWorker' in navigator) {
    let reloading = false;
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      if (reloading) return;      // guard against a reload loop
      reloading = true;
      location.reload();
    });

    navigator.serviceWorker
      .register('/sw.js')
      .then((reg) => {
        reg.update().catch(() => undefined);
        // Check again whenever the app is brought back to the foreground; a
        // phone PWA can sit open for days without ever reloading.
        document.addEventListener('visibilitychange', () => {
          if (!document.hidden) reg.update().catch(() => undefined);
        });
      })
      .catch(() => { /* plain http during development */ });

    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data && event.data.type === 'occurrence-changed') render();
    });
  }

  // Show the running build in the rail footer, so "is my update live?" is a
  // question you can answer by looking rather than by guessing.
  API.get_version = () => fetch('/api/version').then((r) => r.json());
  API.get_version()
    .then(({ version }) => {
      const el = $('#railStatus');
      if (el) el.textContent = 'build ' + version;
    })
    .catch(() => undefined);

  // Coming back to a phone that has been in a pocket for hours should show
  // current state, not a stale snapshot.
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) render();
  });

  setInterval(() => { if (!document.hidden && state.view === 'now') render(); }, 60000);

  $('#langToggle').textContent = I18n.getLang() === 'he' ? 'EN' : 'עב';
  document.querySelectorAll('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });

  // Feature flags are read once at boot; loop cards consult them to decide
  // whether the call-assist action is worth offering.
  API.health()
    .then((h) => { Views.features = h.features || {}; render(); })
    .catch(() => { /* offline: cards simply omit the optional action */ });

  readHash();
  render();
})();
