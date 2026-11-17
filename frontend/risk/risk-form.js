/* The Risk site: the questionnaire for one team, one section on screen at a time.
   Each answer is saved the moment it is changed. */
"use strict";

const riskForm = {group: null, sections: [], sectionIndex: 0, unanswered: 0, answeredFromData: [], missing: null};

/* One driver answered from data: ON, OFF or not known, its sentence, and where the data came from. */
function riskDataDriverHtml(driver) {
  const word = driver.state === true ? 'ON' : driver.state === false ? 'OFF' : 'Not known';
  const sources = (driver.sources || []).map(source => esc(source.what) + ': ' + esc(source.feed) + ' file'
    + (source.file ? ' ' + esc(source.file) : '') + (source.as_of ? ', loaded ' + esc(source.as_of) : '')).join('; ');
  return '<li><span class="risk-code">' + esc(driver.code) + '</span> <b>' + word + '</b> · ' + esc(driver.plain_name)
    + '<br><span class="cap">' + esc(driver.sentence) + (sources ? ' Source: ' + sources + '.' : '') + '</span>' + riskWorkedOutHtml(driver.place) + '</li>';
}

/* "2026-10" -> "October 2026". */
function riskMonthWords(month) {
  const [year, number] = String(month).split('-');
  const names = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  return (names[Number(number) - 1] || month) + ' ' + (year || '');
}

async function riskDrawForm(groupId) {
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId));
  if (!answer.ok) { riskShowProblem(answer.error); return; }
  riskForm.group = answer.group;
  riskForm.sections = answer.sections;
  riskForm.unanswered = answer.unanswered;
  riskForm.answeredFromData = answer.answered_from_data;
  riskForm.dataMonth = answer.data_month;
  riskForm.missing = null;
  const remembered = Number(sessionStorage.getItem('riskSection:' + groupId) || 0);
  riskForm.sectionIndex = Math.min(remembered, Math.max(riskForm.sections.length - 1, 0));
  riskDrawSection();
}

/* True while an answer is one the team gave in an earlier assessment and has not changed or re-confirmed this time. */
function riskIsCarriedOver(question) {
  const lastSubmitted = riskForm.group.submitted_at;
  return Boolean(lastSubmitted && question.by && riskAnswerWords(question.answer) !== '' && new Date(question.at) <= new Date(lastSubmitted));
}

/* The line under a question: who last saved it, and when. A carried-over answer says when it was last confirmed. */
function riskSavedLine(question) {
  if (!question.by) return 'Not answered yet.';
  if (riskIsCarriedOver(question)) return 'Last confirmed ' + when(question.at) + ' (' + esc(question.by) + ').';
  const fromTechRisk = question.from_tech_risk ? ' <span class="risk-tag">from Tech Risk</span>' : '';
  return (riskAnswerWords(question.answer) === '' ? 'Cleared by ' : 'Last saved by ') + esc(question.by) + ' on ' + when(question.at) + '.' + fromTechRisk;
}

/* The options already ticked, in lower case. An answer is a list; an older saved answer may be one text ("A; B" or "A, B"). */
function riskTickedOptions(question) {
  const answer = question.answer;
  const items = Array.isArray(answer) ? answer : String(answer || '').split(/[;,]/);
  const kept = items.map(item => String(item).trim().toLowerCase()).filter(item => item !== '');
  const whole = String(Array.isArray(answer) ? '' : answer || '').trim().toLowerCase();
  return whole ? kept.concat([whole]) : kept;
}

/* What the ticks on one question say now: the ticked options in order, and only None of these when that one was just ticked. */
function riskTicksOf(card, changed) {
  const boxes = Array.from(card.querySelectorAll('input[type=checkbox]'));
  const noneBox = boxes.find(box => box.value === 'None of these');
  if (changed && changed === noneBox && changed.checked) {
    boxes.forEach(box => { box.checked = box === noneBox; });
  } else if (changed && changed !== noneBox && changed.checked && noneBox) {
    noneBox.checked = false;
  }
  return boxes.filter(box => box.checked).map(box => box.value);
}

/* The saved line shows a tick-any answer as "A; B". */
function riskAnswerWords(answer) {
  return Array.isArray(answer) ? answer.join('; ') : String(answer || '');
}

function riskQuestionHtml(question, canAnswer) {
  const id = 'q-' + question.field;
  const disabled = canAnswer ? '' : ' disabled';
  let input;
  if (question.kind === 'yes_no') {
    input = '<div class="risk-choices" role="radiogroup" aria-labelledby="' + id + '-text">'
      + ['yes', 'no'].map(value => '<label class="risk-choice"><input type="radio" name="' + id + '" value="' + value + '"'
        + (question.answer === value ? ' checked' : '') + disabled + '> ' + (value === 'yes' ? 'Yes' : 'No') + '</label>').join('') + '</div>';
  } else if (question.kind === 'tick_any') {
    /* Tick any that apply: the options are the answers the driver's trigger looks for, and None of these (which clears the rest). */
    const ticked = riskTickedOptions(question);
    input = '<div class="risk-choices risk-choices-text risk-choices-tick" role="group" aria-labelledby="' + id + '-text">'
      + (question.choices || []).map(value => '<label class="risk-choice"><input type="checkbox" name="' + id + '" value="' + esc(value) + '"'
        + (ticked.includes(value.toLowerCase()) ? ' checked' : '') + disabled + '> ' + esc(value) + '</label>').join('') + '</div>';
  } else if (question.kind === 'text' && question.accepts_number && (question.choices || []).length) {
    /* Compared with numbers and with text: a box that takes a number, with the texts offered as suggestions. */
    input = '<div class="risk-number"><label class="sr-only" for="' + id + '">Your answer to ' + esc(question.driver) + '</label>'
      + '<input type="text" id="' + id + '" name="' + id + '" list="' + id + '-list" value="' + esc(question.answer) + '" maxlength="200"' + disabled + '> '
      + '<datalist id="' + id + '-list">' + question.choices.concat(['Other']).map(value => '<option value="' + esc(value) + '">').join('') + '</datalist>'
      + '<span class="cap">Type a number, or choose: ' + question.choices.concat(['Other']).map(esc).join(', ') + '.</span></div>';
  } else if (question.kind === 'text' && (question.choices || []).length) {
    /* A choice of answers: the texts the driver's trigger compares the answer with, and Other for none of them. */
    input = '<div class="risk-choices risk-choices-text" role="radiogroup" aria-labelledby="' + id + '-text">'
      + question.choices.concat(['Other']).map(value => '<label class="risk-choice"><input type="radio" name="' + id + '" value="' + esc(value) + '"'
        + (question.answer.trim().toLowerCase() === value.toLowerCase() ? ' checked' : '') + disabled + '> ' + esc(value) + '</label>').join('') + '</div>';
  } else if (question.kind === 'text') {
    input = '<div class="risk-number"><label class="sr-only" for="' + id + '">Your answer to ' + esc(question.driver) + '</label>'
      + '<input type="text" id="' + id + '" name="' + id + '" value="' + esc(question.answer) + '" maxlength="200"' + disabled + '></div>';
  } else {
    input = '<div class="risk-number"><label class="sr-only" for="' + id + '">Your answer to ' + esc(question.driver) + '</label>'
      + '<input type="text" inputmode="decimal" id="' + id + '" name="' + id + '" value="' + esc(question.answer) + '" maxlength="40"' + disabled + '> '
      + '<span class="cap">Type a number. For a percent, type the % sign, for example 25%.</span></div>';
  }
  return '<li class="risk-card risk-question" data-field="' + esc(question.field) + '">'
    + '<div class="risk-qhead"><span class="risk-code" title="Driver ' + esc(question.driver) + '">' + esc(question.driver) + '</span>'
    + '<p class="risk-qtext" id="' + id + '-text">' + esc(question.text) + '</p>'
    + (question.help ? '<p class="cap risk-qhelp">' + esc(question.help) + '</p>' : '') + '</div>' + input
    + '<p class="cap risk-saved" aria-live="polite">' + riskSavedLine(question) + '</p>' + riskStillTrueHtml(question, canAnswer) + '</li>';
}

/* "Still true": keeps the carried-over answer as it is and saves it again, so it counts as confirmed this time. */
function riskStillTrueHtml(question, canAnswer) {
  if (!canAnswer || !riskIsCarriedOver(question)) return '';
  return '<button type="button" class="risk-button risk-still" data-still="' + esc(question.field) + '">Still true</button>';
}

function riskProgressHtml() {
  const total = riskForm.sections.length;
  const number = riskForm.sectionIndex + 1;
  const section = riskForm.sections[riskForm.sectionIndex];
  const share = Math.round(number / total * 100);
  return '<div class="risk-progress"><p class="risk-progress-line"><b>Section ' + number + ' of ' + total + '</b> · ' + esc(section.name)
    + '</p><div class="risk-bar" aria-hidden="true"><i style="width:' + share + '%"></i></div></div>';
}

function riskMissingHtml() {
  const missing = riskForm.missing;
  if (!missing) return '';
  return '<div class="risk-card risk-missing" role="alert"><h3>' + plural(missing.length, 'question has', 'questions have') + ' no answer yet</h3>'
    + '<p>A driver with no answer is shown as “not answered yet” and never counted as on. You can answer them first, or submit anyway.</p>'
    + '<ul>' + missing.map(item => '<li><a href="#" data-goto="' + esc(item.section) + '">' + esc(item.section) + '</a> · <span class="risk-code">'
      + esc(item.driver) + '</span> ' + esc(item.text) + '</li>').join('') + '</ul>'
    + '<p class="risk-actions"><button type="button" class="risk-button" id="risk-keep">Keep answering</button> '
    + '<button type="button" class="risk-button primary" id="risk-submit-anyway">Submit anyway</button></p></div>';
}

function riskDrawSection() {
  const group = riskForm.group;
  if (!riskForm.sections.length) {
    riskShow('<h2 class="risk-title">' + esc(group.name) + '</h2><div class="risk-card"><p>There are no questions yet. '
      + 'The questions come from the risk files, and none have a questionnaire field.</p></div>');
    return;
  }
  const section = riskForm.sections[riskForm.sectionIndex];
  const isFirst = riskForm.sectionIndex === 0;
  const isLast = riskForm.sectionIndex === riskForm.sections.length - 1;
  const canAnswer = group.can.answer;

  let body = '<p class="risk-crumb"><a href="#/">Risk assessments</a> / ' + esc(group.name) + riskGuideLink('/guides/filling-in-your-teams-risk-questionnaire/', 'filling in the questionnaire') + '</p>'
    + '<div class="risk-group-top"><h2 class="risk-title">' + esc(group.name) + '</h2>' + riskStatusChip(group.status) + '</div>'
    + '<p class="cap">' + riskTeamWho(group) + (group.assessments ? ' · <a href="#/group/' + encodeURIComponent(group.id) + '/results">See the results</a>' : '') + '</p>'
    + (group.status === 'Sent back' && group.signoff && group.signoff.note ? '<p class="banner">Sent back for another look: ' + esc(group.signoff.note) + '</p>' : '');
  if (!canAnswer) body += '<p class="banner">You can look at this form but not answer it.</p>';
  body += riskProgressHtml();
  body += '<h3 class="risk-section-name">' + esc(section.name) + '</h3><ol class="risk-questions">'
    + section.questions.map(question => riskQuestionHtml(question, canAnswer)).join('') + '</ol>';

  if (isLast && riskForm.answeredFromData.length) {
    body += '<details class="risk-card risk-fromdata" open><summary>' + plural(riskForm.answeredFromData.length, 'driver comes', 'drivers come')
      + ' from data, not from this form' + (riskForm.dataMonth ? ' (TRUST’s ' + esc(riskMonthWords(riskForm.dataMonth)) + ' data)' : '')
      + '</summary><p class="cap">TRUST answers these from its own data. A driver whose data isn’t loaded shows “not known” and is never guessed. The numbers are starting values for Tech Risk to tune.</p><ul class="risk-fromdata-list">'
      + riskForm.answeredFromData.map(riskDataDriverHtml).join('')
      + '</ul></details>';
  }
  if (isLast) body += riskMissingHtml();

  body += '<div class="risk-nav"><button type="button" class="risk-button" id="risk-back"' + (isFirst ? ' disabled' : '') + '>Back</button> ';
  if (!isLast) {
    body += '<button type="button" class="risk-button primary" id="risk-next">Next</button>';
  } else if (group.can.submit) {
    body += '<button type="button" class="risk-button primary" id="risk-submit">Submit</button>';
  } else {
    body += '<span class="cap">Only the team’s lead, the managers above, or Tech Risk can submit.</span>';
  }
  body += ' <span class="cap" id="risk-unanswered">' + plural(riskForm.unanswered, 'question', 'questions') + ' with no answer yet.</span></div>';
  riskShow(body);
  riskWireSection();
}

/* ---------- what the buttons and inputs do ---------- */

function riskGoToSection(index) {
  riskForm.sectionIndex = index;
  sessionStorage.setItem('riskSection:' + riskForm.group.id, String(index));
  riskDrawSection();
}

function riskWireSection() {
  const back = document.getElementById('risk-back');
  const next = document.getElementById('risk-next');
  const submit = document.getElementById('risk-submit');
  if (back) back.addEventListener('click', () => riskGoToSection(riskForm.sectionIndex - 1));
  if (next) next.addEventListener('click', () => riskGoToSection(riskForm.sectionIndex + 1));
  if (submit) submit.addEventListener('click', () => riskSubmit(false));

  document.querySelectorAll('.risk-question').forEach(card => {
    card.querySelectorAll('input[type=checkbox]').forEach(input => input.addEventListener('change', () => riskSaveAnswer(card, riskTicksOf(card, input))));
    card.querySelectorAll('input:not([type=checkbox])').forEach(input => input.addEventListener('change', () => riskSaveAnswer(card, input.value)));
    const still = card.querySelector('[data-still]');
    if (still) still.addEventListener('click', () => riskSaveAnswer(card, riskFindQuestion(card.dataset.field).answer));
  });
  const keep = document.getElementById('risk-keep');
  if (keep) keep.addEventListener('click', () => { riskForm.missing = null; riskDrawSection(); });
  const anyway = document.getElementById('risk-submit-anyway');
  if (anyway) anyway.addEventListener('click', () => riskSubmit(true));
  document.querySelectorAll('[data-goto]').forEach(link => link.addEventListener('click', event => {
    event.preventDefault();
    const index = riskForm.sections.findIndex(section => section.name === link.dataset.goto);
    riskForm.missing = null;
    riskGoToSection(index);
  }));
}

function riskFindQuestion(field) {
  for (const section of riskForm.sections) {
    const found = section.questions.find(question => question.field === field);
    if (found) return found;
  }
  return null;
}

/* Save one answer now. The line under the question then says who saved it and when. */
async function riskSaveAnswer(card, value) {
  const question = riskFindQuestion(card.dataset.field);
  const line = card.querySelector('.risk-saved');
  line.textContent = 'Saving…';
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(riskForm.group.id) + '/answers',
    {question: question.field, answer: value});
  if (!answer.ok) {
    line.innerHTML = '<span class="risk-error">' + esc(answer.error) + ' Your answer was not saved.</span>';
    return;
  }
  Object.assign(question, {answer: answer.saved.answer, by: answer.saved.by, at: answer.saved.at, from_tech_risk: answer.saved.from_tech_risk});
  riskForm.unanswered = answer.unanswered;
  riskForm.group.status = answer.status;
  line.innerHTML = riskSavedLine(question);
  const still = card.querySelector('[data-still]');
  if (still) still.remove();
  document.getElementById('risk-unanswered').textContent = plural(answer.unanswered, 'question', 'questions') + ' with no answer yet.';
}

/* Submit: unanswered questions are listed first; "Submit anyway" sends confirm_unanswered. */
async function riskSubmit(confirmUnanswered) {
  const button = document.getElementById('risk-submit') || document.getElementById('risk-submit-anyway');
  if (button) button.disabled = true;
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(riskForm.group.id) + '/submit', {confirm_unanswered: confirmUnanswered});
  if (answer.ok) {
    location.hash = '#/group/' + encodeURIComponent(riskForm.group.id) + '/results';
    return;
  }
  if (answer.unanswered) {
    riskForm.missing = answer.unanswered;
    riskDrawSection();
    document.querySelector('.risk-missing').scrollIntoView({block: 'center'});
    return;
  }
  if (button) button.disabled = false;
  riskShowProblem(answer.error);
}

riskAddPage(parts => parts[0] === 'group' && parts[1] && !parts[2], parts => riskDrawForm(parts[1]));
