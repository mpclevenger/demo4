/* L3 team page: Where to focus, the metrics table, the items behind a metric, downloads, this family's own risk assessment. */
"use strict";
/* ---------- family drill-down (item-level evidence, loaded lazily) ---------- */
const EV = {state:'idle', data:null};
const DDS = {l1:new Set(), tf:{}, focus:null};
function secSave(){ DDS.secs = [...document.querySelectorAll('details.lsec')].map(d => d.open); }
function secRestore(){ if (DDS.secs) document.querySelectorAll('details.lsec').forEach((d, i) => { if (DDS.secs[i]) d.open = true; }); }
function ddFocus(){ if (!DDS.focus) return; const b = document.querySelector(`[data-dd="${DDS.focus}"]`); if (b) b.focus({preventScroll:true}); }
function evLoad(){
  if (EV.state !== 'idle') return;
  EV.state = 'loading';
  const done = () => { const ta = document.querySelector('.cf textarea'); if (ta && ta.value) return; S.keepScroll = true; render(); secRestore(); ddFocus(); };
  try {
    fetch('evidence.json').then(r => { if (!r.ok) throw new Error('not ok'); return r.json(); })
      .then(d => { EV.data = d; Object.values(d).forEach(per => Object.values(per).forEach(f => Object.values(f).forEach(e => e.by_team.forEach(t => { if (!SUBT[t.team_key]) SUBT[t.team_key] = t.team_name; })))); EV.state = 'ok'; }).catch(() => { EV.state = 'fail'; }).then(done);
  } catch (_) { EV.state = 'fail'; done(); }
}

/* ---------- family page: sub-teams, drivers, briefing layout ---------- */
const SUBT = {};      // team key -> team name; filled from the evidence file when it loads (team key = the manager's account name)
const stName = (k, fallback) => SUBT[k] || fallback || k;

const subLabel = (k, fallback) => (stName(k, fallback));   // live: sub-teams are named by the HR column in settings (owner, 3 Nov 2026)

const famEv = fid => EV.state === 'ok' && EV.data[S.p] && EV.data[S.p][fid] ? EV.data[S.p][fid] : null;
const probOf = (m, num, den) => m.higher_is_better ? Math.max(0, (den || 0) - num) : num;

function famCards(fid){
  const date = P().meta.current_bd ? bizDay(S.p, P().meta.current_bd) : P().meta.last_day, f = fam(fid), out = [];
  D.entries.filter(e => e.kind === 'Note' && e.family_id === fid && (e.period === S.p || (e.period < S.p && e.status !== 'Done'))).forEach(e => out.push({mid:e.metric_id || null, block:e.block || null, text:e.text, date:e.created, who:e.owner}));
  COMMENTS.filter(c => c.p === S.p && c.fid === fid && c.type === 'explain').forEach(c => out.push({mid:c.mid || null, block:c.block || null, text:c.text, date:c.date || date, who:c.by || (f.leads || [])[0] || ''}));
  return out;
}

/* ---------- saving files: a normal browser download; printing is the browser's own ---------- */

/* ---------- family page: "Download my data" panel ---------- */
const DL = {open:false, tab:'scores', msg:''};
const DLT = {
  scores:{label:'Scores', cols:[['Metric ID','Short code of the metric'], ['Name','Plain-language name of the metric'], ['Value','This month’s result for the L3 team; the two pass/fail metrics show a count such as “21 of 23 apps governed”'], ['Numerator','Items counted in the top of the fraction'], ['Denominator','Items in scope: the bottom of the fraction'],
    ['Status','Green, Amber or Red against the thresholds; Information only or Not scored where none applies'], ['Green tolerance','The value at which a metric is Green; blank for pass/fail metrics'], ['Red limit','The value past which a metric is Red; blank for pass/fail metrics'], ['Basis','How the threshold was set: Policy, Prevailing median or Placeholder; “Pass/fail (not calibrated)” for the two pass/fail metrics'],
    ['Threshold version','Version of the thresholds this month was scored with'], ['Flags','Automatic Red rule, chronic, new this month, risk accepted, behind peers or provisional'], ['Prior-month value','Last month’s result, for comparison']]},
  breakdown:{label:'Breakdown', cols:[['Metric ID','Short code of the metric'], ['Cut','Whether the row groups items by sub-team or by app'], ['Group','The sub-team (with manager) or the app ID; “Other” is the apps outside the top eight'], ['Numerator','Items counted in the top of the fraction for this group'], ['Denominator','Items in scope for this group; blank for rate metrics measured per app']]},
  expl:{label:'Explanations & actions', cols:[['Kind','Explanation, action, data query, accepted risk or L3 team note'], ['Ref','Reference number of the entry'], ['Metric ID','Metric the entry is about; blank for the whole L3 team'], ['Text','What was written'], ['Owner','Who owns it'], ['Status','Open, done or approved'], ['Due','Date it is due'], ['Date','Date it was created']]},
  dict:{label:'Dictionary', cols:[['Tab','The tab the column belongs to'], ['Column','The column name'], ['Meaning','What the column means in plain language']]}
};
function flagTexts(fid, id, x){
  const m = met(id), tg = [];
  if (x.provisional) tg.push(`Provisional (${monthOf(x.carried_from)} result reused)`);
  if (x.override) tg.push('Automatic Red rule');
  const n = streak(x.history); if (n >= 3 && x.status === 'Red') tg.push(`Chronic: Red ${n} months`);
  if (x.status === 'Red' && x.prior_status != null && x.prior_status !== 'Red') tg.push('Newly Red');
  const acc = D.entries.find(e => e.kind === 'Accepted risk' && e.status === 'Approved' && e.family_id === fid && e.metric_id === id && e.period <= S.p && e.due >= P().meta.last_day);
  if (acc) tg.push(`Risk accepted until ${fd(acc.due)}`);
  if (x.behind_peers) tg.push(`Behind peers ${fv(m, x.value)} vs ${fv(m, x.typical)}`);
  return tg.join('; ');
}
function dlData(fid, tab){                 // -> {head, rows, note}
  const p = P(), fr = p.families[fid].metrics, head = DLT[tab].cols.map(c => c[0]);
  const needEv = tab === 'breakdown';
  if (needEv && (EV.state === 'idle' || EV.state === 'loading')) return {head, rows:[], note:'Loading…'};
  if (needEv && !famEv(fid)) return {head, rows:[], note:('Item detail couldn’t be loaded. Reload the page to try again.')};
  let rows = [];
  if (tab === 'scores') rows = D.metrics.map(m => { const y = fr[m.id], t = p.thresholds[m.id], sc = m.scored && t;
    if (isPF(m)) return [m.id, m.name, y.numerator == null ? '' : countText(m, y), y.numerator == null ? '' : y.numerator, y.denominator == null ? '' : y.denominator, stInfo(y.status)[2], '', '', PF_BASIS_TXT, '', flagTexts(fid, m.id, y), y.prior_numerator == null ? '' : countText(m, {numerator:y.prior_numerator, denominator:y.prior_denominator})];
    return [m.id, m.name, y.value == null ? '' : fv(m, y.value), y.numerator == null ? '' : y.numerator, y.denominator == null ? '' : y.denominator, stInfo(y.status)[2], sc ? fv(m, t.green) : '', sc ? fv(m, t.red) : '', sc ? basisName(t) : '', sc ? t.version : '', flagTexts(fid, m.id, y), y.prior_value == null ? '' : fv(m, y.prior_value)]; });
  else if (tab === 'breakdown') Object.entries(famEv(fid)).forEach(([mid, e]) => {
    e.by_team.forEach(t => rows.push([mid, 'Sub-team', subLabel(t.team_key, t.team_name), t.num, t.den == null ? '' : t.den]));
    e.by_app.forEach(a => rows.push([mid, 'App', a.app_id === 'NO-APP' ? 'Not mapped to an app' : a.app_id === 'Other' ? `Other (${a.n_apps} apps)` : a.app_id, a.num, a.den == null ? '' : a.den])); });
  else if (tab === 'expl') {
    D.entries.filter(e => e.family_id === fid && e.period <= S.p).forEach(e => rows.push([e.kind === 'Note' ? 'L3 team note' : e.kind, e.id, e.metric_id || '', e.text, e.owner, e.status, e.due || '', e.created || '']));
    COMMENTS.filter(c => c.p === S.p && c.fid === fid).forEach(c => rows.push([{explain:'Explanation', query:'Data query', action:'Action requested'}[c.type] || 'Explanation', '', c.mid || '', c.text, fam(fid).leads[0], 'Submitted', '', c.date || '']));
  }
  else if (tab === 'dict') Object.entries(DLT).filter(([k]) => k !== 'dict').forEach(([k, v]) => v.cols.forEach(c => rows.push([v.label, c[0], c[1]])));
  return {head, rows, note:''};
}
const csvCell = v => { const t = String(v == null ? '' : v); return /[",\n\r]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; };
const toCsv = (head, rows) => [head, ...rows].map(r => r.map(csvCell).join(',')).join('\r\n');
const roleLabel = () => isCTO() ? 'CTO' : isTR() ? 'Tech Risk' : 'Team lead';
function dlPanel(fid){
  if (S.snap) return '';
  const f = fam(fid), tabs = Object.keys(DLT);
  const counts = {}; tabs.forEach(t => { counts[t] = dlData(fid, t).rows.length; });
  const cur = DLT[DL.tab] ? DL.tab : 'scores', d = dlData(fid, cur), more = d.rows.length - 15;
  const today = new Date().toISOString().slice(0, 10);
  return `<section class="dlp noprint" id="dlp" role="region" aria-labelledby="dlp-h"><div class="dlh"><h2 id="dlp-h">Download the data behind this scorecard</h2><button type="button" class="sm" data-act="dl-close" data-dl="close">Close</button></div>
    <p class="cap" style="margin:0 0 8px">${(`A preview of the scores, tab by tab. <b>Download every item</b> gives an Excel file with one tab per metric: every item behind ${esc(f.name)}'s numbers for ${esc(monthLabel(S.p))}, with its key details, the ones to focus on first. Each metric's table on this page also has its own download.`)}</p>
    <div role="tablist" aria-label="Workbook tabs" class="dltabs">${tabs.map(t => `<button type="button" role="tab" class="dltab" id="dlt-${t}" data-act="dl-tab" data-tab="${t}" data-dl="tab-${t}" aria-selected="${t === cur}" aria-controls="dlbody" tabindex="${t === cur ? 0 : -1}">${DLT[t].label}${counts[t] ? ` <span class="cap">${counts[t]}</span>` : ''}</button>`).join('')}</div>
    <div id="dlbody" role="tabpanel" aria-labelledby="dlt-${cur}" tabindex="0">${d.note ? `<p class="muted" style="margin:8px 0">${esc(d.note)}</p>` : `<div class="ddscroll"><table class="dt ddt2"><thead><tr>${d.head.map(h => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${d.rows.slice(0, 15).map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('') || `<tr><td colspan="${d.head.length}" class="muted">No rows.</td></tr>`}</tbody></table></div>${more > 0 ? `<p class="cap" style="margin:4px 0 0">… ${more} more ${more === 1 ? 'row' : 'rows'} in the file</p>` : ''}`}</div>
    <div class="dlb">${(!canDl(fid)) ? '<span class="cap">Downloading is for L3 team leads and Tech Risk.</span>' : (`<a class="btnlink" href="/api/items/${encodeURIComponent(S.p)}/${encodeURIComponent(fid)}.xlsx?by=${encodeURIComponent(LIVE.by || '')}" download>Download every item (Excel, one tab per metric)</a>`)}
      <button type="button" data-act="dl-copy" data-dl="copy">Copy CSV (Scores)</button> <span class="cap" id="dl-msg" role="status" aria-live="polite">${esc(DL.msg)}</span></div>
    <p class="cap" style="margin:8px 0 0">Prepared for ${esc(f.name)} · ${roleLabel()} · ${fd(today)} · Confidential · ${('Contains people’s names: confidential, for this L3 team’s use only.')}</p>
    <p class="cap" style="margin:2px 0 0">${(`Every download is logged${LIVE.by ? ` as ${esc(LIVE.by)}` : ''}; the file contains only this L3 team’s rows.`)}</p></section>`;
}

function heldBy(fid, mid){
  const ev = famEv(fid), e = ev && ev[mid], m = met(mid); if (!e || !m.scored) return null;
  const rows = e.by_team.map(t => ({k:t.team_key, n:stName(t.team_key, t.team_name), p:probOf(m, t.num, t.den)})).filter(r => r.p > 0).sort((a, b) => b.p - a.p || a.k.localeCompare(b.k));
  const total = rows.reduce((t, r) => t + r.p, 0); return total ? {list:rows, total} : null;
}
const pctOf = (p, t) => Math.floor((200 * p + t) / (2 * t));   // whole percent, rounded half up
function shareBubs(o, m, w){
  /* "+N more" opens the rest of the teams, "Show fewer" closes them (owner, 4 Nov 2026) */
  const k = `${S.p}|${w}|${m.id}`, all = FOC.bubAll.has(k), extra = o.list.length - 2;
  return (all ? o.list : o.list.slice(0, 2)).map(r => `<button type="button" class="bub-team wfam" data-act="dd-team" data-w="${w}" data-m="${m.id}" data-t="${r.k}" data-dd="t:${w}|${m.id}|${r.k}" aria-label="Show the items for ${esc(m.name)} that sit with ${esc(r.n)} (${pctOf(r.p, o.total)}% of the outstanding items)">${esc(r.n)} · ${pctOf(r.p, o.total)}%</button>`).join('') + (extra > 0 ? `<button type="button" class="sm noprint" data-act="bub-more" data-k="${k}" data-dd="bm:${k}" aria-expanded="${all}" aria-label="${all ? 'Show fewer teams' : `Show ${extra} more ${extra === 1 ? 'team' : 'teams'}`} for ${esc(m.name)}">${all ? 'Show fewer' : `+${extra} more`}</button>` : '');
}
function heldCell(fid, m, loading){
  if (!m.scored) return '<span class="muted">—</span>';
  if (loading) return '<span class="skel" style="width:70%"></span>';
  const o = heldBy(fid, m.id); if (!o) return '<span class="muted">—</span>';
  if (o.list.length === 1 && o.list[0].k === 'NO-TEAM') return '<span class="muted">—</span>';   // one team that is "Not placed with a team" is noise
  return `<div class="bubs">${shareBubs(o, m, 'l')}</div>`;
}
/* ---------- Where to focus cards: counts, what it would take, tags ---------- */
/* Phrase table for the card sentence "{count} of {denominator} {noun} {verb}". The noun agrees with the denominator, the verb with the count.
   In production these phrases come from the dictionary (metric_version), not from this table. Rate metrics (rate:true) read "{n} {noun} {verb} {N} {den_noun}"
   with the noun and verb both agreeing with n; `fewer` is the word used in "n fewer {fewer} to reach Green". */
const OUTSTANDING = MW('outstanding')   /* shortfall wording: config/metrics.json wording.outstanding */;
const COUNTS = MW('counts')   /* numerator and denominator wording: config/metrics.json wording.counts */;
/* D-104: item allowance (TR-01, TR-02, TR-03): a family at most N items short is Amber, not Red. Family level only; the firm line has none. */
const allowOf = id => { const x = DX(id); return x && x.item_allowance != null ? {n:x.item_allowance, one:x.allowance_unit[0], many:x.allowance_unit[1]} : null; };
const itemsTxt = (a, k) => `${k} ${k === 1 ? a.one : a.many}`;

const wholeUnit = m => !!m.unit && m.unit !== '%' && !/\bper\b/.test(m.unit) && !isPF(m);   // counts of things (incidents), shown as whole numbers in sentences
const limitText = (m, t, fam) => { const a = fam ? allowOf(m.id) : null, b = m.higher_is_better ? `Red below ${fv(m, t.red)}` : wholeUnit(m) ? `Red at ${Math.floor(t.red + 1e-9) + 1} or more ${m.unit}` : `Red above ${fv(m, t.red)}`; return a ? `${b} and more than ${itemsTxt(a, a.n)} short` : b; };
function countText(m, y){
  if (y.numerator == null || y.denominator == null) return '';
  const o = COUNTS[m.id], n = Math.round(y.numerator), d = Math.round(y.denominator), nn = nfmt(n), dn = nfmt(d);
  if (!o) return `${nn} of ${dn}`;
  if (m.id === 'TR-02') return `${nn} of ${dn} hygiene checks passed across ${plural(Math.round(d / 5), 'active repo', 'active repos')}`;   // 5 checks per active repo
  if (isPF(m)) return `${nn} of ${dn} ${d === 1 ? o.den_one : o.den_many} ${o.verb_many}`;
  if (o.verb_one) return `${nn} of ${dn} ${d === 1 ? o.den_one : o.den_many} ${n === 1 ? o.verb_one : o.verb_many}`;
  return `${nn} ${n === 1 ? o.num_one : o.num_many} ${o.join} ${dn} ${d === 1 ? o.den_one : o.den_many}`;
}
const RULE_ACTION = {client_impact:'next month with no release with client impact', critical_secret:'critical secret is remediated', t01_internet_eol:'end-of-life component is upgraded'};
const cardCount = (m, x) => { const n = Math.round(x.numerator), d = Math.round(x.denominator); return {n, d, c: m.higher_is_better ? Math.max(0, d - n) : n}; };
const B_MORE = {'TR-01':'be mapped to an app', 'TR-02':'pass', 'TR-03':'be confirmed by their owner', 'RE-01':'have a completed DR test', 'RE-02':'have a current test plan', 'RE-03':'have a passed test', 'SE-01':'pass the Checkmarx SAST policy', 'SE-02':'pass the Checkmarx SCA policy', 'SE-04':'be vaulted in CyberArk', 'SE-05':'be governed in SailPoint'};
function bMoreText(id, need, o){   // "3 more active repos need to pass the hygiene checks to reach Green"
  const v = B_MORE[id], noun = id === 'TR-02' ? (need === 1 ? 'hygiene check' : 'hygiene checks') : need === 1 ? o.noun_one : o.noun_many;   // TR-02 counts checks, not repos
  return v ? `${need} more ${noun} ${need === 1 ? 'needs' : 'need'} to ${v} to reach Green` : `${need} more ${noun} to reach Green`;
}
function needLine(id, x, t){
  const m = met(id), o = OUTSTANDING[id];
  if (isPF(m)) { if (x.numerator == null) return ''; const c = Math.round(x.denominator) - Math.round(x.numerator); if (c <= 0) return '';
    return `Onboard the ${nfmt(c)} remaining${x.t01_unmet ? ` (${x.t01_unmet} on ${x.t01_unmet === 1 ? 'a Tier 0/1 app' : 'Tier 0/1 apps'})` : ''}${x.provisional ? ` · ${monthOf(x.carried_from)} figures reused` : ''}`; }
  if (!o || !m.scored || x.numerator == null || !t) return '';
  const prov = x.provisional ? ` · ${monthOf(x.carried_from)} figures reused` : '';
  if (x.override) return `${m.override_rule === 'client_impact' ? 'Stays Red until a month passes with no release that affected clients' : 'Red until the ' + (RULE_ACTION[m.override_rule] || 'trigger is cleared')}${prov}`;
  const {n, d} = cardCount(m, x), per = /per (\d+)/.test(m.unit) ? +m.unit.match(/per (\d+)/)[1] : 100, EPS = 1e-9;
  let txt;
  if (m.higher_is_better && x.t01_fail) { const k = x.t01_fail, need = Math.ceil(t.green / 100 * d - EPS) - n;   // Tier 0/1 rule (SE-01/02): Red until those repos pass
    return `Red until the ${k} failing ${k === 1 ? 'repo on a Tier 0/1 app passes' : 'repos on Tier 0/1 apps pass'}${need > k ? ` · ${bMoreText(id, need, o)}` : ''}` + prov; }
  if (m.higher_is_better) { const need = Math.ceil(t.green / 100 * d - EPS) - n; txt = need <= 0 ? 'At the Green tolerance' : o.fewer ? `${need} fewer ${o.fewer} to reach Green` : bMoreText(id, need, o); }   // TE-02: fewer reverted releases, not more releases
  else { const allowed = Math.floor(t.green / per * d + EPS), need = n - allowed; txt = need <= 0 ? 'At the Green tolerance' : `${need} fewer${o.fewer ? ' ' + o.fewer : ''} to reach Green`; }
  return txt + prov;
}
function cardTags(fid, id, x){
  const tg = [], n = streak(x.history);
  if (x.status === 'Red' && x.prior_status != null && x.prior_status !== 'Red') tg.push('Newly Red');
  if (n >= 3 && x.status === 'Red') tg.push(`Chronic Red · ${n} months in a row`);
  if (x.override) tg.push('Automatic Red rule');
  const acc = D.entries.find(e => e.kind === 'Accepted risk' && e.status === 'Approved' && e.family_id === fid && e.metric_id === id && e.period <= S.p && e.due >= P().meta.last_day);
  if (acc) tg.push(`Risk accepted until ${fd(acc.due)}`);
  return tg.slice(0, 3);
}
/* B4: plain-English "how this score came about" lines for the family header */
const rh = x => Math.floor(x + 0.5 + 1e-9);   /* ROUND_HALF_UP for non-negative numbers */
function bigSwing(fr, code, x){   /* a building block that moved a lot: which of its metrics changed color (CTO review, 3 Nov 2026) */
  if (!x || x.delta == null || Math.abs(x.delta) < 30) return '';
  const ch = D.metrics.filter(m => m.block === code).map(m => [m, fr.metrics[m.id]]).filter(([m, y]) => y && SCORED.includes(y.status) && SCORED.includes(y.prior_status) && y.status !== y.prior_status);
  if (!ch.length) return '';
  return `${ch.length === 1 ? 'One metric' : ch.length + ' metrics'} changed color: ${ch.map(([m, y]) => `${m.id} ${y.prior_status} → ${y.status}`).join(', ')}`;
}
function trustWhy(fr){
  const ls = D.blocks.filter(l => fr.blocks[l.code].score != null);
  if (fr.trust == null) return `Needs ${NEED_BLOCKS() === 1 ? '1 measured building block' : NEED_BLOCKS() + ' measured building blocks'}; ${ls.length ? ls.length + ' measured so far' : 'none measured so far'}`;
  if (!ls.length) return '';
  const avg = rh(ls.reduce((a, l) => a + fr.blocks[l.code].score, 0) / ls.length), red = ls.filter(l => fr.blocks[l.code].status === 'Red').map(l => l.name);
  const capped = red.length && avg > CAP().red_block_trust && fr.trust === CAP().red_block_trust;
  if (!capped && ls.length === D.blocks.length) return '';                      // nothing to add: the score is the plain average
  let t = `Average of ${plural(ls.length, 'building block', 'building blocks')}${ls.length < D.blocks.length ? ` (${D.blocks.length - ls.length} not scored)` : ''}`;
  if (capped) t += `, capped at ${CAP().red_block_trust} because ${red.length === 1 ? red[0] + ' is' : red.length === 2 ? red.join(' and ') + ' are' : red.length + ' building blocks are'} Red`;
  return t;
}
/* ---------- D-78 / B3: Where to focus selection, "Which ones", Explain, Challenge ---------- */
const FOC = {which:new Set(), chOpen:null, sent:{}, bubAll:new Set()};     // what the reader has open on the family page; keys are period|family|metric
const focKey = (fid, id) => `${S.p}|${fid}|${id}`;
const canSeeItems = () => true;               // owner, 9 Nov 2026: whoever is logged in can drill into the data (the server sends each person only the families they may see)             // D-88: Tech Risk, and the family lead on their own family page (the only family page they can open)
function dropSize(id, x, t){                                // how far the metric moved in the worse direction since last month, as a share of its Green-to-Red span (counts: share of the denominator)
  const m = met(id); if (x.provisional) return 0;
  if (isPF(m)) { if (x.numerator == null || x.prior_numerator == null) return 0;
    const d = (Math.round(x.denominator) - Math.round(x.numerator)) - (Math.round(x.prior_denominator) - Math.round(x.prior_numerator));
    return d > 0 ? d / Math.max(1, Math.round(x.denominator)) : 0; }
  if (x.value == null || x.prior_value == null || m.higher_is_better == null) return 0;
  const w = +((m.higher_is_better ? x.prior_value - x.value : x.value - x.prior_value)).toFixed(1); if (w <= 0) return 0;
  const span = t && t.green != null && t.red != null ? Math.abs(t.green - t.red) : 0;
  return span ? w / span : w / 100;
}
function pickFocus(fr, p){                                  // at most four, in priority order; the rest stay in All metrics
  const order = id => D.metrics.findIndex(m => m.id === id), ents = Object.entries(fr.metrics).filter(([, x]) => x.status === 'Red' || x.status === 'Amber');
  const dz = ([id, x]) => dropSize(id, x, p.thresholds[id]), byDrop = (a, b) => (dz(b) - dz(a)) || order(a[0]) - order(b[0]);
  const t1 = ents.filter(([, x]) => x.status === 'Red' && x.prior_status !== 'Red').sort(byDrop);   // no comparable last month (new or redefined metric) counts as new
  const t2 = ents.filter(([, x]) => x.status === 'Red' && x.override && !t1.some(e => e[1] === x)).sort(byDrop);
  const tc = ents.filter(([, x]) => x.status === 'Red' && !t1.some(e => e[1] === x) && !t2.some(e => e[1] === x) && x.history && x.history.length >= 3 && streak(x.history) >= 3).sort(byDrop);   // Red three months running (owner review, 5 Nov 2026)
  const t3 = ents.filter(e => !t1.includes(e) && !t2.includes(e) && !tc.includes(e) && dz(e) > 0).sort(byDrop);
  const all = [...t1.map(e => [...e, 'new']), ...t2.map(e => [...e, 'auto']), ...tc.map(e => [...e, 'chronic']), ...t3.map(e => [...e, 'drop'])];
  return {shown: all.slice(0, 4), more: Math.max(0, all.length - 4)};
}
/* ---------- the data behind a metric (owner, 9 Nov 2026) ----------
   One table per metric with its own key details (config/metrics.json counting.columns), built by the back end into
   evidence.json (entry.table: columns, rows with cells, attention, team_key, link). Items that pull the number down
   come first. The first 10 rows show, then "Show all"; "Contributing" (ATT below) narrows it; "Download this table" gets
   the same rows as a CSV. Used under a metric row (See the data) and in the per-team drill-down. */
const TBL = {allv:new Set(), pg:{}};         // tables showing All (else Contributing), and each table's page
/* The words for the items behind a result (owner, 9 Nov 2026: neutral, not negative). Change them here; the
   downloads' column name is ATTENTION_LABEL in backend/trust/evidence.py. */
const ATT = {label:'Contributing', sum:n => `${nfmt(n)} contributing to the result, listed first`, none:'none contributing'};
const ROWS_SHOWN = 10;
function itemTable(fid, mid, e, team){
  const t = e && e.table;
  if (!t || !t.rows.length) return '<p class="cap" style="margin:0">No item detail for this metric this month.</p>';
  const k = `${fid}|${mid}|${team || ''}`, all = team ? t.rows.filter(r => r.team_key === team) : t.rows;
  if (!all.length) return '<p class="cap" style="margin:0">No items for this team.</p>';
  const it = (e.items[0] || {}).item_type || 'item', noun = n => n === 1 ? it : it + 's';
  /* owner, 9 Nov 2026: Contributing is the default view (worst first, ranked by the back end); All on request */
  const nAtt = all.filter(r => r.attention).length, onlyAtt = nAtt > 0 && !TBL.allv.has(k);
  const rows = onlyAtt ? all.filter(r => r.attention) : all, N = rows.length;
  const pages = Math.max(1, Math.ceil(N / ROWS_SHOWN)), pg = Math.min(TBL.pg[k] || 0, pages - 1);
  const shown = S.snap ? rows : rows.slice(pg * ROWS_SHOWN, (pg + 1) * ROWS_SHOWN);
  const filt = S.snap || !nAtt || nAtt === all.length ? '' : `<span class="tbf noprint" role="group" aria-label="Which rows to show"><button type="button" class="sm" data-act="tbl-view" data-v="c" data-k="${esc(k)}" data-dd="tc:${esc(k)}" aria-pressed="${onlyAtt}">${ATT.label} ${nfmt(nAtt)}</button><button type="button" class="sm" data-act="tbl-view" data-v="a" data-k="${esc(k)}" data-dd="ta:${esc(k)}" aria-pressed="${!onlyAtt}">See all ${nfmt(all.length)}</button></span>`;
  const sum = `${nfmt(all.length)} ${noun(all.length)}${team ? ` from ${esc(subLabel(team))}` : ''} · ${nAtt ? ATT.sum(nAtt) : ATT.none}`;
  const ty = t.types || [], cell = (c, j, r) => j ? (ty[j] === 'date' && c ? `<span class="nw">${fd(c)}</span>` : esc(c)) || '<span class="muted">—</span>' : safeLink(r.link) ? `<a href="${esc(safeLink(r.link))}" target="_blank" rel="noopener"><b>${esc(c)}</b></a>` : `<b>${esc(c)}</b>`;
  const dash = '<span class="muted">—</span>', ppl = (r, f) => (r.who || []).length ? r.who.map(f).join('') : dash;
  const person = w => `<div class="wh"><b>${esc(w.name || w.sam || w.email)}</b>${w.name && w.sam ? `<span class="cap">${esc(w.sam)}</span>` : ''}${(w.name || w.sam) && w.email ? `<span class="cap">${esc(w.email)}</span>` : ''}</div>`;
  /* contributing rows keep the metric’s color (owner, 9 Nov 2026): Red or Amber; a Green metric's stay neutral */
  const mst = ((((P().families || {})[fid] || {}).metrics || {})[mid] || {}).status, tint = mst === 'Red' ? ' att r' : mst === 'Amber' ? ' att a' : ' att';
  const body = shown.map(r => `<tr${r.attention ? ` class="${tint.trim()}"` : ''}>${r.cells.map((c, j) => `<td>${cell(c, j, r)}</td>`).join('')}`
    + `<td class="dtl">${esc(r.detail) || dash}</td><td>${ppl(r, person)}</td><td>${(r.who || []).some(w => w.l4 || w.l3) ? r.who.map(w => `<div class="wh">${w.l4 ? `<span>L4 ${esc(w.l4)}</span>${w.l4_email ? `<span class="cap">${esc(w.l4_email)}</span>` : ''}` : ''}${w.l3 ? `<span class="cap">L3 ${esc(w.l3)}</span>` : ''}</div>`).join('') : dash}</td><td class="nw">${r.as_of ? fd(r.as_of) : dash}</td></tr>`).join('');
  const from = pg * ROWS_SHOWN + 1, to = Math.min(N, (pg + 1) * ROWS_SHOWN);
  const pager = S.snap || pages < 2 ? '' : `<span class="pgr" role="group" aria-label="Pages"><button type="button" class="sm" data-act="tbl-pg" data-d="-1" data-k="${esc(k)}" data-dd="pp:${esc(k)}" ${pg === 0 ? 'disabled' : ''} aria-label="Previous ${ROWS_SHOWN} rows">‹ Previous</button><span class="cap" aria-live="polite">${nfmt(from)}–${nfmt(to)} of ${nfmt(N)} · page ${pg + 1} of ${pages}</span><button type="button" class="sm" data-act="tbl-pg" data-d="1" data-k="${esc(k)}" data-dd="pn:${esc(k)}" ${pg >= pages - 1 ? 'disabled' : ''} aria-label="Next ${ROWS_SHOWN} rows">Next ›</button></span>`;
  const dl = canDl(fid) && !S.snap ? `<a class="btnlink sm" href="/api/items/${encodeURIComponent(S.p)}/${encodeURIComponent(fid)}/${encodeURIComponent(mid)}.csv?${team ? 'team=' + encodeURIComponent(team) + '&' : ''}by=${encodeURIComponent(LIVE.by || '')}" download>Download this table (.csv)</a>` : '';
  return `<div class="itb"><div class="itbh"><span class="cap">${sum}</span>${filt}</div>
    <div class="ddscroll"><table class="dt ddt2 itt"><caption class="sr-only">The data behind ${esc(met(mid).name)}${onlyAtt ? `: the ${ATT.label.toLowerCase()} items, worst first` : ''}</caption><thead><tr>${t.columns.map(h => `<th>${esc(h)}</th>`).join('')}<th>Detail</th><th>Person</th><th>Managers (L4, L3)</th><th>As of</th></tr></thead><tbody>${body}</tbody></table></div>
    ${pager || dl ? `<div class="itbf noprint">${pager}${dl ? `<span>${dl}</span>` : ''}</div>` : ''}</div>`;
}
/* ---------- the opened row on the family page (locked look, 15 Nov 2026) ----------
   In this order: the items (where they sit by team, then the items), a row of buttons, and "How this was scored",
   which is closed until its button is pressed. */
const FAMHOW = new Set();                         // rows whose "How this was scored" is open (period|family|metric)

/* The short count shown next to the percentage: "24 of 27 releases". */
function famBriefCount(metric, result){
  if (result.numerator == null || result.denominator == null) return '';
  const wording = COUNTS[metric.id];
  const counted = Math.round(result.numerator);
  const total = Math.round(result.denominator);
  if (isPF(metric)) return countText(metric, result);
  if (metric.id === 'TR-02') return `${nfmt(counted)} of ${nfmt(total)} hygiene checks`;
  if (wording && wording.verb_one) return `${nfmt(counted)} of ${nfmt(total)} ${total === 1 ? wording.den_one : wording.den_many}`;
  return countText(metric, result);
}
/* The Result cell: the percentage first, then the brief count. Pass/fail metrics are already a count. */
function famResultCell(metric, result){
  if (result.status === 'Not Tier 0/1') return '<span class="res st-Not-Tier-0-1">Not applicable</span>';
  const provisionalMark = result.provisional ? '*' : '';
  const statusClass = `st-${result.status.replace(/ /g, '-')}`;
  const headline = `<span class="res ${statusClass}">${resTxt(metric, result)}${provisionalMark}</span>`;
  if (isPF(metric)) return headline;
  const count = famBriefCount(metric, result);
  return count ? `${headline}<span class="famcount"> · ${esc(count)}</span>` : headline;
}
/* Where the items sit by team (the buttons filter the item list below), and the item list itself. */
function famItemsBlock(fid, metricId, result, loading){
  const metric = met(metricId);
  const filterKey = 'l|' + metricId;
  const teamFilter = DDS.tf[filterKey];
  const where = heldCell(fid, metric, loading);
  const hasWhere = where.indexOf('bubs') !== -1 || where.indexOf('skel') !== -1;
  const clear = teamFilter && !S.snap ? `<span class="famfilter noprint"><span class="cap">Showing the items for ${esc(subLabel(teamFilter))}</span> <button type="button" class="sm" data-act="dd-clear" data-dd="c:${filterKey}">Show all teams</button></span>` : '';
  const whereHtml = hasWhere ? `<div class="famwhere"><span class="cap">Where they sit by team</span>${where}${clear}</div>` : '';
  let itemsHtml;
  if (!canSeeItems()) itemsHtml = '<p class="cap" style="margin:0">Item-level detail is for Tech Risk and the L3 team’s own people.</p>';
  else if (EV.state === 'idle' || EV.state === 'loading') itemsHtml = '<p class="cap" role="status" style="margin:0">Loading…</p>';
  else if (EV.state === 'fail') itemsHtml = '<p class="cap" style="margin:0">Item detail couldn’t be loaded. Reload the page to try again.</p>';
  else {
    const evidence = EV.data[S.p] && EV.data[S.p][fid] && EV.data[S.p][fid][metricId];
    itemsHtml = itemTable(fid, metricId, evidence, teamFilter);
  }
  return `${whereHtml}<div class="whp" id="whp-${metricId}" role="region" aria-label="The data behind ${esc(metric.name)}">${itemsHtml}</div>`;
}
/* The row of buttons under the items. */
function famButtons(fid, metricId){
  if (S.snap) return '';
  const rowKey = focKey(fid, metricId);
  const howOpen = FAMHOW.has(rowKey);
  const explainOpen = S.form === metricId && S.formWhere === 'a';
  const challengeOpen = FOC.chOpen === rowKey;
  const metricName = esc(met(metricId).name);
  const mayRespond = !isCTO() && may('comment', fid);
  const how = `<button type="button" class="sm fambtn" data-act="fam-how" data-m="${metricId}" aria-expanded="${howOpen}" aria-controls="how-${metricId}">How this was scored</button>`;
  const dictionary = `<button type="button" class="sm fambtn" data-act="dict-open" data-id="${metricId}">Metric dictionary</button>`;
  const explain = mayRespond ? `<button type="button" class="sm fambtn" data-act="open" data-m="${metricId}" data-w="a" aria-expanded="${explainOpen}" aria-label="Explain this number: ${metricName}">Explain this number</button>` : '';
  const challenge = mayRespond ? `<button type="button" class="sm fambtn" data-act="foc-ch" data-id="${metricId}" data-dd="c|${metricId}" aria-expanded="${challengeOpen}" aria-controls="chf-${metricId}" aria-label="Challenge this number: ${metricName}">Challenge it</button>` : '';
  return `<div class="fambtns noprint">${how}${dictionary}${explain}${challenge}</div>`;
}
/* The source file's as-of date for a metric: the accepted file that feeds it, else the items' own date. */
function famAsOf(fid, metricId){
  const feedingFile = (P().submissions || []).find(file => file.status === 'Accepted' && (file.metrics || []).includes(metricId));
  if (feedingFile && feedingFile.data_as_of) return {feed:feedingFile.feed, date:feedingFile.data_as_of.slice(0, 10)};
  const evidence = famEv(fid), entry = evidence && evidence[metricId];
  const dates = entry && entry.table ? entry.table.rows.map(row => row.as_of).filter(Boolean).sort() : [];
  return dates.length ? {feed:null, date:dates[dates.length - 1]} : null;
}
/* Rows in the source file, before exclusions: every item the file holds for this family. Only known once the item detail has loaded. */
function famSourceRows(fid, metricId){
  const evidence = famEv(fid), entry = evidence && evidence[metricId];
  if (!entry) return null;
  const itemType = (entry.items[0] || {}).item_type || 'item';
  return {count:entry.items.length, itemType};
}
function famFirmSourceRows(metricId){
  const everyFamily = EV.state === 'ok' && EV.data[S.p];
  if (!everyFamily) return null;
  const present = Object.keys(EV.data[S.p]);
  const missing = D.families.filter(family => !present.includes(family.id));
  if (missing.length) return null;            // this person only sees some families: the firm figure is not known here
  const holders = present.map(key => EV.data[S.p][key][metricId]).filter(Boolean);
  return holders.length ? holders.reduce((total, entry) => total + entry.items.length, 0) : null;
}
/* "How this was scored": one tile per step with an arrow between tiles; each tile shows the whole firm and this family. */
function famHowScored(fid, metricId, result){
  const rowKey = focKey(fid, metricId);
  if (!FAMHOW.has(rowKey) || S.snap) return '';
  const metric = met(metricId);
  const firm = P().firm[metricId];
  const family = fam(fid);
  const dictionaryEntry = (D.dictionary.metrics || {})[metricId] || {};
  const source = famSourceRows(fid, metricId);
  const firmSourceRows = famFirmSourceRows(metricId);
  const asOf = famAsOf(fid, metricId);
  const largeShare = (P().large_share || {})[metricId];
  const largeTeamNote = largeShare && fam(largeShare.family) ? `<span class="cap">${esc(fam(largeShare.family).name)} holds ${num1(largeShare.percent)}% of the firm’s items</span>` : '';
  const tileRow = (label, text, note) => `<div class="famtilerow"><span class="cap">${label}</span><b>${text}</b>${note || ''}</div>`;
  const noun = source ? (source.count === 1 ? source.itemType : source.itemType + 's') : '';
  const sourceTile = `<div class="famtile"><h4>${esc(dictionaryEntry.source_system || 'Source file')}</h4>`
    + (firmSourceRows != null ? tileRow('Whole firm', `${nfmt(firmSourceRows)} ${noun}`) : '')
    + (source ? tileRow('This L3 team', `${nfmt(source.count)} ${noun}`) : '') + '</div>';
  const firmCount = firm && firm.numerator != null ? (isPF(metric) ? countText(metric, firm) : famBriefCount(metric, firm)) : '';
  const familyCount = result.numerator != null ? (isPF(metric) ? countText(metric, result) : famBriefCount(metric, result)) : '';
  const countedTile = `<div class="famtile"><h4>What was counted</h4>`
    + tileRow('Whole firm', esc(firmCount) || '—', largeTeamNote) + tileRow('This L3 team', esc(familyCount) || '—') + '</div>';
  const firmResult = firm && firm.value != null ? fv(metric, firm.value) : (isPF(metric) && firm && firm.numerator != null ? countText(metric, firm) : '—');
  const familyResult = `${resTxt(metric, result)}${result.provisional ? '*' : ''} · ${famStatus(result)}`;
  const resultTile = `<div class="famtile"><h4>Result</h4>` + tileRow('Whole firm', esc(firmResult)) + tileRow('This L3 team', esc(familyResult)) + '</div>';
  const arrow = '<span class="famarrow" aria-hidden="true">→</span>';
  const asOfLine = asOf ? `<p class="cap famasof">Source file${asOf.feed ? ` (${esc(asOf.feed)})` : ''} as of ${fd(asOf.date)}</p>` : '';
  return `<div class="famhow" id="how-${metricId}" role="region" aria-label="How ${esc(metric.name)} was scored for ${esc(family.name)}"><div class="famtiles">${sourceTile}${arrow}${countedTile}${arrow}${resultTile}</div>${asOfLine}</div>`;
}
function challengeForm(fid, id){
  if (FOC.chOpen !== focKey(fid, id) || S.snap || !may('comment', fid)) return '';
  return `<form class="cf chf" id="chf-${id}" data-m="${id}" data-f="${fid}" aria-label="Challenge this number: ${esc(met(id).name)}"><label for="chr-${id}"><b>What looks wrong?</b></label>
    <select id="chr-${id}" required><option>Wrong data</option><option>Wrong team or app</option><option>Exception not applied</option><option>Other</option></select>
    <label for="cht-${id}" style="margin-top:8px"><b>Tell us more</b> (plain text, up to 600 characters)</label><textarea id="cht-${id}" maxlength="600" required></textarea>
    ${(`${byField('margin-top:8px')}`)}
    <p class="cap" style="margin:6px 0 8px">Goes to Tech Risk. Nothing changes in the numbers until they have looked.</p>
    <button class="pri" type="submit">Send to Tech Risk</button> <button type="button" data-act="foc-ch-cancel" data-id="${id}">Cancel</button></form>`;
}
function focusSent(fid, id){
  const lc = ((LIVE.comments[S.p] || []).filter(c => !c.reply_to && c.family === fid && c.metric === id));
  const sx = FOC.sent[focKey(fid, id) + '|ex'] || lc.some(c => c.kind === 'explanation'), sc = FOC.sent[focKey(fid, id) + '|ch'] || lc.some(c => c.kind !== 'explanation');
  const line = (t, k) => `<p class="cap focst" id="foc-st-${k}-${id}" role="status" tabindex="-1" style="margin:6px 0 0">${t}</p>`;
  return (sx ? line('Explanation added. It shows on the Scorecard for the CTO and leadership.', 'ex') : '')
    + (sc ? line(`Sent to Tech Risk. You'll see the outcome here.`, 'ch') : '');
}
/* ---------- family page metrics table (owner, 6 Nov 2026) ----------
   One row per measured metric, worst first (Red, Amber, Green, then the rest; within Red the Where to focus order:
   newly Red, automatic Red rule, chronic, biggest drop). Rows carry a soft tint of their status and a solid strip on
   the left, so color is never the only signal. Every column sorts (the generic sorter; a row's detail panel stays
   with it). The block tiles above filter it. ▸ opens a panel under the row: what is outstanding, what is needed,
   Which ones, Explain, Challenge, what the family said, and the drill-down. */
const FAMT = {open:new Set(), blk:null};          // open rows (period|family|metric) and the block filter {f, b}
const ST_RANK = {Red:1, Amber:2, Green:3, 'Info only':4};
const ST_CLS = {Red:'r', Amber:'a', Green:'g'};
function famStatus(y){ return y.status === 'Not Tier 0/1' ? 'No Tier 0/1 apps' : y.status === 'DNR' ? 'No data' : y.status === 'N/A' ? 'Not scored' : y.status; }
function famRowOpen(fid, id){
  const k = focKey(fid, id);
  return FAMT.open.has(k) || FOC.which.has(k) || FOC.chOpen === k || (S.form === id && S.formWhere === 'a') || DDS.l1.has('l|' + id)
    || !!FOC.sent[k + '|ex'] || !!FOC.sent[k + '|ch'];
}
function famTable(fid, fr, p, f, loading){
  const all = (() => {
    const o = id => D.metrics.findIndex(m => m.id === id), pf = {};
    // the full Where to focus order, not only its first four
    const ents = Object.entries(fr.metrics), dz = ([id, x]) => dropSize(id, x, p.thresholds[id]);
    const isNew = x => x.status === 'Red' && x.prior_status !== 'Red', isChr = x => x.history && x.history.length >= 3 && streak(x.history) >= 3;
    ents.forEach(([id, x]) => { pf[id] = x.status !== 'Red' ? 9 : isNew(x) ? 0 : x.override ? 1 : isChr(x) ? 2 : 3; });
    return (a, b) => ((ST_RANK[a[1].status] || 9) - (ST_RANK[b[1].status] || 9)) || (pf[a[0]] - pf[b[0]]) || (dz(b) - dz(a)) || (o(a[0]) - o(b[0]));
  })();
  const blk = FAMT.blk && FAMT.blk.f === fid && !S.snap ? FAMT.blk.b : null;
  const ms = D.metrics.filter(m => metState(m.id) === 'measured' && (!blk || m.block === blk));
  const ents = ms.map(m => [m.id, fr.metrics[m.id]]).filter(([, y]) => y).sort(all);
  const bname = c => (D.blocks.find(l => l.code === c) || {}).name || c;
  const rowsH = ents.map(([id, y]) => {
    const m = met(id), t = p.thresholds[id], st = famStatus(y), sc = ST_CLS[y.status] || 'n', k = focKey(fid, id), open = !S.snap && famRowOpen(fid, id);
    const tags = SCORED.includes(y.status) ? cardTags(fid, id, y).slice(0, 2) : [];
    if (y.status === 'Red' && y.history && y.history.length >= 3 && streak(y.history) >= 3 && !tags.some(x => /chronic/i.test(x))) tags.unshift(`Chronic Red · ${streak(y.history)} months in a row`);
    const res = famResultCell(m, y);
    const tog = S.snap ? '' : `<button type="button" class="sm rtog noprint" data-act="row-tog" data-m="${id}" aria-expanded="${open}" aria-controls="rd-${id}" aria-label="${open ? 'Hide' : 'Show'} the detail for ${esc(m.name)}">${open ? '▾' : '▸'}</button>`;
    const main = `<tr class="mrow s-${sc}" id="mrow-${id}" tabindex="-1" data-mrow="${id}"><td class="famblock" data-sv="${esc(bname(m.block))}">${esc(bname(m.block))}</td>
      <td><span class="nm">${esc(m.name)}</span>${tags.length ? `<div class="ftags">${tags.map(x => `<span class="tag">${esc(x)}</span>`).join('')}</div>` : ''}</td>
      <td data-sv="${y.value == null ? '' : y.value}">${res}</td><td>${mdelta(m, y)}</td><td class="tc">${tog}</td></tr>`;
    if (!open) return main;
    const toReachGreen = needLine(id, y, t);
    const limit = t && m.scored ? limitText(m, t, true) : '';
    const lead = [toReachGreen, limit].filter(Boolean).join(' · ');
    const detail = `${lead ? `<div class="c3">${esc(lead)}</div>` : ''}${famItemsBlock(fid, id, y, loading)}${famButtons(fid, id)}${famHowScored(fid, id, y)}${S.form === id && S.formWhere === 'a' && may('comment', fid) ? formHTML(id) : ''}${challengeForm(fid, id)}${focusSent(fid, id)}${famSaysLines(fid, id)}`;
    return main + `<tr class="subrow rdet s-${sc}" id="rd-${id}"><td colspan="5">${detail}</td></tr>`; }).join('');
  const wanted = D.blocks.filter(l => !blk || l.code === blk).map(l => { const pl = bWantedLine(D.metrics.filter(m => m.block === l.code)); return pl ? `<b>${esc(l.name)}:</b> ${pl}` : ''; }).filter(Boolean);
  const notes = [];
  if (f.tier01 != null && (!blk || blk === 'RES')) { const tl = tierLine(f); if (tl) notes.push(`<b>Resiliency:</b> ${tl}`); }
  const provs = ms.filter(m => fr.metrics[m.id] && fr.metrics[m.id].provisional);
  if (provs.length) notes.push(`* ${monthOf(fr.metrics[provs[0].id].carried_from)} results reused — ${[...new Set(provs.map(m => m.provider))].join(' and ')}’s ${monthOf(S.p)} data was not received`);
  const anyOpen = !S.snap && ents.some(([id]) => famRowOpen(fid, id));
  const tools = S.snap ? '' : `<span class="noprint ftools">${blk ? `<span class="fchip">Showing ${esc(bname(blk))} only</span>` : ''}${anyOpen ? `<button type="button" class="sm" data-act="row-close-all">Close all</button>` : ''}</span>`;
  const head = `<thead><tr><th>Building block</th><th>Metric</th><th>Result</th><th>${PRIOR[S.p] ? 'Since ' + priorName() : 'Change'}</th><th><span class="sr-only">Detail</span></th></tr></thead>`;
  const table = ents.length ? `<div class="ftwrap"><table class="dt lt ft"><caption class="sr-only">${esc(f.name)} metrics. Click a column head to sort.</caption><colgroup><col class="cb" style="width:15%"><col style="width:40%"><col style="width:27%"><col style="width:12%"><col style="width:6%"></colgroup>${head}<tbody>${rowsH}</tbody></table></div>`
    : `<p class="muted">${blk ? `Nothing measured in ${esc(bname(blk))} yet.` : 'Nothing measured yet.'}</p>`;
  return `<section class="grp" aria-labelledby="h-all">${tools}<h2 id="h-all">Metrics</h2>${table}
    ${wanted.length ? `<p class="cap" style="margin:8px 0 0">${wanted.join(' · ')}</p>` : ''}${notes.length ? `<p class="cap" style="margin:4px 0 0">${notes.join(' · ')}</p>` : ''}</section>`;
}
/* ---------- family top row (locked look, 15 Nov 2026): what improved, and where we can help ---------- */
const FTOP = {all:false};
const FAM_RANK = {Red:0, Amber:1, Green:2};
function famImproved(fid){        // better since last month: a better color first, then the biggest move
  const fr = P().families[fid], out = []; if (!PRIOR[S.p]) return out;
  D.metrics.forEach(m => { const x = fr.metrics[m.id]; if (!x || x.provisional || FAM_RANK[x.status] == null) return;
    const up = FAM_RANK[x.prior_status] != null ? FAM_RANK[x.status] - FAM_RANK[x.prior_status] : 0;
    let d = null;
    if (isPF(m)) { if (x.numerator != null && x.prior_numerator != null) d = (Math.round(x.prior_denominator) - Math.round(x.prior_numerator)) - (Math.round(x.denominator) - Math.round(x.numerator)); }
    else if (x.value != null && x.prior_value != null) d = m.higher_is_better ? x.value - x.prior_value : x.prior_value - x.value;
    if (up > 0 || (up === 0 && d > 0)) out.push({mid:m.id, up, d}); });
  return out.sort((a, b) => b.up - a.up || (b.d || 0) - (a.d || 0));
}
function famHelp(fid){
  const fr = P().families[fid], red = D.metrics.filter(m => fr.metrics[m.id] && fr.metrics[m.id].status === 'Red').map(m => m.id), out = [];
  const isNew = id => PRIOR[S.p] && fr.metrics[id].prior_status != null && fr.metrics[id].prior_status !== 'Red';
  const nw = PRIOR[S.p] ? red.filter(isNew) : red, ch = red.filter(id => !nw.includes(id) && (fr.metrics[id].history || []).length >= 3 && streak(fr.metrics[id].history) >= 3);
  if (nw.length) out.push({ids:nw, label:PRIOR[S.p] ? `newly Red ${nw.length === 1 ? 'metric' : 'metrics'}` : `Red ${nw.length === 1 ? 'metric' : 'metrics'}`});
  if (ch.length) out.push({ids:ch, label:`${ch.length === 1 ? 'metric' : 'metrics'} Red for 3+ months`});
  return out;
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act^="fam-"]'); if (!b) return; const a = b.dataset.act, fid = parse()[1];
  if (a === 'fam-all') { FTOP.all = !FTOP.all; S.keepScroll = true; render(); const n = document.querySelector('[data-act="fam-all"]'); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'fam-how') { const rowKey = focKey(fid, b.dataset.m);
    if (FAMHOW.has(rowKey)) FAMHOW.delete(rowKey); else FAMHOW.add(rowKey);
    evLoad(); S.keepScroll = true; render();
    const again = document.querySelector(`[data-act="fam-how"][data-m="${b.dataset.m}"]`); if (again) again.focus({preventScroll:true}); return; }
  if (a !== 'fam-line') return;
  const ms = b.dataset.ms.split(','); FAMT.blk = null;
  ms.forEach(id => { const k = focKey(fid, id); FAMT.open.add(k); FOC.which.add(k); }); evLoad(); S.keepScroll = true; render();
  const r = document.getElementById('mrow-' + ms[0]); if (!r) return;
  r.scrollIntoView({block:'center', behavior: window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'}); r.focus({preventScroll:true});
});
function vFamily(fid){
  evLoad();
  const p = P(), fr = p.families[fid], f = fam(fid), [tc,,tw] = stInfo(fr.status), canEdit = !S.snap && !isCTO(), fl = !!roleFam();
  S.lastFam = fid;
  const loading = EV.state === 'idle' || EV.state === 'loading';
  const picker = roleFam() ? '' : `<label class="cap" for="fpick">L3 team&nbsp;</label><select id="fpick" aria-label="Choose L3 team">${D.families.map(x => `<option value="${x.id}" ${x.id === fid ? 'selected' : ''}>${x.name}</option>`).join('')}</select>`;
  /* scoreboard strip */
  const pids = Object.keys(D.periods).sort(), pv = pids[pids.indexOf(S.p) - 1], pf = pv && D.periods[pv].families[fid];
  const SF = {g:'var(--gf)', a:'var(--af)', r:'var(--rf)'};
  /* Top row and building block boxes (locked look, 15 Nov 2026). A box is off-white with the score in its status
     color; along the bottom a pale band is the full scale (its top edge is 100) and the darker fill is the score for
     each of the last three months. A month with no data has no fill and an empty ring. */
  const DK = {g:'var(--gt)', a:'var(--at)', r:'var(--rt)'};
  const series = (cur, prior, dPrior) => [prior != null && dPrior != null ? prior - dPrior : null, PRIOR[S.p] && prior != null ? prior : null, cur];
  let anyRing = false;
  const band = (c, vals) => { const H = 44, y = v => (H * (1 - v / 100)).toFixed(1), xs = [0, 50, 100];
    let start = 2; while (start > 0 && vals[start - 1] != null) start--;
    const run = xs.slice(start).map((x, k) => [x, vals[start + k]]);
    const shape = run.length > 1 ? `<polygon points="${run.map(([x, v]) => `${x},${y(v)}`).join(' ')} 100,${H} ${run[0][0]},${H}" fill="${DK[c]}"/>` : `<rect x="86" y="${y(vals[2])}" width="14" height="${(H * vals[2] / 100).toFixed(1)}" fill="${DK[c]}"/>`;
    if (start > 0) anyRing = true;
    const mn = [FULLMON[(+S.p.slice(5) - 3 + 12) % 12], pv ? monthOf(pv) : FULLMON[(+S.p.slice(5) - 2 + 12) % 12], monthOf(S.p)];
    return `<div class="band" style="background:${SF[c]}"><svg viewBox="0 0 100 ${H}" preserveAspectRatio="none" role="img" aria-label="Score, last three months: ${vals.map((v, k) => mn[k] + ' ' + (v == null ? 'no data' : v)).join(', ')}">${shape}</svg>${xs.slice(0, start).map((x, k) => `<span class="ring" style="left:${k === 0 ? 6 : 44}%" aria-hidden="true"></span>`).join('')}</div>`; };
  /* no change = nothing drawn (owner, 15 Nov 2026) */
  const arrow = d => !d || !PRIOR[S.p] ? '' : `<span class="dl ${d > 0 ? 'up' : 'dn'}" aria-label="${d > 0 ? 'up' : 'down'} ${Math.abs(d)} since ${priorName()}">${d > 0 ? '▲' : '▼'}${Math.abs(d)}</span>`;
  const segs = D.blocks.map(l => { const x = fr.blocks[l.code], [c] = stInfo(x.status);
    const fon = FAMT.blk && FAMT.blk.f === fid && FAMT.blk.b === l.code, fat = S.snap ? '' : ` data-act="blkf" data-b="${l.code}" role="button" tabindex="0" aria-pressed="${fon}" aria-label="${fon ? 'Show all metrics' : 'Show only ' + esc(l.name) + ' metrics'}"`;
    if (x.score == null) return `<div class="sgm ns${fon ? ' fon' : ''}"${fat}><div class="in"><div class="nm">${l.name}</div><div class="sl"><span class="sc ns">${x.status === 'Not Tier 0/1' ? 'No Tier 0/1 apps' : D.metrics.filter(m => m.block === l.code).every(isWanted) ? 'Wanted' : 'Not scored'}</span></div></div></div>`;
    return `<div class="sgm${fon ? ' fon' : ''}"${fat}><div class="in"><div class="nm">${l.name}</div><div class="sl"><span class="sc"${DK[c] ? ` style="color:${DK[c]}"` : ''}>${scoreNum(x.score, x.status, x.provisional)}</span><span class="sr-only">${stInfo(x.status)[2]}. </span>${arrow(x.delta)}</div></div>${DK[c] ? band(c, series(x.score, pf && pf.blocks[l.code].score, pf && pf.blocks[l.code].delta)) : ''}</div>`; }).join('');
  const imp = S.snap ? [] : famImproved(fid), help = S.snap ? [] : famHelp(fid);
  const impLine = it => { const m = met(it.mid), x = fr.metrics[it.mid], ct = countText(m, x), val = fv(m, x.value);
    return `<button type="button" class="tl" data-act="fam-line" data-ms="${it.mid}"><span><b>${esc(m.name)}</b><span class="tl2">${isPF(m) ? (ct || val) : ct ? `${ct} = ${val}` : val}${it.d > 0 ? ` · <span class="dl up">▲${isPF(m) ? it.d : num1(it.d)}</span>${m.unit === '%' && !isPF(m) ? ' points' : ''}` : ''}</span></span></button>`; };
  const upBox = !imp.length ? '' : `<div class="tb"><h2><span class="dl up">▲</span> Improved since ${priorName()}</h2>${(FTOP.all ? imp : imp.slice(0, 3)).map(impLine).join('')}${imp.length > 3 ? `<button type="button" class="sm tmore" data-act="fam-all" aria-expanded="${FTOP.all}">${FTOP.all ? 'Show top 3' : `Show all ${imp.length}`}</button>` : ''}</div>`;
  const helpBox = !help.length ? '' : `<div class="tb"><h2><span class="dl dn">▼</span> Where to focus</h2>${help.map(h => `<button type="button" class="tl" data-act="fam-line" data-ms="${h.ids.join(',')}"><span class="cnt">${h.ids.length}</span><span><b>${esc(h.label)}</b><span class="tl2">${esc(h.ids.map(id => met(id).name).join(', '))}</span></span></button>`).join('')}</div>`;
  const tq = trendVals(fid), why = trustWhy(fr);
  const strip = `<div class="ctop ftop"><div class="tb sbt${S.snap ? '' : (FAMT.blk && FAMT.blk.f === fid ? '' : ' fon')}"${S.snap ? '' : ` data-act="blkf" data-b="ALL" role="button" tabindex="0" aria-pressed="${!(FAMT.blk && FAMT.blk.f === fid)}" aria-label="Show all metrics"`}><div class="k">${esc(f.name)} TRUST · ${esc(p.meta.label)}</div>
      <div class="vrow"><div class="v"${DK[tc] ? ` style="color:${DK[tc]}"` : ''}>${fr.trust == null ? '<span style="font-size:24px;line-height:1.2;display:block">Not scored yet</span>' : S.snap ? scoreTxt(fr.trust, fr.status, false) : scoreNum(fr.trust, fr.status, false)}</div>${tq && tq.length >= 2 && fr.trust != null ? `<div class="tq">${quarterHTML(tq, fr.incomplete, true, '')}</div>` : ''}</div>
      ${fr.trust == null ? '' : `<span class="sr-only">${tw}. </span>`}${fr.delta && PRIOR[S.p] ? `<div class="st">${arrow(fr.delta)} since ${priorName()}</div>` : ''}${why ? `<div class="why">${why}</div>` : ''}</div>${upBox}${helpBox}</div>
    <div class="bbx" role="group" aria-label="The building blocks">${segs}</div>${anyRing ? '<p class="bbkey"><span class="ring" aria-hidden="true"></span>Month with no data</p>' : ''}`;
  const order = id => D.metrics.findIndex(m => m.id === id);
  /* action bar */
  const owe = Object.entries(fr.metrics).filter(([id, x]) => x.status === 'Red' && x.prior_status !== 'Red' && cover(fid, id).k === 'none').sort((a, b) => order(a[0]) - order(b[0]));
  const names = owe.map(([id]) => met(id).name), nameTxt = names.length > 2 ? `${names.slice(0, 2).join(', ')} and ${names.length - 2} more` : names.join(' and ');
  const needTxt = (S.snap || isCTO() || !may('comment', fid)) ? '' : owe.length
    ? `What we need from you: explain ${owe.length} newly Red ${owe.length === 1 ? 'metric' : 'metrics'} — ${esc(nameTxt)}.`
    : `What we need from you: nothing outstanding.`;
  const bar = S.snap ? '' : `<div class="abar noprint">${needTxt ? `<span class="need1${owe.length ? ' open' : ''}">${needTxt}</span>` : ''}${may('download', fid) ? `<button type="button" class="sm" data-act="dl-open" data-dl="open" aria-expanded="${DL.open}" aria-controls="dlp">Download the data</button>` : ''}${snapBtn()}</div>${!may('comment', fid) && roSay() ? `<p class="cap noprint" style="margin:6px 0 0">${isCTO() || (ME && !ME.read_only) ? 'Read only: explanations and queries are added on team pages by the L3 team’s own people and Tech Risk.' : roSay()}</p>` : ''}`;
  const {shown} = pickFocus(fr, p);
  /* explanations */
  const cs = famCards(fid);
  /* an empty box is one line (design review, 5 Nov 2026); the add control is the Explain form on the first Where to focus card */
  const addOne = !S.snap && !isCTO() && may('comment', fid) && shown.length ? ` · <button type="button" class="sm noprint" data-act="row-explain" data-m="${shown[0][0]}">Add one</button>` : '';
  const expl = cs.length ? `<section class="grp" aria-labelledby="h-exp"><h2 id="h-exp">${fl ? 'Your explanations' : 'Explanations'}</h2><div class="xc">${cs.map(c => `<figure class="xcard"><blockquote>“${esc(c.text)}”</blockquote><figcaption>${esc(c.who)} · ${fd(c.date)} · ${scopeLbl(c)}</figcaption></figure>`).join('')}</div></section>`
    : `<section class="grp" aria-label="${fl ? 'Your explanations' : 'Explanations'}"><p class="muted" style="margin:0"><b>${fl ? 'Your explanations' : 'Explanations'}:</b> No explanations yet${addOne}</p></section>`;
  const ents = D.entries.filter(e => e.family_id === fid && e.period <= S.p && e.kind !== 'Note');
  const lvRows = (lvThreads(S.p).filter(x => x.t.family === fid).map(x => { const t = x.t, q = t.kind === 'query', mn = t.metric && MET_IDS.has(t.metric) ? met(t.metric).name : '';
    return `<tr><td>${q ? 'Q' : 'A'}-${esc(String(t.id))}</td><td class="wrapok"><b>${q ? 'Data query' : 'Action'}</b>${t.metric ? ' on ' + (mn ? esc(mn) + ' (' + esc(t.metric) + ')' : esc(t.metric)) : ''}: ${esc(t.text)}</td><td>${esc(t.by || '')}</td><td>${esc(x.status)}</td><td>—</td></tr>`; }));
  const notes = !(ents.length || lvRows.length) ? `<p class="muted" style="margin:0"><b>Actions, queries and accepted risks:</b> None recorded yet${addOne}</p>` : `<section class="panel nt" aria-label="Actions and accepted risks"><h2 style="font-size:16px">Actions, queries and accepted risks</h2>${ents.length || lvRows.length ? `<table class="dt nowr"><colgroup><col style="width:10%"><col style="width:40%"><col style="width:20%"><col style="width:16%"><col style="width:14%"></colgroup><thead><tr><th>Ref</th><th>What</th><th>Owner</th><th>Status</th><th>Due</th></tr></thead><tbody>${ents.map(e =>
    `<tr><td>${e.id}</td><td class="wrapok"><b>${e.kind}</b>${e.metric_id ? ' on ' + esc(met(e.metric_id).name) + ' (' + e.metric_id + ')' : ''}: ${esc(e.text)}</td><td>${esc(e.owner)}</td><td>${e.status}${e.due && e.status !== 'Done' && e.due < p.meta.last_day && e.kind === 'Action' ? ' (overdue)' : ''}</td><td>${e.due ? fd(e.due) : '—'}</td></tr>`).join('')}${lvRows.join('')}</tbody></table>` : '<p class="muted" style="margin:0">None recorded.</p>'}</section>`;
  return `<div class="fam${S.snap ? ' sheet' : ''}">${S.snap ? snapTop() : ''}<div class="titlebar"><div><h1>${esc(f.name)}</h1><div class="sub">L3 team · ${P().meta.label}</div></div><div class="noprint">${picker}</div></div>
    ${strip}
    ${bar}${DL.open && may('download', fid) ? dlPanel(fid) : ''}${famTable(fid, fr, p, f, loading)}${tl4Section(fid, loading)}${risksRaisedPanel(fid)}${expl}<div class="grp">${notes}</div>
    <p class="cap" style="margin-top:14px">${PRIOR[S.p] ? `Change since ${priorName()}: ▲ better, ▼ worse, ${FLAT_MARK} no change.` : 'This is the first month in the scorecard, so there is nothing to compare with yet.'}${Object.values(fr.metrics).some(x => x.provisional) ? '<br>* Provisional: the provider’s data was not received.' : ''}</p>${unmappedNote('family')}${S.snap ? `<p class="cap">${SNAP_CAPTION}</p>` : ''}</div>`;
}
const MET_IDS = new Set(D.metrics.map(m => m.id));
/* ---------- This family's own risk assessment (owner, 16 Nov 2026) ----------
   Risks are raised so the right treatment can be agreed; they are never compared between teams. So this is drawn on a
   family's OWN page only, from the Risk site's newest assessment of each of the family's groups (/api/risk/family/<id>).
   Nothing here is on the CTO view, Firm position, a table of families or the watch list. Nothing Elevated = nothing drawn.
   It shows; it changes no score. */
const RFL = {};                               // family id -> {state: 'loading' | 'ok' | 'fail', groups: []}
const RFL_LEVEL = {LOW:'Low', MEDIUM:'Medium', HIGH:'High', CRITICAL:'Critical'};
function rflLoad(fid){
  if (RFL[fid]) return;
  RFL[fid] = {state:'loading', groups:[]};
  api('/api/risk/family/' + encodeURIComponent(fid))
    .then(r => { RFL[fid] = {state:'ok', groups:r.groups || [], line:r.rated_with_current_rules || ''}; })
    .catch(() => { RFL[fid] = {state:'fail', groups:[]}; })
    .then(() => { S.keepScroll = true; if (document.querySelector('.fam')) render(); });
}
const rflDay = iso => iso ? fd(String(iso).slice(0, 10)) : '';
function rflSignoff(g){
  if (g.signoff && g.signoff.state === 'Signed off') return `Signed off by ${esc(g.signoff.by)} on ${rflDay(g.signoff.at)}`;
  if (g.signoff && g.signoff.state === 'Sent back') return 'Sent back for changes';
  return g.status === 'Submitted' ? 'Submitted, not signed off yet' : esc(g.status);
}
const rflAgain = g => g.signoff && g.signoff.rated_again ? ' · rated again with today’s rules since sign-off' : '';
function rflCard(risk){
  return `<li class="rflc"><div class="rflh"><span class="rflchip">Elevated</span><b>${esc(risk.name)}</b></div>`
    + (risk.description ? `<p class="rfld">${esc(risk.description)}</p>` : '')
    + `<p class="rflr">${esc(RFL_LEVEL[risk.likelihood] || risk.likelihood)} likelihood · ${esc(RFL_LEVEL[risk.impact] || risk.impact)} impact</p></li>`;
}
/* Every L4 team and the L3 team have a results page on the Risk site. */
const rflTeamPage = teamId => '/risk/#/team/' + encodeURIComponent(teamId);
function rflGroup(g){
  const head = `<div class="rflg"><b>${esc(g.name)}</b> <span class="cap">Assessed ${rflDay(g.assessed_at)} · ${rflSignoff(g)}${rflAgain(g)} · <a href="${esc(rflTeamPage(g.id))}">Open this team’s results on the Risk site</a></span></div>`;
  return head + `<ul class="rfl">${g.elevated.map(rflCard).join('')}</ul>`;
}
function risksRaisedPanel(fid){
  if (S.snap) return '';
  rflLoad(fid);
  const groups = (RFL[fid] || {}).groups || [];
  const withRisks = groups.filter(g => g.assessed && g.elevated.length);
  const notYet = groups.filter(g => !g.assessed);
  if (!withRisks.length && !notYet.length) return '';
  const lines = notYet.map(g => `<p class="rflnone">${esc(g.name)} has not been assessed yet. <a href="${esc(rflTeamPage(g.id))}">Open the team on the Risk site</a>.</p>`).join('');
  return `<section class="grp rflsec" aria-labelledby="h-rfl"><h2 id="h-rfl">Risks we have raised</h2>
    <p class="cap" style="margin:2px 0 8px;max-width:none">From the risk assessments of this L3 team’s L4 teams. These are risks to agree a treatment for, so the right help can follow. They don’t change any score.</p>
    ${(RFL[fid] || {}).line ? `<p class="cap rflline" style="margin:0 0 8px;max-width:none">${esc(RFL[fid].line)}</p>` : ''}
    ${withRisks.map(rflGroup).join('')}${lines}
    <p class="cap rflline" style="margin:8px 0 0;max-width:none"><a href="${esc(rflTeamPage(fid))}">Open this L3 team’s results on the Risk site</a></p></section>`;
}
function formHTML(id){
  return `<form class="cf" data-m="${id}" aria-label="Add explanation"><label for="cft"><b>Explanation</b> (plain text, up to 600 characters)</label>
    <textarea id="cft" maxlength="600" required></textarea><div class="cap"><span id="cfc">0</span> / 600</div>
    ${MET_IDS.has(id) ? `<fieldset><legend>What is it about?</legend><label><input type="radio" name="sc" value="m" checked> ${esc(met(id).name)} (${id})</label><label><input type="radio" name="sc" value="l"> ${esc(BLK(met(id).block).name)} as a whole</label><label><input type="radio" name="sc" value="f"> The whole L3 team</label></fieldset>` : ''}
    <fieldset><legend>What is this?</legend><label><input type="radio" name="ty" value="explain" checked> This explains the score</label>
    <label><input type="radio" name="ty" value="query"> This is a data query</label><label><input type="radio" name="ty" value="action"> This needs an action</label></fieldset>
    ${(`${byField()}`)}
    <p class="cap" style="margin:0 0 8px">Visible to the CTO and leadership on the Scorecard.</p>
    <button class="pri" type="submit">Submit explanation</button> <button type="button" data-act="cancel">Cancel</button></form>`;
}
function commentaryAppendix(only){
  const p = P(), fams = D.families.filter(f => !only || f.id === only);
  const out = fams.map(f => {
    const es = D.entries.filter(e => e.family_id === f.id && (e.period === S.p || (e.period < S.p && e.status !== 'Done')));
    const cs = COMMENTS.filter(c => c.p === S.p && c.fid === f.id);
    if (!es.length && !cs.length) return '';
    return `<h3 style="margin-top:10px">${esc(f.name)}</h3><ul style="margin:2px 0;padding-left:20px">${es.map(e => `<li>${e.kind}${e.metric_id ? ' on ' + esc(met(e.metric_id).name) + ' (' + e.metric_id + ')' : ''}, ${esc(e.owner)}, ${e.status}${e.due ? ', due ' + fd(e.due) : ''}: ${esc(e.text)}</li>`).join('')}
      ${cs.map(c => `<li>${{explain:'Explanation', query:'Data query', action:'Action requested'}[c.type]}${c.mid ? ' on ' + esc(met(c.mid).name) + ' (' + c.mid + ')' : ''}, team lead: ${esc(c.text)}</li>`).join('')}</ul>`; }).join('');
  return out || '<p class="muted">No commentary recorded this month.</p>';
}
/* The story the CTO wants from the firm position (owner, 5 Nov 2026): the firm's score and whether it moved,
   why it differs from the families (scored from every row received, not an average), which building blocks
   and metrics are holding it back and where that concentrates, and what isn't measured yet. */
function firmStoryHTML(){
  const p = P();
  const ft = p.firm_trust, fams = Object.entries(p.families).filter(([, fr]) => fr.trust != null);
  const fname = id => esc((D.families.find(f => f.id === id) || {name:id}).name);
  const out = [];
  if (ft == null) {
    out.push(`No firm TRUST score for ${esc(p.meta.label)} yet: ${p.firm_blocks && Object.values(p.firm_blocks).some(b => b.score != null) ? 'too few building blocks are scored firm-wide.' : 'no building block is scored firm-wide yet. Scores appear once the files below arrive and the scorecard is updated.'}`);
  } else {
    const st = p.firm_status && SCORED.includes(p.firm_status) ? p.firm_status : (ft >= METHOD.band_green_from ? 'Green' : ft >= METHOD.band_amber_from ? 'Amber' : 'Red');
    const chg = (p.firm_incomplete || !PRIOR[S.p]) ? '' : p.firm_trust_delta ? `, ${p.firm_trust_delta > 0 ? 'up' : 'down'} ${Math.abs(p.firm_trust_delta)} since ${priorName()}` : `, unchanged since ${priorName()}`;
    out.push(`Firm TRUST is <b>${ft}</b> (${st})${chg}.`);
    if (fams.length) {
      const vals = fams.map(([, fr]) => fr.trust), lo = Math.min(...vals), hi = Math.max(...vals);
      const where = ft < lo ? `below every L3 team’s score (the lowest is ${lo})` : ft > hi ? `above every L3 team’s score (the highest is ${hi})` : `between the L3 teams’ scores (${lo} to ${hi})`;
      out.push(`That is ${where}: the firm is scored from every row the firm received, so the biggest L3 teams weigh most${p.firm_capped ? ', and an automatic Red rule in one L3 team holds the firm Red too' : ''}.`);
    }
    const reds = D.blocks.filter(l => p.firm_blocks && p.firm_blocks[l.code] && p.firm_blocks[l.code].status === 'Red');
    const greens = D.blocks.filter(l => p.firm_blocks && p.firm_blocks[l.code] && p.firm_blocks[l.code].status === 'Green');
    if (reds.length) {
      const why = reds.map(l => { const ms = D.metrics.filter(m => m.block === l.code && p.firm[m.id] && p.firm[m.id].status === 'Red');
        const drivers = ms.map(m => { const worst = Object.entries(p.families).filter(([, fr]) => fr.metrics[m.id] && fr.metrics[m.id].status === 'Red').map(([id]) => fname(id));
          return `${esc(m.name)}${worst.length ? ` (Red in ${listOf(worst)})` : ''}`; });
        return `${esc(l.name)} is Red${drivers.length ? ` on ${listOf(drivers)}` : ''}`; });
      out.push(`Holding it back: ${listOf(why)}.`);
    }
    if (greens.length) out.push(`${listOf(greens.map(l => esc(l.name)))} ${greens.length === 1 ? 'is' : 'are'} Green firm-wide.`);
  }
  const wanted = D.blocks.filter(l => D.metrics.filter(m => m.block === l.code).every(m => metState(m.id) !== 'measured'));
  const notRec = (p.dnr || []).filter(pr => D.metrics.some(m => m.provider === pr && metState(m.id) === 'measured'));
  if (wanted.length && ft != null) out.push(`${listOf(wanted.map(l => esc(l.name)))} ${wanted.length === 1 ? 'isn’t' : 'aren’t'} measured yet (no data source), so the firm score rests on ${D.blocks.length - wanted.length} of ${D.blocks.length} building blocks.`);
  if (notRec.length) out.push(`${listOf(notRec.map(esc))}’s ${monthOf(S.p)} file did not arrive, so ${notRec.length === 1 ? 'its' : 'their'} metrics show No data.`);
  return `<section class="story" aria-label="The firm in brief"><p>${out.join(' ')}</p></section>`;
}

function firmTable(){
  const p = P();
  const row = m => {
    const f = p.firm[m.id], t = p.thresholds[m.id], missing = f.value == null;
    const st = !m.scored ? 'Info only' : missing ? 'Not scored' : f.status;
    const x = {value:f.value, prior_value:f.prior_value, provisional:false, numerator:f.numerator, denominator:f.denominator, prior_numerator:f.prior_numerator, prior_denominator:f.prior_denominator};
    const ct = isPF(m) ? (missing ? '' : pfUnder(m, f)) : f.numerator != null ? countText(m, f) : '';
    return `<tr><td><span class="nm">${esc(m.name)} <span class="id">(${m.id})</span></span></td><td><span class="res st-${st.replace(/ /g, '-')}">${m.wanted_shown ? 'Wanted' : missing ? 'No data' : isPF(m) ? countText(m, f) : fv(m, f.value)}</span>${ct ? `<div class="cap">${ct}</div>` : ''}${t && m.scored ? `<div class="cap">${limitText(m, t)}</div>` : ''}</td>
      <td>${missing ? '—' : mdelta(m, x)}</td><td>${isPF(m) ? 'Pass or fail, no tolerance' : t && m.scored ? (m.higher_is_better ? '≥ ' : '≤ ') + fv(m, t.green) : '—'}${f.status === 'N/A' && f.reason && !missing ? `<div class="cap">${esc(f.reason)}</div>` : ''}</td></tr>`; };
  const groups = D.blocks.map(l => {
    const ms = D.metrics.filter(m => m.block === l.code), fb = (p.firm_blocks || {})[l.code] || {}, plLine = bWantedLine(ms);
    const sc = fb.score == null ? 'Not scored' : `${fb.score} · ${stInfo(fb.status)[2]}`;
    return `<tr class="bhead"><td colspan="4"><b class="ln">${esc(l.name)}</b> <span class="lq">${esc(l.question)}</span><span class="bsc">${sc}</span></td></tr>`
      + ms.filter(m => metState(m.id) === 'measured').map(row).join('')
      + (plLine ? `<tr class="plrow"><td colspan="4" class="cap">${plLine}</td></tr>` : ''); }).join('');
  return `<table class="dt firmt"><colgroup><col style="width:38%"><col style="width:26%"><col style="width:18%"><col style="width:18%"></colgroup><thead><tr><th>Metric</th><th>Firm result</th><th>${PRIOR[S.p] ? 'Change since ' + priorName() : 'Change'}</th><th>Green tolerance</th></tr></thead><tbody>${groups}</tbody></table>`;
}
const SNAP_CAPTION = 'Printed from the TRUST scorecard. The official figures are the ones in TRUST for this month.';
const snapBtn = () => `<button class="sm" data-act="snap">Print view</button>`;
function snapTop(){
  const p = P();
  return `<div class="snapnote noprint" role="note"><b>Print view.</b> Everything is expanded. To print, use your browser’s Print (Ctrl+P, or Cmd+P on a Mac). <button class="sm" data-act="snap-exit">Back to the live view</button></div>
  <div class="snapmark"><span class="cap" style="font-size:12px">Results as of ${fd(p.meta.last_day)} 23:59 · ${esc(D.env_label || 'Live data')}</span></div>`;
}
function snapScorecard(){
  const p = P();
  return `<div class="sheet">${snapTop()}<h1>TRUST scorecard: ${p.meta.label}</h1>${heroHTML()}${heatmapHTML(true)}<div class="pb">${watchHTML(true)}</div>
    <h2 class="pb">L3 team commentary</h2>${commentaryAppendix()}
    <p class="cap" style="margin-top:14px">Method: ${pointsWords(' / ')} → building block = average → TRUST = average of the building block scores, whole numbers. A metric scores by its color, not by how far it is from a line: a result just past the Red limit scores 0, the same as one far past it. Any Red metric caps its building block at ${CAP().red_metric_block}; an automatic Red rule caps it at ${CAP().automatic_red_block}. Any Red building block caps TRUST at ${CAP().red_block_trust}. Score bands: ${bandWords().replace(/ · /g, ', ')}. Tolerance thresholds (Green tolerance, Red limit) apply to individual metrics and are shown above. * provisional: prior month result reused. Details in the Glossary.</p><p class="cap">${SNAP_CAPTION}</p></div>`;
}
const indCount = k => Object.values(D.dictionary.metrics).filter(x => x.indicator_type === k).length;
