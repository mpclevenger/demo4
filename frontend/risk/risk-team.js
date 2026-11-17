/* The Risk site: a team's risk results (#/team/<id>) and the list of teams (#/teams).
   One page, two layouts: an L4 team (one assessment) and an L3 team (its L4 teams' answers pooled).
   It shows WHAT is on and WHY, never how drivers combine into a rating (owner, 17 Nov 2026).
   Every name starts with "riskTeam" because all the scripts share one global scope. */
"use strict";

const RISK_TEAM_LEVEL_ORDER = ['Critical', 'High', 'Medium', 'Low'];
const RISK_TEAM_NOT_APPLICABLE = "Doesn't apply";
const RISK_TEAM_LEVEL_CLASS = {Critical: 'critical', High: 'high', Medium: 'medium', Low: 'low'};
const RISK_TEAM_NO_VALUE = '—';

/* The risks with the ones that don't apply last; the order the server sent is otherwise kept. */
function riskTeamInOrder(risks) {
  return risks.filter(risk => risk.applies).concat(risks.filter(risk => !risk.applies));
}

/* ---------- small helpers ---------- */

/* "2026-11-14" becomes "14 Nov 2026", or "14 Nov" with the year left off. */
function riskTeamDay(isoDay, withYear) {
  if (!isoDay) return '';
  const day = new Date(String(isoDay).slice(0, 10) + 'T12:00:00');
  if (isNaN(day)) return esc(isoDay);
  const options = withYear ? {day: 'numeric', month: 'short', year: 'numeric'} : {day: 'numeric', month: 'short'};
  return day.toLocaleDateString('en-GB', options);
}

/* "2026-10" becomes "October 2026". */
function riskTeamMonth(isoMonth) {
  if (!isoMonth) return '';
  const first = new Date(isoMonth + '-01T12:00:00');
  if (isNaN(first)) return esc(isoMonth);
  return first.toLocaleDateString('en-GB', {month: 'long', year: 'numeric'});
}

/* A level (Critical, High, Medium or Low) as a small pill. Words can be given when the pill says more ("2 High"). */
function riskTeamPill(level, words) {
  return '<span class="rt-lvl rt-' + (RISK_TEAM_LEVEL_CLASS[level] || 'low') + '">' + esc(words || level) + '</span>';
}

function riskTeamNotApplicablePill(words) {
  return '<span class="rt-lvl rt-na">' + esc(words || RISK_TEAM_NOT_APPLICABLE) + '</span>';
}

function riskTeamElevatedMark() {
  return '<span class="rt-elevated">Elevated</span>';
}

/* The count pills for a set of counts: "2 Elevated", then each likelihood level, then "1 doesn't apply".
   With showZeros every likelihood level shows, even with none ("0 Critical"). */
function riskTeamCountPills(counts, showZeros) {
  if (!counts) return '';
  const elevated = counts.elevated || 0;
  let pills = (elevated > 0 || showZeros) ? '<span class="rt-elevated rt-count">' + elevated + ' Elevated</span>' : '';
  for (const level of RISK_TEAM_LEVEL_ORDER) {
    const count = (counts.likelihood || {})[level] || 0;
    if (count > 0 || showZeros) pills += riskTeamPill(level, count + ' ' + level);
  }
  const notApplicable = counts.doesnt_apply || 0;
  if (notApplicable > 0) pills += riskTeamNotApplicablePill(notApplicable + " doesn't apply");
  return pills;
}

/* "Lending Engineering" under the L3 team "Lending" is shown as "Engineering" where it is clear which team is meant. */
function riskTeamShortName(teamName, l3Name) {
  if (l3Name && teamName.indexOf(l3Name + ' ') === 0) return teamName.slice(l3Name.length + 1);
  return teamName;
}

function riskTeamAnchor(riskId) {
  return 'risk-team-detail-' + String(riskId).replace(/[^A-Za-z0-9]+/g, '-');
}

function riskTeamTeamLink(teamId, words) {
  return '<a href="#/team/' + encodeURIComponent(teamId) + '">' + esc(words) + '</a>';
}

/* ---------- the top of the page ---------- */

/* Who submitted, in one line, for an L3 team: "both L4 teams submitted (12 and 14 Nov 2026)". */
function riskTeamSubmittedLine(l4Teams) {
  if (!l4Teams.length) return '';
  const submitted = l4Teams.filter(team => team.assessed_on);
  if (!submitted.length) return 'no L4 team has submitted yet';
  const days = [...new Set(submitted.map(team => String(team.assessed_on).slice(0, 10)))].sort();
  const sameMonthAndYear = days.every(day => day.slice(0, 7) === days[0].slice(0, 7));
  let dateWords;
  if (sameMonthAndYear && days.length > 1) {
    const dayNumbers = days.map(day => String(Number(day.slice(8, 10))));
    dateWords = listOf(dayNumbers) + ' ' + riskTeamDay(days[0], true).replace(/^\d+ /, '');
  } else {
    dateWords = listOf(days.map(day => riskTeamDay(day, true)));
  }
  const who = submitted.length === l4Teams.length
    ? (l4Teams.length === 2 ? 'both L4 teams' : 'all ' + l4Teams.length + ' L4 teams')
    : submitted.length + ' of ' + plural(l4Teams.length, 'L4 team', 'L4 teams');
  return who + ' submitted (' + dateWords + ')';
}

function riskTeamCrumb(team) {
  let crumb = '<a href="#/teams">Teams’ results</a> / ';
  if (team.level === 'L4' && team.l3) crumb += riskTeamTeamLink(team.l3.id, team.l3.name) + ' / ';
  return '<div class="cap risk-crumb">' + crumb + esc(team.name) + riskGuideLink('/guides/reading-your-results-and-the-risk-heat-map/', 'reading your results') + '</div>';
}

function riskTeamRatedLine(team) {
  const rules = team.rated_with_current_rules ? 'Rated with today’s questions and rules.' : 'Rated with the questions and rules in place when it was submitted.';
  const data = team.data_month ? ' TRUST data from ' + riskTeamMonth(team.data_month) + '.' : '';
  const pooled = team.level === 'L3'
    ? 'Rated as one team from its L4 teams’ answers together: a driver is on for ' + esc(team.name) + ' when it is on in any of its L4 teams. '
    : '';
  return '<div class="cap rt-rated">' + pooled + rules + data + '</div>';
}

function riskTeamHeaderHtml(team) {
  const people = plural(team.people, 'person', 'people');
  const lead = team.lead ? 'led by ' + esc(team.lead) : '';
  let facts;
  if (team.level === 'L4') {
    const parts = ['L4 team' + (team.l3 ? ' in ' + riskTeamTeamLink(team.l3.id, team.l3.name) : '')];
    if (lead) parts.push(lead);
    parts.push(people);
    if (team.assessed_on) parts.push('assessment submitted ' + riskTeamDay(team.assessed_on, true));
    if (team.signed_off) parts.push('signed off by ' + esc(team.signed_off.by) + ' on ' + riskTeamDay(team.signed_off.on, false));
    facts = parts.join(' · ');
  } else {
    const parts = ['L3 team' + (lead ? ' ' + lead : ''), plural(team.l4_teams.length, 'L4 team', 'L4 teams'), people];
    const submitted = riskTeamSubmittedLine(team.l4_teams);
    if (submitted) parts.push(submitted);
    facts = parts.join(' · ');
  }
  const chip = team.proposed ? ' <span class="rt-proposed-chip">Proposed</span>' : '';
  return '<div>' + riskTeamCrumb(team) + '<h1 class="risk-title rt-title">' + esc(team.name) + chip + '</h1><div class="rt-facts">' + facts + '</div>'
    + riskTeamRatedLine(team) + '</div>';
}

/* ---------- L3 only: its L4 teams ---------- */

const RISK_TEAM_STATUS_WORDS = {
  'Signed off': 'Signed off',
  'Submitted': 'Waiting for sign-off',
  'Sent back': 'Sent back for changes',
  'In progress': 'In progress',
  'Not started': 'Not started'
};

function riskTeamL4CardHtml(l4Team) {
  const counts = riskTeamCountPills(l4Team.counts, false);
  const status = RISK_TEAM_STATUS_WORDS[l4Team.status] || l4Team.status;
  const assessed = (l4Team.assessed_on ? ' · assessed ' + riskTeamDay(l4Team.assessed_on, false) : '') + (l4Team.proposed ? ' · proposed results' : '');
  return '<a class="rt-l4card" href="#/team/' + encodeURIComponent(l4Team.id) + '">'
    + '<div class="rt-l4top"><b>' + esc(l4Team.name) + '</b><span class="cap">' + esc(status) + assessed + '</span></div>'
    + '<div class="cap">' + esc(l4Team.lead || 'No leader named') + ' · ' + plural(l4Team.people, 'person', 'people') + '</div>'
    + '<div class="rt-pills">' + (counts || '<span class="cap">No results yet</span>') + '</div></a>';
}

function riskTeamL4StripHtml(team) {
  if (team.level !== 'L3' || !team.l4_teams.length) return '';
  return '<section class="risk-card rt-card" aria-labelledby="rt-l4s"><h2 id="rt-l4s">L4 teams</h2><div class="rt-grid">'
    + team.l4_teams.map(riskTeamL4CardHtml).join('') + '</div></section>';
}

/* ---------- key insights ---------- */

/* Key insights (owner, 17 Nov 2026): a short story, then up to three points on where to focus, each a driver in plain
   words and the risks it pushes up. Written on the server (team_results.insights_for). */
function riskTeamInsightsHtml(results) {
  const insights = results.insights;
  if (!insights || !insights.story) return '';
  const focus = (insights.focus || []).length
    ? '<h3 class="rt-focus-h">Where to focus</h3><ol class="rt-focus">' + insights.focus.map(point =>
        '<li><b>' + esc(point.title) + '</b> <span class="rt-code">' + esc(point.code) + '</span><div>' + esc(point.text) + '</div></li>').join('') + '</ol>'
    : '';
  return '<section class="risk-card rt-card" aria-labelledby="rt-ki"><h2 id="rt-ki">Key insights</h2><p class="rt-story">' + esc(insights.story) + '</p>'
    + focus + '</section>';
}

/* ---------- risk summary ---------- */

/* How each L4 team rates on its own, one line each: "Engineering: likelihood High, impact Medium, Elevated". */
function riskTeamByL4Words(risk, l3Name) {
  return (risk.by_l4 || []).map(entry => {
    const name = esc(riskTeamShortName(entry.team, l3Name));
    if (!entry.likelihood && !entry.impact) return '<div>' + name + ': doesn’t apply</div>';
    return '<div>' + name + ': likelihood ' + esc(entry.likelihood || RISK_TEAM_NO_VALUE) + ', impact ' + esc(entry.impact || RISK_TEAM_NO_VALUE)
      + (entry.elevated ? ', <b class="rt-elevatedword">Elevated</b>' : '') + '</div>';
  }).join('');
}

/* The likelihood or impact of a risk as a pill; a risk that doesn't apply says so once, in the first column. */
function riskTeamLevelCell(risk, level, saysNotApplicable) {
  if (!risk.applies) return saysNotApplicable ? riskTeamNotApplicablePill() : RISK_TEAM_NO_VALUE;
  return level ? riskTeamPill(level) : RISK_TEAM_NO_VALUE;
}

function riskTeamElevatedCell(risk) {
  return risk.elevated ? riskTeamElevatedMark() : '<span class="cap">' + RISK_TEAM_NO_VALUE + '</span>';
}

function riskTeamSummaryRowHtml(risk, team) {
  const isL3 = team.level === 'L3';
  return '<tr' + (risk.applies ? '' : ' class="rt-greyed"') + '><td><b>' + esc(risk.category) + '</b></td>'
    + '<td><a href="#" data-rt-jump="' + riskTeamAnchor(risk.id) + '">' + esc(risk.name) + '</a><div class="cap">' + esc(risk.id) + '</div></td>'
    + '<td>' + riskTeamLevelCell(risk, risk.likelihood, true) + '</td><td>' + riskTeamLevelCell(risk, risk.impact, false) + '</td>'
    + '<td>' + riskTeamElevatedCell(risk) + '</td>'
    + (isL3 ? '<td class="cap">' + riskTeamByL4Words(risk, team.name) + '</td>' : '') + '</tr>';
}

function riskTeamSummaryHtml(results) {
  const team = results.team;
  const isL3 = team.level === 'L3';
  const intro = isL3
    ? 'Each risk by category, rated for ' + esc(team.name) + ' as one team. The last column shows how each L4 team rates on its own.'
    : 'Each risk by category, rated with the rating settings Tech Risk sets.';
  return '<section class="risk-card rt-card" aria-labelledby="rt-rs"><div class="rt-headrow"><h2 id="rt-rs">Risk summary</h2>'
    + '<div class="rt-pills">' + riskTeamCountPills(results.counts, true) + '</div></div>'
    + '<p class="muted rt-intro">' + intro + '</p><div class="rt-scroll"><table class="rt-table"><thead><tr>'
    + '<th class="rt-w120">Category</th><th>Risk</th><th class="rt-w100">Likelihood</th><th class="rt-w100">Impact</th><th class="rt-w100">Elevated</th>'
    + (isL3 ? '<th class="rt-w260">L4 teams on their own</th>' : '') + '</tr></thead><tbody>'
    + riskTeamInOrder(results.risks).map(risk => riskTeamSummaryRowHtml(risk, team)).join('') + '</tbody></table></div></section>';
}

/* ---------- risk and driver summary ---------- */

/* Where a driver lands: "Cyber · 1 risk" for a likelihood driver, "Change · regulatory" for an impact driver. */
function riskTeamWhereWords(place, isImpact) {
  if (isImpact && place.dimensions && place.dimensions.length) return place.category + ' · ' + place.dimensions.join(', ');
  return place.category + ' · ' + plural(place.risks, 'risk', 'risks');
}

function riskTeamDriverHtml(driver, isImpact, team) {
  const pervasive = driver.pervasive ? '<span class="rt-pervasive">Pervasive</span>' : '';
  const sourceLine = team.level === 'L3'
    ? 'On in: ' + esc((driver.teams || []).map(name => riskTeamShortName(name, team.name)).join(', '))
    : esc(driver.source);
  return '<div class="rt-driver"><div class="rt-driverhead"><span class="rt-code">' + esc(driver.code) + '</span><b>' + esc(driver.name) + '</b>' + pervasive + '</div>'
    + '<div class="cap rt-driversource">' + sourceLine + '</div>'
    + '<div>' + (driver.where || []).map(place => '<span class="rt-tag">' + esc(riskTeamWhereWords(place, isImpact)) + '</span>').join('') + '</div></div>';
}

function riskTeamDriverColumnHtml(title, drivers, total, isImpact, team) {
  return '<div><h3>' + title + ' <span class="cap">(' + drivers.length + ' of ' + total + ')</span></h3>'
    + (drivers.length ? drivers.map(driver => riskTeamDriverHtml(driver, isImpact, team)).join('') : '<p class="cap">None on.</p>');
}

/* L4 only: how many drivers each category has on, and how many risks. */
function riskTeamLandHtml(categories) {
  if (!categories || !categories.length) return '';
  return '<div class="rt-land"><b>Where the drivers land</b><div class="rt-landgrid"><span></span><span class="cap">Likelihood</span><span class="cap">Impact</span><span class="cap">Risks</span>'
    + categories.map(category => '<span>' + esc(category.name) + '</span><span>' + plural(category.likelihood_drivers, 'driver', 'drivers') + '</span><span>'
      + plural(category.impact_drivers, 'driver', 'drivers') + '</span><span>' + plural(category.risks, 'risk', 'risks') + '</span>').join('')
    + '</div></div>';
}

function riskTeamDriversHtml(results) {
  const team = results.team;
  const intro = team.level === 'L3'
    ? 'The drivers that are on for ' + esc(team.name) + ', which L4 teams they come from, and where each one lands. Pervasive = reaches three or more risk categories.'
    : 'The drivers that are on for this team, and where each one lands. A driver is <b>pervasive</b> when it reaches three or more risk categories.';
  const totals = results.drivers_total || {likelihood: results.drivers.likelihood.length, impact: results.drivers.impact.length};
  return '<section class="risk-card rt-card" aria-labelledby="rt-ds"><h2 id="rt-ds">Risk and driver summary</h2><p class="muted rt-intro">' + intro + '</p><div class="rt-twocol">'
    + riskTeamDriverColumnHtml('Likelihood drivers on', results.drivers.likelihood, totals.likelihood, false, team) + '</div>'
    + riskTeamDriverColumnHtml('Impact drivers on', results.drivers.impact, totals.impact, true, team)
    + (team.level === 'L4' ? riskTeamLandHtml(results.categories) : '') + '</div></div></section>';
}

/* ---------- detailed view ---------- */

function riskTeamDriversOnHtml(drivers) {
  if (!drivers.length) return '<span class="cap">None on</span>';
  return drivers.map(driver => '<div class="rt-on"><span class="rt-code">' + esc(driver.code) + '</span> <span class="rt-txt" title="' + esc(driver.name) + '">' + esc(driver.name) + '</span><div class="cap">' + esc(driver.source) + '</div></div>').join('');
}

function riskTeamDetailRowHtml(risk, team) {
  const isL3 = team.level === 'L3';
  return '<tr id="' + riskTeamAnchor(risk.id) + '"' + (risk.applies ? '' : ' class="rt-greyed"') + '><td><b>' + esc(risk.category) + '</b></td>'
    + '<td>' + esc(risk.name) + '<div class="cap">' + esc(risk.id) + '</div></td>'
    + '<td>' + riskTeamElevatedCell(risk) + '</td>'
    + '<td>' + riskTeamLevelCell(risk, risk.likelihood, true) + '</td><td>' + riskTeamDriversOnHtml(risk.likelihood_drivers || []) + '</td>'
    + '<td>' + riskTeamLevelCell(risk, risk.impact, false) + '</td><td>' + riskTeamDriversOnHtml(risk.impact_drivers || []) + '</td>'
    + (isL3 ? '<td class="cap">' + riskTeamByL4Words(risk, team.name) + '</td>' : '') + '</tr>';
}

function riskTeamDetailHtml(results) {
  const team = results.team;
  const isL3 = team.level === 'L3';
  const intro = 'Every risk with the drivers that are on and the answer or TRUST data behind each one'
    + (isL3 ? ', and which L4 team it comes from' : '') + '. Download it to share with your team. How drivers combine into a rating isn’t shown here.';
  const rowWords = '(category, risk, elevated, likelihood or impact, driver, where it came from' + (isL3 ? ', L4 team' : '') + ')';
  return '<section class="risk-card rt-card" aria-labelledby="rt-dv"><div class="rt-headrow"><h2 id="rt-dv">Detailed view</h2><div class="rt-buttons noprint">'
    + '<a class="risk-button primary" href="/api/risk/teams/' + encodeURIComponent(team.id) + '/results.csv" download>Download (.csv)</a>'
    + '<button type="button" class="risk-button" id="rt-print">Print</button></div></div>'
    + '<p class="muted rt-intro">' + esc(intro) + '</p><div class="rt-scroll"><table class="rt-table rt-detail"><thead><tr>'
    + '<th class="rt-w100">Category</th><th class="rt-w220">Risk</th><th class="rt-w90">Elevated</th><th class="rt-w90">Likelihood</th><th>Likelihood drivers on</th><th class="rt-w90">Impact</th><th>Impact drivers on</th>'
    + (isL3 ? '<th class="rt-w260">L4 teams on their own</th>' : '') + '</tr></thead><tbody>'
    + riskTeamInOrder(results.risks).map(risk => riskTeamDetailRowHtml(risk, team)).join('') + '</tbody></table></div>'
    + '<p class="cap rt-foot">The download has one row per risk and driver ' + esc(rowWords) + ', so it sorts and filters in Excel.</p></section>';
}

/* ---------- not assessed yet ---------- */

function riskTeamNotAssessedHtml(results) {
  const team = results.team;
  const button = team.level === 'L4'
    ? '<p><a class="risk-button primary" href="#/group/' + encodeURIComponent(team.id) + '">Answer the questions</a></p>'
    : '<p class="cap">Each L4 team answers its own questions. Open one above to start.</p>';
  return riskTeamL4StripHtml(team)
    + '<section class="risk-card rt-card"><h2>No results yet</h2><p>' + esc(results.message || 'This team has not submitted an assessment yet, so there are no results to show.') + '</p>' + button + '</section>';
}

/* ---------- the page ---------- */

function riskTeamWire(main) {
  const printButton = document.getElementById('rt-print');
  if (printButton) printButton.addEventListener('click', () => window.print());
  for (const link of main.querySelectorAll('[data-rt-jump]')) {
    link.addEventListener('click', event => {
      event.preventDefault();
      const row = document.getElementById(link.getAttribute('data-rt-jump'));
      if (!row) return;
      row.scrollIntoView({block: 'center'});
      row.classList.add('rt-flash');
      setTimeout(() => row.classList.remove('rt-flash'), 2500);
    });
  }
}

async function riskTeamDrawPage(teamId) {
  riskShow('<p class="muted">Loading…</p>');
  const results = await riskApi('/api/risk/teams/' + encodeURIComponent(teamId) + '/results');
  if (!results.ok) { riskShowProblem(results.error || 'There is no such team.'); return; }
  let body = riskTeamHeaderHtml(results.team) + riskTeamKeptHtml(results.kept);
  if (!results.assessed) {
    body += riskTeamNotAssessedHtml(results);
  } else {
    // Draft answers (saved, not submitted; a bulk upload loads them so) are rated and shown as Proposed (owner, 17 Nov 2026).
    if (results.team.proposed && results.message) body += '<p class="rt-proposed-note" role="note">' + esc(results.message) + '</p>';
    body += riskTeamL4StripHtml(results.team) + riskTeamInsightsHtml(results) + riskTeamSummaryHtml(results)
      + riskTeamDriversHtml(results) + riskTeamDetailHtml(results);
  }
  const main = riskShow('<div class="rt-page">' + body + '</div>');
  riskTeamWire(main);
}

/* ---------- the list of teams ---------- */

function riskTeamIndexRowHtml(l4Team) {
  const status = RISK_TEAM_STATUS_WORDS[l4Team.status] || l4Team.status;
  const counts = riskTeamCountPills(l4Team.counts, false);
  return '<tr><th scope="row">' + riskTeamTeamLink(l4Team.id, l4Team.name) + '<div class="cap">' + esc(l4Team.lead || 'No leader named') + ' · ' + plural(l4Team.people, 'person', 'people') + '</div></th>'
    + '<td>' + esc(status) + (l4Team.proposed ? ' <span class="rt-proposed-chip">Proposed</span>' : '') + '</td><td>' + (l4Team.assessed_on ? riskTeamDay(l4Team.assessed_on, true) : '') + '</td>'
    + '<td><div class="rt-pills">' + (counts || '<span class="cap">No results yet</span>') + '</div></td></tr>';
}

function riskTeamIndexCardHtml(l3Team) {
  const counts = riskTeamCountPills(l3Team.counts, false);
  return '<section class="risk-card rt-card"><div class="rt-headrow"><div><h2>' + riskTeamTeamLink(l3Team.id, l3Team.name) + '</h2>'
    + '<div class="cap">L3 team' + (l3Team.lead ? ' led by ' + esc(l3Team.lead) : '') + ' · ' + plural(l3Team.people, 'person', 'people') + ' · ' + plural(l3Team.l4_teams.length, 'L4 team', 'L4 teams') + '</div></div>'
    + '<div class="rt-pills">' + counts + '</div></div>'
    + (l3Team.l4_teams.length
      ? '<div class="rt-scroll"><table class="rt-table"><thead><tr><th>L4 team</th><th class="rt-w150">Where it stands</th><th class="rt-w120">Assessed</th><th class="rt-w300">Risks by rating</th></tr></thead><tbody>'
        + l3Team.l4_teams.map(riskTeamIndexRowHtml).join('') + '</tbody></table></div>'
      : '<p class="cap">No L4 teams yet.</p>')
    + '</section>';
}

/* "Results as of …" (owner, 17 Nov 2026: results are kept, and worked out in their own process because the website ran
   out of memory doing it). Tech Risk sees how to work them out again. */
function riskTeamKeptHtml(kept) {
  if (!kept) return '';
  const when = String(kept.made_at || '').slice(0, 16).replace('T', ' ');
  const how = riskIsTechRisk() ? ' · To work them out again after new answers, submits or risk files, run <code>python manage.py risk_results</code> in the platform shell.' : '';
  return '<div class="cap rt-kept noprint">Results as of ' + riskTeamDay(when.slice(0, 10), true) + ', ' + esc(when.slice(11)) + ' UTC' + how + '</div>';
}

async function riskTeamDrawIndex() {
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/risk/teams');
  if (!answer.ok) { riskShowProblem(answer.error || 'The list of teams can’t be shown.'); return; }
  const cards = answer.l3_teams.length
    ? answer.l3_teams.map(riskTeamIndexCardHtml).join('')
    : '<p class="muted">' + esc(answer.message || 'No teams are set up yet.') + '</p>';
  riskShow('<div class="rt-page"><div><div class="cap risk-crumb"><a href="#/">Risk assessments</a> / Teams’ results</div><h1 class="risk-title rt-title">Teams’ results</h1>'
    + '<div class="rt-facts">Every L3 team and its L4 teams. Open a team to see what is on and why.</div>' + riskTeamKeptHtml(answer.kept) + '</div>' + cards + '</div>');
}

riskTopBarLinks.push({id: 'risk-teamslink', href: '#/teams', words: 'Teams’ results', isShown: () => true});
riskAddPage(parts => parts[0] === 'teams', riskTeamDrawIndex);
riskAddPage(parts => parts[0] === 'team' && !!parts[1], parts => riskTeamDrawPage(parts[1]));
