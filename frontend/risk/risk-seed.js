/* The Risk site: Tech Risk uploads that seed the risks, drivers and questionnaire, and the TRAC controls refresh.
   Page #/upload ("Upload risk files"), linked from the Edit page. Three kinds of file, each one step at a time:
   read and check -> what was found and every problem in plain words -> "See what would move" -> Load.
   The server does all the reading (backend/trust/risk/seed_routes.py); nothing is rated here.
   It adds itself to the lists in risk-core.js: the page, and a card on the Edit page. All names start with "riskSeed". */
"use strict";

const RISK_SEED_KINDS = [
  {kind: 'risks', title: '1. Risk files',
   about: 'The risk engine’s own YAML files: each file holds risks keyed by id, like air.ops.02. Choose one or more files, or a .zip of them.',
   accept: '.yaml,.yml,.zip', many: true,
   columns: [['id', 'Id'], ['name', 'Name'], ['detail', 'Domain']]},
  {kind: 'drivers', title: '2. Driver rules',
   about: 'The engine’s driver_mapping.yaml: risk_drivers, each driver (RD01, RD12 …) with its trigger, questionnaire fields and rationale.',
   accept: '.yaml,.yml', many: false,
   columns: [['id', 'Driver'], ['name', 'What it says'], ['detail', 'Trigger']]},
  {kind: 'questions', title: '3. Questionnaire',
   about: 'The questionnaire YAML. Which key gives each part of a question is named in a mapping file you can edit (below). A question needs the driver field it feeds.',
   accept: '.yaml,.yml', many: false,
   columns: [['id', 'Field'], ['name', 'Question'], ['section', 'Section'], ['order', 'Order'], ['switches', 'Driver is on when']]}];
const RISK_SEED_CHIP_COLORS = {New: 'green', Changed: 'amber', Same: 'gray', Restored: 'amber', 'Switched off': 'gray'};

const riskSeedState = {can: false};      // whether this person may upload

/* ---------- the way in: a card on the Edit page, and the address ---------- */

/* The card on the Edit page that leads here. */
function riskSeedEditCardHtml() {
  return '<li class="risk-card risk-group"><h2>Upload risk files</h2>'
    + '<p class="cap">Seed the risks, driver rules and questionnaire from files. The site then holds them, with the history of each load.</p>'
    + '<p class="risk-actions"><a class="risk-button primary" href="#/upload">Upload risk files</a></p></li>';
}

/* ---------- talking to the server with files ---------- */

async function riskSeedPost(kind, step, files) {
  const form = new FormData();
  for (const file of files) form.append('file', file, file.name);
  return riskApi('/api/risk/seed/' + kind + '/' + step, form);
}

/* ---------- the page ---------- */

async function riskSeedDrawPage() {
  riskShow('<p class="muted">Loading…</p>');
  const status = await riskApi('/api/risk/seed');
  if (!status.ok) { riskShowProblem(status.error || 'This page could not be loaded.'); return; }
  riskSeedState.can = status.can_upload;
  const held = status.held;
  let html = '<p class="risk-crumb"><a href="#/">Risk assessments</a> › <a href="#/edit">Edit</a> › Upload risk files</p>'
    + '<h2 class="risk-title">Upload risk files</h2>'
    + '<p class="risk-intro">Seed the Risk site from the engine’s files and the questionnaire. Each file is read and checked first, and every problem is listed in plain words. '
    + 'You can see which teams’ newest ratings would change before anything is loaded. After a load the site holds the risks, drivers and questions, and every load is kept with who did it and when.'
    + (riskSeedState.can ? '' : ' Tech Risk uploads these files.') + '</p>'
    + '<p class="riskseed-held" id="riskseed-held">' + riskSeedHeldHtml(held) + '</p>';
  if (riskSeedState.can) {
    html += '<div class="riskseed-cards">' + RISK_SEED_KINDS.map(riskSeedCardHtml).join('') + riskSeedBulkCardHtml() + '</div>'
      + riskSeedMappingHtml(status.mapping) + riskSeedControlsHtml(status.controls);
  }
  html += '<h3 class="riskseed-heading">Earlier uploads</h3><div id="riskseed-earlier">' + riskSeedEarlierHtml(status.earlier) + '</div>';
  riskShow(html);
  if (!riskSeedState.can) return;
  for (const definition of RISK_SEED_KINDS) {
    document.getElementById('riskseed-check-' + definition.kind).addEventListener('click', () => riskSeedCheck(definition));
  }
  document.getElementById('riskseed-refresh').addEventListener('click', riskSeedRefreshControls);
  document.getElementById('riskseed-check-answers').addEventListener('click', () => riskSeedBulk('check'));
}

/* ---------- questionnaire answers in bulk, as a CSV (owner, 17 Nov 2026) ---------- */
/* Download every team's questions with their newest answers, fill in the answer column, upload it back. The upload is
   checked first; Save keeps the answers as drafts (nothing is submitted), and each team's results page shows them as
   Proposed until the form is submitted. The server does the checking (backend/trust/risk/bulk_answers.py). */
function riskSeedBulkCardHtml() {
  return '<section class="risk-card riskseed-card" id="riskseed-card-answers"><h3>4. Questionnaire answers (CSV)</h3>'
    + '<p class="cap">Every team’s questions with their newest answers, one row per team and question. Fill in the <b>answer</b> column and upload the file back. '
    + 'Blank answers are left as they are. The answers are saved as drafts: nothing is submitted, and each team’s results show as Proposed until its form is submitted.</p>'
    + '<p class="riskseed-pick"><a class="risk-button" href="/api/risk/answers.csv" download>Download the answers (.csv)</a></p>'
    + '<p class="riskseed-pick"><input type="file" id="riskseed-file-answers" accept=".csv" aria-label="Questionnaire answers file"> '
    + '<button type="button" class="risk-button primary" id="riskseed-check-answers">Read and check</button></p>'
    + '<div id="riskseed-out-answers" role="status"></div></section>';
}

async function riskSeedBulk(step) {
  const out = document.getElementById('riskseed-out-answers');
  const file = (document.getElementById('riskseed-file-answers').files || [])[0];
  if (!file) { out.innerHTML = '<p class="risk-error">Choose the CSV file first.</p>'; return; }
  out.innerHTML = '<p class="muted">' + (step === 'check' ? 'Reading…' : 'Saving…') + '</p>';
  const form = new FormData();
  form.append('file', file, file.name);
  const result = await riskApi('/api/risk/answers/' + step, form);
  if (!result.ok) { out.innerHTML = '<p class="risk-error">' + esc(result.error || 'The file could not be read.') + '</p>'; return; }
  const problems = riskSeedListHtml('Rows that can’t be used (' + result.problems.length + ')', result.problems, true);
  if (step === 'load') {
    out.innerHTML = '<p class="riskseed-done"><b>Saved as drafts.</b> ' + esc(result.summary) + ' Teams’ results have been worked out again, so the Proposed ratings show there now.</p>' + problems;
    document.getElementById('riskseed-file-answers').value = '';
    return;
  }
  const rows = (result.changes || []).map(change => '<tr><td>' + esc(change.team) + '</td><td>' + esc(change.field) + '</td><td>'
    + esc(change.before || '—') + ' → ' + esc(Array.isArray(change.answer) ? change.answer.join('; ') : change.answer) + '</td></tr>').join('');
  const table = rows ? '<div class="riskseed-scroll"><table class="risk-table"><thead><tr><th>Team</th><th>Question</th><th>Answer</th></tr></thead><tbody>' + rows + '</tbody></table></div>'
    + (result.more ? '<p class="cap">And ' + plural(result.more, 'more answer', 'more answers') + '.</p>' : '') : '';
  const save = result.counts.to_save ? '<p class="risk-actions"><button type="button" class="risk-button primary" id="riskseed-load-answers">Save as drafts</button></p>' : '';
  out.innerHTML = '<p><b>' + esc(result.summary) + '</b> Nothing is saved yet.</p>' + problems + table + save;
  if (save) document.getElementById('riskseed-load-answers').addEventListener('click', () => riskSeedBulk('load'));
}

function riskSeedHeldHtml(held) {
  return 'The site holds <b>' + plural(held.risks, 'risk', 'risks') + '</b> (from ' + esc(held.risks_from) + '), <b>'
    + plural(held.drivers, 'driver', 'drivers') + '</b> (from ' + esc(held.drivers_from) + ') and <b>'
    + plural(held.questions, 'question', 'questions') + '</b>.';
}

function riskSeedCardHtml(definition) {
  const kind = definition.kind;
  return '<section class="risk-card riskseed-card" id="riskseed-card-' + kind + '"><h3>' + esc(definition.title) + '</h3>'
    + '<p class="cap">' + esc(definition.about) + '</p>'
    + '<p class="riskseed-pick"><input type="file" id="riskseed-file-' + kind + '" accept="' + definition.accept + '"' + (definition.many ? ' multiple' : '')
    + ' aria-label="' + esc(definition.title) + ' file"> '
    + '<button type="button" class="risk-button primary" id="riskseed-check-' + kind + '">Read and check</button></p>'
    + '<div id="riskseed-out-' + kind + '" role="status"></div></section>';
}

/* ---------- the mapping file, for the questionnaire ---------- */

function riskSeedMappingHtml(mapping) {
  let body;
  if (mapping.problem) {
    body = '<p class="risk-error">' + esc(mapping.problem) + '</p>';
  } else {
    const lines = [];
    for (const key of Object.keys(mapping.content)) {
      if (key.charAt(0) === '_') continue;
      const value = mapping.content[key];
      const shown = Array.isArray(value) ? value.join(', ') : Object.keys(value).map(kind => kind + ': ' + value[kind].join(', ')).join('; ');
      lines.push('<tr><th scope="row">' + esc(key) + '</th><td>' + esc(shown) + '</td></tr>');
    }
    const howTo = [].concat(mapping.content._how_to || []).map(line => '<li>' + esc(line) + '</li>').join('');
    body = '<ul class="cap riskseed-howto">' + howTo + '</ul><table class="risk-table riskseed-map"><tbody>' + lines.join('') + '</tbody></table>';
  }
  return '<details class="risk-card riskseed-mapping"><summary><b>Where the questionnaire’s keys are named</b> · ' + esc(mapping.file) + '</summary>'
    + '<p class="cap">The owner edits this file, not the code. Add the name your questionnaire uses at the start of the right list, save, and check the questionnaire again.</p>' + body + '</details>';
}

/* ---------- the TRAC controls ---------- */

function riskSeedControlsLine(controls) {
  if (!controls.copy) {
    return controls.trac_address_set ? 'No copy of TRAC’s controls has been kept yet.' : 'No copy has been kept yet, and TRAC’s address is not set.';
  }
  return 'The kept copy was fetched ' + when(controls.copy.fetched_at) + ' and holds ' + plural(controls.copy.controls, 'control', 'controls') + '.';
}

function riskSeedControlsHtml(controls) {
  return '<section class="risk-card riskseed-card riskseed-controls"><h3>Controls from TRAC</h3>'
    + '<p class="cap">The results pages show which controls address each risk, from a copy of TRAC’s list that the Risk site keeps. Refresh it when TRAC’s list has changed.</p>'
    + '<p class="riskseed-pick"><button type="button" class="risk-button primary" id="riskseed-refresh">Refresh controls from TRAC</button></p>'
    + '<p id="riskseed-controls-line" role="status">' + esc(riskSeedControlsLine(controls)) + '</p></section>';
}

async function riskSeedRefreshControls() {
  const line = document.getElementById('riskseed-controls-line');
  line.className = '';
  line.textContent = 'Asking TRAC…';
  const answer = await riskApi('/api/risk/controls/refresh', {});
  if (!answer.ok) {
    line.className = 'risk-error';
    line.textContent = answer.error || 'The copy could not be refreshed.';
    return;
  }
  line.textContent = 'Refreshed. ' + riskSeedControlsLine({copy: answer.copy, trac_address_set: true});
}

/* ---------- earlier uploads ---------- */

function riskSeedEarlierHtml(earlier) {
  if (!earlier.length) return '<p class="cap">Nothing has been uploaded yet.</p>';
  const names = {risks: 'Risk files', drivers: 'Driver rules', questions: 'Questionnaire'};
  const rows = earlier.map(row => '<tr><td class="nowrap">' + when(row.at) + '</td><td>' + esc(row.by) + '</td><td>' + esc(names[row.kind] || row.kind)
    + '</td><td>' + esc(row.file_name) + '</td><td>' + esc(row.summary || '') + '</td><td class="nowrap">' + esc(row.file_hash.slice(0, 8)) + '</td></tr>').join('');
  return '<table class="risk-table"><thead><tr><th>When</th><th>Who</th><th>What</th><th>File</th><th>What was read</th><th>File hash</th></tr></thead><tbody>' + rows + '</tbody></table>';
}

/* ---------- one kind: check, see what would move, load ---------- */

function riskSeedChosenFiles(kind) {
  return Array.from(document.getElementById('riskseed-file-' + kind).files);
}

function riskSeedListHtml(title, sentences, open) {
  if (!sentences.length) return '';
  return '<details class="riskseed-list"' + (open ? ' open' : '') + '><summary>' + esc(title) + ' (' + plural(sentences.length, 'item', 'items') + ')</summary><ul>'
    + sentences.map(sentence => '<li>' + esc(sentence) + '</li>').join('') + '</ul></details>';
}

function riskSeedItemsHtml(definition, result) {
  if (!result.items.length) return '';
  const head = definition.columns.map(column => '<th>' + esc(column[1]) + '</th>').join('') + '<th>Status</th>';
  const rows = result.items.map(item => '<tr>' + definition.columns.map(column => {
    const help = column[0] === 'name' && item.help ? '<br><span class="cap">Help: ' + esc(item.help) + '</span>' : '';
    return '<td>' + esc(item[column[0]]) + help + '</td>';
  }).join('') + '<td><span class="risk-chip ' + (RISK_SEED_CHIP_COLORS[item.status] || 'gray') + '">' + esc(item.status) + '</span></td></tr>').join('');
  const more = result.items_total > result.items.length
    ? '<p class="cap">Showing ' + result.items.length + ' of ' + plural(result.items_total, 'item', 'items') + '.</p>' : '';
  return '<div class="riskseed-scroll"><table class="risk-table"><thead><tr>' + head + '</tr></thead><tbody>' + rows + '</tbody></table></div>' + more;
}

function riskSeedFoundHtml(definition, result) {
  let html = '<p class="riskseed-summary"><b>' + esc(result.summary) + '</b></p>';
  html += riskSeedListHtml('Problems: these were left out', result.problems, true).replace('class="riskseed-list"', 'class="riskseed-list riskseed-problems"');
  html += riskSeedListHtml('Notes', result.notes, false);
  html += riskSeedItemsHtml(definition, result);
  if (result.can_load) {
    html += '<p class="risk-actions"><button type="button" class="risk-button" id="riskseed-preview-' + definition.kind + '">See what would move</button> '
      + '<button type="button" class="risk-button primary" id="riskseed-load-' + definition.kind + '" disabled>Load</button></p>'
      + '<p class="cap">Load is available once you have seen what would move.</p><div id="riskseed-moves-' + definition.kind + '"></div>';
  } else {
    html += '<p class="cap">' + esc(result.why_not || '') + '</p>';
  }
  return html;
}

async function riskSeedCheck(definition) {
  const kind = definition.kind;
  const out = document.getElementById('riskseed-out-' + kind);
  const files = riskSeedChosenFiles(kind);
  if (!files.length) { out.innerHTML = '<p class="risk-error">Choose a file first.</p>'; return; }
  out.innerHTML = '<p class="muted">Reading…</p>';
  const result = await riskSeedPost(kind, 'check', files);
  if (!result.ok) { out.innerHTML = '<p class="risk-error">' + esc(result.error || 'The file could not be checked.') + '</p>'; return; }
  out.innerHTML = riskSeedFoundHtml(definition, result);
  if (!result.can_load) return;
  document.getElementById('riskseed-preview-' + kind).addEventListener('click', () => riskSeedPreview(definition));
  document.getElementById('riskseed-load-' + kind).addEventListener('click', () => riskSeedLoad(definition));
}

function riskSeedMovesHtml(result) {
  let html = '<p><b>' + esc(result.moves_summary) + '</b> These are each team’s newest ratings, rated again with what this file would put in. Nothing is saved yet.</p>';
  if (!result.moves.length) return html;
  const rows = result.moves.map(move => '<tr><td>' + esc(move.group) + '</td><td>' + esc(move.name) + ' <span class="cap">' + esc(move.risk) + '</span></td><td>'
    + esc(move.what) + '</td><td>' + esc(move.before) + ' → ' + esc(move.after) + '</td></tr>').join('');
  return html + '<div class="riskseed-scroll"><table class="risk-table"><thead><tr><th>Team</th><th>Risk</th><th>What</th><th>Change</th></tr></thead><tbody>' + rows + '</tbody></table></div>';
}

async function riskSeedPreview(definition) {
  const kind = definition.kind;
  const box = document.getElementById('riskseed-moves-' + kind);
  box.innerHTML = '<p class="muted">Working out what would move…</p>';
  const result = await riskSeedPost(kind, 'preview', riskSeedChosenFiles(kind));
  if (!result.ok) { box.innerHTML = '<p class="risk-error">' + esc(result.error || 'This could not be worked out.') + '</p>'; return; }
  box.innerHTML = riskSeedMovesHtml(result);
  document.getElementById('riskseed-load-' + kind).disabled = false;
}

async function riskSeedLoad(definition) {
  const kind = definition.kind;
  const out = document.getElementById('riskseed-out-' + kind);
  const button = document.getElementById('riskseed-load-' + kind);
  button.disabled = true;
  const result = await riskSeedPost(kind, 'load', riskSeedChosenFiles(kind));
  if (!result.ok) {
    out.insertAdjacentHTML('beforeend', '<p class="risk-error">' + esc(result.error || 'The load did not happen.') + '</p>');
    button.disabled = false;
    return;
  }
  out.innerHTML = '<p class="riskseed-done"><b>Loaded.</b> ' + esc(result.summary) + ' Kept by ' + esc(result.kept.by) + ', file ' + esc(result.kept.file_hash.slice(0, 8)) + '. '
    + 'The site now holds these.</p>' + riskSeedListHtml('Problems that were left out', result.problems, false);
  document.getElementById('riskseed-held').innerHTML = riskSeedHeldHtml(result.held);
  document.getElementById('riskseed-file-' + kind).value = '';
  const status = await riskApi('/api/risk/seed');
  if (status.ok) document.getElementById('riskseed-earlier').innerHTML = riskSeedEarlierHtml(status.earlier);
}

riskEditExtras.push({html: riskSeedEditCardHtml});
riskAddPage(parts => parts[0] === 'upload', riskSeedDrawPage);
