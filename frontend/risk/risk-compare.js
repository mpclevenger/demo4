/* The Risk site: the engine bridge and the side-by-side page (BUILD_PLAN R8). For Tech Risk.
   #/compare                  every team with its last comparison result
   #/group/<id>/compare       one team: upload the engine's file, then the engine's rating beside the site's
   It adds itself to the lists in risk-core.js: the pages, and a link on the front page and on a team's results page.
   All names start with "riskCompare". */
"use strict";

const RISK_COMPARE_LAYOUT_NOTE = 'Wanted: confirm this layout with the engine’s owner.';
const RISK_COMPARE_CHIP_COLORS = {'Same': 'green', 'Different': 'red', 'Site only': 'gray', 'Engine only': 'amber'};

/* ---------- small pieces ---------- */

function riskCompareChip(result) {
  return '<span class="risk-chip ' + RISK_COMPARE_CHIP_COLORS[result] + '">' + esc(result) + '</span>';
}

/* "High / Critical" for likelihood / impact. */
function riskCompareLevels(side) {
  if (!side) return '<span class="cap">not in this file</span>';
  if (!side.applicable) return '<span class="cap">Does not apply</span>';
  const word = level => level ? riskLevelWord(level) : '–';
  return esc(word(side.likelihood) + ' / ' + word(side.impact));
}

function riskCompareRowHtml(row) {
  let reasons = '';
  if (row.reasons.length) {
    reasons = '<tr class="cmp-reason"><td colspan="4"><ul>' + row.reasons.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul></td></tr>';
  }
  return '<tr><td><b>' + esc(row.name) + '</b><br><span class="cap">' + esc(row.risk_id) + '</span></td>'
    + '<td>' + riskCompareLevels(row.engine) + '</td><td>' + riskCompareLevels(row.site) + '</td>'
    + '<td>' + riskCompareChip(row.result) + '</td></tr>' + reasons;
}

function riskCompareTableHtml(title, intro, rows) {
  if (!rows.length) return '';
  return '<h3 class="risk-section-name">' + esc(title) + ' <span class="cap">(' + plural(rows.length, 'risk', 'risks') + ')</span></h3>'
    + (intro ? '<p class="cap">' + esc(intro) + '</p>' : '')
    + '<div class="risk-scroll"><table class="risk-table"><thead><tr><th>Risk</th><th>Engine<br><span class="cap">likelihood / impact</span></th>'
    + '<th>Site<br><span class="cap">likelihood / impact</span></th><th>Result</th></tr></thead><tbody>'
    + rows.map(riskCompareRowHtml).join('') + '</tbody></table></div>';
}

function riskCompareDriverListHtml(heading, list) {
  if (!list.length) return '';
  return '<h4>' + esc(heading) + '</h4><ul>' + list.map(driver => '<li><b>' + esc(driver.code) + '</b> ' + esc(driver.text) + '</li>').join('') + '</ul>';
}

function riskCompareDriversHtml(drivers) {
  if (!drivers) return '<p class="cap">The engine’s file has no list of active drivers, so the drivers can’t be compared.</p>';
  const engineOnly = drivers.on_in_engine_only, siteOnly = drivers.on_on_site_only;
  let body = '<h3 class="risk-section-name">Drivers that differ</h3>';
  if (!engineOnly.length && !siteOnly.length) {
    return body + '<p>The same drivers are on in the engine and on the site.</p>';
  }
  body += '<p class="cap">Often the cause of a difference in a rating.</p><div class="risk-card">';
  body += riskCompareDriverListHtml('On in the engine, not on the site (' + plural(engineOnly.length, 'driver', 'drivers') + ')', engineOnly);
  body += riskCompareDriverListHtml('On the site, not in the engine (' + plural(siteOnly.length, 'driver', 'drivers') + ')', siteOnly);
  return body + '</div>';
}

/* ---------- one group ---------- */

function riskCompareUploadBoxHtml(groupId) {
  return '<div class="risk-card cmp-upload"><h3>Engine file</h3>'
    + '<p class="cap">Upload the engine’s output file for this team (the JSON, schema 2.0). Each upload is kept; the newest one is compared.</p>'
    + '<p><input type="file" id="risk-compare-file" accept=".json,application/json"> '
    + '<button type="button" class="risk-button primary" id="risk-compare-send">Upload and compare</button></p>'
    + '<p id="risk-compare-message" class="cap" role="status"></p>'
    + '<p class="cap"><a href="/api/risk/groups/' + encodeURIComponent(groupId) + '/engine-input">Download this team’s answers for the engine</a> (JSON). '
    + '<b>' + esc(RISK_COMPARE_LAYOUT_NOTE) + '</b></p></div>';
}

function riskCompareHeaderHtml(comparison) {
  const run = comparison.engine_run, kept = comparison.assessment;
  return '<p class="cap">Engine file uploaded ' + when(run.at) + ' by ' + esc(run.by) + ' (file ' + esc(run.file_hash.slice(0, 8)) + '). '
    + 'Compared with the site’s assessment of ' + when(kept.at) + ' by ' + esc(kept.by) + '.</p>';
}

function riskCompareBodyHtml(comparison) {
  const rows = comparison.rows;
  const withResult = result => rows.filter(row => row.result === result);
  let body = riskCompareHeaderHtml(comparison);
  body += '<p class="cmp-summary"><b>' + esc(comparison.summary) + '</b></p>';
  if (comparison.notes.length) {
    body += '<div class="banner">' + comparison.notes.map(note => '<div>' + esc(note) + '</div>').join('') + '</div>';
  }
  if (!withResult('Different').length && !withResult('Engine only').length) {
    body += '<p class="cmp-clear">No differences. On this team the site rates every Critical and High risk the way the engine does.</p>';
  }
  body += riskCompareTableHtml('Differences', 'Where we’d like to look together. The reason is under each risk.', withResult('Different'));
  body += riskCompareTableHtml('Engine only', 'Risks the engine rated that the site’s risk files don’t have.', withResult('Engine only'));
  body += riskCompareDriversHtml(comparison.drivers);
  body += riskCompareTableHtml('Same', 'The engine and the site agree.', withResult('Same'));
  body += riskCompareTableHtml('Site only', 'The site rates these Medium or Low, which are new on the site, so the engine has nothing to match. These are not differences.', withResult('Site only'));
  return body;
}

async function riskCompareDrawGroup(groupId) {
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId) + '/compare');
  if (!answer.ok) { riskShowProblem(answer.error); return; }
  const link = '#/group/' + encodeURIComponent(groupId);
  let body = '<p class="risk-crumb"><a href="#/">Risk assessments</a> / <a href="' + link + '/results">' + esc(answer.group.name) + '</a> / Compare with the engine</p>'
    + '<h2 class="risk-title">Compare with the engine</h2>'
    + '<p class="risk-intro">The site rates each risk itself. Upload the risk engine’s result for this team to see the two ratings side by side, with every difference and its reason.</p>';
  if (answer.can_upload) body += riskCompareUploadBoxHtml(groupId);
  if (answer.comparison) {
    body += riskCompareBodyHtml(answer.comparison);
  } else {
    body += '<div class="risk-card"><p>' + esc(answer.why_not) + '</p></div>';
  }
  riskShow(body);
  const send = document.getElementById('risk-compare-send');
  if (send) send.addEventListener('click', () => riskCompareUpload(groupId));
}

async function riskCompareUpload(groupId) {
  const message = document.getElementById('risk-compare-message');
  const chosen = document.getElementById('risk-compare-file').files[0];
  if (!chosen) { message.textContent = 'Choose the engine’s file first.'; return; }
  const form = new FormData();
  form.append('file', chosen);
  message.textContent = 'Uploading…';
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId) + '/engine-output', form);
  if (!answer.ok) { message.textContent = answer.error || 'That file could not be used.'; return; }
  riskCompareDrawGroup(groupId);
}

/* ---------- every group ---------- */

function riskCompareGroupRowHtml(group) {
  const link = '#/group/' + encodeURIComponent(group.id) + '/compare';
  let result = '<span class="cap">' + esc(group.why_not || '') + '</span>';
  if (group.counts) {
    const chip = group.counts.different + group.counts.engine_only > 0 ? riskCompareChip('Different') : riskCompareChip('Same');
    result = chip + ' ' + esc(group.summary) + '<br><span class="cap">Engine file of ' + when(group.engine_at)
      + ' against the assessment of ' + when(group.assessment_at) + '</span>';
  }
  return '<tr><td><b>' + esc(group.name) + '</b></td><td>' + result + '</td><td><a class="risk-button" href="' + link + '">Open</a></td></tr>';
}

async function riskCompareDrawAll() {
  if (!riskIsTechRisk()) { riskShowProblem('Tech Risk makes this comparison.'); return; }
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/risk/compare');
  if (!answer.ok) { riskShowProblem(answer.error); return; }
  let body = '<p class="risk-crumb"><a href="#/">Risk assessments</a> / Compare with the engine' + riskGuideLink('/guides/comparing-the-risk-site-with-the-risk-engine/', 'comparing with the engine') + '</p><h2 class="risk-title">Compare with the engine</h2>'
    + '<p class="risk-intro">For each team, the engine’s rating beside the site’s, risk by risk. '
    + 'The Python can stop once this list shows no differences on real cases.</p>';
  if (!answer.groups.length) {
    body += '<div class="risk-card"><p>There are no teams you can open yet.</p></div>';
  } else {
    body += '<div class="risk-scroll"><table class="risk-table"><thead><tr><th>Team</th><th>Last comparison</th><th></th></tr></thead><tbody>'
      + answer.groups.map(riskCompareGroupRowHtml).join('') + '</tbody></table></div>';
  }
  riskShow(body);
}

/* ---------- the way in ---------- */

riskHomeExtras.push({
  isShown: riskIsTechRisk,
  html: () => '<p class="cap"><a href="#/compare">Compare with the engine</a> (the engine’s rating beside the site’s, team by team)</p>'
});
riskResultsExtras.push({
  isShown: riskIsTechRisk,
  html: teamId => '<p class="cap"><a href="#/group/' + encodeURIComponent(teamId) + '/compare">Compare with the engine</a></p>'
});
riskAddPage(parts => parts[0] === 'compare', riskCompareDrawAll);
riskAddPage(parts => parts[0] === 'group' && parts[1] && parts[2] === 'compare', parts => riskCompareDrawGroup(parts[1]));
