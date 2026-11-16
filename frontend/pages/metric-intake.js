/* Metric intake (Tech Risk): the record of every metric a team wants, and the numbers teams send. */
"use strict";
/* ---------- Metric intake (owner, 15 Nov 2026) ----------
   Every metric a team wants on the scorecard starts here as Wanted and counts in no score. Tech Risk fills in the
   record (teams do not): the six Wanted fields in the room, then the In progress fields, which are the data contract.
   Measured is set by hand after the usual metric approval; this page only records the stage.
   The page shows what each team's service account has sent (back end: backend/trust/metric_intake.py).
   Every global name here starts with "mi" or "MI". */
const MI = {state:'idle', data:null, open:null, adding:false, draft:{}, msg:'', err:'', note:false, month:{}, err_load:''};
const MI_STAGES = ['Wanted', 'In progress', 'Measured'];
const MI_STAGE_SAYS = {
  'Wanted': 'We want it and it isn’t there yet. It counts in no score.',
  'In progress': 'Agreed and being built. The record is the data contract. It still counts in no score.',
  'Measured': 'Counted and scored. Tech Risk sets this by hand, after the usual metric approval.'};

function miLoad(force){
  if (!force && (MI.state === 'loading' || MI.state === 'ok')) return;
  MI.state = 'loading';
  api('/api/metric-intake').then(j => { MI.data = j; MI.state = 'ok'; })
    .catch(e => { MI.state = 'fail'; MI.err_load = e.message; }).finally(() => { S.keepScroll = true; render(); });
}
const miRecord = id => ((MI.data && MI.data.records) || []).find(r => r.id === id) || null;
const miChoices = () => (MI.data && MI.data.choices) || {};
const miMayEdit = () => !!(MI.data && MI.data.can_edit) && !S.snap;
const miLastMonth = id => Object.keys((MI.data.received || {})[id] || {}).sort().slice(-1)[0] || '';
const miDraftValue = (record, key) => (key in MI.draft) ? MI.draft[key] : ((record && record[key]) || '');
const miLabelOf = (key, value) => {
  const c = miChoices();
  if (key === 'direction') return (c.directions || {})[value] || value;
  if (key === 'shape') return (c.shapes || {})[value] || value;
  if (key === 'cadence') return (c.cadences || {})[value] || value;
  if (key === 'arrival') return (c.arrivals || {})[value] || value;
  return value;
};
const miFieldLabel = key => {
  const c = miChoices(), all = [...(c.wanted_fields || []), ...(c.in_progress_fields || [])];
  return (all.find(f => f.key === key) || {}).label || key;
};

/* ---- the form fields, one small function per kind ---- */
function miText(record, key, label, hint, wide){
  return `<div class="pfld${wide ? ' mi-wide' : ''}"><label for="mi-${key}">${esc(label)}</label>${hint ? `<span class="cap">${esc(hint)}</span>` : ''}<input type="text" id="mi-${key}" name="${key}" value="${esc(miDraftValue(record, key))}" maxlength="400" ${miMayEdit() ? '' : 'readonly'}></div>`;
}
function miPick(record, key, label, hint, options){
  const now = miDraftValue(record, key);
  const list = options.map(([value, text]) => `<option value="${esc(value)}"${value === now ? ' selected' : ''}>${esc(text)}</option>`).join('');
  return `<div class="pfld"><label for="mi-${key}">${esc(label)}</label>${hint ? `<span class="cap">${esc(hint)}</span>` : ''}<select id="mi-${key}" name="${key}" ${miMayEdit() ? '' : 'disabled'}><option value="">Choose…</option>${list}</select></div>`;
}
function miWantedFields(record){
  const c = miChoices();
  return `${miText(record, 'name', 'Metric name', '', true)}
    ${miText(record, 'tells_leadership', 'What it tells leadership', 'One sentence.', true)}
    ${miPick(record, 'building_block', 'Building block', '', (c.building_blocks || []).map(b => [b, b]))}
    ${miText(record, 'provider_team', 'Provider team', '')}
    ${miText(record, 'contact_name', 'Contact name', '')}
    ${miText(record, 'system', 'System the data lives in', '')}`;
}
function miContractFields(record){
  const c = miChoices(), pairs = obj => Object.entries(obj || {});
  return `${miText(record, 'counted_label', 'What is counted', 'For example: applications with a restore test in the last 12 months.', true)}
    ${miText(record, 'measured_against_label', 'What it is measured against', 'For example: applications in the inventory.', true)}
    ${miPick(record, 'unit', 'Unit', '', (c.units || []).map(u => [u, u]))}
    ${miPick(record, 'direction', 'Direction', '', pairs(c.directions))}
    ${miPick(record, 'key_type', 'What ties each row to a team', 'Application, repository or person.', (c.key_types || []).map(k => [k, k]))}
    ${miPick(record, 'shape', 'Shape', 'Totals: one row per team. Items: one row per item (preferred: the team can see what sits behind its number).', pairs(c.shapes))}
    ${miPick(record, 'cadence', 'How often it is sent', 'Monthly unless agreed otherwise.', pairs(c.cadences))}
    ${miPick(record, 'arrival', 'How it arrives', '', pairs(c.arrivals))}
    ${miText(record, 'service_account', 'Service account that will send it', 'Its SAM account name, for example svc-lending. Needed when the team sends it (API).')}
    ${miText(record, 'approved_by', 'Who approved on the provider’s side', '')}
    <div class="pfld"><label for="mi-approved_on">Date the provider approved</label><span class="cap">Written like 2026-11-15.</span><input type="text" id="mi-approved_on" name="approved_on" value="${esc(miDraftValue(record, 'approved_on'))}" maxlength="10" placeholder="YYYY-MM-DD" ${miMayEdit() ? '' : 'readonly'}></div>`;
}

/* ---- the list: records grouped by stage ---- */
function miGroup(stage, records){
  const received = stage !== 'Wanted';
  const rows = records.map(r => `<tr><td class="nw"><b>${esc(r.id)}</b></td>
      <td><button type="button" class="mi-link" data-act="mi-open" data-id="${esc(r.id)}">${esc(r.name)}</button></td>
      <td>${esc(r.building_block)}</td><td>${esc(r.provider_team)}</td>
      ${received ? `<td>${miLastMonth(r.id) ? esc(monthLabel(miLastMonth(r.id))) : '<span class="muted">Nothing received yet</span>'}</td>` : ''}</tr>`).join('');
  const table = records.length
    ? `<table class="dt mi-table"><caption class="sr-only">${esc(stage)} metrics</caption><thead><tr><th>ID</th><th>Metric</th><th>Building block</th><th>Provider team</th>${received ? '<th>Last month received</th>' : ''}</tr></thead><tbody>${rows}</tbody></table>`
    : `<p class="muted mi-empty">${stage === 'Wanted' ? 'No metrics are Wanted yet. Use “Add a metric” when a team asks for one.' : stage === 'In progress' ? 'Nothing is In progress yet. A Wanted metric moves here once its details are complete.' : 'Nothing is Measured through this page yet.'}</p>`;
  return `<section class="grp mi-group" aria-labelledby="mi-h-${stage.replace(' ', '')}"><h2 id="mi-h-${stage.replace(' ', '')}">${esc(stage)} <span class="mi-count">${plural(records.length, 'metric', 'metrics')}</span></h2><p class="cap">${esc(MI_STAGE_SAYS[stage])}</p>${table}</section>`;
}
function miAddForm(){
  return `<form class="mi-form mi-addform" data-kind="add" aria-label="Add a metric"><h2>Add a metric</h2>
    <p class="cap">Six short answers, filled in with the team in the room. The metric starts as Wanted and counts in no score.</p>
    <div class="mi-grid">${miWantedFields(null)}</div>${byField('margin-top:6px;display:block')}
    <p style="margin:10px 0 0"><button type="submit" class="pri">Add as Wanted</button> <button type="button" data-act="mi-cancel-add">Cancel</button></p></form>`;
}
function miList(){
  const records = MI.data.records || [];
  const add = miMayEdit() ? (MI.adding ? miAddForm() : '<p><button type="button" class="pri" data-act="mi-add">Add a metric</button></p>') : '';
  return `${add}${MI_STAGES.map(stage => miGroup(stage, records.filter(r => r.stage === stage))).join('')}`;
}

/* ---- one record ---- */
function miHowToSend(record){
  const origin = location.origin + location.pathname.replace(/[^/]*$/, '').replace(/\/$/, '');
  const address = origin + '/api/metric-values';
  const month = miLastFullMonth();
  const key = {application: 'APP-1234', repository: 'lending-payments-api', person: 'jsmith'}[record.key_type] || 'APP-1234';
  const typed = ME ? '' : ',\n  "by": "Your name"';
  const rows = record.shape === 'items'
    ? [{intake_id:record.id, month, item_id:'RESTORE-TEST-17', item_name:'Restore test of Payments DB', key_type:record.key_type, key, counted:'yes', as_of:month + '-28'},
       {intake_id:record.id, month, item_id:'RESTORE-TEST-18', item_name:'Restore test of Ledger DB', key_type:record.key_type, key, counted:'no', as_of:month + '-28'}]
    : [{intake_id:record.id, month, key_type:record.key_type, key, count:3, total:4, as_of:month + '-28'}];
  const rowLines = rows.map(r => '    ' + JSON.stringify(r)).join(',\n');
  const body = `{\n  "intake_id": "${record.id}",\n  "month": "${month}",\n  "shape": "${record.shape}",\n  "rows": [\n${rowLines}\n  ]${typed}\n}`;
  const curl = `curl -X POST "${address}" \\\n  -H "X-TRUST: 1" -H "Content-Type: application/json" \\\n  -d '${body.replace(/'/g, '’')}'`;
  return `<section class="grp mi-box"><h2>How to send</h2>
    <p class="cap">${record.arrival === 'api' ? `The service account <b>${esc(record.service_account || '(not named yet)')}</b> sends it. ` : ''}Each send names one month and replaces the earlier send for that month. The earlier one stays in the history. Nothing sent here changes a score.</p>
    <table class="dt kv mi-kv"><tbody><tr><th>Address</th><td><code>POST ${esc(address)}</code></td></tr><tr><th>Header</th><td><code>X-TRUST: 1</code> (every change needs it)</td></tr><tr><th>Body</th><td>JSON as below, or the same rows as a CSV file in the field <code>file</code></td></tr></tbody></table>
    <h3>Example body for ${esc(record.id)}</h3><pre class="mi-pre" tabindex="0">${esc(body)}</pre>
    <h3>The same, as a curl line</h3><pre class="mi-pre" tabindex="0">${esc(curl)}</pre>
    <p class="cap">The full layout, the checks and a PowerShell example are in design doc 20 (Metric intake).&#32;<a data-trac-path="/guides/sending-data-for-trust/" hidden>For the team that sends: the TRAC guide “Sending data for TRUST”.</a></p></section>`;
}
function miLastFullMonth(){
  const [y, m] = S.p.split('-').map(Number), d = new Date(Date.UTC(y, m - 2, 1));
  return d.getUTCFullYear() + '-' + String(d.getUTCMonth() + 1).padStart(2, '0');
}
function miReceived(record){
  const months = (MI.data.received || {})[record.id] || {}, keys = Object.keys(months).sort().reverse();
  if (!keys.length) return `<section class="grp"><h2>What has been received</h2><p class="muted">Nothing has been received yet.</p></section>`;
  const rows = keys.map(m => { const x = months[m], opened = MI.month[record.id + '|' + m];
    return `<tr><td><button type="button" class="mi-link" data-act="mi-month" data-id="${esc(record.id)}" data-month="${esc(m)}" aria-expanded="${!!opened}">${esc(monthLabel(m))}</button></td><td>${plural(x.rows_kept, 'row', 'rows')} kept</td><td>${x.rows_set_aside ? plural(x.rows_set_aside, 'row', 'rows') + ' set aside' : 'None set aside'}</td><td>${plural(x.teams, 'team', 'teams')}</td><td>${esc(x.by)}<div class="cap">${esc(when(x.at))}</div></td><td>${x.sends > 1 ? plural(x.sends, 'send', 'sends') + ' (newest shown)' : '1 send'}</td></tr>`
      + (opened ? `<tr class="subrow"><td colspan="6">${miMonthDetail(record, m, opened)}</td></tr>` : ''); }).join('');
  return `<section class="grp"><h2>What has been received</h2><table class="dt mi-table"><caption class="sr-only">Numbers received by month</caption><thead><tr><th>Month</th><th>Kept</th><th>Set aside</th><th>Teams</th><th>From, and when</th><th>Sends</th></tr></thead><tbody>${rows}</tbody></table>
    <p class="cap">Open a month to see each team’s numbers and why any row was set aside.</p></section>`;
}
function miMonthDetail(record, month, detail){
  if (detail === 'loading') return '<p class="cap" role="status">Loading…</p>';
  if (detail.error) return `<p class="ferr" role="alert">${esc(detail.error)}</p>`;
  const totals = detail.totals.map(t => `<tr><td>${esc(t.key)}</td><td class="tn">${t.count}</td><td class="tn">${t.total}</td><td>${esc(t.as_of)}</td></tr>`).join('');
  const aside = detail.rows_set_aside.map(a => `<tr><td class="tn">${a.row_number}</td><td>${esc(a.reason)}</td></tr>`).join('');
  const items = detail.shape === 'items' ? `<details class="mi-items"><summary>The ${plural(detail.rows_kept_count, 'item', 'items')} behind these numbers</summary><table class="dt"><thead><tr><th>Item</th><th>Name</th><th>Team</th><th>Counted</th></tr></thead><tbody>${detail.rows_kept.map(r => `<tr><td>${esc(r.item_id)}</td><td>${esc(r.item_name)}</td><td>${esc(r.key)}</td><td>${r.counted ? 'yes' : 'no'}</td></tr>`).join('')}</tbody></table></details>` : '';
  return `<div class="mi-detail"><table class="dt"><caption class="cap" style="text-align:left">Numbers per ${esc(record.key_type)}, from the newest send</caption><thead><tr><th>${esc(record.key_type)}</th><th class="tn">Counted</th><th class="tn">Total</th><th>As of</th></tr></thead><tbody>${totals}</tbody></table>${items}
    ${aside ? `<table class="dt mi-aside"><caption class="cap" style="text-align:left">Rows set aside, and why</caption><thead><tr><th class="tn">Row</th><th>Reason</th></tr></thead><tbody>${aside}</tbody></table>` : '<p class="cap">No rows were set aside.</p>'}</div>`;
}
function miHistory(record){
  const rows = ((MI.data.history || {})[record.id] || []).slice().reverse().map(h => {
    let what = {added:'Added as Wanted', moved:'Moved', changed:'Changed details'}[h.action] || h.action, detail = '';
    if (h.action === 'moved') what = `Moved from ${(h.before || {}).stage} to ${(h.after || {}).stage}`;
    if (h.action === 'changed') detail = Object.keys(h.after || {}).map(k => `${miFieldLabel(k)}: ${(h.before || {})[k] ? esc(miLabelOf(k, h.before[k])) : '(empty)'} → ${esc(miLabelOf(k, h.after[k]) || '(empty)')}`).join('<br>');
    return `<tr><td class="nw">${esc(when(h.at))}</td><td>${esc(h.by)}</td><td>${esc(what)}${detail ? `<div class="cap">${detail}</div>` : ''}${h.note ? `<div class="cap">Note: ${esc(h.note)}</div>` : ''}</td></tr>`; }).join('');
  return `<section class="grp"><h2>History</h2><table class="dt mi-table"><caption class="sr-only">Every change, newest first</caption><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead><tbody>${rows}</tbody></table><p class="cap">Every change is kept with who and when. Nothing is overwritten.</p></section>`;
}
function miStageButtons(record){
  if (!miMayEdit()) return '';
  const to = (stage, label, cls) => `<button type="button"${cls ? ` class="${cls}"` : ''} data-act="mi-move" data-stage="${esc(stage)}">${esc(label)}</button>`;
  if (record.stage === 'Wanted') return to('In progress', 'Move to In progress', 'pri');
  if (record.stage === 'In progress') return `${to('Measured', 'Set as Measured…', '')} ${to('Wanted', 'Move back to Wanted', '')}`;
  return to('In progress', 'Move back to In progress', '');
}
function miDetail(record){
  const missing = record.missing_for_in_progress || [];
  const ready = record.stage === 'Wanted'
    ? (missing.length ? `<p class="mi-missing" role="status"><b>To move this to In progress, still to fill in:</b> ${missing.map(esc).join('; ')}.</p>` : '<p class="mi-ready" role="status">Everything for In progress is filled in. It can move on.</p>')
    : (missing.length ? `<p class="mi-missing" role="status"><b>Still to fill in:</b> ${missing.map(esc).join('; ')}.</p>` : '');
  const measuredNote = MI.note ? `<div class="pfld"><label for="mi-note">Which metric approval does this follow? (needed for Measured)</label><span class="cap">This only records the stage. It does not create a metric or change any score.</span><input type="text" id="mi-note" name="note" maxlength="1000" value="${esc(MI.draft.note || '')}"> <button type="button" class="pri" data-act="mi-move-go" data-stage="Measured">Set as Measured</button> <button type="button" data-act="mi-move-cancel">Cancel</button></div>` : '';
  const save = miMayEdit() ? `${byField('margin-top:6px;display:block')}<p style="margin:10px 0 0"><button type="submit" class="pri">Save details</button> ${miStageButtons(record)}</p>${measuredNote}` : '<p class="cap">Read only: you can see everything here but not change it.</p>';
  const howTo = (record.stage !== 'Wanted' && record.arrival === 'api' && record.shape && record.key_type) ? miHowToSend(record) : '';
  return `<p><button type="button" data-act="mi-back">← All metrics</button></p>
    <div class="mi-title"><h2 class="mi-name">${esc(record.id)} · ${esc(record.name)}</h2><span class="mi-stage mi-st-${record.stage.replace(' ', '')}">${esc(record.stage)}</span></div>
    <p class="cap">${esc(MI_STAGE_SAYS[record.stage])} Added by ${esc(record.created_by)} on ${esc(when(record.created_at))}.</p>
    <form class="mi-form" data-kind="save" data-id="${esc(record.id)}" aria-label="Details of ${esc(record.id)}">
      <section class="grp"><h2>About this metric</h2><div class="mi-grid">${miWantedFields(record)}</div></section>
      <section class="grp"><h2>The data contract</h2><p class="cap">Filled in once, here. Nobody fills in the same thing twice: this is also what the team’s numbers are checked against.</p>${ready}<div class="mi-grid">${miContractFields(record)}</div></section>
      ${save}</form>${howTo}${miReceived(record)}${miHistory(record)}`;
}

function vMetricIntake(){
  const refresh = MI.stale; MI.stale = false;
  miLoad(refresh);
  const head = `<div class="ph"><h1>Metric intake</h1><p class="cap" style="margin:4px 0 0;max-width:none">Every metric a team asks for starts here as Wanted. It counts in no score until Tech Risk sets it as Measured, after the usual metric approval. Tech Risk fills in the record; teams only send their numbers, from their own service account.</p></div>`;
  if (MI.state !== 'ok') return `<main class="wrap sheet mip">${head}<p class="cap" role="status">${MI.state === 'fail' ? esc(MI.err_load || 'The list couldn’t be loaded. Reload the page to try again.') : 'Loading…'}</p></main>`;
  const record = MI.open ? miRecord(MI.open) : null;
  const msg = (MI.msg ? `<p class="okmsg" role="status">${esc(MI.msg)}</p>` : '') + (MI.err ? `<p class="ferr" role="alert">${esc(MI.err)}</p>` : '');
  return `<main class="wrap sheet mip">${head}${msg}${record ? miDetail(record) : miList()}</main>`;
}

/* ---- clicks and saving ---- */
function miRerender(){ S.keepScroll = true; render(); }
function miFormValues(form){
  const fields = {};
  form.querySelectorAll('input[name], select[name]').forEach(el => { if (el.name !== 'by' && el.name !== 'note') fields[el.name] = el.value; });
  return fields;
}
function miSave(form, extra){
  const fields = miFormValues(form), id = form.dataset.id || '';
  const wasAdding = form.dataset.kind === 'add';
  return apiPost('/api/metric-intake', {by:liveName(form), id, fields, ...extra})
    .then(j => { MI.msg = j.message; MI.err = ''; MI.draft = {}; MI.note = false; MI.adding = false; if (wasAdding) MI.open = j.record.id; miLoad(true); })
    .catch(err => { MI.err = err.message; MI.msg = ''; miRerender(); });
}
document.addEventListener('input', e => {
  const form = e.target.closest && e.target.closest('form.mi-form');
  if (form && e.target.name) MI.draft[e.target.name] = e.target.value;
});
document.addEventListener('change', e => {
  const form = e.target.closest && e.target.closest('form.mi-form');
  if (form && e.target.name) MI.draft[e.target.name] = e.target.value;
});
document.addEventListener('click', e => {
  const b = e.target.closest && e.target.closest('[data-act^="mi-"]'); if (!b) return;
  const a = b.dataset.act;
  if (a === 'mi-add') { MI.adding = true; MI.msg = MI.err = ''; MI.draft = {}; miRerender(); const n = document.getElementById('mi-name'); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'mi-cancel-add') { MI.adding = false; MI.err = ''; MI.draft = {}; miRerender(); return; }
  if (a === 'mi-open') { MI.open = b.dataset.id; MI.msg = MI.err = ''; MI.draft = {}; MI.note = false; S.keepScroll = false; render(); window.scrollTo(0, 0); return; }
  if (a === 'mi-back') { MI.open = null; MI.msg = MI.err = ''; MI.draft = {}; MI.note = false; S.keepScroll = false; render(); window.scrollTo(0, 0); return; }
  if (a === 'mi-month') { const k = b.dataset.id + '|' + b.dataset.month;
    if (MI.month[k]) { delete MI.month[k]; miRerender(); return; }
    MI.month[k] = 'loading'; miRerender();
    api(`/api/metric-intake/${encodeURIComponent(b.dataset.id)}/${encodeURIComponent(b.dataset.month)}`).then(j => { MI.month[k] = j; }).catch(err => { MI.month[k] = {error:err.message}; }).finally(miRerender); return; }
  if (a === 'mi-move') {
    if (b.dataset.stage === 'Measured') { MI.note = true; MI.err = ''; miRerender(); const n = document.getElementById('mi-note'); if (n) n.focus({preventScroll:true}); return; }
    miSave(b.closest('form'), {stage:b.dataset.stage}); return; }
  if (a === 'mi-move-go') { const form = b.closest('form'); miSave(form, {stage:'Measured', note:(document.getElementById('mi-note') || {}).value || ''}); return; }
  if (a === 'mi-move-cancel') { MI.note = false; miRerender(); return; }
});
document.addEventListener('click', e => { if (e.target.closest && e.target.closest('a[href="#metric-intake"]')) { MI.stale = true; MI.open = null; } });   // opened from the sidebar: load it fresh
document.addEventListener('submit', e => {
  const form = e.target;
  if (!form.matches || !form.matches('form.mi-form')) return;
  e.preventDefault();
  miSave(form, {});
});
