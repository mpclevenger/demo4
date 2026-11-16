/* The Risk site: the front page, in three equal parts (tabs): Continue an assessment, Start a new assessment, View results.
   Each part is a table. No ratings or counts here: risk results are never compared across teams. */
"use strict";

/* A status as a chip. A status this page does not know is drawn gray. */
const RISK_STATUS_COLORS = {'Not started': 'gray', 'Draft': 'amber', 'Submitted': 'green', 'Signed off': 'green', 'Sent back': 'red'};

function riskStatusChip(status) {
  return '<span class="risk-chip ' + (RISK_STATUS_COLORS[status] || 'gray') + '">' + esc(status) + '</span>';
}

/* Who the team is, in one line. */
function riskTeamWho(team) {
  const people = plural(team.people, 'person', 'people');
  if (team.lead) return 'TRUST team led by ' + esc(team.lead) + ' · ' + people;
  return 'TRUST team · ' + people;
}

const riskHome = {groups: [], tab: null, note: null};
const RISK_HOME_TABS = [
  {id: 'continue', words: 'Continue an assessment'},
  {id: 'start', words: 'Start a new assessment'},
  {id: 'results', words: 'View results'}
];

function riskHomeLink(group, ending) {
  return '#/group/' + encodeURIComponent(group.id) + (ending || '');
}

/* "15 Nov 2026, 2:03 PM by Pat Lee (pat1)" */
function riskHomeWhenBy(moment) {
  if (!moment) return '<span class="cap">—</span>';
  return when(moment.at) + '<br><span class="cap">by ' + esc(moment.by) + '</span>';
}

function riskHomeProgress(open) {
  return open.answered + ' of ' + plural(open.of, 'question', 'questions') + ' ' + open.counted_as;
}

function riskHomeTable(headings, rows) {
  return '<div class="risk-home-scroll"><table class="risk-table"><thead><tr>'
    + headings.map(heading => '<th scope="col">' + heading + '</th>').join('') + '</tr></thead><tbody>'
    + rows.join('') + '</tbody></table></div>';
}

function riskHomeContinue() {
  const open = riskHome.groups.filter(group => group.open && group.can.answer);
  if (!open.length) return '<p class="risk-home-none">No assessments are in progress. To begin one, use “Start a new assessment”.</p>';
  const rows = open.map(group => {
    const sentBack = group.open.status === 'Sent back' && group.signoff;
    const reason = sentBack ? '<br><span class="cap">' + esc(group.signoff.by) + ': ' + esc(group.signoff.note) + '</span>' : '';
    return '<tr><th scope="row">' + esc(group.name) + '</th><td>' + riskHomeWhenBy(group.open.started) + '</td><td>' + riskHomeWhenBy(group.open.last_saved)
      + '</td><td>' + riskHomeProgress(group.open) + '</td><td>' + riskStatusChip(group.open.status) + reason
      + '</td><td class="risk-home-act"><a class="risk-button primary" href="' + riskHomeLink(group) + '">Continue</a></td></tr>';
  });
  return riskHomeTable(['Team', 'Started', 'Last saved', 'Progress', 'Status', ''], rows);
}

function riskHomeStart() {
  const mine = riskHome.groups.filter(group => group.can.answer);
  if (!mine.length) return '<p class="risk-home-none">There are no teams you can start an assessment for.</p>';
  const rows = mine.map(group => {
    const last = group.assessments > 0 ? when(group.submitted_at) : '<span class="cap">Never assessed</span>';
    const action = group.open
      ? '<a href="' + riskHomeLink(group) + '">In progress — continue it</a>'
      : '<button type="button" class="risk-button primary" data-start="' + esc(group.id) + '">Start</button>';
    const prefill = !group.open && group.assessments > 0 ? '<br><span class="cap">Opens with the last submitted answers.</span>' : '';
    return '<tr><th scope="row">' + esc(group.name) + '<br><span class="cap">' + riskTeamWho(group) + '</span></th><td>' + last
      + '</td><td class="risk-home-act">' + action + prefill + '</td></tr>';
  });
  return riskHomeTable(['Team', 'Last submitted', ''], rows);
}

function riskHomeResults() {
  const submitted = riskHome.groups.filter(group => group.assessments > 0);
  if (!submitted.length) return '<p class="risk-home-none">No team you can view has submitted an assessment yet.</p>';
  const rows = submitted.map(group => '<tr><th scope="row">' + esc(group.name) + '</th><td>' + when(group.submitted_at)
    + '</td><td>' + riskStatusChip(group.results_status) + '</td><td class="risk-home-act"><a class="risk-button" href="' + riskHomeLink(group, '/results') + '">View results</a></td></tr>');
  return riskHomeTable(['Team', 'Last submitted', 'Sign-off', ''], rows);
}

function riskHomeCount(tabId) {
  if (tabId === 'continue') return riskHome.groups.filter(group => group.open && group.can.answer).length;
  if (tabId === 'start') return riskHome.groups.filter(group => group.can.answer).length;
  return riskHome.groups.filter(group => group.assessments > 0).length;
}

function riskHomeDraw() {
  const tabs = RISK_HOME_TABS.map(tab => '<button type="button" role="tab" class="risk-home-tab" id="risk-tab-' + tab.id + '" data-tab="' + tab.id
    + '" aria-selected="' + (riskHome.tab === tab.id) + '" aria-controls="risk-home-panel">' + tab.words + ' <span class="risk-chip gray risk-home-count">' + riskHomeCount(tab.id) + '</span></button>').join('');
  const panel = {continue: riskHomeContinue, start: riskHomeStart, results: riskHomeResults}[riskHome.tab]();
  let body = '<h2 class="risk-title">Risk assessments</h2>'
    + '<p class="risk-intro">Pick up an assessment you began, start a new one for a team, or look at a team’s results. The site rates each risk for the team once it is submitted.</p>';
  body += '<p class="cap"><a href="/api/risk/download">Download risks and drivers</a> (a .zip in the risk engine\'s file shape, for TRAC)</p>';
  for (const extra of riskHomeExtras) {
    if (extra.isShown()) body += extra.html();
  }
  if (riskHome.note) body += '<p class="banner">' + esc(riskHome.note) + '</p>';
  body += '<div class="risk-home-tabs" role="tablist" aria-label="What would you like to do?">' + tabs + '</div>'
    + '<section class="risk-home-panel" id="risk-home-panel" role="tabpanel" aria-labelledby="risk-tab-' + riskHome.tab + '">' + panel + '<p class="risk-error" id="risk-home-problem" role="alert"></p></section>';
  riskShow(body);
  const main = document.getElementById('risk-main');
  main.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    riskHome.tab = button.dataset.tab;
    sessionStorage.setItem('riskHomeTab', riskHome.tab);
    riskHomeDraw();
    document.getElementById('risk-tab-' + riskHome.tab).focus();
  }));
  main.querySelectorAll('[data-start]').forEach(button => button.addEventListener('click', () => riskHomeStartOne(button)));
}

/* Start: the site keeps who and when, then the form opens with the team's last answers in place. */
async function riskHomeStartOne(button) {
  button.disabled = true;
  const groupId = button.dataset.start;
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId) + '/start', {});
  if (!answer.ok) {
    button.disabled = false;
    document.getElementById('risk-home-problem').textContent = answer.error + ' Nothing was started.';
    return;
  }
  location.hash = '#/group/' + encodeURIComponent(groupId);
}

async function riskDrawHome() {
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/risk/groups');
  if (!answer.ok) { riskShowProblem(answer.error); return; }
  riskHome.groups = answer.groups;
  riskHome.note = answer.note;
  const remembered = sessionStorage.getItem('riskHomeTab');
  riskHome.tab = RISK_HOME_TABS.some(tab => tab.id === remembered) ? remembered : (riskHomeCount('continue') ? 'continue' : 'start');
  if (!answer.groups.length) {
    riskShow('<h2 class="risk-title">Risk assessments</h2>' + (answer.note ? '<p class="banner">' + esc(answer.note) + '</p>' : '')
      + '<div class="risk-card"><p>There are no teams you can open yet. The teams are TRUST\'s teams, so they appear once TRUST holds them and you are one of their people (or Tech Risk, or leadership).</p></div>');
    return;
  }
  riskHomeDraw();
}
