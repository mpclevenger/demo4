/* The Risk site: the current risk heat map (owner's decision, 16 Nov 2026).
   Page #/heat-map: a 4 x 4 grid of likelihood by impact with TOTALS across the firm, "Where to focus" by risk, and
   how many risks got better or worse. Nothing here is per team: the server sends totals only (GET /api/risk/matrix),
   so there is no team to show. The old address #/matrix sends people to #/heat-map. Nothing is rated here.
   It adds itself to the lists in risk-core.js. All names start with "riskHeatmap". */
"use strict";

const riskHeatmapState = {answer: null, picked: null, blockFilter: '', focusOpen: false};
const RISK_HEATMAP_FOCUS_SHOWN = 3;          // how many Where to focus rows show before "Show all"
const RISK_HEATMAP_ELEVATED_BONUS = 1000;   // an Elevated box always beats a box that is not (larger than any box's count)

/* ---------- the answer, narrowed to one building block ---------- */

/* Only the numbers shown change; nothing is rated. Every list is a list of RISKS, never of teams. */
function riskHeatmapNarrowed(answer) {
  const block = riskHeatmapState.blockFilter;
  const wanted = item => !block || item.block === block;
  const cells = {};
  for (const likelihood of RISK_LEVELS) {
    cells[likelihood] = {};
    for (const impact of RISK_LEVELS) cells[likelihood][impact] = answer.cells[likelihood][impact].filter(wanted);
  }
  return {cells: cells, focus: answer.focus.filter(wanted), movement: answer.movement.filter(wanted)};
}

function riskHeatmapSum(items, field) {
  let total = 0;
  for (const item of items) total += item[field];
  return total;
}

/* How many risks (counted once per assessment) sit in the grid, and how many of them are Elevated. */
function riskHeatmapTotals(narrowed) {
  let assessed = 0;
  for (const likelihood of RISK_LEVELS) for (const impact of RISK_LEVELS) assessed += riskHeatmapSum(narrowed.cells[likelihood][impact], 'assessments');
  return {assessed: assessed, elevated: riskHeatmapSum(narrowed.focus, 'elevated_assessments')};
}

function riskHeatmapInAssessments(count) {
  return 'in ' + plural(count, 'assessment', 'assessments');
}

/* ---------- the page ---------- */

async function riskHeatmapDrawPage() {
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/risk/matrix');
  if (!answer.ok) { riskShowProblem(answer.error || 'The heat map could not be loaded.'); return; }
  riskHeatmapState.answer = answer;
  riskHeatmapState.picked = null;
  riskHeatmapState.blockFilter = '';
  riskHeatmapState.focusOpen = false;
  const crumb = '<p class="risk-crumb"><a href="#/">Risk assessments</a> › Current risk heat map' + riskGuideLink('/guides/reading-your-results-and-the-risk-heat-map/', 'reading the heat map') + '</p>';
  if (!answer.groups_assessed) {
    riskShow(crumb + '<h2 class="risk-title">Current risk heat map</h2><div class="risk-card"><p>No team has been assessed yet, so there is nothing to place on the grid. Once a team submits its questions, its risks appear here.</p></div>');
    return;
  }
  const blockOptions = '<option value="">All building blocks</option>'
    + answer.blocks.map(block => '<option value="' + esc(block) + '">' + esc(block) + '</option>').join('');
  riskShow(crumb
    + '<div class="riskheatmap-titlerow"><div><h2 class="risk-title">Current risk heat map</h2>'
    + '<p class="riskheatmap-sub">This view shows totals across the firm, so risks can be raised and a treatment agreed. Each team’s own results are on that team’s page.</p></div>'
    + '<label class="riskheatmap-filter"><span class="cap">Building block</span><select id="riskheatmap-block">' + blockOptions + '</select></label></div>'
    + '<div id="riskheatmap-body"></div>');
  document.getElementById('riskheatmap-block').addEventListener('change', event => {
    riskHeatmapState.blockFilter = event.target.value; riskHeatmapState.picked = null; riskHeatmapDrawBody();
  });
  riskHeatmapDrawBody();
}

/* Everything under the filter. Drawn again whenever the filter or a pick changes. Boxes on one row are built to
   carry about the same amount, and stretch to the same height. */
function riskHeatmapDrawBody() {
  const answer = riskHeatmapState.answer;
  const narrowed = riskHeatmapNarrowed(answer);
  const totals = riskHeatmapTotals(narrowed);
  const detail = '<section class="risk-card riskheatmap-detailcard" aria-live="polite">' + riskHeatmapDetailHtml(answer, narrowed) + '</section>';
  const grid = '<section class="risk-card riskheatmap-gridcard" aria-label="Likelihood by impact">'
    + riskHeatmapGridHtml(answer, narrowed) + riskHeatmapLegendHtml() + '</section>';
  const focus = riskHeatmapFocusHtml(answer, narrowed.focus);
  let html = '<div class="riskheatmap-pair">' + riskHeatmapHeadlineHtml(answer, totals) + riskHeatmapMovementHtml(answer, narrowed) + '</div>';
  html += focus ? '<div class="riskheatmap-pair">' + grid + focus + '</div>' : '<div class="riskheatmap-single">' + grid + '</div>';
  html += detail;                                                                              // the box's risks always get a full row
  document.getElementById('riskheatmap-body').innerHTML = html;
  riskHeatmapWireBody();
}

function riskHeatmapHeadlineHtml(answer, totals) {
  const elevatedWords = 'Likelihood ' + riskLevelWord(answer.elevated_likelihood_at_least) + ' or higher and impact ' + riskLevelWord(answer.elevated_impact_at_least) + ' or higher is Elevated.';
  return '<section class="risk-card riskheatmap-headline"><h3>Elevated risks</h3>'
    + '<div class="riskheatmap-big"><span class="riskheatmap-bignumber' + (totals.elevated ? ' has' : '') + '">' + totals.elevated + '</span>'
    + '<span>of ' + plural(totals.assessed, 'assessed risk', 'assessed risks') + '</span></div>'
    + '<p class="cap">' + (totals.elevated ? '' : 'Nothing is Elevated here. ') + elevatedWords + ' '
    + plural(answer.groups_assessed, 'team has', 'teams have') + ' assessed.</p></section>';
}

/* Where a person can learn more about a risk: what it is, an example, and the controls TRAC lists for it. */
function riskHeatmapRiskHelpHtml(answer, riskId) {
  const detail = answer.risk_details[riskId] || {};
  let html = '';
  if (detail.description) html += '<p class="riskheatmap-describe">' + esc(detail.description) + '</p>';
  if (detail.example) html += '<p class="riskheatmap-describe cap">For example: ' + esc(detail.example) + '</p>';
  if (detail.controls && detail.controls.length) {
    html += '<p class="cap riskheatmap-controls">Controls: ' + detail.controls.map(control => (safeLink(control.url)
      ? '<a href="' + esc(safeLink(control.url)) + '" target="_blank" rel="noopener">' + esc(control.code) + '</a>' : esc(control.code))
      + (control.title ? ' ' + esc(control.title) : '')).join(' · ') + '</p>';
  }
  return html;
}

/* TRAC's guide on choosing a treatment. Drawn only once TRAC's address is known (appsmFillTracLinks fills it in). */
function riskHeatmapGuideLinkHtml() {
  return '<a class="riskheatmap-guide" data-trac-path="/guides/choosing-how-to-respond-to-a-risk/" target="_blank" rel="noopener" hidden>Choosing how to respond to a risk</a>';
}

/* Where to focus: the Elevated risks, most serious first, a few at a time. Only risks, no teams. */
function riskHeatmapFocusHtml(answer, focus) {
  if (!focus.length) return '';   // nothing to say = nothing drawn (owner, 15 Nov 2026)
  const shown = riskHeatmapState.focusOpen ? focus : focus.slice(0, RISK_HEATMAP_FOCUS_SHOWN);
  const rows = shown.map(item => '<li class="riskheatmap-focusrow">'
    + '<div class="riskheatmap-focushead"><span class="riskheatmap-focusname"><b>' + esc(item.risk_name) + '</b><span class="cap">' + esc(item.risk_id) + (item.block ? ' · ' + esc(item.block) : '') + '</span></span>'
    + '<span class="riskheatmap-focuslevels">' + esc(riskLevelWord(item.likelihood) + ' / ' + riskLevelWord(item.impact))
    + '<span class="cap">Elevated ' + riskHeatmapInAssessments(item.elevated_assessments) + '</span></span></div>'
    + riskHeatmapRiskHelpHtml(answer, item.risk_id) + '</li>').join('');
  const more = focus.length > RISK_HEATMAP_FOCUS_SHOWN
    ? '<button type="button" class="riskheatmap-more" id="riskheatmap-focusmore">' + (riskHeatmapState.focusOpen ? 'Show fewer' : 'Show all ' + plural(focus.length, 'risk', 'risks')) + '</button>' : '';
  return '<section class="risk-card riskheatmap-focus"><h3>Where to focus</h3>'
    + '<p class="cap">' + plural(focus.length, 'Elevated risk', 'Elevated risks') + ' to agree a treatment for, most serious first. ' + riskHeatmapGuideLinkHtml() + '</p>'
    + '<ul class="riskheatmap-focuslist">' + rows + '</ul>' + more + '</section>';
}

/* Movement since previous assessments, as totals: "4 risks better, 2 worse across all assessments". */
function riskHeatmapMovementHtml(answer, narrowed) {
  const heading = '<section class="risk-card riskheatmap-headline"><h3>Since previous assessments</h3>';
  if (!answer.groups_with_a_previous_assessment) {
    return heading + '<p class="cap">No team has a second assessment yet, so there is nothing to compare.</p></section>';
  }
  const better = riskHeatmapSum(narrowed.movement, 'better');
  const worse = riskHeatmapSum(narrowed.movement, 'worse');
  const parts = [];
  if (better) parts.push('<span class="risk-trend better"><span aria-hidden="true">▲</span> ' + plural(better, 'risk', 'risks') + ' better</span>');
  if (worse) parts.push('<span class="risk-trend worse"><span aria-hidden="true">▼</span> ' + plural(worse, 'risk', 'risks') + ' worse</span>');
  const text = parts.length ? '<div class="riskheatmap-moves">' + parts.join('') + '</div><p class="cap">Totals across all assessments.</p>'
    : '<p class="cap">No risk got better or worse since previous assessments.</p>';
  return heading + text + '</section>';
}

/* The grid: likelihood down the side (Critical at the top), impact across the bottom. */
function riskHeatmapIsElevatedCell(answer, likelihood, impact) {
  const likelihoodEnough = RISK_LEVELS.indexOf(likelihood) >= RISK_LEVELS.indexOf(answer.elevated_likelihood_at_least);
  const impactEnough = RISK_LEVELS.indexOf(impact) >= RISK_LEVELS.indexOf(answer.elevated_impact_at_least);
  return likelihoodEnough && impactEnough;
}

function riskHeatmapCellCount(items) {
  return riskHeatmapSum(items, 'assessments');
}

function riskHeatmapGridHtml(answer, narrowed) {
  const picked = riskHeatmapState.picked;
  let cells = '';
  for (const likelihood of RISK_LEVELS.slice().reverse()) {
    cells += '<div class="riskheatmap-rowhead">' + riskLevelWord(likelihood) + '</div>';
    for (const impact of RISK_LEVELS) {
      const count = riskHeatmapCellCount(narrowed.cells[likelihood][impact]);
      const elevated = riskHeatmapIsElevatedCell(answer, likelihood, impact);
      const label = 'Likelihood ' + riskLevelWord(likelihood) + ', impact ' + riskLevelWord(impact) + ': ' + (count ? plural(count, 'risk', 'risks') : 'no risks') + (elevated ? ', Elevated' : '');
      const classes = 'riskheatmap-cell' + (elevated ? ' is-elevated' : '') + (count ? '' : ' is-empty');
      if (!count) { cells += '<div class="' + classes + '" role="img" aria-label="' + esc(label) + '"></div>'; continue; }
      const isPicked = picked && picked.likelihood === likelihood && picked.impact === impact;
      cells += '<button type="button" class="' + classes + '" data-likelihood="' + likelihood + '" data-impact="' + impact + '" aria-pressed="' + (isPicked ? 'true' : 'false')
        + '" aria-label="' + esc(label) + '"><span class="riskheatmap-count">' + count + '</span><span class="cap">' + (count === 1 ? 'risk' : 'risks') + '</span></button>';
    }
  }
  cells += '<div></div>' + RISK_LEVELS.map(impact => '<div class="riskheatmap-colhead">' + riskLevelWord(impact) + '</div>').join('');
  return '<p class="riskheatmap-axes cap">Likelihood ↑ · Impact →</p><div class="riskheatmap-grid">' + cells + '</div>';
}

function riskHeatmapLegendHtml() {
  return '<p class="riskheatmap-legend"><span class="risk-chip elevated">Elevated</span> Shaded boxes are Elevated · Grayed boxes have no risks</p>';
}

/* What the picked box holds. With nothing picked, the Elevated box with the most risks is shown. */
function riskHeatmapDefaultPick(narrowed) {
  const answer = riskHeatmapState.answer;
  let best = null;
  let bestScore = -1;
  for (const likelihood of RISK_LEVELS) {
    for (const impact of RISK_LEVELS) {
      const count = riskHeatmapCellCount(narrowed.cells[likelihood][impact]);
      if (!count) continue;
      const elevatedBonus = riskHeatmapIsElevatedCell(answer, likelihood, impact) ? RISK_HEATMAP_ELEVATED_BONUS : 0;
      const score = elevatedBonus + count;
      if (score > bestScore) { bestScore = score; best = {likelihood: likelihood, impact: impact}; }
    }
  }
  return best;
}

function riskHeatmapDetailHtml(answer, narrowed) {
  const picked = riskHeatmapState.picked || riskHeatmapDefaultPick(narrowed);
  if (!picked) return '<h3>Which risks sit where</h3><p class="cap">Nothing to show for this choice.</p>';
  const items = narrowed.cells[picked.likelihood][picked.impact];
  const rows = items.map(item => '<li class="riskheatmap-detailrow"><div class="riskheatmap-focushead">'
    + '<span class="riskheatmap-focusname"><b>' + esc(item.risk_name) + '</b>'
    + '<span class="' + (item.elevated_assessments ? 'riskheatmap-elevatedtag' : 'cap') + '">' + esc(item.risk_id) + (item.block ? ' · ' + esc(item.block) : '') + (item.elevated_assessments ? ' · Elevated' : '') + '</span></span>'
    + '<span class="cap riskheatmap-nowrap">' + riskHeatmapInAssessments(item.assessments) + '</span></div>'
    + riskHeatmapRiskHelpHtml(answer, item.risk_id) + '</li>').join('');
  return '<div class="riskheatmap-cardhead"><h3>Likelihood ' + riskLevelWord(picked.likelihood) + ' · Impact ' + riskLevelWord(picked.impact) + '</h3>'
    + '<span class="cap">' + plural(riskHeatmapCellCount(items), 'risk', 'risks') + ' in this box · ' + riskHeatmapGuideLinkHtml() + '</span></div>'
    + '<ul class="riskheatmap-detaillist">' + rows + '</ul>';
}

function riskHeatmapWireBody() {
  document.querySelectorAll('.riskheatmap-gridcard button.riskheatmap-cell').forEach(button => {
    button.addEventListener('click', () => { riskHeatmapState.picked = {likelihood: button.dataset.likelihood, impact: button.dataset.impact}; riskHeatmapDrawBody(); });
  });
  const more = document.getElementById('riskheatmap-focusmore');
  if (more) more.addEventListener('click', () => { riskHeatmapState.focusOpen = !riskHeatmapState.focusOpen; riskHeatmapDrawBody(); });
}

riskTopBarLinks.push({id: 'risk-heatmaplink', href: '#/heat-map', words: 'Risk heat map', isShown: () => true});   // everyone who can open the site: the page holds totals only
riskAddPage(parts => parts[0] === 'matrix', () => location.replace('#/heat-map'));                                // the old address
riskAddPage(parts => parts[0] === 'heat-map', riskHeatmapDrawPage);
