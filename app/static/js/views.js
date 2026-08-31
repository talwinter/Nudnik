/* View rendering.
 *
 * Plain template literals, no framework. Every view is a pure function from
 * data to HTML; all interaction is delegated from one listener in app.js, so
 * re-rendering never leaks handlers.
 */
(function (global) {
  'use strict';

  const t = (k, v) => I18n.t(k, v);

  function esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function minutesFromNow(iso) {
    return (I18n.toDate(iso).getTime() - Date.now()) / 60000;
  }

  /* The signature element: `attempts` drawn as tally marks. Five strokes to a
     group, the fifth struck through, exactly like counting on a wall. */
  function tally(count) {
    if (!count || count < 1) return '';
    const shown = Math.min(count, 15);
    let marks = '';
    for (let i = 1; i <= shown; i += 1) {
      marks += `<i class="${i % 5 === 0 ? 'fifth' : ''}"></i>`;
    }
    const label = count === 1 ? t('asked_1') : t('asked_n', { n: count });
    return `<span class="tally" title="${esc(label)}" aria-label="${esc(label)}">${marks}</span>
      <span class="tally-label">${count > 15 ? count : ''}</span>`;
  }

  function statusChip(occ) {
    if (occ.status === 'done') return `<span class="chip chip-done">✓ ${t('done')}</span>`;
    if (occ.status === 'skipped') return `<span class="chip chip-missed">${t('skip')}</span>`;
    if (occ.status === 'missed') return `<span class="chip chip-missed">${t('overdue')}</span>`;
    if (occ.status === 'snoozed') {
      return `<span class="chip chip-snoozed">⏰ ${t('snoozed_to', { t: I18n.fmtDateTime(occ.snooze_until) })}</span>`;
    }
    if (occ.is_overdue) return `<span class="chip chip-overdue">${t('overdue')}</span>`;
    return '';
  }

  function stageChip(occ) {
    if (!occ.stage_label || occ.stage_kind === 'main') return '';
    const cls = occ.stage_kind === 'followup' ? 'chip-followup' : 'chip-prep';
    return `<span class="chip ${cls}">${occ.stage_kind === 'followup' ? '↷' : '↱'}</span>`;
  }

  function loopClass(occ) {
    if (occ.status === 'done' || occ.status === 'skipped') return 'is-done';
    if (occ.status === 'snoozed') return 'is-snoozed';
    if (occ.is_overdue) return 'is-overdue';
    if (minutesFromNow(occ.due_at) < 1440) return 'is-today';
    return 'is-scheduled';
  }

  function whenText(occ) {
    const mins = minutesFromNow(occ.due_at);
    if (occ.status === 'done') return I18n.fmtDateTime(occ.done_at);
    if (mins < 0) return t('open_for', { t: I18n.humanDuration(mins) });
    if (mins < 1440) return t('due_in', { t: I18n.humanDuration(mins) });
    return I18n.fmtDateTime(occ.due_at);
  }

  /* One open loop. The card carries the whole decision: what it is, how long
     it has been asking, and every way to close it. */
  function loopCard(occ, opts) {
    const o = opts || {};
    const closed = occ.status === 'done' || occ.status === 'skipped' || occ.status === 'missed';
    const title = occ.stage_label || occ.title;
    const showParent = occ.stage_label && occ.stage_label !== occ.title;

    let actions = '';
    if (!closed) {
      actions = `
        <div class="loop-actions">
          <button class="btn btn-sm btn-done" data-act="done" data-id="${occ.id}">✓ ${t('done')}</button>
          <button class="btn btn-sm" data-act="snooze" data-id="${occ.id}">⏰ ${t('snooze')}</button>
          ${occ.contact_phone ? `<a class="btn btn-sm" href="tel:${esc(occ.contact_phone)}">📞 ${t('call')}</a>` : ''}
          ${occ.contact_phone && global.Views.features.call_assist
            ? `<button class="btn btn-sm" data-act="call-assist" data-id="${occ.id}">☎︎ ${t('call_for_me')}</button>` : ''}
          ${occ.contact_url ? `<a class="btn btn-sm" href="${esc(occ.contact_url)}" target="_blank" rel="noopener">🔗</a>` : ''}
          <button class="btn btn-sm" data-act="detail" data-id="${occ.id}">${t('details')}</button>
        </div>`;
    } else if (o.allowReopen) {
      actions = `<div class="loop-actions">
        <button class="btn btn-sm" data-act="reopen" data-id="${occ.id}">${t('reopen')}</button>
      </div>`;
    }

    return `
      <article class="loop ${loopClass(occ)}" data-occ="${occ.id}">
        <div class="loop-top">
          <div class="loop-emoji">${esc(occ.emoji) || '•'}</div>
          <div class="loop-body">
            <div class="loop-title">${esc(title)}</div>
            ${showParent ? `<div class="loop-parent">${esc(occ.title)}</div>` : ''}
            <div class="loop-meta">
              <span class="loop-when">${esc(whenText(occ))}</span>
              ${stageChip(occ)}
              ${statusChip(occ)}
              ${!closed && occ.attempts > 0 ? tally(occ.attempts) : ''}
            </div>
          </div>
        </div>
        ${actions}
      </article>`;
  }

  function statCard(label, value, note, tone) {
    return `<div class="stat ${tone || ''}">
      <div class="stat-label">${esc(label)}</div>
      <div class="stat-value">${esc(value)}</div>
      ${note ? `<div class="stat-note">${esc(note)}</div>` : ''}
    </div>`;
  }

  function emptyState(title, sub, mark) {
    return `<div class="empty">
      <div class="empty-mark">${mark || '○'}</div>
      <strong>${esc(title)}</strong>
      ${sub ? `<span>${esc(sub)}</span>` : ''}
    </div>`;
  }

  /* ---------------------------------------------------------------- now  */

  function now(data) {
    const { overdue, today, upcoming, stats, channels } = data;
    let html = '';

    // If nothing can actually deliver, say so before anything else -- an app
    // that silently cannot notify is worse than no app.
    const anyChannel = Object.values(channels || {}).some(Boolean);
    if (!anyChannel) {
      html += `<div class="banner hot">
        <div class="banner-mark">⚠️</div>
        <div class="banner-body">
          <strong>${esc(t('ch_not_ready'))}</strong>
          <p>${esc(I18n.getLang() === 'he'
            ? 'אף ערוץ התראה לא מוגדר, כך שאף תזכורת לא תגיע אליך בפועל.'
            : 'No notification channel is configured, so no reminder can actually reach you.')}</p>
          <button class="btn btn-sm btn-primary" data-act="go" data-view="settings">${esc(t('nav_settings'))}</button>
        </div>
      </div>`;
    }

    if (overdue.length) {
      const worst = overdue.reduce((a, b) => (b.attempts > a.attempts ? b : a), overdue[0]);
      if (worst.attempts >= 4) {
        html += `<div class="banner warn">
          <div class="banner-mark">👀</div>
          <div class="banner-body">
            <strong>${esc(t('worst_offender'))}</strong>
            <p>${esc(worst.stage_label || worst.title)} — ${esc(t('asked_n', { n: worst.attempts }))}</p>
          </div>
        </div>`;
      }
    }

    html += `<div class="stat-grid">
      ${statCard(t('overdue'), overdue.length, '', overdue.length ? 'hot' : '')}
      ${statCard(t('due_today'), today.length, '', today.length ? 'warn' : '')}
      ${statCard(t('completion_rate'), stats.completion_rate + '%', '', stats.completion_rate >= 70 ? 'good' : '')}
      ${statCard(t('avg_attempts'), stats.avg_attempts_to_close, '', '')}
    </div>`;

    html += `<section class="section">
      <div class="section-head">
        <h2>${esc(t('overdue'))}</h2>
        <span class="section-count">${overdue.length}</span>
      </div>
      ${overdue.length
        ? overdue.map((o) => loopCard(o)).join('')
        : emptyState(t('nothing_open'), t('nothing_open_sub'), '✓')}
    </section>`;

    html += `<section class="section">
      <div class="section-head">
        <h2>${esc(t('due_today'))}</h2>
        <span class="section-count">${today.length}</span>
      </div>
      ${today.length ? today.map((o) => loopCard(o)).join('') : emptyState(t('nothing_today'), '', '·')}
    </section>`;

    if (upcoming.length) {
      html += `<section class="section">
        <div class="section-head">
          <h2>${esc(t('upcoming'))}</h2>
          <span class="section-count">${upcoming.length}</span>
        </div>
        ${upcoming.slice(0, 8).map((o) => loopCard(o)).join('')}
      </section>`;
    }

    return html;
  }

  /* ----------------------------------------------------------- timeline  */

  function timeline(items) {
    if (!items.length) return emptyState(t('nothing_today'), '', '·');

    const groups = new Map();
    items.forEach((occ) => {
      const key = I18n.toDate(occ.due_at).toDateString();
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(occ);
    });

    let html = '<div class="timeline">';
    groups.forEach((list, key) => {
      html += `<div class="tl-day">${esc(I18n.fmtDay(list[0].due_at))}</div>`;
      list.forEach((occ) => {
        const cls = [
          loopClass(occ) === 'is-overdue' ? 'is-overdue' : '',
          occ.status === 'done' ? 'is-done' : '',
          occ.stage_kind === 'main' ? 'is-main' : '',
        ].join(' ');
        html += `<div class="tl-item ${cls}">${loopCard(occ)}</div>`;
      });
    });
    html += '</div>';
    return html;
  }

  /* ---------------------------------------------------------- reminders  */

  function repeatText(rem) {
    if (!rem.repeat_kind || rem.repeat_kind === 'none') return t('repeat_none');
    const unit = t('repeat_' + rem.repeat_kind);
    const base = rem.repeat_interval > 1 ? `${t('every_n')} ${rem.repeat_interval} · ${unit}` : unit;
    return rem.anchor_to_completion ? base + ' ⟳' : base;
  }

  function reminders(list, filters) {
    let html = `<div class="row" style="margin-bottom:16px">
      <input type="text" id="remSearch" placeholder="${esc(t('search'))}" value="${esc(filters.search || '')}">
      <label class="switch" style="flex:0 0 auto">
        <input type="checkbox" id="showInactive" ${filters.include_inactive ? 'checked' : ''}>
        <span class="switch-text">${esc(t('show_inactive'))}</span>
      </label>
    </div>`;

    if (!list.length) {
      return html + emptyState(t('no_reminders'), t('no_reminders_sub'), '＋');
    }

    html += `<div class="table-wrap"><table>
      <thead><tr>
        <th>${esc(t('col_reminder'))}</th>
        <th>${esc(t('col_next'))}</th>
        <th>${esc(t('col_repeat'))}</th>
        <th>${esc(t('col_intensity'))}</th>
        <th>${esc(t('col_open'))}</th>
        <th>${esc(t('col_actions'))}</th>
      </tr></thead><tbody>`;

    list.forEach((rem) => {
      html += `<tr data-rem="${rem.id}">
        <td class="cell-primary">
          <div style="display:flex;gap:9px;align-items:center">
            <span style="font-size:18px">${esc(rem.emoji) || '•'}</span>
            <strong>${esc(rem.title)}</strong>
            ${!rem.active ? `<span class="chip chip-missed">${esc(t('show_inactive'))}</span>` : ''}
          </div>
          ${rem.next_label ? `<div class="loop-parent">↱ ${esc(rem.next_label)}</div>` : ''}
        </td>
        <td class="num" data-label="${esc(t('col_next'))}">${rem.next_due ? esc(I18n.fmtDateTime(rem.next_due)) : '—'}</td>
        <td data-label="${esc(t('col_repeat'))}">${esc(repeatText(rem))}</td>
        <td data-label="${esc(t('col_intensity'))}">
          <span class="chip ${rem.intensity === 'relentless' ? 'chip-overdue' : 'chip-main'}">
            ${esc(t('intensity_' + rem.intensity))}
          </span>
        </td>
        <td class="num" data-label="${esc(t('col_open'))}">
          ${rem.overdue_count ? `<span style="color:var(--rose);font-weight:700">${rem.overdue_count}</span> / ` : ''}${rem.open_count}
        </td>
        <td class="cell-actions" data-label="${esc(t('col_actions'))}">
          <button class="btn btn-sm" data-act="edit-rem" data-id="${rem.id}">${esc(t('edit'))}</button>
          <button class="btn btn-sm" data-act="view-rem" data-id="${rem.id}">${esc(t('details'))}</button>
          <button class="btn btn-sm btn-danger" data-act="del-rem" data-id="${rem.id}">${esc(t('del'))}</button>
        </td>
      </tr>`;
    });

    html += '</tbody></table></div>';
    return html;
  }

  /* ------------------------------------------------- reminder detail  */

  /* The stage chain, grouped by cycle.
   *
   * A recurring reminder with three stages produces a dozen occurrences across
   * the horizon. Listed flat that reads as duplication, and closing one moved
   * it into a separate section where the change was invisible among eleven
   * near-identical cards. Cycles are groups now; a closed stage stays exactly
   * where it was and simply goes quiet. */
  function reminderDetail(rem) {
    const cycles = new Map();
    (rem.occurrences || []).forEach((o) => {
      if (!cycles.has(o.cycle)) cycles.set(o.cycle, []);
      cycles.get(o.cycle).push(o);
    });
    cycles.forEach((list) => list.sort((a, b) => a.due_at.localeCompare(b.due_at)));

    const order = [...cycles.keys()].sort((a, b) => a - b);
    // Open the earliest cycle that still has something outstanding.
    const activeCycle = order.find((c) =>
      cycles.get(c).some((o) => ['active', 'snoozed', 'scheduled'].includes(o.status))
    );

    let html = `<div class="card" style="margin-bottom:20px">
      <div style="display:flex;gap:13px;align-items:flex-start">
        <div style="font-size:30px">${esc(rem.emoji) || '•'}</div>
        <div style="flex:1;min-width:0">
          <h2 style="font-size:23px">${esc(rem.title)}</h2>
          ${rem.notes ? `<p class="muted" style="margin:7px 0 0;font-size:14px;line-height:1.6">${esc(rem.notes)}</p>` : ''}
        </div>
        <button class="btn btn-sm" data-act="edit-rem" data-id="${rem.id}">${esc(t('edit'))}</button>
      </div>
      <dl class="kv" style="margin-top:17px">
        <dt>${esc(t('when_label'))}</dt><dd>${esc(I18n.fmtDateTime(rem.anchor_at))}</dd>
        <dt>${esc(t('col_repeat'))}</dt><dd>${esc(repeatText(rem))}</dd>
        <dt>${esc(t('intensity_label'))}</dt><dd>${esc(t('intensity_' + rem.intensity))}</dd>
        <dt>${esc(t('priority_label'))}</dt><dd>${esc(t('prio_' + rem.priority))}</dd>
        ${rem.contact_phone ? `<dt>${esc(t('contact_label'))}</dt><dd><a href="tel:${esc(rem.contact_phone)}" style="color:var(--jade)">${esc(rem.contact_phone)}</a></dd>` : ''}
      </dl>
    </div>`;

    html += `<div class="section-head">
      <h2>${esc(t('the_chain'))}</h2>
      <span class="section-count">${order.length} × ${(rem.stages || []).length}</span>
    </div>
    <p class="muted" style="font-size:13px;margin:-6px 0 15px;line-height:1.6">${esc(t('chain_hint'))}</p>`;

    order.forEach((cycleNo) => {
      const list = cycles.get(cycleNo);
      const main = list.find((o) => o.stage_kind === 'main') || list[list.length - 1];
      const closed = list.filter((o) => ['done', 'skipped'].includes(o.status)).length;
      const complete = closed === list.length;
      const isActive = cycleNo === activeCycle;

      const label = isActive ? t('cycle_current') : `${t('cycle')} ${cycleNo + 1}`;
      const progress = complete
        ? `<span class="chip chip-done">✓ ${esc(t('cycle_all_done'))}</span>`
        : `<span class="chip">${esc(t('cycle_done_of', { done: closed, total: list.length }))}</span>`;

      html += `<details class="cycle-group"${isActive ? ' open' : ''}>
        <summary class="cycle-summary">
          <span class="cycle-name">${esc(label)}</span>
          <span class="cycle-date mono">${esc(I18n.fmtDate(main.due_at))}</span>
          ${progress}
        </summary>
        <div class="cycle-body">
          ${list.map((o) => loopCard(Object.assign({}, o, {
            title: rem.title, emoji: rem.emoji,
            contact_phone: rem.contact_phone, contact_url: rem.contact_url,
          }), { allowReopen: true })).join('')}
        </div>
      </details>`;
    });

    return html;
  }

  /* ------------------------------------------------ occurrence detail  */

  function occurrenceDetail(occ) {
    let html = loopCard(occ);

    html += `<section class="section" style="margin-top:22px">
      <div class="section-head">
        <h2>${esc(t('delivery_log'))}</h2>
        <span class="section-count">${occ.logs.length}</span>
      </div>
      <p class="muted" style="font-size:13px;margin:-6px 0 13px;line-height:1.6">${esc(t('delivery_log_hint'))}</p>
      <div class="card">`;

    if (!occ.logs.length) {
      html += `<p class="muted" style="margin:0;font-size:14px">${esc(t('no_deliveries'))}</p>`;
    } else {
      occ.logs.forEach((log) => {
        html += `<div class="log-line ${esc(log.status)}">
          <span class="log-time">${esc(I18n.fmtDateTime(log.created_at))}</span>
          <span class="log-ch">${esc(log.channel)}</span>
          <span class="log-detail">${esc(log.detail || log.status)}</span>
        </div>`;
      });
    }
    html += `</div>
      <div class="loop-actions" style="margin-top:13px">
        <button class="btn btn-sm" data-act="nudge" data-id="${occ.id}">${esc(t('nudge_now'))}</button>
        <button class="btn btn-sm" data-act="view-rem" data-id="${occ.reminder_id}">${esc(t('nav_reminders'))}</button>
      </div>
    </section>`;
    return html;
  }

  /* ----------------------------------------------------------- insights */

  function insights(data) {
    const o = data.overview;
    let html = `<div class="stat-grid">
      ${statCard(t('completion_rate'), o.completion_rate + '%', '', o.completion_rate >= 70 ? 'good' : 'warn')}
      ${statCard(t('first_try'), o.first_nudge_success + '%',
        I18n.getLang() === 'he' ? 'ככל שגבוה יותר, כך פחות רדיפה' : 'higher means less chasing',
        o.first_nudge_success >= 50 ? 'good' : '')}
      ${statCard(t('avg_attempts'), o.avg_attempts_to_close, '', o.avg_attempts_to_close > 4 ? 'hot' : '')}
      ${statCard(t('hours_late'), o.avg_hours_late, '', '')}
      ${statCard(t('open_loops'), o.open_now, '', o.overdue_now ? 'hot' : '')}
      ${statCard(t('total_snoozes'), o.total_snoozes, '', '')}
    </div>`;

    // Activity sparkline: real daily counts, not decoration.
    if (data.series && data.series.length) {
      const max = Math.max(1, ...data.series.map((d) => Math.max(d.done, d.missed)));
      html += `<section class="section">
        <div class="section-head"><h2>${esc(t('activity_30d'))}</h2></div>
        <div class="card">
          <div class="spark">
            ${data.series.map((d) => {
              const h = Math.round((Math.max(d.done, d.missed) / max) * 100);
              return `<span class="${d.missed > d.done ? 'miss' : ''}" style="height:${Math.max(3, h)}%"
                title="${esc(d.date)}: ${d.done}✓ ${d.missed}✗"></span>`;
            }).join('')}
          </div>
        </div>
      </section>`;
    }

    html += `<section class="section">
      <div class="section-head"><h2>${esc(t('channel_perf'))}</h2></div>
      <p class="muted" style="font-size:13px;margin:-6px 0 13px;line-height:1.6">${esc(t('channel_perf_hint'))}</p>`;

    if (!data.channels.length) {
      html += emptyState(t('no_deliveries'), '', '·');
    } else {
      html += `<div class="table-wrap"><table><thead><tr>
        <th>${esc(t('col_channel'))}</th><th>${esc(t('col_sent'))}</th>
        <th>${esc(t('col_credited'))}</th><th>${esc(t('col_conversion'))}</th>
      </tr></thead><tbody>`;
      data.channels.forEach((c) => {
        html += `<tr>
          <td data-label="${esc(t('col_channel'))}"><span class="log-ch">${esc(c.channel)}</span></td>
          <td class="num" data-label="${esc(t('col_sent'))}">${c.sent}</td>
          <td class="num" data-label="${esc(t('col_credited'))}">${c.closes_credited}</td>
          <td class="num" data-label="${esc(t('col_conversion'))}"
              style="color:${c.conversion >= 40 ? 'var(--jade)' : 'var(--muted)'}">${c.conversion}%</td>
        </tr>`;
      });
      html += '</tbody></table></div>';
    }
    html += '</section>';

    html += `<section class="section">
      <div class="section-head"><h2>${esc(t('problems'))}</h2></div>
      <p class="muted" style="font-size:13px;margin:-6px 0 13px;line-height:1.6">${esc(t('problems_hint'))}</p>`;

    if (!data.problems.length) {
      html += emptyState(t('no_problems'), '', '✓');
    } else {
      data.problems.forEach((p) => {
        const advice = p.suggestion[I18n.getLang()] || p.suggestion.en;
        html += `<div class="banner warn" style="margin-bottom:11px">
          <div class="banner-mark">${esc(p.emoji) || '⚠️'}</div>
          <div class="banner-body">
            <strong>${esc(p.title)}</strong>
            <p>${esc(advice)}</p>
            <div class="loop-meta" style="margin-top:9px">
              <span class="chip">${esc(t('avg_attempts'))}: ${p.avg_attempts}</span>
              ${p.avg_snoozes ? `<span class="chip">${esc(t('total_snoozes'))}: ${p.avg_snoozes}</span>` : ''}
              ${p.missed ? `<span class="chip chip-overdue">${esc(t('overdue'))}: ${p.missed}</span>` : ''}
            </div>
            <button class="btn btn-sm btn-primary" data-act="edit-rem" data-id="${p.reminder_id}">${esc(t('fix_it'))}</button>
          </div>
        </div>`;
      });
    }
    html += '</section>';
    return html;
  }

  /* ----------------------------------------------------------- channels */

  function channelsView(list) {
    let html = `<p class="muted" style="margin:0 0 17px;font-size:14px;line-height:1.6">${
      esc(I18n.getLang() === 'he'
        ? 'ההסלמה מתרחבת מרמה 0 כלפי מעלה. ככל שלולאה נשארת פתוחה יותר זמן, כך נכנסים לפעולה יותר ערוצים.'
        : 'Escalation widens from level 0 upward. The longer a loop stays open, the more channels join in.')
    }</p><div class="grid-2">`;

    list.forEach((c) => {
      const ok = c.last_7d.ok || 0;
      const failed = c.last_7d.failed || 0;
      html += `<div class="card">
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:11px">
          <strong style="flex:1">${esc(t('ch_' + c.channel) !== 'ch_' + c.channel ? t('ch_' + c.channel) : c.channel)}</strong>
          <span class="chip ${c.ready ? 'chip-done' : 'chip-missed'}">
            ${esc(c.ready ? t('ch_ready') : t('ch_not_ready'))}
          </span>
        </div>
        <div class="loop-meta" style="margin:0 0 12px">
          <span class="chip">${esc(t('tier_label'))} ${c.tiers.length ? Math.min.apply(null, c.tiers) : '—'}</span>
          ${ok ? `<span class="chip chip-done">✓ ${ok}</span>` : ''}
          ${failed ? `<span class="chip chip-overdue">✗ ${failed}</span>` : ''}
        </div>
        <button class="btn btn-sm btn-block" data-act="test-ch" data-ch="${esc(c.channel)}">
          ${esc(t('test'))}
        </button>
      </div>`;
    });
    html += '</div>';
    return html;
  }

  /* ----------------------------------------------------------- activity */

  function activity(events) {
    if (!events.length) return emptyState(t('no_deliveries'), '', '·');
    const ICONS = {
      done: '✅', created: '➕', updated: '✏️', deleted: '🗑️', snoozed: '⏰',
      skipped: '⏭️', missed: '⚠️', brief: '📋', buddy: '🗣️', push: '📱',
      settings: '⚙️', import: '📥',
    };
    return `<div class="card">${events.map((e) => `
      <div class="log-line">
        <span class="log-time">${esc(I18n.fmtDateTime(e.created_at))}</span>
        <span class="log-ch">${ICONS[e.kind] || '•'} ${esc(e.kind)}</span>
        <span class="log-detail">${esc(e.summary || '')}</span>
      </div>`).join('')}</div>`;
  }

  global.Views = {
    features: {},
    esc, tally, loopCard, statCard, emptyState, repeatText, minutesFromNow,
    now, timeline, reminders, reminderDetail, occurrenceDetail,
    insights, channelsView, activity,
  };
})(window);
