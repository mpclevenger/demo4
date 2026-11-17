/* "By L4" on a team page: each L4 leader's share of the team's numbers, as counts only (owner, 17 Nov 2026).
   The numbers come from the back end (backend/trust/l4_split.py, sent inside evidence.json as each metric's "by_l4").
   Nothing here is scored: no status, no colour and no letter for an L4. Every name here starts with tl4. */
"use strict";

/* the metrics that have a split to show for this team, in the dictionary's order */
function tl4Metrics(teamEvidence){
  return D.metrics.filter(metric => metState(metric.id) === 'measured' && teamEvidence[metric.id] && teamEvidence[metric.id].by_l4);
}

/* one cell, short like the metrics table's Result ("4 of 4 scanned repos"; the column header names the metric),
   a dash when nothing is counted, or a dash with a mark when the metric isn't split (the reason is said once, under the table) */
/* Short nouns where the dictionary's own count words are a whole sentence (the column header names the metric). */
const TL4_SHORT = {
  'UN-01': (n, d) => `${nfmt(n)} ${n === 1 ? 'incident' : 'incidents'} · ${nfmt(d)} ${d === 1 ? 'app' : 'apps'}`,
  'UN-02': (n, d) => `${nfmt(n)} overdue of ${nfmt(d)} ${d === 1 ? 'action' : 'actions'}`,
};
function tl4Short(metric, num, den){
  const words = COUNTS[metric.id], n = Math.round(num), d = Math.round(den);
  if (TL4_SHORT[metric.id]) return TL4_SHORT[metric.id](n, d);
  if (metric.id === 'TR-02') return `${nfmt(n)} of ${nfmt(d)} ${d === 1 ? 'hygiene check' : 'hygiene checks'}`;
  if (words && (words.verb_one || isPF(metric))) return `${nfmt(n)} of ${nfmt(d)} ${d === 1 ? words.den_one : words.den_many}`;
  return countText(metric, {numerator: num, denominator: den});     // "4 overdue out of 5 postmortem actions": the words carry the meaning
}
function tl4Cell(metric, split, counts){
  if (!split.split) return '<span class="muted" title="Not split by L4: see the note under the table">—*</span>';
  if (!counts || !counts.den) return '<span class="muted">—</span>';
  return esc(tl4Short(metric, counts.num, counts.den));
}

/* the L4 leaders across every metric: name and email, biggest share of the team's items first */
function tl4Leaders(metrics, teamEvidence){
  const leaders = {};
  metrics.forEach(metric => teamEvidence[metric.id].by_l4.rows.forEach(row => {
    const key = (row.l4_email || row.l4).toLowerCase();
    const leader = leaders[key] = leaders[key] || {name: row.l4, email: row.l4_email, size: 0};
    leader.size += row.den;
  }));
  return Object.entries(leaders).sort((a, b) => b[1].size - a[1].size || a[1].name.localeCompare(b[1].name));
}

function tl4Section(teamId, loading){
  if (loading) return '<section class="grp" aria-labelledby="h-l4"><h2 id="h-l4">By L4</h2><p class="muted">Loading…</p></section>';
  const teamEvidence = famEv(teamId);
  if (!teamEvidence) return '';
  const metrics = tl4Metrics(teamEvidence);
  if (!metrics.length) return '';
  const leaders = tl4Leaders(metrics, teamEvidence);
  const countsOf = (metric, key) => teamEvidence[metric.id].by_l4.rows.find(row => (row.l4_email || row.l4).toLowerCase() === key);
  const ownerCell = (name, email) => `<span class="nm">${esc(name)}</span>${email ? `<div class="cap">${esc(email)}</div>` : ''}`;
  const rows = leaders.map(([key, leader]) =>
    `<tr><td>${ownerCell(leader.name, leader.email)}</td>${metrics.map(metric => `<td>${tl4Cell(metric, teamEvidence[metric.id].by_l4, countsOf(metric, key))}</td>`).join('')}</tr>`);
  const notUnder = metrics.map(metric => teamEvidence[metric.id].by_l4.not_under).find(Boolean);
  if (notUnder) {
    rows.push(`<tr><td>${ownerCell(notUnder.l4, '')}<div class="cap">Owner: ${esc(notUnder.owner || 'the team lead')}${notUnder.owner_email ? ` (${esc(notUnder.owner_email)})` : ''}</div></td>${metrics.map(metric => {
      const split = teamEvidence[metric.id].by_l4;
      return `<td>${tl4Cell(metric, split, split.not_under)}</td>`; }).join('')}</tr>`);
  }
  const countedTwice = metrics.some(metric => teamEvidence[metric.id].by_l4.counted_twice);
  const twiceLine = countedTwice ? ' An item with people under two L4 leaders counts once for each, so these rows can add up to more than the team’s total.' : '';
  const reasons = metrics.filter(metric => !teamEvidence[metric.id].by_l4.split)
    .map(metric => `${esc(metric.name)}: ${esc(teamEvidence[metric.id].by_l4.reason)}`);
  const reasonLine = reasons.length ? `<p class="cap" style="margin:8px 0 0">* Not split by L4. ${reasons.join(' ')}</p>` : '';
  return `<section class="grp" aria-labelledby="h-l4"><h2 id="h-l4">By L4</h2>
    <p class="cap" style="margin:0 0 8px">Each L4 leader’s share of the team’s numbers, as counts. Nothing here is scored.${twiceLine}</p>
    <div class="ddscroll"><table class="dt lt nosort"><caption class="sr-only">The team’s numbers by L4 leader. Counts only.</caption>
    <thead><tr><th>L4 leader</th>${metrics.map(metric => `<th>${esc(metric.name)}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>${reasonLine}</section>`;
}
