/* Sortable table columns, on every data table. */
"use strict";
/* ----- sortable table columns (owner, 4 Nov 2026; small v1 design addition) -----
   Every data table (class "dt") gets clickable column heads: first click sorts low to high (A to Z, oldest first),
   second click high to low, third click goes back to the page's own order. Blank values ("—", "No data",
   "Not scored", "No comparison") always go last. A detail row (class "subrow", or one cell across the whole row)
   stays with the row above it. Tables whose order means something (the monthly cycle, versions, the seal) carry
   class "nosort". The family heatmap sorts in heatmapHTML instead (its band cell spans rows). The choice is kept
   for this visit only, per page and table, and survives re-drawing and changing month. Sorting never changes a score. */
const SORTS = new Map();   // table key -> {c: column index, d: 1 ascending | -1 descending}
const SORT_BLANK = /^(—|–|-|no data|not scored|not scored yet|no comparison|none|n\/a|)$/i;
const MON3 = {jan:0, feb:1, mar:2, apr:3, may:4, jun:5, jul:6, aug:7, sep:8, oct:9, nov:10, dec:11};
function sortCell(td){   // -> {k:'n'|'d'|'t', v} or null for a blank; a cell can give its own value in data-sv
  if (!td) return null;
  const sv = td.dataset.sv, t = (sv !== undefined ? sv : td.textContent).replace(/\s+/g, ' ').trim();
  if (SORT_BLANK.test(t)) return null;
  let m = t.match(/^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/);
  if (m) return {k:'d', v:Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0))};
  m = t.match(/^(\d{1,2}) ([A-Za-z]{3})[a-z]*(?: (\d{4}))?(?:,? (\d{2}):(\d{2}))?/);
  if (m && MON3[m[2].toLowerCase()] !== undefined) return {k:'d', v:Date.UTC(+(m[3] || 2000), MON3[m[2].toLowerCase()], +m[1], +(m[4] || 0), +(m[5] || 0))};
  m = t.match(/^([▲▼])\s*([\d.,]+)/);   // change cells: ▲ better = up, ▼ worse = down, so low to high = worst first
  if (m) return {k:'n', v:(m[1] === '▲' ? 1 : -1) * parseFloat(m[2].replace(/,/g, ''))};
  m = t.match(/^[−-]?\d[\d,]*(?:\.\d+)?/);
  if (m) return {k:'n', v:parseFloat(m[0].replace(/,/g, '').replace('−', '-'))};
  return {k:'t', v:t};
}
function sortGroups(tb){   // rows in groups: a main row plus its detail rows
  const cols = tb.closest('table').tHead.rows[0].cells.length, gs = [];
  [...tb.rows].forEach(r => { const sub = r.classList.contains('subrow') || (r.cells.length === 1 && r.cells[0].colSpan >= cols);
    if (sub && gs.length) gs[gs.length - 1].push(r); else gs.push([r]); });
  return gs;
}
function sortKey(t, i){ return parse().join('/') + '|' + t.className.replace(/ ?sortable/, '') + '|' + [...t.tHead.rows[0].cells].map(h => h.textContent.trim()).join('·') + '|' + i; }
function sortApply(t){
  const tb = t.tBodies[0], st = SORTS.get(t.dataset.sk), gs = sortGroups(tb);
  gs.forEach((g, i) => { if (g[0].dataset.so === undefined) g[0].dataset.so = i; });   // the page's own order
  let key = g => +g[0].dataset.so, cmp = (a, b) => a - b;
  if (st) { const vals = gs.map(g => sortCell(g[0].cells[st.c])), kinds = new Set(vals.filter(Boolean).map(v => v.k));
    const kind = kinds.size === 1 ? [...kinds][0] : 't';   // mixed column: compare as text
    const val = new Map(gs.map((g, i) => [g, vals[i] ? (kind === 't' ? String(vals[i].v) : vals[i].v) : null]));
    key = g => val.get(g);
    cmp = (a, b) => kind === 't' ? String(a).localeCompare(String(b), undefined, {numeric:true, sensitivity:'base'}) : a - b; }
  gs.sort((a, b) => { const x = key(a), y = key(b);
    if (x === null || y === null) return x === y ? +a[0].dataset.so - +b[0].dataset.so : x === null ? 1 : -1;   // blanks last, either way
    return (st ? st.d : 1) * cmp(x, y) || +a[0].dataset.so - +b[0].dataset.so; });
  gs.flat().forEach(r => tb.appendChild(r));
  [...t.tHead.rows[0].cells].forEach((h, c) => { const b = h.querySelector('.sortb'); if (!b) return;
    const on = st && st.c === c, dir = on ? (st.d === 1 ? 'ascending' : 'descending') : null;
    if (dir) h.setAttribute('aria-sort', dir); else h.removeAttribute('aria-sort');
    b.dataset.on = on ? (st.d === 1 ? 'up' : 'dn') : '';
    b.title = on ? (st.d === 1 ? 'Sorted low to high. Click for high to low' : 'Sorted high to low. Click to go back to the usual order') : 'Click to sort by this column'; });
}
const SORT_ICON = '<svg class="sarr" viewBox="0 0 10 14" width="8" height="12" aria-hidden="true"><path class="su" d="M2 5.5 5 2.5 8 5.5"/><path class="sd" d="M2 8.5 5 11.5 8 8.5"/></svg>';
function sortEnhance(root){
  const seen = {};
  (root || document).querySelectorAll('#app table.dt').forEach(t => {
    if (t.classList.contains('nosort') || !t.tHead || !t.tBodies[0]) return;
    const sig = t.className.replace(/ ?sortable/, '') + [...t.tHead.rows[0].cells].map(h => h.textContent.trim()).join('·'); seen[sig] = (seen[sig] || 0) + 1;
    if (t.dataset.sk) return;
    if (sortGroups(t.tBodies[0]).length < 2 || t.tBodies[0].querySelector('td.muted[colspan]')) return;   // nothing to sort
    t.dataset.sk = sortKey(t, seen[sig]); t.classList.add('sortable');
    [...t.tHead.rows[0].cells].forEach((h, c) => { if (!h.textContent.trim() || h.colSpan > 1) return;
      h.innerHTML = `<button type="button" class="sortb" data-act="sort" data-c="${c}">${h.innerHTML}${SORT_ICON}</button>`; });
    sortApply(t); });
}
document.addEventListener('change', e => { if (e.target.id === 'hmf') { HMF = e.target.value; S.keepScroll = true; render(); const n = $('#hmf'); if (n) n.focus({preventScroll:true}); } });
document.addEventListener('click', e => {
  const h = e.target.closest('[data-act="hm-sort"]'); if (!h) return;
  const k = h.dataset.k; HMS = !HMS || HMS.k !== k ? {k, d:1} : HMS.d === 1 ? {k, d:-1} : null;
  S.keepScroll = true; render(); const n = document.querySelector(`[data-act="hm-sort"][data-k="${k}"]`); if (n) n.focus({preventScroll:true});
});
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act="sort"]'); if (!b) return;
  const t = b.closest('table'), c = +b.dataset.c, st = SORTS.get(t.dataset.sk);
  const next = !st || st.c !== c ? {c, d:1} : st.d === 1 ? {c, d:-1} : null;   // low to high -> high to low -> usual order
  if (next) SORTS.set(t.dataset.sk, next); else SORTS.delete(t.dataset.sk);
  sortApply(t); b.focus();
});
{ let q = false;   // tables are drawn by many functions, some redrawing only part of the page: enhance whatever appears
  new MutationObserver(() => { if (q) return; q = true; queueMicrotask(() => { q = false; sortEnhance(); }); }).observe(document.getElementById('app'), {childList:true, subtree:true}); }
