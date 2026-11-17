/* The Risk site: the front page. A box at the top gets a team lead to their own questionnaire (their teams as big
   buttons, or a search to find the team), four numbered steps say how it works, then three parts (tabs): Continue an
   assessment, Start a new assessment, View results. Each part is a table, grouped under its L3 teams. No ratings or counts here: risk results are never compared across teams. */
"use strict";

/* A status as a chip. A status this page does not know is drawn gray. */
const RISK_STATUS_COLORS = {'Not started': 'gray', 'Draft': 'amber', 'Submitted': 'green', 'Signed off': 'green', 'Sent back': 'red'};

function riskStatusChip(status) {
  return '<span class="risk-chip ' + (RISK_STATUS_COLORS[status] || 'gray') + '">' + esc(status) + '</span>';
}

/* Who the team is, in one line. A team here is an L4 team: its leader and everyone under them. */
function riskTeamWho(team) {
  const people = plural(team.people, 'person', 'people');
  if (team.lead) return 'L4 team led by ' + esc(team.lead) + ' · ' + people;
  return 'L4 team · ' + people;
}

const riskHome = {groups: [], tab: null, note: null, search: ''};
const RISK_HOME_TABS = [
  {id: 'continue', words: 'Continue an assessment'},
  {id: 'start', words: 'Start a new assessment'},
  {id: 'results', words: 'View results'}
];

/* The four steps, in one line under the title. */
const RISK_HOME_STEPS = [
  'Find your team',
  'Answer the questions (saved as you go)',
  'Submit',
  'The L4 leader signs off'
];

function riskHomeLink(group, ending) {
  return '#/group/' + encodeURIComponent(group.id) + (ending || '');
}

/* The team's results page (the page for one team, open to everyone who can open the site). */
function riskTeamResultsLink(group) {
  return '#/team/' + encodeURIComponent(group.id);
}

/* "15 Nov 2026, 2:03 PM by Pat Lee (pat1)" */
function riskHomeWhenBy(moment) {
  if (!moment) return '<span class="cap">—</span>';
  return when(moment.at) + '<br><span class="cap">by ' + esc(moment.by) + '</span>';
}

function riskHomeProgress(open) {
  return open.answered + ' of ' + plural(open.of, 'question', 'questions') + ' ' + open.counted_as;
}

/* The words a search looks in: team, leader and L3 team. */
function riskHomeFindText(group) {
  return [group.name, group.lead, group.l3_name].filter(Boolean).join(' ').toLowerCase();
}

/* A table whose rows sit under a light heading row for each L3 team. The groups arrive in L3 order, so each
   L3 team's L4 teams are together. Each row carries what a search looks in, so typing can hide rows. */
function riskHomeTable(headings, groups, rowOf) {
  let body = '';
  let currentL3 = null;
  for (const group of groups) {
    const l3Name = group.l3_name || 'Other teams';
    if (l3Name !== currentL3) {
      currentL3 = l3Name;
      body += '<tr class="risk-l3-row" data-l3="' + esc(l3Name) + '"><th scope="colgroup" colspan="' + headings.length + '">' + esc(l3Name) + ' <span class="cap">L3 team</span></th></tr>';
    }
    body += rowOf(group).replace('<tr>', '<tr data-find="' + esc(riskHomeFindText(group)) + '" data-under="' + esc(l3Name) + '">');
  }
  return '<div class="risk-home-scroll"><table class="risk-table"><thead><tr>'
    + headings.map(heading => '<th scope="col">' + heading + '</th>').join('') + '</tr></thead><tbody>'
    + body + '</tbody></table></div><p class="risk-home-none" id="risk-home-nomatch" hidden>No team matches. Try a shorter word, or a leader’s name.</p>';
}

function riskHomeContinue() {
  const open = riskHome.groups.filter(group => group.open && group.can.answer);
  if (!open.length) return '<p class="risk-home-none">No assessments are in progress. To begin one, use “Start a new assessment”.</p>';
  return riskHomeTable(['L4 team', 'Started', 'Last saved', 'Progress', 'Status', ''], open, group => {
    const sentBack = group.open.status === 'Sent back' && group.signoff;
    const reason = sentBack ? '<br><span class="cap">' + esc(group.signoff.by) + ': ' + esc(group.signoff.note) + '</span>' : '';
    return '<tr><th scope="row">' + esc(group.name) + '</th><td>' + riskHomeWhenBy(group.open.started) + '</td><td>' + riskHomeWhenBy(group.open.last_saved)
      + '</td><td>' + riskHomeProgress(group.open) + '</td><td>' + riskStatusChip(group.open.status) + reason
      + '</td><td class="risk-home-act"><a class="risk-button primary" href="' + riskHomeLink(group) + '">Continue answering</a></td></tr>';
  });
}

function riskHomeStart() {
  const mine = riskHome.groups.filter(group => group.can.answer);
  if (!mine.length) return '<p class="risk-home-none">There are no L4 teams you can answer questions for.</p>';
  return riskHomeTable(['L4 team', 'Last submitted', ''], mine, group => {
    const last = group.assessments > 0 ? when(group.submitted_at) : '<span class="cap">Never assessed</span>';
    const action = group.open
      ? '<a class="risk-button primary" href="' + riskHomeLink(group) + '">Continue answering</a>'
      : '<button type="button" class="risk-button primary" data-start="' + esc(group.id) + '">Answer questions</button>';
    const prefill = !group.open && group.assessments > 0 ? '<br><span class="cap">Opens with the last submitted answers.</span>' : '';
    return '<tr><th scope="row">' + esc(group.name) + '<br><span class="cap">' + riskTeamWho(group) + '</span></th><td>' + last
      + '</td><td class="risk-home-act">' + action + prefill + '</td></tr>';
  });
}

function riskHomeResults() {
  const submitted = riskHome.groups.filter(group => group.assessments > 0);
  if (!submitted.length) return '<p class="risk-home-none">No L4 team you can view has submitted an assessment yet.</p>';
  return riskHomeTable(['L4 team', 'Last submitted', 'Sign-off', ''], submitted, group =>
    '<tr><th scope="row">' + esc(group.name) + '</th><td>' + when(group.submitted_at)
    + '</td><td>' + riskStatusChip(group.results_status) + '</td><td class="risk-home-act"><a class="risk-button" href="' + riskTeamResultsLink(group) + '">View results</a></td></tr>');
}

function riskHomeCount(tabId) {
  if (tabId === 'continue') return riskHome.groups.filter(group => group.open && group.can.answer).length;
  if (tabId === 'start') return riskHome.groups.filter(group => group.can.answer).length;
  return riskHome.groups.filter(group => group.assessments > 0).length;
}

/* "Find your team": the box that filters the table below as the person types. */
function riskHomeSearchBox(label) {
  return '<div class="risk-home-search"><label for="risk-home-find"><b>' + label + '</b></label> '
    + '<input id="risk-home-find" type="search" autocomplete="off" placeholder="Type a team, a leader or an L3 team" value="' + esc(riskHome.search) + '"></div>';
}

/* The one big button for one of the person's own teams: what they most likely want to do next. */
function riskHomeMyTeamButton(group) {
  if (group.open && group.can.answer) {
    const progress = group.open.answered + ' of ' + group.open.of + ' answered';
    return '<a class="risk-button primary risk-home-big" href="' + riskHomeLink(group) + '">Continue answering for ' + esc(group.name) + ' <span class="risk-home-sub">(' + progress + ')</span></a>';
  }
  if (group.assessments > 0 || !group.can.answer) {
    const again = group.can.answer ? ' <button type="button" class="risk-button" data-start="' + esc(group.id) + '">Start a new assessment</button>' : '';
    return '<a class="risk-button primary risk-home-big" href="' + riskTeamResultsLink(group) + '">View results for ' + esc(group.name) + '</a>' + again;
  }
  return '<button type="button" class="risk-button primary risk-home-big" data-start="' + esc(group.id) + '">Answer the questions for ' + esc(group.name) + '</button>';
}

/* The top box. Teams that are the person's own come first as big buttons. Otherwise: find your team. */
function riskHomeTopBox() {
  const mine = riskHome.groups.filter(group => group.mine);
  let box = '<section class="risk-card risk-home-top" aria-labelledby="risk-home-top-title"><h3 id="risk-home-top-title">Answer your team’s questionnaire</h3>';
  if (mine.length) {
    box += '<p>' + (mine.length === 1 ? 'This is your team. Click to answer its questions.' : 'These are your teams. Click one to answer its questions.') + '</p>'
      + '<div class="risk-home-mine">' + mine.map(group => '<div class="risk-home-mine-row">' + riskHomeMyTeamButton(group) + '</div>').join('') + '</div>'
      + '<p class="cap">Not your team? Find it in the list below.</p>';
  } else {
    box += '<p>Pick your team, then click <b>Answer questions</b>.</p>' + riskHomeSearchBox('Find your team');
  }
  return box + '</section>';
}

/* The small line for Tech Risk only: the download and the engine comparison. */
function riskHomeTechRiskLine() {
  if (!riskIsTechRisk()) return '';
  let line = '<a href="/api/risk/download">Download risks and drivers</a> (a .zip in the risk engine’s file shape, for TRAC)';
  for (const extra of riskHomeExtras) {
    if (extra.isShown()) line += ' ' + extra.html();
  }
  return '<div class="risk-home-techrisk cap"><b>For Tech Risk:</b> ' + line + '</div>';
}

/* Typing in the search box hides the rows that do not match, and the L3 heading of a team with no rows left. */
function riskHomeFilter() {
  const words = riskHome.search.toLowerCase().split(/\s+/).filter(Boolean);
  const main = document.getElementById('risk-main');
  const shownUnder = new Set();
  let shown = 0;
  main.querySelectorAll('tr[data-find]').forEach(row => {
    const text = row.dataset.find;
    const matches = words.every(word => text.includes(word));
    row.hidden = !matches;
    if (matches) { shownUnder.add(row.dataset.under); shown += 1; }
  });
  main.querySelectorAll('tr.risk-l3-row').forEach(row => { row.hidden = !shownUnder.has(row.dataset.l3); });
  const nothing = document.getElementById('risk-home-nomatch');
  if (nothing) nothing.hidden = shown > 0 || main.querySelectorAll('tr[data-find]').length === 0;
}

function riskHomeDraw() {
  const tabs = RISK_HOME_TABS.map(tab => '<button type="button" role="tab" class="risk-home-tab" id="risk-tab-' + tab.id + '" data-tab="' + tab.id
    + '" aria-selected="' + (riskHome.tab === tab.id) + '" aria-controls="risk-home-panel">' + tab.words + ' <span class="risk-chip gray risk-home-count">' + riskHomeCount(tab.id) + '</span></button>').join('');
  const panel = {continue: riskHomeContinue, start: riskHomeStart, results: riskHomeResults}[riskHome.tab]();
  const hasMine = riskHome.groups.some(group => group.mine);
  let body = '<h2 class="risk-title">Risk assessments</h2>'
    + '<ol class="risk-home-steps">' + RISK_HOME_STEPS.map(step => '<li>' + step + '</li>').join('') + '</ol>';
  body += riskHomeTopBox();
  if (riskHome.note) body += '<p class="banner">' + esc(riskHome.note) + '</p>';
  if (hasMine) body += riskHomeSearchBox('Find another team');
  body += '<div class="risk-home-tabs" role="tablist" aria-label="What would you like to do?">' + tabs + '</div>'
    + '<section class="risk-home-panel" id="risk-home-panel" role="tabpanel" aria-labelledby="risk-tab-' + riskHome.tab + '">' + panel + '<p class="risk-error" id="risk-home-problem" role="alert"></p></section>';
  body += riskHomeTechRiskLine();
  riskShow(body);
  const main = document.getElementById('risk-main');
  main.querySelectorAll('[data-tab]').forEach(button => button.addEventListener('click', () => {
    riskHome.tab = button.dataset.tab;
    sessionStorage.setItem('riskHomeTab', riskHome.tab);
    riskHomeDraw();
    document.getElementById('risk-tab-' + riskHome.tab).focus();
  }));
  main.querySelectorAll('[data-start]').forEach(button => button.addEventListener('click', () => riskHomeStartOne(button)));
  const finder = document.getElementById('risk-home-find');
  if (finder) finder.addEventListener('input', () => {
    riskHome.search = finder.value;
    // Looking for a team means looking at all of them: "Start a new assessment" lists every team the person may answer for.
    if (riskHome.search && riskHome.tab === 'continue') {
      riskHome.tab = 'start';
      riskHomeDraw();
      const again = document.getElementById('risk-home-find');
      again.focus();
      again.setSelectionRange(again.value.length, again.value.length);
      return;
    }
    riskHomeFilter();
  });
  riskHomeFilter();
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
      + '<div class="risk-card"><p>There are no L4 teams you can open yet. They appear once TRUST holds them and you are one of their people (or Tech Risk, or leadership).</p></div>');
    return;
  }
  riskHomeDraw();
}
