/* Pieces every page draws with: status chips, scores, change arrows, links, and the data helpers behind them. */
"use strict";
/* ---------- small renderers ---------- */
// Resilient row on the family page (owner, 4 Nov 2026; not in the header): "X Tier 0/1 apps out of Y apps", ITDR application file.
function tierLine(f){
  const n = f.tier01_apps || 0, t = f.apps_total || 0;
  if (!t) return 'no apps in the ITDR application file';
  return `${nfmt(n)} Tier 0/1 ${n === 1 ? 'app' : 'apps'} out of ${nfmt(t)} ${t === 1 ? 'app' : 'apps'}`;
}
function stInfo(s){
  if (s === 'Green') return ['g','G','Green'];
  if (s === 'Amber') return ['a','A','Amber'];
  if (s === 'Red') return ['r','R','Red'];
  if (s === 'Info only') return ['i','','Information only'];
  if (s === 'Wanted') return ['i','','Wanted'];
  if (s === 'DNR') return ['n','','No data'];
  if (s === 'Not Tier 0/1') return ['n','','Not Tier 0/1'];
  return ['n','','Not scored'];
}
function scoreNum(score, s, prov){ const w = stInfo(s)[2]; return score == null ? 'Not scored' : `${score}${prov ? '*' : ''}<span class="sr-only"> ${w}${prov ? ', provisional' : ''}</span>`; }
function chip(s, text){ const [c,,w] = stInfo(s); return `<span class="chip ${c}">${text ?? w}</span>`; }
function scoreTxt(score, s, prov){ const [,k,w] = stInfo(s); return score == null ? 'Not scored' : `${k} ${score}${prov ? '*' : ''}`; }
const FLAT_MARK = '<span class="dl z flat" aria-label="no change"><svg width="14" height="8" viewBox="0 0 14 8" aria-hidden="true"><rect x="1" y="3" width="12" height="2.5" rx="1.25" fill="currentColor"/></svg></span>';

function mdelta(m, x){
  if (x.provisional) return `<span class="dl z">Reused from ${monthOf(x.carried_from)}</span>`;
  if (isPF(m)) {            // change in the count not yet done: fewer is better
    if (x.numerator == null || x.prior_numerator == null) return '<span class="dl z">No comparison</span>';
    const d = (Math.round(x.denominator) - Math.round(x.numerator)) - (Math.round(x.prior_denominator) - Math.round(x.prior_numerator));
    if (d === 0) return FLAT_MARK;
    return `<span class="dl ${d < 0 ? 'up' : 'dn'}" aria-label="${Math.abs(d)} ${d < 0 ? 'fewer' : 'more'} ${PFW[m.id].todo} than ${priorName()}">${d < 0 ? '▲' : '▼'}${Math.abs(d)}</span>`;
  }
  if (x.value == null || x.prior_value == null) return '<span class="dl z">No comparison</span>';
  const d = +(x.value - x.prior_value).toFixed(1), u = m.unit === '%' ? ' pts' : '';
  if (d === 0) return FLAT_MARK;
  if (m.higher_is_better == null) return `<span class="dl z">${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(1)}${u}</span>`;
  const better = m.higher_is_better ? d > 0 : d < 0, ad = wholeUnit(m) ? String(Math.round(Math.abs(d))) : Math.abs(d).toFixed(1);
  return `<span class="dl ${better ? 'up' : 'dn'}" aria-label="${better ? 'Better' : 'Worse'} than ${priorName()} by ${ad}${u || ' ' + m.unit}: ${fv(m, x.prior_value)} then, ${fv(m, x.value)} now">${better ? '▲' : '▼'}${ad}${u}</span>`;
}
const href = path => '#' + path.replace(/^\//,'').replace('/','-');
const famLink = id => `<a href="${href('/family/' + id)}">${esc(fam(id).name)}</a>`;
const roleFam = () => S.r.startsWith('fl:') ? S.r.slice(3) : null;
const isCTO = () => S.r === 'cto', isTR = () => S.r === 'tr';

/* ---------- data helpers ---------- */
function streak(hist){ let n = 0; for (let i = hist.length - 1; i >= 0 && hist[i] === 'Red'; i--) n++; return n; }
function cover(fid, mid){
  const last = P().meta.last_day;
  const es = D.entries.filter(e => e.family_id === fid && e.metric_id === mid && e.period <= S.p);
  const acc = es.find(e => e.kind === 'Accepted risk' && e.status === 'Approved' && e.due >= last);
  if (acc) return {k:'ok', t:`Risk accepted until ${fd(acc.due)}`};
  const act = es.find(e => e.kind === 'Action' && e.status !== 'Done');
  if (act) return {k:'ok', t:`Action owned by ${act.owner} due ${fd(act.due)}${act.due < last ? ' (overdue)' : ''}`};
  const dq = es.find(e => e.kind === 'Data query' && e.status !== 'Done');
  if (dq) return {k:'ok', t:`Data query open with ${dq.owner}`};
  // owner 1 Nov: any family comment on this metric or on the whole family counts as explained (no month lock, owner 17 Nov 2026)
  const notes = D.entries.filter(e => e.kind === 'Note' && e.family_id === fid && (e.metric_id === mid || (!e.metric_id && (!e.block || e.block === met(mid).block))) && (e.period === S.p || (e.period < S.p && e.status !== 'Done')));
  const pre = notes[0];
  if (pre) return {k:'ok', t:`L3 team note on file (${pre.owner})`};
  const said = es.find(e => e.period === S.p);      // a query or action this month also counts as the family commenting
  if (said) return {k:'ok', t:said.kind === 'Data query' ? `Data query answered (${said.owner})` : said.kind === 'Action' ? `Action closed (${said.owner})` : `L3 team note on file (${said.owner})`};
  const cm = COMMENTS.find(c => c.p === S.p && c.fid === fid && (c.mid === mid || (!c.mid && (!c.block || c.block === met(mid).block))));
  if (cm) return {k:'ok', late:true, t:cm.type === 'query' ? 'Data query raised by the L3 team' : cm.type === 'action' ? 'Action requested by the L3 team' : 'Explanation submitted by the L3 team'};
  const closed = es.find(e => e.kind === 'Action' && e.status === 'Done');
  return {k:'none', t:'No explanation yet' + (closed ? ` (earlier action ${closed.id} is closed)` : '')};
}
function bizDay(pid, n){          // nth business day after the period: weekdays, skipping US federal holidays (observed dates)
  const [y, m] = pid.split('-').map(Number); const d = new Date(Date.UTC(y, m, 1)), hol = D.holidays || {}; let c = 0;
  if (!(n >= 1)) return new Date(Date.UTC(y, m, 0)).toISOString().slice(0, 10);   // no business day yet (live data): the month's last day, never an endless count
  for (;;) { const w = d.getUTCDay(); if (w && w < 6 && !hol[d.toISOString().slice(0, 10)] && ++c === n) break; d.setUTCDate(d.getUTCDate() + 1); }
  return d.toISOString().slice(0, 10);
}

// WHY lines: built from status changes, never prose. Building blocks that fell, then the metrics inside them that worsened, by points lost.
function whyDrop(fid){
  const fr = P().families[fid], m = fr.metrics;
  const worsened = Object.entries(m).filter(([, x]) => RANK[x.status] != null && RANK[x.prior_status] != null && RANK[x.status] > RANK[x.prior_status])
    .sort((a, b) => (RANK[b[1].status] - RANK[b[1].prior_status]) - (RANK[a[1].status] - RANK[a[1].prior_status]));
  const byBlock = {};
  worsened.forEach(([id, x]) => { const L = met(id).block; (byBlock[L] = byBlock[L] || []).push([id, x]); });
  const fell = Object.entries(byBlock).map(([L, ms]) => ({L, d:(fr.blocks[L] && fr.blocks[L].delta) || 0, ms})).sort((a, b) => a.d - b.d);
  const part = ({L, d, ms}) => {
    const names = ms.slice(0, 2).map(([id, x]) => `${met(id).name} ${x.prior_status} → ${x.status}${x.override ? ' (automatic rule)' : ''}`);
    const more = ms.length > 2 ? ` and ${ms.length - 2} more` : '';
    return `${BLK(L).name} down ${Math.abs(d)}: ${names.join(', ')}${more}`;
  };
  const shown = fell.slice(0, 2).map(part), rest = fell.length - 2;
  return shown.join(' · ') + (rest > 0 ? ` · ${rest} other building block${rest > 1 ? 's' : ''} also fell` : '');
}
function whyDeclining(fid){
  const fr = P().families[fid], m = fr.metrics;
  return fr.declining.map(L => {
    const fell = Object.entries(m).filter(([id, x]) => met(id).block === L && x.history.length >= 3 && RANK[x.status] != null && RANK[x.history[x.history.length - 3]] != null && RANK[x.status] > RANK[x.history[x.history.length - 3]])
      .map(([id, x]) => `${met(id).name} ${x.history[x.history.length - 3]} → ${x.status}`);
    return `${BLK(L).name} now ${fr.blocks[L].score}: ${fell.length ? fell.slice(0, 2).join(', ') + (fell.length > 2 ? ` and ${fell.length - 2} more` : '') : 'metrics slipped within their bands'}`;
  }).join(' · ');
}

/* ---------- the page shell: breadcrumb and "Data as of" (prefix: shell) ---------- */
/* The names come from the sidebar that was just drawn, so there is one list of page names, not two. */
function shellSidebarLink(route){ return document.querySelector(`#side a.sbi[href="${href('/' + route)}"]`); }
function shellGroupOf(route){
  const link = shellSidebarLink(route); if (!link) return null;
  const list = link.closest('ul'), heading = list && document.getElementById(list.getAttribute('aria-labelledby'));
  return heading ? {name: heading.textContent.trim(), link: list.querySelector('a.sbi')} : null;
}
/* The trail for the current route: a list of {name, link} (link is a '#...' address, or null for the page you are on). */
function shellTrail(route, arg){
  const pageName = r => { const link = shellSidebarLink(r); return link ? link.getAttribute('title') : r; };
  const trail = [];
  if (route === 'scorecard') trail.push({name: pageName('scorecard')});
  else if (route === 'firm') trail.push({name: pageName('scorecard'), link: href('/scorecard')}, {name: pageName('firm')});
  else if (route === 'family' && fam(arg)) trail.push({name: pageName('scorecard'), link: href('/scorecard')}, {name: 'L3 teams', link: href('/scorecard')}, {name: fam(arg).name});
  else {
    const group = shellGroupOf(route);
    if (group) trail.push({name: group.name, link: group.link.getAttribute('href')});
    trail.push({name: pageName(route), link: arg ? href('/' + route) : null});
    if (route === 'dictionary' && arg && DX(arg)) trail.push({name: arg});
    if (route === 'datadict' && arg && typeof LAYOUTS !== 'undefined' && LAYOUTS.find(f => f.id === arg)) trail.push({name: LAYOUTS.find(f => f.id === arg).name});
  }
  if (!trail.length) return trail;
  trail[trail.length - 1].link = null;      // the last part is the page you are on
  return trail;
}
/* "Data as of": the OLDEST data date among the selected month's files, so the page never says the data is newer
   than it is (owner, 15 Nov 2026). Each file's date is worked out once, in score_month.data_as_of. No files: nothing shown. */
function shellDataAsOf(){
  const dataDates = (P().submissions || []).map(s => s.data_as_of).filter(t => typeof t === 'string' && t.length >= 10).sort();
  const oldestDataDate = dataDates[0];
  return oldestDataDate ? fd(oldestDataDate) : '';
}
/* The list behind "Data as of": every data source for the selected month with its own date, oldest first. */
function shellDataDates(){
  const files = (P().submissions || []).filter(s => typeof s.data_as_of === 'string' && s.data_as_of.length >= 10);
  const oldestFirst = files.slice().sort((a, b) => a.data_as_of < b.data_as_of ? -1 : a.data_as_of > b.data_as_of ? 1 : 0);
  const rows = oldestFirst.map(s => `<li><span>${esc(feedTitle(s.feed))}<span class="cap"> · ${esc(s.provider)}</span></span><span>${fd(s.data_as_of)}</span></li>`);
  return rows.join('');
}
function shellBar(route, arg){
  const trail = shellTrail(route, arg); if (!trail.length) return '';
  const parts = trail.map(t => t.link ? `<li><a href="${esc(t.link)}">${esc(t.name)}</a></li>` : `<li aria-current="page">${esc(t.name)}</li>`).join('');
  const asOf = shellDataAsOf();
  return `<div class="shellbar"><nav class="crumbs" aria-label="Breadcrumb"><ol>${parts}</ol></nav>${asOf ? `<details class="asof"><summary>Data as of ${asOf}</summary><div class="asoflist"><p class="cap">Each data source and the date its data is good to. The date above is the oldest.</p><ul>${shellDataDates()}</ul></div></details>` : ''}</div>`;
}

/* See the code (owner, 16 Nov 2026): a closed "See the code" box listing places in the repository, like the metric
   cards'. places = [{file, function, what, from, to, url}]; links when a place has a url, else plain text. */
function cplPlaceText(r){ return `${esc(r.file)} · <code>${esc(r.function)}()</code> lines ${r.from}–${r.to}`; }
function cplPlaceCell(r){ return r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${cplPlaceText(r)}</a>` : cplPlaceText(r); }
function cplSeeTheCode(places, intro){
  if (!places || !places.length) return '';
  return `<details class="exs cplcode"${S.snap ? ' open' : ''}><summary>See the code: ${plural(places.length, 'place', 'places')} in the repository</summary>
    <p class="cap" style="margin:4px 0 6px">${esc(intro)}</p>
    <table class="dt nosort"><colgroup><col style="width:44%"><col style="width:56%"></colgroup><thead><tr><th>What it does</th><th>Where</th></tr></thead><tbody>${places.map(r => `<tr><td>${esc(r.what)}</td><td>${cplPlaceCell(r)}</td></tr>`).join('')}</tbody></table></details>`;
}
