/* The Risk site: sign-off by the team's lead (the product family owner, or the person the team is built around).
   The box on the results page: who should sign off, Sign off or Send back with a note, the flag, and the history.
   Every name here starts with "riskSignoff" because every script on the page shares one global scope. */
"use strict";

/* One decision, as a line in the history: who, when, the note, and the flag. */
function riskSignoffEntryHtml(entry) {
  let line = '<li class="risk-signoff-entry"><p>' + riskStatusChip(entry.state)
    + ' <span class="cap">Assessment of ' + when(entry.at) + ' (submitted by ' + esc(entry.by) + ')</span></p>';
  if (entry.decided_by) {
    const verb = entry.state === 'Sent back' ? 'Sent back' : 'Signed off';
    line += '<p>' + verb + ' by <b>' + esc(entry.decided_by) + '</b>, ' + when(entry.decided_at) + '.</p>'
      + '<p class="risk-signoff-note">' + esc(entry.note) + '</p>';
    if (entry.flag) line += '<p class="risk-signoff-flag"><b>Flag:</b> ' + esc(entry.flag) + ' <span class="cap">This is shown for everyone to see. It does not stop a sign-off.</span></p>';
  }
  return line + '</li>';
}

function riskSignoffActionsHtml(info) {
  let html = '';
  if (info.open) {
    html += '<p class="banner">Access isn’t set up yet, so anyone can sign off. Type your name in the box at the top first, so the record shows who did it.</p>';
  }
  html += '<label class="risk-signoff-label" for="risk-signoff-note"><b>Note</b></label>'
    + '<textarea id="risk-signoff-note" rows="3" maxlength="500"></textarea>'
    + '<p class="cap">A short note is needed for both. If you send it back, this is the reason the team sees.</p>'
    + '<p class="risk-actions"><button type="button" class="risk-button primary" id="risk-signoff-yes">Sign off</button> '
    + '<button type="button" class="risk-button" id="risk-signoff-back">Send back</button></p>'
    + '<p class="risk-error" id="risk-signoff-problem" role="alert"></p>';
  return html;
}

function riskSignoffDelegateHtml(info) {
  if (!info.can_name_delegate) return '';
  const leadNames = info.who.leads.map(lead => lead.name).join(' or ');
  const current = info.who.delegates.length ? info.who.delegates.map(person => person.name + ' (' + person.sam + ')').join(', ') : 'nobody';
  const firstDelegate = info.who.delegates.length ? info.who.delegates[0].sam : '';
  return '<details class="risk-signoff-delegate"><summary>Name someone to sign off for ' + esc(leadNames) + '</summary>'
    + '<p class="cap">Now: ' + esc(current) + '. The delegate covers every team ' + esc(leadNames) + ' signs off.</p>'
    + '<label for="risk-signoff-delegate"><b>Their SAM_ACCOUNT</b></label> '
    + '<input id="risk-signoff-delegate" type="text" maxlength="60" value="' + esc(firstDelegate) + '"> '
    + '<button type="button" class="risk-button" id="risk-signoff-delegate-save">Save</button> '
    + '<button type="button" class="risk-button" id="risk-signoff-delegate-clear">Clear</button>'
    + '<p class="risk-error" id="risk-signoff-delegate-problem" role="alert"></p></details>';
}

function riskSignoffBoxHtml(info, showingNewest) {
  let html = '<section class="risk-card risk-signoff" aria-labelledby="risk-signoff-title"><div class="risk-group-top"><h3 id="risk-signoff-title">Sign-off</h3>'
    + riskStatusChip(info.status) + '</div>';
  html += '<p>' + esc(info.who.sentence) + '</p>';
  if (info.status === 'Sent back' && info.sent_back_reason) {
    html += '<p class="banner">Sent back. The team can answer and submit again. <b>Reason:</b> ' + esc(info.sent_back_reason) + '</p>';
  }
  if (info.status === 'Draft' && info.history.length) {
    html += '<p class="cap">The answers changed after the last Submit, so it needs to be submitted again before it can be signed off.</p>';
  }
  if (info.status === 'Not started' || !info.history.length) {
    html += '<p class="cap">Nothing has been submitted yet.</p>';
  } else if (info.can_sign_off && showingNewest) {
    html += riskSignoffActionsHtml(info);
  } else if (info.waiting && !info.may_sign_off) {
    html += '<p class="cap">' + esc(info.why_not) + '</p>';
  } else if (info.waiting && !showingNewest) {
    html += '<p class="cap">Open the newest assessment to sign it off.</p>';
  }
  html += riskSignoffDelegateHtml(info);
  if (info.history.length) {
    html += '<h4 class="risk-signoff-history-title">History</h4><ul class="risk-signoff-history">' + info.history.map(riskSignoffEntryHtml).join('') + '</ul>';
  }
  return html + '</section>';
}

/* Send one decision, then draw the whole page again so every status word on it is right. */
async function riskSignoffSend(groupId, action, body, problemId) {
  const answer = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId) + '/' + action, body);
  if (!answer.ok) {
    document.getElementById(problemId).textContent = answer.error;
    return;
  }
  riskOpenPage();
}

async function riskSignoffDraw(groupId, shownAssessmentId) {
  const place = document.getElementById('risk-signoff-box');
  if (!place) return;
  const info = await riskApi('/api/risk/groups/' + encodeURIComponent(groupId) + '/signoff');
  if (!info.ok) { place.innerHTML = '<p class="cap">' + esc(info.error) + '</p>'; return; }
  const newestId = info.history.length ? info.history[0].assessment_id : null;
  place.innerHTML = riskSignoffBoxHtml(info, shownAssessmentId === newestId);

  const noteField = document.getElementById('risk-signoff-note');
  if (noteField) {
    document.getElementById('risk-signoff-yes').addEventListener('click', () =>
      riskSignoffSend(groupId, 'signoff', {note: noteField.value}, 'risk-signoff-problem'));
    document.getElementById('risk-signoff-back').addEventListener('click', () =>
      riskSignoffSend(groupId, 'sendback', {reason: noteField.value}, 'risk-signoff-problem'));
  }
  const saveButton = document.getElementById('risk-signoff-delegate-save');
  if (saveButton) {
    const field = document.getElementById('risk-signoff-delegate');
    saveButton.addEventListener('click', () => riskSignoffSend(groupId, 'delegate', {delegate_sam: field.value}, 'risk-signoff-delegate-problem'));
    document.getElementById('risk-signoff-delegate-clear').addEventListener('click', () =>
      riskSignoffSend(groupId, 'delegate', {delegate_sam: ''}, 'risk-signoff-delegate-problem'));
  }
}
