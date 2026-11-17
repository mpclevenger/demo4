/* "All metrics": every measured metric across every L3 team, or across every L4 team (owner, 17 Nov 2026).
   L3 rows show each result as the team page shows it. L4 rows are counts only, exactly like the team page's "By L4"
   table (tl4Short and tl4Cell in team-l4.js): no status, no colour, no percentage. Nothing here is scored.
   Open to every role. The numbers come from data.json ("all_metrics", written by backend/trust/publish.py).
   Every name here starts with am. */
"use strict";

const AM = {rows: 'l3', team: 'all', focus: null};     // rows: 'l3' or 'l4'; team: 'all' or one L3 team's id

/* this month's block of data, or null when this update predates the page */
function amBlock(){
  return (D.all_metrics && D.all_metrics[S.p]) || null;
}

/* the measured metrics, grouped under their building blocks, in the dictionary's order: [{block, metrics}] */
function amColumns(){
  const measured = D.metrics.filter(metric => metState(metric.id) === 'measured');
  return D.blocks.map(block => ({block, metrics: measured.filter(metric => metric.block === block.code)}))
    .filter(group => group.metrics.length);
}

/* one L3 cell: the result and its short count, coloured by status like the team page's metrics table */
function amL3Cell(metric, result){
  if (!result) return '<span class="muted">—</span>';
  if (result.status === 'DNR') return '<span class="muted">No data</span>';
  if (result.status !== 'Not Tier 0/1' && !isPF(metric) && result.value == null) return '<span class="muted">—</span>';
  if (result.status === 'Not Tier 0/1' || isPF(metric) || result.numerator == null || result.denominator == null) return famResultCell(metric, result);
  const statusClass = `st-${result.status.replace(/ /g, '-')}`;     // the team page's result colouring, with the short count on its own line
  return `<span class="res ${statusClass}">${resTxt(metric, result)}${result.provisional ? '*' : ''}</span>`
    + `<div class="cap">${esc(tl4Short(metric, result.numerator, result.denominator))}</div>`;
}

/* the L3 team's own result for a metric (from the block, so every role sees every team) */
function amTeamResult(block, teamId, metric){
  const entry = (block.teams[teamId] || {})[metric.id];
  return entry ? entry.result : null;
}

/* the firm's result, as the Firm position page reads it */
function amFirmResult(metric){
  const firm = P().firm[metric.id];
  if (!firm) return null;
  return {value: firm.value, status: firm.status, numerator: firm.numerator, denominator: firm.denominator, provisional: false};
}

/* the teams on show: every L3 team in the page's order, or the one picked */
function amTeams(block){
  return D.families.filter(team => block.teams[team.id] && (AM.team === 'all' || team.id === AM.team));
}

function amHeadRows(columns, firstHead){
  const blockRow = `<tr class="amblocks"><th rowspan="2" class="amfirst">${firstHead}</th>${columns.map(group => `<th colspan="${group.metrics.length}" class="amblock">${esc(group.block.name)}</th>`).join('')}</tr>`;
  const metricRow = `<tr>${columns.map(group => group.metrics.map(metric => `<th>${esc(metric.name)}</th>`).join('')).join('')}</tr>`;
  return `<thead>${blockRow}${metricRow}</thead>`;
}

function amL3Table(block, columns, metrics){
  const teamRows = amTeams(block).map(team =>
    `<tr><td class="amfirst"><span class="nm">${famLink(team.id)}</span>${team.accountable ? `<div class="cap">${esc(team.accountable)}</div>` : ''}</td>${metrics.map(metric => `<td>${amL3Cell(metric, amTeamResult(block, team.id, metric))}</td>`).join('')}</tr>`);
  const firmRow = `<tr class="amfirm"><td class="amfirst"><span class="nm">Firmwide</span></td>${metrics.map(metric => `<td>${amL3Cell(metric, amFirmResult(metric))}</td>`).join('')}</tr>`;
  return `<div class="ddscroll amscroll"><table class="dt lt nosort amt"><caption class="sr-only">Every measured metric for each L3 team, and the firm.</caption>${amHeadRows(columns, 'L3 team')}<tbody>${teamRows.join('')}${firmRow}</tbody></table></div>`;
}

/* a team's entries with a split for every metric, so a metric with no counts reads as "—" */
function amTeamEntries(block, teamId, metrics){
  const entries = {};
  metrics.forEach(metric => {
    const entry = (block.teams[teamId] || {})[metric.id];
    entries[metric.id] = {by_l4: (entry && entry.by_l4) || {split: true, rows: [], not_under: null, counted_twice: false}};
  });
  return entries;
}

function amL4Rows(block, team, metrics, width){
  const entries = amTeamEntries(block, team.id, metrics);
  const leaders = tl4Leaders(metrics, entries);
  const teamNames = block.l4_team_names || {};
  const countsOf = (metric, key) => entries[metric.id].by_l4.rows.find(row => (row.l4_email || row.l4).toLowerCase() === key);
  const rows = [`<tr class="amgroup"><th colspan="${width}" scope="colgroup">${famLink(team.id)}</th></tr>`];
  leaders.forEach(([key, leader]) => {
    const l4TeamName = teamNames[(leader.email || '').toLowerCase()];
    const caption = [l4TeamName, leader.email].filter(Boolean).map(esc).join(' · ');
    rows.push(`<tr><td class="amfirst"><span class="nm">${esc(leader.name)}</span>${caption ? `<div class="cap">${caption}</div>` : ''}</td>${metrics.map(metric => `<td>${tl4Cell(metric, entries[metric.id].by_l4, countsOf(metric, key))}</td>`).join('')}</tr>`);
  });
  const notUnder = metrics.map(metric => entries[metric.id].by_l4.not_under).find(Boolean);
  if (notUnder) {
    const owner = `Owner: ${esc(notUnder.owner || 'the team lead')}${notUnder.owner_email ? ` (${esc(notUnder.owner_email)})` : ''}`;
    rows.push(`<tr><td class="amfirst"><span class="nm">${esc(notUnder.l4)}</span><div class="cap">${owner}</div></td>${metrics.map(metric => `<td>${tl4Cell(metric, entries[metric.id].by_l4, entries[metric.id].by_l4.not_under)}</td>`).join('')}</tr>`);
  }
  if (!leaders.length && !notUnder) rows.push(`<tr><td class="amfirst"><span class="muted">No L4 counts for this team</span></td>${metrics.map(() => '<td><span class="muted">—</span></td>').join('')}</tr>`);
  return rows.join('');
}

function amL4Table(block, columns, metrics){
  const width = metrics.length + 1;
  const teams = amTeams(block);
  const body = teams.map(team => amL4Rows(block, team, metrics, width)).join('');
  return `<div class="ddscroll amscroll"><table class="dt lt nosort amt"><caption class="sr-only">Every measured metric by L4 leader, under each L3 team. Counts only.</caption>${amHeadRows(columns, 'L4 leader')}<tbody>${body}</tbody></table></div>${amL4Notes(block, metrics, teams)}`;
}

/* under the L4 table: why some metrics are not split (once each), and the counted-twice line */
function amL4Notes(block, metrics, teams){
  const splitsOf = metric => teams.map(team => ((block.teams[team.id] || {})[metric.id] || {}).by_l4).filter(Boolean);
  const reasons = metrics.map(metric => {
    const unsplit = splitsOf(metric).find(split => !split.split);
    return unsplit ? `${esc(metric.name)}: ${esc(unsplit.reason)}` : '';
  }).filter(Boolean);
  const countedTwice = metrics.some(metric => splitsOf(metric).some(split => split.counted_twice));
  const reasonLine = reasons.length ? `<p class="cap" style="margin:8px 0 0">* Not split by L4. ${reasons.join(' ')}</p>` : '';
  const twiceLine = countedTwice ? '<p class="cap" style="margin:8px 0 0">An item with people under two L4 leaders counts once for each, so the L4 rows can add up to more than the team’s total.</p>' : '';
  return reasonLine + twiceLine;
}

function amControls(block){
  const rowButton = (mode, label) => `<button type="button" class="sm" data-act="am-rows" data-mode="${mode}" aria-pressed="${AM.rows === mode}">${label}</button>`;
  const teamOptions = D.families.filter(team => block.teams[team.id])
    .map(team => `<option value="${esc(team.id)}"${AM.team === team.id ? ' selected' : ''}>${esc(team.name)}</option>`).join('');
  return `<div class="amcontrols noprint"><span class="cap" id="am-rows-label">Rows</span>
    <span class="amswitch" role="group" aria-labelledby="am-rows-label">${rowButton('l3', 'L3 teams')}${rowButton('l4', 'L4 teams')}</span>
    <label class="cap" for="am-team">Team</label>
    <select id="am-team"><option value="all"${AM.team === 'all' ? ' selected' : ''}>All L3 teams</option>${teamOptions}</select></div>`;
}

function vAllMetrics(){
  const block = amBlock();
  const intro = '<p class="intro">Every measured metric for every L3 team, side by side. L4 rows are counts only and are never scored.</p>';
  if (!block) {
    return `<div class="ampg"><h1>All metrics — ${P().meta.label}</h1>${intro}<p class="muted">The numbers for this page arrive with the next update.</p></div>`;
  }
  if (AM.team !== 'all' && !block.teams[AM.team]) AM.team = 'all';
  const columns = amColumns();
  const metrics = columns.flatMap(group => group.metrics);
  const table = AM.rows === 'l4' ? amL4Table(block, columns, metrics) : amL3Table(block, columns, metrics);
  return `<div class="ampg"><h1>All metrics — ${P().meta.label}</h1>${intro}${amControls(block)}${table}</div>`;
}

/* the switch and the team filter keep their place on the screen when the page is drawn again */
document.addEventListener('click', event => {
  const button = event.target.closest('[data-act="am-rows"]');
  if (!button) return;
  AM.rows = button.dataset.mode;
  S.keepScroll = true;
  render();
  const again = document.querySelector(`[data-act="am-rows"][data-mode="${AM.rows}"]`);
  if (again) again.focus({preventScroll: true});
});
document.addEventListener('change', event => {
  if (event.target.id !== 'am-team') return;
  AM.team = event.target.value;
  S.keepScroll = true;
  render();
  const again = document.getElementById('am-team');
  if (again) again.focus({preventScroll: true});
});
