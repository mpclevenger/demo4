/* The frame around every page: header, sidebar, which page to show, and the clicks and keys shared by all pages. */
"use strict";
/* ---------- chrome, routing ---------- */
const SBI = {
  console:'<path d="M3 4h12M3 9h12M3 14h8"/>', datasources:'<ellipse cx="9" cy="5" rx="6" ry="2.5"/><path d="M3 5v8c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5V5M3 9c0 1.4 2.7 2.5 6 2.5s6-1.1 6-2.5"/>',
  datadict:'<rect x="3" y="3" width="12" height="12" rx="1.5"/><path d="M3 7h12M3 11h12M7 3v12"/>', scorecard:'<rect x="2.5" y="2.5" width="5.5" height="5.5"/><rect x="10" y="2.5" width="5.5" height="5.5"/><rect x="2.5" y="10" width="5.5" height="5.5"/><rect x="10" y="10" width="5.5" height="5.5"/>',
  'all-metrics':'<rect x="2.5" y="3.5" width="13" height="11" rx="1.5"/><path d="M2.5 7.5h13M2.5 11h13M7 7.5v7M11.5 7.5v7"/>',
  firm:'<path d="M3 15V9M7.5 15V3.5M12 15v-7M16 15V6"/>', family:'<circle cx="9" cy="5.5" r="2.5"/><path d="M3.5 15c0-3 2.5-5 5.5-5s5.5 2 5.5 5"/>', dictionary:'<path d="M4 2.5h8.5a1.5 1.5 0 0 1 1.5 1.5v11H5.5A1.5 1.5 0 0 1 4 13.5zM4 13.5A1.5 1.5 0 0 1 5.5 12H14"/>',
  settings:'<path d="M3 5h12M3 9h12M3 13h12"/><circle cx="6.5" cy="5" r="1.6" fill="currentColor"/><circle cx="11.5" cy="9" r="1.6" fill="currentColor"/><circle cx="8" cy="13" r="1.6" fill="currentColor"/>',
  lost:'<circle cx="8" cy="8" r="4.5"/><path d="M11.3 11.3L15 15M6.5 8h3M8 6.5v3"/>',
  'metric-intake':'<path d="M9 3v12M3 9h12"/><rect x="2.5" y="2.5" width="13" height="13" rx="2"/>',
  validation:'<path d="M9 2l6 2.5v4.5c0 3.4-2.5 5.8-6 7-3.5-1.2-6-3.6-6-7V4.5z"/><path d="M6.2 9l2 2 3.6-3.8"/>', glossary:'<circle cx="4" cy="5" r="1"/><circle cx="4" cy="9" r="1"/><circle cx="4" cy="13" r="1"/><path d="M7.5 5h7M7.5 9h7M7.5 13h7"/>'};
let SBC = null;      // sidebar collapsed (set from sessionStorage, else width)
function sbCollapsed(){
  if (SBC === null) { try { const v = sessionStorage.getItem('sbCollapsed'); if (v === '1' || v === '0') SBC = v === '1'; } catch (_) {} if (SBC === null) SBC = window.innerWidth < 1366; }
  return SBC;
}
function sidebar(route){
  const p = P(), fl = roleFam(), cons = isTR(), col = sbCollapsed();
  const defFam = S.lastFam || fl || (Object.entries(p.families).sort((a, b) => a[1].trust - b[1].trust)[0] || [])[0];   // none yet: no family link
  const item = (h, t, k) => `<li><a class="sbi" href="${href(h)}" title="${esc(t)}" ${k === route ? 'aria-current="page"' : ''}><svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${SBI[k]}</svg><span class="lb">${esc(t)}</span></a></li>`;
  const grp = (id, t, items) => items.length ? `<h2 class="sbh" id="sb-${id}"><span class="${col ? 'sr-only' : ''}">${t}</span></h2><ul aria-labelledby="sb-${id}">${items.join('')}</ul>` : '';
  const run = cons ? [item('/console', 'This month', 'console'), item('/datasources', 'Data sources', 'datasources'), item('/settings', 'Scoring settings', 'settings')] : [];
  const sc = fl ? [item('/scorecard', 'CTO view', 'scorecard'), item('/family/' + fl, fam(fl).name, 'family'), item('/firm', 'Firm position', 'firm'), item('/all-metrics', 'All metrics', 'all-metrics')] : [item('/scorecard', 'CTO view', 'scorecard'), item('/firm', 'Firm position', 'firm'), item('/all-metrics', 'All metrics', 'all-metrics'), ...(defFam ? [item('/family/' + defFam, 'L3 teams', 'family')] : [])];
  const gov = [item('/dictionary', 'Metric dictionary', 'dictionary'), item('/datadict', 'Data dictionary', 'datadict'), ...(cons ? [item('/lost', 'Lost and found', 'lost'), item('/metric-intake', 'Metric intake', 'metric-intake'), item('/validation', 'Validation checks', 'validation')] : []), item('/glossary', 'Glossary', 'glossary')];
  $('#side').className = 'side' + (col ? ' col' : '');
  $('#side').innerHTML = `<button type="button" class="sbtog" data-act="sb-toggle" aria-expanded="${!col}" aria-label="${col ? 'Expand sidebar' : 'Collapse sidebar'}" title="${col ? 'Expand sidebar' : 'Collapse sidebar'}">${col ? '' : '<span>Collapse</span>'}<svg viewBox="0 0 18 18" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 3L5 9l6 6"/></svg></button>
    <nav aria-label="Main">${grp('run', 'Run', run)}${grp('score', 'Scorecard', sc)}${grp('gov', 'Governance', gov)}</nav>`;
}
function chrome(route){
  const p = P(), fl = roleFam(), cons = isTR(), pick = !ME || ME.can.run_month;
  const roleOpts = `<option value="cto" ${isCTO() ? 'selected' : ''}>CTO</option><optgroup label="Team lead (choose team)">${D.families.map(f => `<option value="fl:${f.id}" ${S.r === 'fl:' + f.id ? 'selected' : ''}>Team lead: ${f.name}</option>`).join('')}</optgroup><option value="tr" ${cons ? 'selected' : ''}>Tech Risk</option>`;
  const m = p.meta;
  $('#chrome').innerHTML = `<header class="top"><div class="wrap"><h1 class="sitet"><a class="mark" href="${href('/')}">TRUST scorecard</a></h1><span class="env">${esc(D.env_label || 'Live data')}</span><span class="sp"></span><span id="appsm"></span>
    <select id="month" aria-label="Month">${Object.values(D.periods).map(x => `<option value="${x.meta.id}" ${x.meta.id === S.p ? 'selected' : ''}>${x.meta.label}</option>`).join('')}</select>
    ${pick ? `<select id="role" aria-label="View as">${roleOpts}</select>` : `<span class="cap" title="${esc(ME.role_names.join(', '))}">${esc(ME.name)}</span>`}</div></header>${D.test_env ? '<div class="banner noprint" role="note" style="margin:0;border-radius:0;background:#fff3cd;border-color:#8a5a00">TEST environment · synthetic data. Nothing here is real: the L3 teams, people, files and scores are made up so the site can be tried out.</div>' : ''}${(!(D.access && D.access.enforced)) ? '<div class="banner noprint" role="note" style="margin:0;border-radius:0">Access isn’t set up yet: anyone who reaches this page can see and do everything. Tech Risk sets this up before go-live.</div>' : ''}${ME && ME.read_only ? '<div class="banner noprint" role="note" style="margin:0;border-radius:0">Read only: auditors can see and download everything but can’t change anything.</div>' : ''}
    ${route === 'console' || route === 'datasources' ? `<div class="band-console"><div class="wrap"><b>Tech Risk console${route === 'datasources' ? ' · Data sources' : ''}</b><span>${m.label}${m.current_bd ? ' · Business day ' + m.current_bd : ''}</span></div></div>` : ''}`;
  sidebar(route);
  appsMenuMount(document.getElementById('appsm'), 'TRUST');
}
function parse(){
  if (!D.periods[S.p]) S.p = START_MONTH;
  if (ME && !ME.can.run_month && S.r !== ME.page_role) S.r = ME.page_role;
  if (!(S.r === 'cto' || S.r === 'tr' || (S.r.startsWith('fl:') && fam(S.r.slice(3))))) S.r = 'cto';
  const h = location.hash.slice(1) || '';
  if (h.startsWith('family-')) return ['family', h.slice(7)];
  if (h.startsWith('dictionary-')) return ['dictionary', h.slice(11)];
  if (h.startsWith('glossary-')) return ['glossary', h.slice(9)];
  if (h.startsWith('datadict-')) return ['datadict', h.slice(9)];
  if (h.startsWith('console-')) return ['console', h.slice(8)];
  if (h.startsWith('datasources-')) return ['datasources', h.slice(12)];
  return [h, undefined];
}
/* Printing is the browser's own (owner, 2 Nov 2026: TRUST makes no PDFs). Before the browser prints,
   open every collapsed section so nothing is hidden on paper; put them back afterwards. */
let PRINT_OPENED = [];
window.addEventListener('beforeprint', () => { PRINT_OPENED = [...document.querySelectorAll('details:not([open])')]; PRINT_OPENED.forEach(d => { d.open = true; }); });
window.addEventListener('afterprint', () => { PRINT_OPENED.forEach(d => { d.open = false; }); PRINT_OPENED = []; });
/* Tips: [data-tip] elements show one line on hover or focus (owner, 4 Nov 2026: keep it simple). Printing turns the
   tips on the page into numbered footnotes under the content, so paper says the same as the screen. */
const TIP = document.createElement('div'); TIP.className = 'tipbox'; TIP.id = 'tipbox'; TIP.setAttribute('role', 'tooltip'); TIP.hidden = true; document.body.appendChild(TIP);
let TIP_EL = null;
function showTip(el){
  const t = el.getAttribute('data-tip'); if (!t) return;
  TIP.textContent = t; TIP.hidden = false; TIP_EL = el; el.setAttribute('aria-describedby', 'tipbox');
  const r = el.getBoundingClientRect(), w = TIP.offsetWidth;
  TIP.style.left = Math.max(8, Math.min(window.scrollX + r.left, window.scrollX + document.documentElement.clientWidth - w - 8)) + 'px';
  TIP.style.top = (window.scrollY + r.bottom + 6) + 'px';
}
function hideTip(){ if (TIP_EL) TIP_EL.removeAttribute('aria-describedby'); TIP_EL = null; TIP.hidden = true; }
document.addEventListener('mouseover', e => { const el = e.target.closest && e.target.closest('[data-tip]'); if (el) { if (el !== TIP_EL) showTip(el); } else if (TIP_EL) hideTip(); });
document.addEventListener('focusin', e => { const el = e.target.closest && e.target.closest('[data-tip]'); if (el) showTip(el); });
document.addEventListener('focusout', () => hideTip());
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); });
document.addEventListener('keydown', e => { const t = e.target; if ((e.key === 'Enter' || e.key === ' ') && t.matches && t.matches('.sgm[data-act="blkf"], .sbt[data-act="blkf"]')) { e.preventDefault(); t.click(); } });
let TIP_NOTES = null;
window.addEventListener('beforeprint', () => {
  hideTip();
  const els = [...document.querySelectorAll('#app [data-tip]')].filter(el => el.offsetParent !== null);
  if (!els.length) return;
  TIP_NOTES = document.createElement('ol'); TIP_NOTES.className = 'tipnotes'; TIP_NOTES.setAttribute('aria-label', 'Notes');
  els.forEach((el, i) => { const n = document.createElement('sup'); n.className = 'tipn'; n.textContent = String(i + 1); el.appendChild(n);
    const li = document.createElement('li'); li.textContent = el.getAttribute('data-tip'); TIP_NOTES.appendChild(li); });
  $('#app').appendChild(TIP_NOTES);
});
window.addEventListener('afterprint', () => { document.querySelectorAll('#app .tipn').forEach(n => n.remove()); if (TIP_NOTES) TIP_NOTES.remove(); TIP_NOTES = null; });
function render(){
  pfSnap();
  liveLoad(S.p);
  let [route, arg] = parse(), fl = roleFam();
  keepView();
  const redirect = (r, a) => { location.replace(href('/' + r + (a ? '/' + a : ''))); };
  if (route === 'preread') return redirect('scorecard');
  if (route === 'method') return redirect('glossary');
  if (route === 'auditor') return redirect('validation');
  if (route === 'controls') return redirect('dictionary');
  if (!route) return redirect(fl ? 'family/' + fl : isTR() ? 'console' : 'scorecard');
  if (route === 'thresholds') return redirect('dictionary', 'table');
  if (route === 'dictionary' && (arg === 'table' || arg === 'proposals') && !isTR()) return redirect('dictionary');
  if (fl && (route === 'console' || route === 'datasources' || route === 'validation' || (route === 'family' && arg !== fl))) return redirect('family/' + fl);
  if ((route === 'console' || route === 'datasources' || route === 'validation') && !isTR()) return redirect('scorecard');
  if (route === 'family' && !fam(arg)) return redirect('scorecard');
  if ((route === 'lost' || route === 'settings' || route === 'metric-intake') && !isTR()) return redirect('scorecard');   // a Tech Risk page (owner, 15 Nov 2026)
  if (route === 'datasources' && arg && arg !== 'systems' && !(arg.startsWith('upload-') && inFeed(arg.slice(7)) && may('run_month'))) return redirect('datasources');
  if (route === 'dictionary' && arg && arg !== 'all' && arg !== 'table' && arg !== 'proposals' && !DX(arg)) return redirect('dictionary');
  if (!(route === 'dictionary' && arg === 'table')) DICT.panel = null;
  if (!(route === 'dictionary' && isTR())) { DICT.pf = false; DICT.pv = null; DICT.ret = null; }
  if (!(route === 'dictionary' && arg === 'proposals')) { DICT.pc = null; DICT.sentProp = null; }
  const y = window.scrollY, keep = S.keepScroll; S.keepScroll = false;
  if (route !== 'datasources') { IN.res = null; IN.msg = null; } else if (IN.res && (IN.res.pid !== S.p || !arg || arg !== 'upload-' + IN.res.feed)) IN.res = null;
  FPID = 0; chrome(route);
  $('#app').innerHTML = shellBar(route, arg) + ({dictionary:() => vDictionary(arg), scorecard:vScorecard, family:() => vFamily(arg), glossary:vGlossary, datadict:() => vDataDict(arg), lost:vLost, 'metric-intake':vMetricIntake, settings:vThresholds, firm:vFirm, 'all-metrics':vAllMetrics, console:vConsole, datasources:() => vDataSources(arg), validation:vAuditor}[route] || vScorecard)();
  { const here = location.hash; if (LIVE.route !== here) { if (LIVE.route !== undefined && !LIVE.busy) LIVE.msg = LIVE.err = null; LIVE.route = here; }
    if ((LIVE.msg || LIVE.err) && !document.getElementById('lvmsg')) $('#app').insertAdjacentHTML('afterbegin', liveMsgHTML()); }
  document.title = ('TRUST scorecard');
  window.scrollTo(0, keep ? y : 0);
  if (route === 'glossary' && arg) { const g = document.getElementById(arg); if (g) { g.scrollIntoView(); } }
  if (S.jumpTo && (route !== 'family' || arg !== S.jumpTo.f || Date.now() - S.jumpTo.at > 5000)) S.jumpTo = null;
  if (S.jumpTo) {             // from the CTO page's watch list (owner, 6 Nov 2026); kept for a few seconds, because the
    const j = S.jumpTo, row = document.getElementById('mrow-' + j.m);    // page draws again once the item details load
    if (row) { const d = row.closest('details'); if (d) d.open = true; row.classList.add('jump');
      if (!j.done) { j.done = true; row.scrollIntoView({block:'center'}); }
      row.focus({preventScroll:true}); } }
  if (IN.focus) { const k = IN.focus; IN.focus = null; const el = k === 'msg' ? document.getElementById('inmsg') : document.querySelector(`[data-act="in-upload"][data-f="${k.slice(4)}"]`); if (el) el.focus({preventScroll:true}); }
  dictFilter();
  if (route === 'lost') lfFilter();
  if (DICT.fv) { const n = document.querySelector(`[data-act=dict-view][data-v="${DICT.fv}"]`); DICT.fv = null; if (n) n.focus({preventScroll:true}); }
  if (DICT.focus) { const id = DICT.focus; DICT.focus = null; const card = $('#dict-card'), row = document.querySelector(`.dictrow[data-id="${id}"]`);
    if (card && (window.innerWidth < 1100 || card.getBoundingClientRect().top < 0)) { card.scrollIntoView(); const hd = card.querySelector('h2'); if (hd && window.innerWidth < 1100) hd.focus({preventScroll:true}); else if (row) row.focus({preventScroll:true}); }
    else if (row) row.focus({preventScroll:true}); }
}
function go(path){ const h = href(path); if (location.hash === h) render(); else location.hash = h; }
document.addEventListener('change', e => {
  if (e.target.id === 'month') { S.p = e.target.value; render0(); }
  if (e.target.id === 'role') { S.r = e.target.value; const fl = roleFam(); go(fl ? '/family/' + fl : isTR() ? '/console' : '/scorecard'); }
  if (e.target.id === 'fpick') go('/family/' + e.target.value);
  if (['lf-feed', 'lf-met', 'lf-st'].includes(e.target.id)) lfFilter();
});
function render0(){ const [r, a] = parse(); S.p = $('#month') ? $('#month').value : S.p; go('/' + r + (a ? '/' + a : '')); }
document.addEventListener('click', e => {
  if (!e.target.closest('.fsw')) closePops();
  const b = e.target.closest('[data-act]'); if (!b) return;
  const a = b.dataset.act;
  if (a === 'sb-toggle') { SBC = !sbCollapsed(); try { sessionStorage.setItem('sbCollapsed', SBC ? '1' : '0'); } catch (_) {} sidebar(parse()[0]); const t = document.querySelector('.sbtog'); if (t) t.focus(); return; }
  if (a === 'cn-month') { S.p = b.dataset.p; S.keepScroll = true; go('/console'); return; }
  
  if ((a.startsWith('lv-'))) { liveAct(a, b); return; }
  if (a === 'lf-claim') { LF.form = LF.form === b.dataset.k ? null : b.dataset.k; LF.msg = ''; S.keepScroll = true; render();
    const f = document.querySelector(`form.lff[data-k="${CSS.escape(b.dataset.k)}"] select, form.lff[data-k="${CSS.escape(b.dataset.k)}"] textarea`); if (f) f.focus({preventScroll:true}); return; }
  if (a === 'lf-cancel') { const k = LF.form; LF.form = null; LF.ferr = ''; S.keepScroll = true; render(); const t = document.querySelector(`[data-act=lf-claim][data-k="${CSS.escape(k || '')}"]`); if (t) t.focus(); return; }
  if (a === 'lf-clear') { Object.assign(LF, {q:'', feed:'', met:'', st:''}); ['lf-q', 'lf-feed', 'lf-met', 'lf-st'].forEach(id => { const n = $('#' + id); if (n) n.value = ''; }); lfFilter(); const q = $('#lf-q'); if (q) q.focus(); return; }
  if (a === 'lf-dec') { LF.dec = {id:+b.dataset.id, d:b.dataset.d}; LF.msg = ''; S.keepScroll = true; render(); const i = document.querySelector('form.lfd input[name=reason]'); if (i) i.focus({preventScroll:true}); return; }
  if (a === 'lf-dec-cancel') { LF.dec = null; S.keepScroll = true; render(); return; }
  
  if (a === 'go-fam') { go('/family/' + b.dataset.f); return; }
  if (a === 'blkf') { const fid = parse()[1], c = b.dataset.b; FAMT.blk = c === 'ALL' || (FAMT.blk && FAMT.blk.f === fid && FAMT.blk.b === c) ? null : {f:fid, b:c};
    secSave(); S.keepScroll = true; render(); const n = document.querySelector(`.sgm[data-b="${c}"]`) || document.querySelector('#h-all'); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'row-tog') { const k = focKey(parse()[1], b.dataset.m), was = famRowOpen(parse()[1], b.dataset.m);
    if (was) { FAMT.open.delete(k); FOC.which.delete(k); if (FOC.chOpen === k) FOC.chOpen = null; if (S.form === b.dataset.m) S.form = null; DDS.l1.delete('l|' + b.dataset.m); delete FOC.sent[k + '|ex']; delete FOC.sent[k + '|ch']; }
    else { FAMT.open.add(k); FOC.which.add(k); evLoad(); }     // the items table shows straight away (owner, 6 Nov 2026)
    S.keepScroll = true; render(); const n = document.querySelector(`[data-act="row-tog"][data-m="${b.dataset.m}"]`); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'row-close-all') { const pre = `${S.p}|${parse()[1]}|`;
    [FAMT.open, FOC.which].forEach(set => [...set].filter(k => k.startsWith(pre)).forEach(k => set.delete(k)));
    Object.keys(FOC.sent).filter(k => k.startsWith(pre)).forEach(k => delete FOC.sent[k]);
    if ((FOC.chOpen || '').startsWith(pre)) FOC.chOpen = null; S.form = null; [...DDS.l1].filter(k => k.startsWith('l|')).forEach(k => DDS.l1.delete(k));
    S.keepScroll = true; render(); const n = $('#h-all'); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'row-explain') { FAMT.open.add(focKey(parse()[1], b.dataset.m)); FOC.which.add(focKey(parse()[1], b.dataset.m)); evLoad(); FOC.chOpen = null; S.form = b.dataset.m; S.formWhere = 'a'; S.keepScroll = true; render(); const t = $('#cft'); if (t) t.focus(); return; }
  if (a === 'go-met') { S.jumpTo = {m:b.dataset.m, f:b.dataset.f, at:Date.now(), done:false}; FAMT.blk = null; go('/family/' + b.dataset.f); return; }
  if (a === 'dd-team') {
    const k = (b.dataset.w || 'l') + '|' + b.dataset.m; DDS.l1.add(k); DDS.tf[k] = b.dataset.t; evLoad(); DDS.focus = b.dataset.dd;
    secSave(); S.keepScroll = true; render(); secRestore(); ddFocus(); return; }
  if (a === 'dd-clear') {
    const k = b.dataset.dd.slice(2); delete DDS.tf[k]; DDS.focus = 'x:' + k;
    secSave(); S.keepScroll = true; render(); secRestore(); ddFocus(); return; }
  if (a === 'bub-more') { const set = FOC.bubAll, k = b.dataset.k;
    if (set.has(k)) set.delete(k); else set.add(k); DDS.focus = b.dataset.dd; secSave(); S.keepScroll = true; render(); secRestore(); ddFocus(); return; }
  if (a === 'dd-form') { DD.form = DD.form ? null : {}; DD.err = DD.msg = null; S.keepScroll = true; render(); const n = $('#dd-feed'); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'dd-form-cancel') { DD.form = null; DD.err = null; S.keepScroll = true; render(); return; }
  if (a === 'dd-decide') { DD.decide = {id:+b.dataset.id, d:b.dataset.d}; DD.err = DD.msg = null; S.keepScroll = true; render(); const n = document.querySelector('.ddf input[name=reason]'); if (n) n.focus({preventScroll:true}); return; }
  if (a === 'dd-decide-cancel') { DD.decide = {}; S.keepScroll = true; render(); return; }
  if (a === 'tbl-view' || a === 'tbl-pg') { const k = b.dataset.k;
    if (a === 'tbl-view') { if (b.dataset.v === 'a') TBL.allv.add(k); else TBL.allv.delete(k); TBL.pg[k] = 0; } else TBL.pg[k] = Math.max(0, (TBL.pg[k] || 0) + +b.dataset.d);
    DDS.focus = b.dataset.dd; secSave(); S.keepScroll = true; render(); secRestore(); ddFocus();
    if (a === 'tbl-pg' && b.disabled !== undefined) { const nb = document.querySelector(`[data-dd="${CSS.escape(b.dataset.dd)}"]`); if (nb && nb.disabled) { const o = document.querySelector(`[data-dd="${CSS.escape((b.dataset.d === '1' ? 'pp:' : 'pn:') + k)}"]`); if (o) o.focus({preventScroll:true}); } }
    return; }
  if (a === 'foc-ch') { const k = focKey(parse()[1], b.dataset.id); FOC.chOpen = FOC.chOpen === k ? null : k; S.form = null; S.keepScroll = true; render(); const t = document.getElementById('cht-' + b.dataset.id); if (t) t.focus(); else { const o = document.querySelector(`[data-dd="c|${b.dataset.id}"]`); if (o) o.focus({preventScroll:true}); } return; }
  if (a === 'foc-ch-cancel') { FOC.chOpen = null; S.keepScroll = true; render(); const o = document.querySelector(`[data-dd="c|${b.dataset.id}"]`); if (o) o.focus({preventScroll:true}); return; }
  if (a === 'dict-open') { DICT.focus = null; DICT.sent = null; go('/dictionary/' + b.dataset.id); return; }
  if (a === 'dl-open' || a === 'dl-close') { DL.open = a === 'dl-open' ? !DL.open : false; DL.msg = ''; S.keepScroll = true; render(); const t = document.querySelector('[data-dl="open"]'); if (a === 'dl-close' && t) t.focus(); else if (DL.open) { const h = $('#dlp-h'); const tb = document.querySelector('.dltab[aria-selected=true]'); if (tb) tb.focus({preventScroll:true}); } return; }
  if (a === 'dl-tab') { DL.tab = b.dataset.tab; DL.msg = ''; S.keepScroll = true; render(); const t = document.querySelector(`[data-dl="tab-${DL.tab}"]`); if (t) t.focus({preventScroll:true}); return; }
  if (a === 'dl-copy') {
    const fid = parse()[1], d = dlData(fid, 'scores'), say = t => { DL.msg = t; const el = $('#dl-msg'); if (el) el.textContent = t; };
    try { navigator.clipboard.writeText(toCsv(d.head, d.rows)).then(() => say('Copied'), () => say('Copy is not available in this browser')); } catch (_) { say('Copy is not available in this browser'); }
    return; }
  if (a === 'snap') { S.snap = true; render(); window.scrollTo(0, 0); return; }
  if (a === 'snap-exit') { S.snap = false; render(); return; }
  if (a === 'say') { const w = b.closest('.fsw'), was = w.classList.contains('pin'); closePops(); if (!was) { w.classList.add('pin'); b.setAttribute('aria-expanded', 'true'); placePop(w); } return; }
  if (a === 'dict-select') { if (DICT.form !== b.dataset.id) DICT.form = null; if (DICT.hist !== b.dataset.id) DICT.hist = null; DICT.sent = null; S.keepScroll = true; DICT.focus = b.dataset.id; go('/dictionary/' + b.dataset.id); return; }
  if (a === 'dict-view') { DICT.panel = null; DICT.focus = null; S.keepScroll = true; DICT.fv = b.dataset.v; DICT.pc = null; DICT.sentProp = null; go(b.dataset.v === 'table' ? '/dictionary/table' : b.dataset.v === 'proposals' ? '/dictionary/proposals' : '/dictionary'); return; }
  
  if (a === 'dict-hist') { DICT.hist = DICT.hist === b.dataset.id ? null : b.dataset.id; S.keepScroll = true; render(); const o = document.querySelector('[data-act=dict-hist]'); if (o) o.focus({preventScroll:true}); return; }
  if (a === 'dict-propose') { e.preventDefault && e.preventDefault(); DICT.form = b.dataset.id; DICT.sent = null; S.keepScroll = true; if (parse()[1] !== b.dataset.id) { go('/dictionary/' + b.dataset.id); return; } render(); const f = document.querySelector('.dictf select'); if (f) f.focus(); return; }
  if (a === 'dict-cancel') { DICT.form = null; S.keepScroll = true; render(); const f = document.querySelector('[data-act=dict-propose]'); if (f) f.focus(); return; }
  if (a === 'open') { FOC.chOpen = null; S.form = b.dataset.m; S.formWhere = b.dataset.w; S.keepScroll = true; render(); const t = $('#cft'); if (t) t.focus(); }
  if (a === 'in-upload') { IN.res = null; IN.msg = null; go('/datasources/upload-' + b.dataset.f); return; }
  if (a === 'in-cancel') { const f = (parse()[1] || '').replace(/^upload-/, ''); IN.res = null; IN.focus = 'row:' + f; go('/datasources'); return; }
  
  if (a === 'cancel') { S.form = null; S.keepScroll = true; render(); }
});
document.addEventListener('input', e => { if (e.target.id === 'lf-q') lfFilter(); if (e.target.id === 'dsearch') dictFilter(); if (e.target.id === 'cft') $('#cfc').textContent = e.target.value.length; });
document.addEventListener('submit', e => {
  const f = e.target.closest('.cf'); if (!f) return; e.preventDefault();
  if (f.classList.contains('chf')) { const fid = f.dataset.f, mid = f.dataset.m, why = f.querySelector('select').value, more = f.querySelector('textarea').value.trim();
    liveComment({by:liveName(f), family:fid, metric:mid, kind:'query', text:`Challenge (${why})${more ? ': ' + more : ''}`}, () => { FOC.sent[focKey(fid, mid) + '|ch'] = {reason:why}; FOC.chOpen = null; }); return; }
  if (f.classList.contains('dictf')) { const id = f.dataset.id, fe = f.elements, field = fe.f.value;
    apiPost('/api/proposals', {by:liveName(f), kind:'change', metric:id, title:`${id}: change to ${field.toLowerCase()}`, detail:{field, wording:fe.wording.value.trim(), reason:fe.reason.value.trim()}})
      .then(() => { LIVE.props = null; DICT.sent = id; DICT.form = null; DICT.err = null; }).catch(x => { DICT.err = x.message; }).finally(() => { S.keepScroll = true; render(); }); return; }
  
  if (f.dataset.kind === 'liveup') { liveUpload(f); return; }
  
  const t = f.querySelector('textarea').value.trim(); if (!t) return;
  const sc = (f.querySelector('input[name=sc]:checked') || {}).value || 'm', mm = f.dataset.m;
  { const ty = f.querySelector('input[name=ty]:checked').value, fid = roleFam() || parse()[1], where = S.formWhere;
    liveComment({by:liveName(f), family:fid, metric:sc === 'm' && MET_IDS.has(mm) ? mm : null, block:sc === 'l' && MET_IDS.has(mm) ? met(mm).block : null, kind:{explain:'explanation', query:'query', action:'action'}[ty], text:t},
      () => { if (where === 'a') FOC.sent[focKey(fid, mm) + '|ex'] = true; S.form = null; }); return; }
});
document.addEventListener('keydown', e => { const r = e.target.closest && e.target.closest('.dsrow'); if (r && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); r.click(); } });
document.addEventListener('keydown', e => {
  const tb = e.target.closest && e.target.closest('.dltab');
  if (tb && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) { const ts = [...document.querySelectorAll('.dltab')], n = ts[(ts.indexOf(tb) + (e.key === 'ArrowRight' ? 1 : ts.length - 1)) % ts.length]; e.preventDefault(); n.click(); return; }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && e.target.id === 'dsearch') { e.preventDefault(); e.target.value = ''; dictFilter(); return; }
  if (e.key === 'Escape') { const w = document.querySelector('.fsw.pin'); if (w) { const b = w.querySelector('.fsay'); closePops(); if (b) b.focus(); } return; }
  const r = e.target.closest && e.target.closest('.dictrow'); if (!r) return;
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); r.click(); }
  else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { const rs = [...document.querySelectorAll('.dictrow:not([hidden])')], n = rs[rs.indexOf(r) + (e.key === 'ArrowDown' ? 1 : -1)]; if (n) { e.preventDefault(); n.focus(); } }
});
document.addEventListener('mouseover', e => { const w = e.target.closest && e.target.closest('.fsw'); if (w) placePop(w); });
