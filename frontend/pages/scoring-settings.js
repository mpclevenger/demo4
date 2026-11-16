/* Scoring settings (Tech Risk): tolerance thresholds, caps and rules, with review and change history. */
"use strict";
/* ---------- Scoring settings (owner, 15 Nov 2026) ----------
   Tech Risk changes tolerance thresholds and caps here instead of in config/thresholds.json. Review shows every
   score the changes would move in each open month; Save records who, when, before, after and why (the audit
   trail, table setting_change). A change applies at the next Update. Auditors see the page read only. */
const TH = {state:'idle', data:null, edits:{}, pv:null, err:'', msg:'', busy:false};
function thLoad(force){
  if (!force && (TH.state === 'loading' || TH.state === 'ok')) return;
  TH.state = 'loading';
  api('/api/thresholds').then(j => { TH.data = j; TH.state = 'ok'; })
    .catch(e => { TH.state = 'fail'; TH.err = e.message; }).finally(() => { S.keepScroll = true; render(); });
}
/* Compare (owner, 15 Nov 2026): each measured metric judged by the prevailing median and by its fixed threshold,
   side by side for the selected month, so the two can be compared before a threshold is set. Read only. */
function thCompareLoad(){
  const m = S.p; TH.cmp = TH.cmp || {};
  if (TH.cmp[m]) return;
  TH.cmp[m] = {state:'loading'};
  api('/api/thresholds/compare/' + encodeURIComponent(m)).then(j => { TH.cmp[m] = {state:'ok', data:j}; })
    .catch(e => { TH.cmp[m] = {state:'fail', err:e.message}; }).finally(() => { S.keepScroll = true; render(); });
}
function thCompare(){
  thCompareLoad();
  const c = TH.cmp[S.p], h = `<h2>Compare: ${esc(monthLabel(S.p))}</h2>`;
  if (!c || c.state !== 'ok') return h + `<p class="cap" role="status">${c && c.state === 'fail' ? esc(c.err) : 'Loading…'}</p>`;
  if (!c.data.updated || !c.data.metrics.length) return h + `<p class="muted">${esc(monthLabel(S.p))} has no results to compare yet.</p>`;
  const num = (m, v) => v === null || v === undefined ? '—' : (m.unit === '%' ? Number(v).toFixed(1) + '%' : String(v));
  const judged = (m, j) => j ? `<div>${num(m, j.green)} / ${num(m, j.red)}</div><div style="margin-top:4px">${['Green', 'Amber', 'Red'].map(s => chip(s, String(j.counts[s]))).join(' ')}</div>` : '<span class="muted">None set</span>';
  const row = m => `<tr><td><b>${esc(m.name)}</b>${m.near_top ? '<div class="cap">Nearly every family is at the top</div>' : ''}</td>
    <td>${num(m, m.lowest)} · <b>${num(m, m.middle)}</b> · ${num(m, m.highest)}<div class="cap">${plural(m.families, 'family', 'families')}</div></td>
    <td>${m.smallest_count === null ? '—' : `${m.smallest_count} to ${m.largest_count}`}${m.min_items ? `<div class="cap">${m.too_few} under the minimum of ${m.min_items}</div>` : ''}${m.large_share ? `<div class="cap">${esc((fam(m.large_share.family) || {}).name || m.large_share.family)} holds ${Number(m.large_share.percent).toFixed(1)}% of the firm’s items</div>` : ''}</td>
    <td>${judged(m, m.by_median)}</td><td>${judged(m, m.by_fixed)}</td></tr>`;
  return h + `<p class="cap" style="margin:0 0 6px">The last two columns give the Green tolerance / Red limit, then how many families are Green, Amber and Red.</p><div class="ddscroll"><table class="dt"><thead><tr><th>Metric</th><th>Results: lowest · middle · highest</th><th>Items counted per family</th><th>By prevailing median</th><th>By fixed threshold</th></tr></thead><tbody>${c.data.metrics.map(row).join('')}</tbody></table></div>`;
}
const thShow = v => v === null || v === undefined || v === '' ? '—' : v === true ? 'On' : v === false ? 'Off' : String(v);
function vThresholds(){
  thLoad();
  const head = `<div class="ph"><h1>Scoring settings</h1><p class="cap" style="margin:4px 0 0;max-width:none">A change applies at the next Update. Locked months don’t change.</p></div>`;
  if (TH.state !== 'ok') return `<main class="wrap sheet">${head}<p class="cap" role="status">${TH.state === 'fail' ? esc(TH.err || 'The page couldn’t be loaded. Reload to try again.') : 'Loading…'}</p></main>`;
  const d = TH.data, edit = d.can_edit && !S.snap, E = TH.edits;
  const val = (path, cur) => (path in E ? E[path] : (cur === null || cur === undefined ? '' : cur));
  const num = (path, cur, label, off) => `<input class="thin${path in E ? ' chg' : ''}" type="number" step="any" data-path="${esc(path)}" value="${esc(val(path, cur))}" aria-label="${esc(label)}"${!edit || off ? ' disabled' : ''}>`;
  const groups = [...new Set(d.general.map(g => g.group))];
  const onoff = (path, cur, label) => { const v = String(val(path, cur)) === 'true'; return `<select class="thin${path in E ? ' chg' : ''}" style="width:auto" data-path="${esc(path)}" aria-label="${esc(label)}"${edit ? '' : ' disabled'}><option value="true"${v ? ' selected' : ''}>On</option><option value="false"${v ? '' : ' selected'}>Off</option></select>`; };
  const general = groups.map(g => `<h2>${esc(g)}</h2><div class="thg">${d.general.filter(x => x.group === g).map(x => `<label>${esc(x.label)}${x.kind === 'onoff' ? onoff(x.path, x.value, x.label) : num(x.path, x.value, x.label)}</label>`).join('')}</div>`).join('');
  const row = m => { const bp = `metrics.${m.id}.basis`, basis = val(bp, m.basis), pol = basis === 'Policy';
    return `<tr><td><b>${esc(m.name)}</b><div class="cap">${m.higher_is_better ? 'Higher is better' : 'Lower is better'}${m.unit === '%' ? ' · %' : ''}</div></td>
      <td><select class="thin${bp in E ? ' chg' : ''}" style="width:auto;max-width:none" data-path="${esc(bp)}" aria-label="${esc(m.name)}: basis"${edit ? '' : ' disabled'}><option value="Prevailing median"${pol ? '' : ' selected'}>Prevailing median</option><option value="Policy"${pol ? ' selected' : ''}>Fixed</option></select></td>
      <td>${pol ? num(`metrics.${m.id}.green`, m.green, m.name + ': Green tolerance') : '<span class="muted">Middle family</span>'}</td>
      <td>${pol ? num(`metrics.${m.id}.red`, m.red, m.name + ': Red limit') : '<span class="muted">Green tolerance and the Amber band</span>'}</td>
      <td>${pol ? '' : num(`metrics.${m.id}.amber_band_min`, m.amber_band_min, m.name + ': smallest Amber band')}</td>
      <td>${num(`low_confidence_below_items.${m.id}`, m.min_items, m.name + ': fewest items to score')}</td>
      <td>${num(`large_share_flag_percent.${m.id}`, m.large_share, m.name + ': largest share for one family, %')}</td>
      <td>${m.switchable ? onoff(`switched_on.${m.id}`, m.switched_on, m.name + ': scored') : ''}</td></tr>`; };
  const metrics = `<h2>Tolerance thresholds</h2><div class="ddscroll"><table class="dt tht nosort"><thead><tr><th>Metric</th><th>Basis</th><th>Green tolerance</th><th>Red limit</th><th>Smallest Amber band</th><th>Fewest items to score</th><th>Largest share for one family, %</th><th>Scored</th></tr></thead><tbody>${d.metrics.map(row).join('')}</tbody></table></div>`;
  const n = Object.keys(E).length;
  const bar = edit && !TH.pv ? `<p style="margin:12px 0"><button type="button" class="pri" data-act="th-review"${n && !TH.busy ? '' : ' disabled'}>Review ${n ? plural(n, 'change', 'changes') : 'changes'}</button>${n ? ' <button type="button" data-act="th-reset">Undo edits</button>' : ''}</p>` : '';
  const err = TH.err ? `<p class="lverr" role="alert">${esc(TH.err)}</p>` : '', msg = TH.msg ? `<p class="lvok" role="status">${esc(TH.msg)}</p>` : '';
  let rev = '';
  if (TH.pv) { const pv = TH.pv;
    const ch = pv.changes.length ? `<table class="dt nosort" style="max-width:760px"><thead><tr><th>Setting</th><th>Now</th><th>After</th></tr></thead><tbody>${pv.changes.map(c => `<tr><td>${esc(c.label)}</td><td>${esc(thShow(c.before))}</td><td><b>${esc(thShow(c.after))}</b></td></tr>`).join('')}</tbody></table>` : '<p class="muted">Nothing differs from the values in use.</p>';
    const mon = pv.months.map(m => `<h3>${esc(m.label)}</h3>${m.moves.length ? `<table class="dt" style="max-width:760px"><thead><tr><th>Who</th><th>What</th><th>Now</th><th>After</th></tr></thead><tbody>${m.moves.map(x => `<tr><td>${esc(x.who)}</td><td>${esc(x.what)}</td><td>${esc(x.before)}</td><td><b>${esc(x.after)}</b></td></tr>`).join('')}</tbody></table>` : '<p class="muted">No score moves.</p>'}`).join('');
    const lock = pv.locked.length ? `<p class="cap">Locked, so unchanged: ${esc(pv.locked.join(', '))}.</p>` : '';
    rev = `<section class="threv" id="threv" tabindex="-1" aria-label="Review changes"><h2 style="margin-top:0">Review ${plural(pv.changes.length, 'change', 'changes')}</h2>${ch}${pv.changes.length ? `<h2>Scores that would move</h2>${mon || '<p class="muted">No open month has been updated yet.</p>'}${lock}
      <form class="thsave" style="margin-top:10px"><label>Why<br><textarea name="reason" maxlength="1000" required></textarea></label><div style="margin-top:6px">${byField()} <button type="submit" class="pri"${TH.busy ? ' disabled' : ''}>Save</button> <button type="button" data-act="th-cancel">Back to editing</button></div></form>` : '<p><button type="button" data-act="th-cancel">Back to editing</button></p>'}</section>`; }
  const hist = d.history.length ? `<h2>Change history</h2><div class="ddscroll"><table class="dt"><thead><tr><th>When</th><th>Who</th><th>Setting</th><th>Before</th><th>After</th><th>Why</th></tr></thead><tbody>${d.history.map(c => `<tr><td data-sv="${esc(c.at)}">${esc(when(c.at))}</td><td>${esc(c.by)}</td><td>${esc(c.label)}</td><td>${esc(thShow(c.before))}</td><td><b>${esc(thShow(c.after))}</b></td><td>${esc(c.reason)}</td></tr>`).join('')}</tbody></table></div>` : '';
  return `<main class="wrap sheet">${head}${msg}${err}${rev}${TH.pv ? '' : general + metrics + bar + thCompare()}${hist}</main>`;
}
document.addEventListener('change', e => {      // Scoring settings: an edited value is kept until Review or Undo
  const t = e.target; if (!t.classList || !t.classList.contains('thin') || !t.dataset.path) return;
  const path = t.dataset.path, cur = (TH.data.values || {})[path];
  const same = t.value === '' ? (cur === null || cur === undefined) : (t.tagName === 'SELECT' ? t.value === String(cur) : Number(t.value) === Number(cur) && cur !== null && cur !== undefined);
  if (same) delete TH.edits[path]; else TH.edits[path] = t.value;
  TH.msg = ''; TH.err = ''; S.keepScroll = true; render();
  const again = document.querySelector(`.thin[data-path="${CSS.escape(path)}"]`); if (again) again.focus({preventScroll:true});
});
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b) return; const a = b.dataset.act;
  if (a === 'th-reset') { TH.edits = {}; TH.err = ''; S.keepScroll = true; render(); }
  if (a === 'th-cancel') { TH.pv = null; TH.err = ''; S.keepScroll = true; render(); }
  if (a === 'th-review') { TH.busy = true; TH.err = ''; TH.msg = '';
    apiPost('/api/thresholds/preview', {changes:TH.edits}).then(j => { TH.pv = j; }).catch(err => { TH.err = err.message; })
      .finally(() => { TH.busy = false; render(); const r = $('#threv'); if (r) r.focus(); }); }
});
document.addEventListener('submit', e => {
  const f = e.target; if (!f.matches('form.thsave')) return; e.preventDefault();
  TH.busy = true; TH.err = '';
  apiPost('/api/thresholds', {changes:TH.edits, reason:f.reason.value.trim(), by:liveName(f)})
    .then(j => { TH.data = Object.assign({}, TH.data, j); TH.cmp = {}; TH.edits = {}; TH.pv = null; TH.msg = `Saved ${plural(j.saved.length, 'change', 'changes')}. Press Update the scorecard on each open month to apply.`; })
    .catch(err => { TH.err = err.message; }).finally(() => { TH.busy = false; render(); });
});
