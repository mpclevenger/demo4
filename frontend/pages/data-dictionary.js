/* Data dictionary: every file TRUST reads, its checks and its data contract. */
"use strict";
/* ---------- Data dictionary (owner, 4 Nov 2026): every file TRUST reads, what it is, the columns read, the metrics it
   feeds, the checks run on it, and its data contract. Everyone can see it; anyone can ask to onboard a source;
   Tech Risk approves (formal = approved). ---------- */
const DD = {open:null, form:null, err:null, msg:null, decide:{}};
const CONTRACTS = {state:'idle', rows:[]};
function contractsLoad(force){
  if (CONTRACTS.state === 'loading' || (CONTRACTS.state === 'ok' && !force)) return;
  CONTRACTS.state = 'loading';
  api('/api/contracts').then(j => { CONTRACTS.rows = j.contracts || []; CONTRACTS.state = 'ok'; })
    .catch(() => { CONTRACTS.state = 'fail'; }).finally(() => { S.keepScroll = true; render(); });
}
const contractsFor = feed => CONTRACTS.rows.filter(c => c.feed === feed).sort((a, b) => a.version - b.version);
const currentContract = feed => contractsFor(feed).filter(c => c.status === 'approved').slice(-1)[0] || null;
const openContract = feed => contractsFor(feed).find(c => c.status === 'draft') || null;
/* The checks run on every file at upload (backend checks.py) and at mapping, in plain words. */
const CHECKS_ALL = [
  ['Readable', 'The file opens and is read with this file’s own reader the moment it arrives. A file that can’t be read at all is refused and the attempt is logged.'],
  ['Right file', 'If most of the columns TRUST needs aren’t in it, or every row is unusable, it is refused as the wrong file (the message names the missing columns).'],
  ['Columns', 'Column names are matched ignoring capitals, spaces and punctuation, then by close spelling; a close match is listed as a warning. A missing column means No data for the metrics that need it.'],
  ['Rows', 'Each row is checked by this file’s rules (below). A row that fails is set aside with its reason, never silently dropped; the count is a warning.'],
  ['Dates', 'Any common date format is read; Z means UTC, no timezone means New York. A row whose date can’t be read is set aside.'],
  ['Only what TRUST uses', 'Only the columns TRUST reads are stored (HR: only the CTO’s line). The file’s fingerprint (SHA-256) as received is recorded.'],
  ['Data contract', 'Once a contract is approved, a file whose columns differ from it is flagged, and TRUST uses the file only for the metrics the contract lists.'],
  ['Acknowledged before lock', 'Every warning is shown on Data sources and This month, and must be acknowledged before the month is locked; the lock seals them.']];
function vDataDict(arg){
  contractsLoad();
  const feeds = LAYOUTS.slice().sort((a, b) => a.name.localeCompare(b.name));
  const sel = arg && feeds.find(f => f.id === arg) ? arg : null;
  const stTag = c => !c ? '<span class="tag" style="--lc:#6b7280">No contract yet</span>' : c.status === 'approved' ? `<span class="tag" style="--lc:#0f766e">Formal · v${c.version}</span>` : c.status === 'draft' ? `<span class="tag" style="--lc:#b45309">Requested · v${c.version}</span>` : '';
  const cKey = f => { const c = currentContract(f.id), o = openContract(f.id);
    if (!c && !o) return `<span class="muted">None yet</span>`;
    const parts = [];
    if (c) parts.push(`<b>Formal</b> v${c.version} · ${esc(c.provider)}${c.contact ? ` (${esc(c.contact)})` : ''} · for ${(c.metrics || []).join(', ')} · approved ${fd(String(c.decided_at).slice(0, 10))} by ${esc(c.decided_by)}`);
    if (o) parts.push(`<span class="muted">v${o.version} requested ${fd(String(o.at).slice(0, 10))}, waiting for Tech Risk</span>`);
    return parts.join('<br>') + ` · <a href="${href('/datadict/' + f.id)}">contract</a>`; };
  /* Data owner (owner, 9 Nov 2026): the named person we get the data from, from config/data_sources.json;
     else the contact on an approved data contract; else not named yet */
  const owner = f => { const o = (D.data_sources || {})[f.id] || {}, c = currentContract(f.id);
    if (o.owner) return `<b>${esc(o.owner)}</b>${o.team ? `<div class="cap">${esc(o.team)}</div>` : ''}`;
    if (c && c.contact) return `${esc(c.contact)}<div class="cap">From the data contract</div>`;
    return '<span class="muted">Not named yet</span>'; };
  const rows = feeds.map(f => `<tr class="${sel === f.id ? 'sel' : ''}"><td><a href="${href('/datadict/' + f.id)}"><b>${esc(f.name)}</b></a><div class="cap">${esc(f.provider)} · ${esc(f.file)}</div></td><td>${owner(f)}</td><td>${feedMetrics(f)}</td><td>${cKey(f)}</td></tr>`).join('');
  const table = `<table class="dt" aria-label="Data sources used for the scorecard"><colgroup><col style="width:24%"><col style="width:16%"><col style="width:28%"><col style="width:32%"></colgroup><thead><tr><th>Data source</th><th>Data owner</th><th>Used for</th><th>Data contract</th></tr></thead><tbody>${rows}</tbody></table>`;
  const detail = sel ? ddDetail(feeds.find(f => f.id === sel)) : '';
  const msg = DD.err ? `<p class="lverr" role="alert"><b>Not done.</b> ${esc(DD.err)}</p>` : '';
  const formBtn = `<button type="button" data-act="dd-form"${DD.form ? ' aria-expanded="true"' : ''}>Onboard a data source</button>`;
  const nWanted = bMetCounts().progress + bMetCounts().wanted;
  return `<div class="method"><h1>Data dictionary</h1>
  <p class="intro">Every data source the scorecard uses: what each file is, who sends it, which metrics it feeds and its data contract (<a href="${href('/glossary/data-contract')}">what a data contract is</a>).&#32;<a data-trac-path="/guides/sending-data-for-trust/" hidden>To send numbers from your own system, see the TRAC guide “Sending data for TRUST”.</a></p>
  <p class="cap">Gray chips are metrics not measured yet: in progress or wanted (${nWanted} of ${D.metrics.length}). They count in no score.</p>
  <p class="noprint" style="margin:0 0 12px">${formBtn}${CONTRACTS.state === 'fail' ? ' <span class="muted">Contracts couldn’t be loaded; try again later.</span>' : ''}</p>${msg}${DD.form ? ddForm() : ''}
  ${table}${detail}
  <details class="exs" id="dd-checks" style="margin-top:22px"${S.snap ? ' open' : ''}><summary>Checks run on every file (${plural(CHECKS_ALL.length, 'check', 'checks')})</summary><dl>${CHECKS_ALL.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl></details>
  ${cplSeeTheCode(((D.code_places || {}).upload_checks || []).concat((D.code_places || {}).mapping || []), 'The checks every upload goes through, and the mapping that places each month’s rows into L3 teams.')}</div>`;
}
function cplReader(f){ const r = ((D.code_places || {}).feed_readers || {})[f.id]; return r ? cplPlaceCell(r) : ''; }
function ddDetail(f){
  const c = currentContract(f.id), o = openContract(f.id), hist = contractsFor(f.id);
  const read = (f.columns || []).filter(x => !(f.not_loaded || []).includes(x));
  const row = (k, v) => `<tr><th scope="row">${k}</th><td>${v}</td></tr>`;
  const contractRow = x => `<tr><td>v${x.version}</td><td>${esc(x.status === 'approved' ? 'Formal (approved)' : x.status)}</td><td>${esc(x.provider)}${x.contact ? ` · ${esc(x.contact)}` : ''}</td><td>${esc((x.metrics || []).join(', '))}</td><td>${esc(x.by)} · ${fd(String(x.at).slice(0, 10))}${x.decided_by ? `<div class="cap">${esc(x.status)} by ${esc(x.decided_by)} · ${fd(String(x.decided_at).slice(0, 10))}${x.reason ? ` — ${esc(x.reason)}` : ''}</div>` : ''}</td>
    <td class="noprint">${x.status === 'draft' && may('run_month') ? `<button type="button" class="sm" data-act="dd-decide" data-id="${esc(x.id)}" data-d="approved">Approve</button> <button type="button" class="sm" data-act="dd-decide" data-id="${esc(x.id)}" data-d="returned">Return</button>` : ''}</td></tr>`;
  const decideBox = DD.decide.id ? `<form class="ddf" data-id="${DD.decide.id}" data-d="${DD.decide.d}" style="margin:8px 0"><label>${DD.decide.d === 'approved' ? 'Approve' : 'Return'} this request${DD.decide.d === 'returned' ? ': say why' : ''}<br><input name="reason" style="width:60%" ${DD.decide.d === 'returned' ? 'required' : ''}></label> ${liveByField()} <button type="submit">${DD.decide.d === 'approved' ? 'Approve' : 'Return'}</button> <button type="button" data-act="dd-decide-cancel">Cancel</button></form>` : '';
  return `<section class="panel" id="dd-detail" style="margin-top:18px" aria-labelledby="dd-h"><h2 id="dd-h">${esc(f.name)}</h2>
  <table class="dt kv"><tbody>${row('Provider', esc(f.provider))}${row('File', esc(f.file) + (f.key ? ` · one row per ${esc(f.key)}` : ''))}${row('Used for', feedMetrics(f))}
  ${row('What TRUST reads from it', read.length ? read.map(x => `<code>${esc(x)}</code>`).join(', ') : '<span class="muted">Layout not received yet</span>')}
  ${f.not_loaded && f.not_loaded.length ? row('In the file, not read', f.not_loaded.map(x => `<code>${esc(x)}</code>`).join(', ')) : ''}
  ${cplReader(f) ? row('Where it’s read', cplReader(f)) : ''}
  ${row('Row checks', (f.row_checks || []).length ? `<ul style="margin:0;padding-left:18px">${f.row_checks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>` : '<span class="muted">No reader yet: kept as received, no row checks</span>')}
  ${f.notes ? row('Notes', esc(Array.isArray(f.notes) ? f.notes.join(' ') : f.notes)) : ''}
  ${row('Data contract', c ? `<b>Formal, version ${c.version}</b> · sent by ${esc(c.provider)}${c.contact ? ` (${esc(c.contact)})` : ''}${c.cadence ? `, ${esc(c.cadence)}` : ''} · may be used for ${(c.metrics || []).map(metChip).join(' ')} · approved by ${esc(c.decided_by)} on ${fd(String(c.decided_at).slice(0, 10))}${c.what ? `<div class="cap">${esc(c.what)}</div>` : ''}` : o ? `Version ${o.version} requested by ${esc(o.by)} on ${fd(String(o.at).slice(0, 10))}, waiting for Tech Risk.` : 'None yet. Anyone can ask with “Onboard a data source”.')}</tbody></table>
  ${hist.length ? `<h3 style="margin-top:14px">Contract history</h3><table class="dt" aria-label="Contract history"><thead><tr><th>Version</th><th>Status</th><th>Provider</th><th>Metrics</th><th>Asked / decided</th><th class="noprint"></th></tr></thead><tbody>${hist.map(contractRow).join('')}</tbody></table>${decideBox}` : ''}
  </section>`;
}
/* Metric state for the dictionaries (owner, 4 Nov 2026; in progress added 8 Nov): measured now, in progress (being built) or wanted (no source yet). The older words for wanted are no longer used anywhere (owner, 15 Nov 2026). */
const metState = id => { const dm = (D.dictionary.metrics || {})[id] || {}, m = met(id) || {}; return dm.status === 'In progress' ? 'in progress' : (m.wanted_shown || dm.not_measured) ? 'wanted' : 'measured'; };   // status in config/metrics.json (owner, 8 Nov 2026)
const metChip = id => { const st = metState(id), m = met(id); if (!m) return esc(id);
  return `<a class="mchip${st === 'measured' ? '' : ' gray'}" href="${href('/dictionary/' + id)}">${esc(m.name)}</a>`; };
const COMMON_FEEDS = {hr:'Common use: places every person in an L3 team (manager chain)', hr_mapping:'Common use: which L3 team each lead owns', };
const bFeedsText = f => f.id === 'app_owner_members' ? 'App owners in the drill-down (not scored)' : String(f.feeds_metrics || '');   // one wording for Data sources and Data dictionary
const feedMetrics = f => { const ids = String(f.feeds_metrics || '').match(/[A-Z]{2}-\d{2}/g) || [];
  if (f.id === 'app_owner_members') return `<span class="cap">${esc(bFeedsText(f))}</span>`;
  if (COMMON_FEEDS[f.id]) return `<span class="cap">${esc(COMMON_FEEDS[f.id])}</span>`;
  return ids.length && ids.every(id => met(id)) ? [...new Set(ids)].map(metChip).join(' ') : `<span class="muted">${esc(f.feeds_metrics || '—')}</span>`; };
const feedTitle = id => ((LAYOUTS.find(x => x.id === id) || {}).name || id);
function liveByField(){ return byField(); }
function ddForm(){
  const v = DD.form || {}, f = v.feed ? LAYOUTS.find(x => x.id === v.feed) : null;
  const cols = f ? (f.columns || []).filter(x => !(f.not_loaded || []).includes(x)).join('\n') : '';
  const opts = LAYOUTS.slice().sort((a, b) => a.name.localeCompare(b.name)).map(x => `<option value="${x.id}"${v.feed === x.id ? ' selected' : ''}>${esc(x.name)}</option>`).join('');
  const mets = D.metrics.map(m => `<label style="display:inline-block;margin:0 10px 4px 0"><input type="checkbox" name="metrics" value="${m.id}"${(v.metrics || (f ? String(f.feeds_metrics || '').split(/,\s*/) : [])).includes(m.id) ? ' checked' : ''}> ${m.id}</label>`).join('');
  return `<form id="ddform" class="panel" style="margin:0 0 16px" aria-label="Onboard a data source">
  <h2 style="font-size:16px;margin:0 0 8px">Onboard a data source</h2><p class="cap">Fill this in with the provider. Tech Risk approves it; once approved it is the formal data contract for the file. For a file that already has one, this asks for a new version.</p>
  <div class="fg"><label>Which file <select name="feed" id="dd-feed" required><option value="">Choose…</option>${opts}</select></label>
  <label>Team that sends it <input name="provider" value="${esc(v.provider ?? (f ? f.provider : ''))}" required maxlength="100"></label>
  <label>Who to ask about it <input name="contact" value="${esc(v.contact || '')}" maxlength="200" placeholder="name or mailbox"></label>
  <label>How often <input name="cadence" value="${esc(v.cadence || 'Monthly, after month-end')}" maxlength="100"></label></div>
  <label>What the file is <textarea name="what" rows="2" required maxlength="2000">${esc(v.what || '')}</textarea></label>
  <label>Columns TRUST may read (one per line) <textarea name="columns" rows="5" required>${esc(v.columns ?? cols)}</textarea></label>
  <fieldset style="border:0;padding:0;margin:8px 0"><legend class="cap">Metrics TRUST may use it for</legend>${mets}</fieldset>
  <label>Anything else <textarea name="note" rows="2" maxlength="2000">${esc(v.note || '')}</textarea></label>
  <p>${liveByField()} <button type="submit">Send to Tech Risk</button> <button type="button" data-act="dd-form-cancel">Cancel</button></p></form>`;
}
