/* The Risk site: the Tech Risk editing pages (rating settings, questions, building blocks, data drivers).
   The pages are drawn by the shared editing screen (/shared/editable.js); this file only adds the way in: an Edit
   link in the top bar (shown to Tech Risk; while TRUST runs open, to everyone) and the addresses #/edit and
   #/edit/<list>. It adds itself to the lists in risk-core.js. All names start with "riskEdit". */
"use strict";

async function riskEditDrawIndex() {
  riskShow('<p class="muted">Loading…</p>');
  const answer = await riskApi('/api/edit');
  if (!answer.ok) { riskShowProblem(answer.error); return; }
  const cards = answer.lists.map(list => '<li class="risk-card risk-group"><h2>' + esc(list.name) + '</h2>'
    + '<p class="cap">' + esc(list.intro) + '</p><p class="cap">' + plural(list.entries, 'entry', 'entries') + '</p>'
    + '<p class="risk-actions"><a class="risk-button primary" href="#/edit/' + encodeURIComponent(list.slug) + '">'
    + (answer.can_save ? 'Edit' : 'See') + ' this list</a></p></li>').join('');
  const extraCards = riskEditExtras.map(extra => extra.html()).join('');
  riskShow('<p class="risk-crumb"><a href="#/">Risk assessments</a> › Edit</p><h2 class="risk-title">Edit</h2>'
    + '<p class="risk-intro">The lists that set how the Risk site works. Every change asks for a reason and is kept in the list’s history, which everyone can read.'
    + (answer.can_save ? '' : ' Tech Risk makes the changes.') + '</p><ul class="risk-grid">' + cards + extraCards + '</ul>');
}

async function riskEditDrawList(slug) {
  const main = riskShow('<p class="risk-crumb"><a href="#/">Risk assessments</a> › <a href="#/edit">Edit</a></p><div id="risk-edit-mount" class="edit-page"></div>');
  await editList(main.querySelector('#risk-edit-mount'), slug, riskApi);
}

riskTopBarLinks.push({id: 'risk-editlink', href: '#/edit', words: 'Edit', isShown: riskIsTechRisk});
riskAddPage(parts => parts[0] === 'edit', parts => parts[1] ? riskEditDrawList(parts[1]) : riskEditDrawIndex());
