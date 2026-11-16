/* Firm position: the firm's own result for every metric. */
"use strict";
/* ---------- firm position page ---------- */
const MAP_NEED = {'Arch':'Assign the repo to an application in the inventory', 'ITDR':'Record the app’s product family in the ITDR applications file', 'Ops':'Make sure the action’s assignee email is in HR, under a product family owner',
  'Cyber':'Link the finding’s repo or asset to an application', 'Hosting platform':'Tag the hosted app with its product family', 'Change':'Make sure the change Author’s email is in HR, under a product family owner'};
/* Unassigned rows per provider. The shares are given (p.unattributed_pct); the row count is that share x the provider's accepted-submission rows, since the
   evidence file's unattributed_num/den are per-metric item counts and do not reconcile to the provider share. */
function unmappedList(){
  const p = P();
  return D.providers_all.map(pr => {
    const v = p.unattributed_pct[pr], subs = p.submissions.filter(x => x.provider === pr && x.status === 'Accepted'), sub = subs[0];
    if (v == null || !sub) return {pr, v:null};
    const rows = subs.reduce((t, x) => t + (x.rows || 0), 0);
    return {pr, v, rows, n: v > 0 ? Math.max(1, Math.round(v * rows / 100)) : 0};
  });
}
function unmappedNote(where){                 // D-73: data not mapped to a family is always visible
  const have = unmappedList().filter(x => x.v != null && x.v > 0).sort((a, b) => b.v - a.v);
  if (!have.length) return '';
  const parts = have.map(x => `${esc(x.pr)} ${num1(x.v)}%`).join(', ');
  if (where === 'family') return `<p class="unmap"><b>Not yet mapped to a family:</b> some rows received could not be placed in a family and may belong to this one. They count in firm totals but in no family\u2019s score. <a href="${href('/firm')}">See Firm position</a></p>`;
  return `<p class="unmap"><b>Not yet mapped to a family:</b> ${parts} of rows received. Firm totals include these rows; family scores do not. <a href="${href('/firm')}">See what is needed to map them</a></p>`;
}
function unmappedExamples(pr){
  if (EV.state !== 'ok' || !EV.data[S.p]) return [];
  const seen = new Map();
  Object.entries(EV.data[S.p]).forEach(([fid, ms]) => Object.entries(ms).forEach(([mid, e]) => { if (met(mid).provider !== pr) return;
    e.items.forEach(i => { if (!i.app_id && i.item_type !== 'app' && !['action', 'deployment', 'release'].includes(i.item_type) && !seen.has(i.item_id)) seen.set(i.item_id, fam(fid) ? fam(fid).name : fid); }); }));
  return [...seen].slice(0, 5);
}
/* One line for the metrics of a building block that are not measured yet (design review, 5 Nov 2026). */
function bWantedLine(ms){
  const pl = ms.filter(m => metState(m.id) === 'wanted'), any = ms.some(m => metState(m.id) === 'measured'), out = [];
  if (pl.length) out.push(`${pl.length} ${any ? 'more ' : ''}wanted: ${pl.map(m => esc(m.name)).join(', ')} — not measured yet, no data source`);
  return out.join('. ');
}
function vFirm(){
  const p = P();
  evLoad();
  const list = unmappedList(), have = list.filter(x => x.v != null && x.v > 0).sort((a, b) => b.v - a.v), none = list.filter(x => x.v == null);
  const blocksOf = pr => [...new Set(D.metrics.filter(m => m.provider === pr).map(m => m.block))].map(c => BLK(c).name).join(', ');
  const owner = pr => { const o = [...new Set(D.connectors.filter(c => c.provider === pr && c.owner).map(c => c.owner))]; return o.length ? o.map(esc).join(', ') : 'Provider'; };
  const rows = have.map(x => { const ex = x.v > 0 ? unmappedExamples(x.pr) : [];
    return `<tr><td>${bSrc(x.pr)}</td><td>${blocksOf(x.pr)}</td><td class="share">${num1(x.v)}% of rows received</td><td>${esc(MAP_NEED[x.pr] || 'Tell Tech Risk which application this belongs to')}</td><td>${owner(x.pr)}</td></tr>
    ${ex.length ? `<tr class="subrow"><td colspan="5"><details class="exs"${S.snap ? ' open' : ''}><summary>Examples (${ex.length})</summary><ul>${ex.map(([id, f]) => `<li>${esc(id)} · ${esc(f)}</li>`).join('')}</ul></details></td></tr>` : ''}`; }).join('');
  const pp = PRIOR[S.p] && D.periods[PRIOR[S.p]], tr = pp ? have.filter(x => pp.unattributed_pct[x.pr] != null).map(x => {
    const d = +(x.v - pp.unattributed_pct[x.pr]).toFixed(1);
    return `${esc(x.pr)} ${d === 0 ? FLAT_MARK : `<span class="dl ${d < 0 ? 'up' : 'dn'}">${d < 0 ? '▲' : '▼'}${Math.abs(d).toFixed(1)} pts</span>`}`; }) : [];
  return `<div class="firmpg"><h1>Firm position — ${p.meta.label}</h1>
    <section class="grp" aria-labelledby="h-firm"><h2 id="h-firm">Firmwide position</h2>${firmStoryHTML()}${firmTable()}</section>
    ${!have.length ? '<section class="grp" aria-label="Data not yet mapped to a family"><p class="muted" style="margin:0">Every row received this month was placed with a product family.</p></section>' : `<section class="grp" aria-labelledby="h-unm"><h2 id="h-unm">Data not yet mapped to a family</h2>
      <p class="intro">Rows we received that we couldn’t place in a product family. They count in the firm totals but in no one’s scorecard — mapping them is the quickest way to make the family pages complete.</p>
      <table class="dt unm"><colgroup><col style="width:16%"><col style="width:17%"><col style="width:17%"><col style="width:32%"><col style="width:18%"></colgroup><thead><tr><th>Provider</th><th>Building blocks it feeds</th><th>Share not mapped</th><th>What’s needed to map it</th><th>Owner to contact</th></tr></thead><tbody>${rows}</tbody></table>
      ${tr.length ? `<p class="trend">vs ${priorName()}: ${tr.join(', ')} <span class="cap">(▲ better, lower share · ▼ worse)</span></p>` : ''}</section>`}</div>`;
}
