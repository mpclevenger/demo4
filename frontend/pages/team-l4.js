/* L4 splits: each L4 leader's share of a team's numbers (owner, 17 Nov 2026): counts, plus on the team page each L4's own percentage. On the team page each
   metric's split shows first when its row opens; the All metrics page uses the same short counts and leader order.
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

/* One metric's L4 split, shown first when its row opens on the team page (owner, 17 Nov 2026: "the l4 break outs
   should be IN THE DETAIL table"): one row per L4 leader, biggest share first, then "Not under an L4". Counts and percentage only: no colour or status. */
function tl4MetricBlock(metric, evidence){
  const split = evidence && evidence.by_l4;
  if (!split) return '';
  if (!split.split) return `<p class="cap tl4note">Not split by L4: ${esc(split.reason || '')}</p>`;
  const ownerCell = (name, email, extra) => `<span class="nm">${esc(name)}</span>${email ? `<div class="cap">${esc(email)}</div>` : ''}${extra || ''}`;
  // Each L4's percentage, worked out from its own counts like the team's (owner, 17 Nov 2026: "percentage per l4 yes").
  // Display only: no colour, no status, nothing scored. Pass/fail metrics are counts already, so they have none.
  const pct = counts => metric.unit === '%' && !isPF(metric) && counts && counts.den ? `<b class="tl4pct">${num1(100 * counts.num / counts.den)}%</b> · ` : '';
  const cell = counts => `${pct(counts)}${tl4Cell(metric, split, counts)}`;
  const rows = [...split.rows].sort((a, b) => b.den - a.den || String(a.l4).localeCompare(String(b.l4)))
    .map(row => `<tr><td>${ownerCell(row.l4, row.l4_email)}</td><td>${cell(row)}</td></tr>`);
  const nu = split.not_under;
  if (nu && nu.den) rows.push(`<tr><td>${ownerCell(nu.l4, '', `<div class="cap">Owner: ${esc(nu.owner || 'the team lead')}${nu.owner_email ? ` (${esc(nu.owner_email)})` : ''}</div>`)}</td><td>${cell(nu)}</td></tr>`);
  if (!rows.length) return '';
  const twice = split.counted_twice ? ' An item with people under two L4 leaders counts once for each, so the rows can add up to more than the team’s total.' : '';
  return `<div class="tl4"><p class="cap tl4note">By L4 leader. Shown for each L4’s own follow-up; nothing here is scored or colored.${twice}</p>
    <table class="dt lt nosort tl4t"><caption class="sr-only">${esc(metric.name)} by L4 leader. Counts only.</caption>
    <thead><tr><th>L4 leader</th><th>${esc(metric.name)}</th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}
