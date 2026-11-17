/* L4 splits: each L4 leader's share of a team's numbers, as counts (owner, 17 Nov 2026). Used by the All metrics page;
   the team page uses the split for its "Where they sit by L4" filter (family.js).
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
