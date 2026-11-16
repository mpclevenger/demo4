/* The Risk site: the results page for one team's assessment. */
"use strict";

const RISK_TREND_WORDS = {
  better: ['better', '▲ Better'],
  worse: ['worse', '▼ Worse'],
  'no change': ['same', '▬ No change'],
  mixed: ['mixed', 'Mixed: one went up, one went down']
};

function riskTrendHtml(entry, hasPrevious) {
  if (!hasPrevious || !entry.trend) return '';
  const [kind, words] = RISK_TREND_WORDS[entry.trend];
  return '<span class="risk-trend ' + kind + '">' + words + '</span>';
}

function riskLevelHtml(label, level) {
  return '<div class="risk-level"><span class="cap">' + label + '</span><span class="risk-levelword">' + riskLevelWord(level) + '</span>' + riskPips(level) + '</div>';
}

/* Highest likelihood and impact first. Elevated risks always come first. */
function riskOrder(entries) {
  const rank = level => RISK_LEVELS.indexOf(level);
  return entries.slice().sort((a, b) =>
    (b[1].elevated - a[1].elevated)
    || (rank(b[1].likelihood) + rank(b[1].impact)) - (rank(a[1].likelihood) + rank(a[1].impact))
    || a[1].name.localeCompare(b[1].name));
}

function riskStepsHtml(steps) {
  return '<ol class="risk-steps">' + steps.map(step => '<li><b>' + esc(step.title) + '</b>: ' + esc(step.result)
    + '<ul>' + step.lines.map(line => '<li>' + esc(line) + '</li>').join('') + '</ul></li>').join('') + '</ol>';
}

/* One small line: where a calculation lives in the code. A link when the repo address is set, else plain text. */
function riskPlaceText(place) {
  const text = esc(place.file.replace('backend/trust/risk/', '')) + ' · <code>' + esc(place.function) + '()</code> lines ' + place.from + '–' + place.to;
  return place.url && safeLink(place.url) ? '<a href="' + esc(safeLink(place.url)) + '" target="_blank" rel="noopener">' + text + '</a>' : text;
}
function riskWorkedOutHtml(place) {
  const places = Array.isArray(place) ? place : (place ? [place] : []);
  return places.length ? '<br><span class="cap">Worked out in ' + places.map(riskPlaceText).join('; and ') + '</span>' : '';
}

/* "See the code" for the rating rules: a closed section with a What it does | Where table. */
function riskCodeSectionHtml(places) {
  if (!places || !places.length) return '';
  return '<details class="exs risk-how"><summary>See the code: ' + plural(places.length, 'place', 'places') + ' that rate a risk</summary>'
    + '<table class="dt nosort"><thead><tr><th>What it does</th><th>Where</th></tr></thead><tbody>'
    + places.map(place => '<tr><td>' + esc(place.what) + '</td><td>' + riskPlaceText(place) + '</td></tr>').join('') + '</tbody></table></details>';
}

/* "Source: GitHub repos file repos_2026-10.csv, 3 Nov 2026" for a driver answered from data; nothing for one answered on the form.
   dataDrivers is what each data driver of the assessment shown said, and where it came from. */
function riskDataSourceHtml(code, dataDrivers) {
  const fromData = dataDrivers[code];
  if (!fromData) return '';
  const sources = (fromData.sources || []).map(source => esc(source.what) + ': ' + esc(source.feed) + ' file' + (source.file ? ' ' + esc(source.file) : '')
    + (source.as_of ? ', ' + riskControlsDate(source.as_of) : '')).join('; ');
  return '<br><span class="cap">Answered from data. ' + esc(fromData.sentence) + (sources ? ' Source: ' + sources + '.' : '') + '</span>' + riskWorkedOutHtml(fromData.place);
}

function riskDriversHtml(driversOn, dataDrivers) {
  if (!driversOn.length) return '<p class="cap">No driver is on.</p>';
  return '<ul class="risk-drivers">' + driversOn.map(driver => '<li><span class="risk-code">' + esc(driver.code) + '</span> ' + esc(driver.text) + riskDataSourceHtml(driver.code, dataDrivers) + '</li>').join('') + '</ul>';
}

/* In "How this was rated": the data drivers this risk uses that are on, with where each came from. */
function riskDataStepsHtml(entry, dataDrivers) {
  const used = entry.drivers_on.filter(driver => dataDrivers[driver.code]);
  if (!used.length) return '';
  return '<p class="cap"><b>Drivers answered from data</b></p><ul>' + used.map(driver => '<li><span class="risk-code">' + esc(driver.code) + '</span> '
    + esc(driver.text) + riskDataSourceHtml(driver.code, dataDrivers) + '</li>').join('') + '</ul>';
}

/* "15 Nov 2026": the day only, day first. */
function riskControlsDate(isoText) {
  const when = new Date(isoText);
  if (isNaN(when)) return esc(isoText);
  return when.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'});
}

/* The controls TRAC lists for one risk. No control means nothing to say, so nothing is drawn. */
function riskControlsHtml(controls) {
  if (!controls || !controls.length) return '';
  return '<div class="risk-row-drivers"><p class="cap"><b>Controls that address this risk</b></p><ul class="risk-drivers">'
    + controls.map(control => {
      const name = '<span class="risk-code">' + esc(control.code) + '</span> ' + esc(control.title);
      return '<li>' + (safeLink(control.url) ? '<a href="' + esc(safeLink(control.url)) + '" target="_blank" rel="noopener">' + name + '</a>' : name) + '</li>';
    }).join('') + '</ul></div>';
}

/* One small line above the list: when the controls were copied from TRAC, and, when no risk has a control yet, why none show. */
function riskControlsNoteHtml(controlsAnswer, riskIds) {
  if (!controlsAnswer || !controlsAnswer.ok) return '';
  if (!controlsAnswer.copy) return controlsAnswer.note ? '<p class="cap">' + esc(controlsAnswer.note) + '</p>' : '';
  const anyHasControl = riskIds.some(riskId => (controlsAnswer.by_risk[riskId] || []).length > 0);
  const wanted = anyHasControl ? '' : 'Which controls address each risk is Wanted: TRAC lists it once it is mapped. ';
  return '<p class="cap">' + wanted + 'Controls as of ' + riskControlsDate(controlsAnswer.copy.fetched_at) + '.</p>';
}

function riskRowHtml(riskId, entry, hasPrevious, controls, dataDrivers) {
  const elevated = entry.elevated ? '<span class="risk-chip elevated">Elevated</span>' : '';
  return '<li class="risk-card risk-row' + (entry.elevated ? ' is-elevated' : '') + '">'
    + '<div class="risk-row-top"><div><h3>' + esc(entry.name) + '</h3><p class="cap">' + esc(riskId) + ' · <span class="risk-tag">' + esc(entry.block) + '</span></p></div>'
    + '<div class="risk-row-levels">' + riskLevelHtml('Likelihood', entry.likelihood) + riskLevelHtml('Impact', entry.impact) + '</div>'
    + '<div class="risk-row-marks">' + elevated + riskTrendHtml(entry, hasPrevious) + '</div></div>'
    + '<div class="risk-row-drivers"><p class="cap"><b>Drivers that are on</b></p>' + riskDriversHtml(entry.drivers_on, dataDrivers) + '</div>'
    + riskControlsHtml(controls)
    + '<details class="risk-how"><summary>How this was rated</summary>' + riskStepsHtml(entry.steps) + riskDataStepsHtml(entry, dataDrivers) + '</details></li>';
}

function riskNotApplicableHtml(entries) {
  if (!entries.length) return '';
  return '<section class="risk-notapply" aria-labelledby="risk-na"><h3 id="risk-na">Does not apply to this team</h3>'
    + '<p class="cap">None of these risks’ drivers is on for this team.</p><ul>'
    + entries.map(([riskId, entry]) => '<li><span>' + esc(entry.name) + '</span> <span class="cap">' + esc(riskId) + ' · ' + esc(entry.block) + '</span></li>').join('')
    + '</ul></section>';
}

function riskTopRowHtml(result, ordered) {
  const counts = result.counts;
  const elevated = ordered.filter(([, entry]) => entry.elevated);
  const focus = elevated.length
    ? '<ul class="risk-focus">' + elevated.map(([riskId, entry]) => '<li><b>' + esc(entry.name) + '</b> <span class="cap">' + esc(riskId) + ' · '
      + riskLevelWord(entry.likelihood) + ' likelihood, ' + riskLevelWord(entry.impact) + ' impact</span></li>').join('') + '</ul>'
    : '';
  const unknown = result.drivers.not_known.length;
  // Nothing Elevated means nothing to say, so the Where to focus box is not drawn.
  const focusBox = elevated.length ? '<div class="risk-card risk-focusbox"><h3>Where to focus</h3>' + focus + '</div>' : '';
  return '<div class="risk-top' + (elevated.length ? '' : ' risk-top-alone') + '">'
    + '<div class="risk-card risk-count"><p class="cap"><b>Elevated risks</b></p><p class="risk-bignumber">' + counts.elevated + '</p>'
    + '<p>' + plural(counts.elevated, 'risk', 'risks') + ' Elevated, out of ' + plural(counts.applicable, 'risk', 'risks') + ' that apply.</p>'
    + '<p class="cap">' + plural(counts.not_applicable, 'risk does', 'risks do') + ' not apply to this team. '
    + plural(unknown, 'driver is', 'drivers are') + ' not answered yet.</p></div>'
    + focusBox + '</div>';
}

async function riskDrawResults(groupId, assessmentId) {
  riskShow('<p class="muted">Loading…</p>');
  const query = assessmentId ? '?id=' + encodeURIComponent(assessmentId) : '';
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId) + '/assessment' + query);
  if (!answer.ok) { riskShowProblem(answer.error); return; }
  const group = answer.group;
  const link = '#/group/' + encodeURIComponent(group.id);
  if (!answer.assessment) {
    riskShow('<p class="risk-crumb"><a href="#/">Risk assessments</a> / ' + esc(group.name) + '</p><h2 class="risk-title">' + esc(group.name) + '</h2>'
      + '<div class="risk-card"><p>This team has not been submitted yet, so there are no results.</p><p><a class="risk-button primary" href="' + link + '">Open the questionnaire</a></p></div>');
    return;
  }
  const kept = answer.assessment;
  const controlsAnswer = await riskApi('/api/risk/controls');
  const controlsByRisk = controlsAnswer.ok ? controlsAnswer.by_risk : {};
  const result = kept.result;
  const dataDrivers = result.data_drivers || {};
  const entries = Object.entries(result.risks);
  const ordered = riskOrder(entries.filter(([, entry]) => entry.applicable));
  const notApplicable = entries.filter(([, entry]) => !entry.applicable).sort((a, b) => a[1].name.localeCompare(b[1].name));

  let earlier = '';
  if (answer.earlier.length > 1) {
    earlier = '<label class="cap" for="risk-earlier">Assessment </label><select id="risk-earlier">'
      + answer.earlier.map(row => '<option value="' + row.id + '"' + (row.id === kept.id ? ' selected' : '') + '>' + when(row.at) + ' · ' + plural(row.elevated, 'risk', 'risks') + ' Elevated</option>').join('') + '</select>';
  }
  let body = '<p class="risk-crumb"><a href="#/">Risk assessments</a> / ' + esc(group.name) + riskGuideLink('/guides/reading-your-results-and-the-risk-heat-map/', 'reading your results') + '</p>'
    + '<div class="risk-group-top"><h2 class="risk-title">' + esc(group.name) + '</h2>' + riskStatusChip(group.status) + '</div>'
    + '<p class="cap">Assessed ' + when(kept.at) + ' by ' + esc(kept.by) + '. <a href="' + link + '">Open the questionnaire</a></p>';
  for (const extra of riskResultsExtras) {
    if (extra.isShown()) body += extra.html(group.id);
  }
  if (earlier) body += '<p>' + earlier + '</p>';
  body += '<div id="risk-signoff-box"></div>';                       // filled by risk-signoff.js
  if (group.status === 'Draft') body += '<p class="banner">The answers have changed since this assessment. Submit again to rate them.</p>';
  body += riskTopRowHtml(result, ordered);
  body += '<h3 class="risk-section-name">Every risk that applies</h3>';
  body += '<p class="cap">' + (result.has_previous ? 'Compared with the previous assessment: ▲ better, ▼ worse, ▬ no change.' : 'This is the first assessment, so there is no trend yet.') + '</p>';
  body += riskControlsNoteHtml(controlsAnswer, entries.map(([riskId]) => riskId));
  body += '<ul class="risk-rows">' + ordered.map(([riskId, entry]) => riskRowHtml(riskId, entry, result.has_previous, controlsByRisk[riskId], dataDrivers)).join('') + '</ul>';
  body += riskNotApplicableHtml(notApplicable);
  body += riskCodeSectionHtml(answer.code_places);
  riskShow(body);
  riskSignoffDraw(group.id, kept.id);

  const picker = document.getElementById('risk-earlier');
  if (picker) picker.addEventListener('change', () => { location.hash = link + '/results/' + picker.value; });
}

riskAddPage(parts => parts[0] === 'group' && parts[1] && parts[2] === 'results', parts => riskDrawResults(parts[1], parts[3] || null));
