/* The Risk site: what every page uses (talking to the server, the top bar, and the lists the page files add themselves to).
   This is a separate front end from TRUST's: it does not load TRUST's page scripts, only /shared/text.js (esc, when, plural).
   All names start with "risk" because every script on the page shares one global scope. */
"use strict";

const riskState = {me: null};
const RISK_NAME_KEY = 'riskTypedName';            // the name typed while TRUST runs open, kept in this browser

/* ---------- who may do what ---------- */

/* Tech Risk (while TRUST runs open, everyone) may edit the lists, upload files and use the engine comparison. */
function riskIsTechRisk() {
  return !!(riskState.me && (riskState.me.open || riskState.me.tech_risk));
}

/* ---------- the four levels: a word and four pips, in neutral ink ---------- */

const RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH', 'CRITICAL'];

function riskLevelWord(level) {
  return level ? level.charAt(0) + level.slice(1).toLowerCase() : 'Not rated';
}

function riskPips(level) {
  const filled = RISK_LEVELS.indexOf(level) + 1;        // Low 1 pip ... Critical 4 pips; not rated 0
  let pips = '';
  for (let place = 1; place <= RISK_LEVELS.length; place++) {
    pips += '<i class="risk-pip' + (place <= filled ? ' on' : '') + '"></i>';
  }
  return '<span class="risk-pips" aria-hidden="true">' + pips + '</span>';
}

/* ---------- talking to the server ---------- */

function riskTypedName() {
  return (localStorage.getItem(RISK_NAME_KEY) || '').trim();
}

/* Always returns the server's JSON (also for a refused change); {ok:false, error} when it can't be reached.
   With a body, it POSTs. A body made with FormData (files) is sent as it is; any other body is sent as JSON.
   Either way the typed name is added as "by". */
async function riskApi(path, body) {
  const options = {headers: {'Accept': 'application/json'}};
  if (body !== undefined) {
    options.method = 'POST';
    options.headers['X-TRUST'] = '1';
    if (body instanceof FormData) {
      body.append('by', riskTypedName());
      options.body = body;
    } else {
      options.headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify({...body, by: riskTypedName()});
    }
  }
  try {
    const response = await fetch(path, options);
    return await response.json().catch(() => ({ok: false, error: 'The server sent something this page can’t read.'}));
  } catch (problem) {
    return {ok: false, error: 'The site can’t be reached right now. Check your connection and try again.'};
  }
}

/* ---------- the top bar and the banners ---------- */

function riskDrawTopBar() {
  const me = riskState.me;
  if (me.test_env) {
    const badge = document.getElementById('risk-env');
    badge.textContent = me.env_label;
    badge.hidden = false;
  }
  const person = document.getElementById('risk-person');
  person.textContent = me.name || '';
  for (const link of riskTopBarLinks) {
    if (link.isShown()) person.insertAdjacentHTML('beforebegin', '<a id="' + link.id + '" class="risk-toplink" href="' + link.href + '">' + esc(link.words) + '</a>');
  }
  if (window.appsMenuMount) window.appsMenuMount(document.getElementById('risk-apps'), 'Risk');

  let banners = '';
  if (me.test_env) {
    banners += '<div class="banner noprint risk-banner risk-test" role="note">TEST environment · synthetic data. Nothing here is real: the teams, people, questions and risks are made up so the site can be tried out.</div>';
  }
  if (me.open) {
    banners += '<div class="banner noprint risk-banner" role="note"><label for="risk-name"><b>Your name</b></label> '
      + '<input id="risk-name" type="text" maxlength="100" autocomplete="name" value="' + esc(riskTypedName()) + '"> '
      + '<span class="cap">Access isn’t set up yet, so type your name. The record shows who answered each question.</span></div>';
  }
  document.getElementById('risk-banners').innerHTML = banners;
  const nameField = document.getElementById('risk-name');
  if (nameField) {
    nameField.addEventListener('input', () => localStorage.setItem(RISK_NAME_KEY, nameField.value.trim()));
  }
}

/* ---------- a page is drawn into <main> ---------- */

function riskShow(html) {
  const main = document.getElementById('risk-main');
  main.innerHTML = html;
  return main;
}

function riskShowProblem(message) {
  riskShow('<div class="risk-card"><h2>This page can’t be shown</h2><p>' + esc(message) + '</p>'
    + '<p><a href="#/">Back to risk assessments</a></p></div>');
}

/* ---------- which page: the part of the address after the # ---------- */

/* Each page file adds itself to these lists when it loads, so no file needs to know about the others.
   The order the files load in decides only the order of links in the top bar and of cards on a page. */
const riskPages = [];             // {matches(parts), draw(parts)}: a page and the address that opens it
const riskTopBarLinks = [];       // {id, href, words, isShown()}: links in the top bar
const riskHomeExtras = [];        // {html(), isShown()}: lines under the title on the front page
const riskResultsExtras = [];     // {html(teamId), isShown()}: lines under "Assessed ..." on a team's results page
const riskEditExtras = [];        // {html()}: cards on the Edit page

function riskAddPage(matches, draw) {
  riskPages.push({matches: matches, draw: draw});
}

/* Draws the page for the address. An address no page claims shows the front page. */
function riskOpenPage() {
  const parts = hashParts();
  window.scrollTo(0, 0);
  const page = riskPages.find(candidate => candidate.matches(parts));
  (page ? page.draw : riskDrawHome)(parts);
}

/* A link to a TRAC guide, shown only when TRAC's address is set (apps-menu.js fills in the address). */
function riskGuideLink(path, words) {
  return '<span class="risk-guide"><a data-trac-path="' + path + '" hidden>Guide: ' + esc(words) + '</a></span>';
}
