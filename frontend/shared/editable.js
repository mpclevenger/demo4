/* The one way to edit things: draws any editable list from its description (docs/design/22_editable_lists.md).
   Shared by TRUST and Risk. The server sends the list's name, fields, entries and history (backend/trust/editable.py);
   this file turns that into a table, a form, a "See what would move" panel and a history. A new list needs no code here.

   Use:  editList(mount, 'rating-settings', api)
     mount  the element to draw into
     api    async function(path, body) that returns the server's JSON; with a body it POSTs (the site's own helper,
            which adds the X-TRUST header and the typed name)
   Every global name here starts with "edit" because all scripts on a page share one global scope. */
"use strict";

const EDIT_SEARCH_FROM = 12;                              // a search box appears when a list has more entries than this

/* ---------- the page for one list ---------- */

async function editList(mount, slug, api) {
  const state = {slug, api, mount, data: null, search: '', showRetired: false, form: null, checked: false, message: ''};
  mount.innerHTML = '<p class="muted">Loading…</p>';
  const answer = await api('/api/edit/' + encodeURIComponent(slug));
  if (!answer.ok) {
    mount.innerHTML = '<div class="risk-card"><h2>This list can’t be shown</h2><p>' + esc(answer.error) + '</p></div>';
    return;
  }
  state.data = answer;
  editDrawAll(state);
}

function editDrawAll(state) {
  const list = state.data.list;
  let notes = list.notes.map(note => '<p class="cap">' + esc(note) + '</p>').join('');
  const who = state.data.can_save
    ? 'Who may save changes: ' + esc(list.who_text) + (state.data.open ? ' (access isn’t set up yet, so anyone may, and the record shows the name typed at the top).' : '.')
    : 'Who may save changes: ' + esc(list.who_text) + '. You can read this list and its history.';
  const base = '/api/edit/' + encodeURIComponent(state.slug) + '/download';
  state.mount.innerHTML = '<h2 class="edit-title">' + esc(list.name) + '</h2>'
    + '<p class="edit-intro">' + esc(list.intro) + '</p>' + notes
    + '<p class="cap">' + who + '</p>'
    + '<div class="edit-tools noprint">'
    + (state.data.entries.length > EDIT_SEARCH_FROM ? '<label class="edit-search">Search <input type="search" data-edit="search" value="' + esc(state.search) + '"></label>' : '')
    + (state.data.entries.some(entry => entry.retired) ? '<label class="edit-check"><input type="checkbox" data-edit="retired"' + (state.showRetired ? ' checked' : '') + '> Show retired</label>' : '')
    + '<span class="edit-grow"></span>'
    + '<span class="cap">Download the list</span> <a class="risk-button" href="' + base + '?format=csv">CSV</a> <a class="risk-button" href="' + base + '?format=json">JSON</a>'
    + (state.data.can_save && list.grows ? ' <button type="button" class="risk-button primary" data-edit="add">Add</button>' : '')
    + '</div>'
    + '<div data-edit-part="message" aria-live="polite">' + (state.message ? '<p class="edit-saved">' + esc(state.message) + '</p>' : '') + '</div>'
    + '<div data-edit-part="form"></div>'
    + '<div data-edit-part="table"></div>'
    + '<div data-edit-part="history"></div>';
  editDrawTable(state);
  editDrawHistory(state);
  state.mount.onclick = event => editClick(state, event);
  state.mount.oninput = event => editInput(state, event);
  state.mount.onchange = event => editInput(state, event);
}

function editPart(state, name) {
  return state.mount.querySelector('[data-edit-part="' + name + '"]');
}

/* ---------- the table ---------- */

function editColumns(state) {
  return state.data.list.fields.filter(field => field.table !== false);
}

function editMatches(state, entry) {
  if (!state.search) return true;
  const words = state.search.toLowerCase().split(/\s+/).filter(Boolean);
  const text = (entry.key + ' ' + Object.values(entry.shown).join(' ')).toLowerCase();
  return words.every(word => text.includes(word));
}

function editDrawTable(state) {
  const columns = editColumns(state);
  const shownEntries = state.data.entries.filter(entry => (state.showRetired || !entry.retired) && editMatches(state, entry));
  let head = columns.map(field => '<th>' + esc(field.table_label || field.label) + '</th>').join('');
  head += state.data.can_save ? '<th class="noprint"><span class="edit-sr">Actions</span></th>' : '';
  const rows = shownEntries.map(entry => {
    const cells = columns.map(field => '<td>' + esc(entry.shown[field.name]) + '</td>').join('');
    let actions = '';
    if (state.data.can_save) {
      const key = esc(entry.key);
      const edit = '<button type="button" class="risk-button small" data-edit="edit" data-key="' + key + '">Edit</button>';
      const retire = !state.data.list.grows ? '' : entry.retired
        ? ' <button type="button" class="risk-button small" data-edit="restore" data-key="' + key + '">Restore</button>'
        : ' <button type="button" class="risk-button small" data-edit="retire" data-key="' + key + '">Retire</button>';
      actions = '<td class="edit-actions noprint">' + (entry.retired ? '' : edit) + retire + '</td>';
    }
    return '<tr' + (entry.retired ? ' class="edit-retired"' : '') + '>' + cells + actions + '</tr>';
  }).join('');
  const retiredCount = state.data.entries.filter(entry => entry.retired).length;
  const counted = plural(state.data.entries.length - retiredCount, 'entry', 'entries')
    + (retiredCount ? ' in use, ' + retiredCount + ' retired' : '');
  editPart(state, 'table').innerHTML = '<p class="cap">' + counted + (state.search ? ' · ' + shownEntries.length + ' match' : '') + '</p>'
    + '<div class="risk-scroll"><table class="risk-table"><thead><tr>' + head + '</tr></thead><tbody>'
    + (rows || '<tr><td colspan="' + (columns.length + 1) + '" class="muted">Nothing to show.</td></tr>') + '</tbody></table></div>';
}

/* ---------- the history: who, when, old value, new value, why ---------- */

function editDrawHistory(state) {
  const history = state.data.history;
  const rows = history.map(change => {
    const what = change.what.map(item => '<div><b>' + esc(item.label) + '</b>: '
      + (item.before !== '' ? '<span class="edit-old">' + esc(item.before) + '</span> → ' : '') + '<span class="edit-new">' + esc(item.after === '' ? 'empty' : item.after) + '</span></div>').join('');
    const verb = {add: 'Added', edit: 'Changed', retire: 'Retired', restore: 'Restored', load: 'Loaded'}[change.action] || change.action;
    return '<tr><td class="nowrap">' + when(change.at) + '</td><td>' + esc(change.by) + '</td><td><b>' + esc(verb) + '</b> ' + esc(change.title)
      + '</td><td>' + what + '</td><td>' + esc(change.reason) + '</td></tr>';
  }).join('');
  editPart(state, 'history').innerHTML = '<details class="edit-history"' + (history.length ? ' open' : '') + '><summary>History · '
    + plural(history.length, 'change', 'changes') + '</summary>'
    + (history.length ? '<div class="risk-scroll"><table class="risk-table"><thead><tr><th>When</th><th>Who</th><th>Entry</th><th>Old → new</th><th>Why</th></tr></thead><tbody>'
      + rows + '</tbody></table></div>' : '<p class="muted">Nothing has been changed on the site yet. The values come from the file.</p>') + '</details>';
}

/* ---------- the form: add, edit, retire, restore ---------- */

function editFieldInput(field, value, locked) {
  const name = esc(field.name);
  if (locked) return '<span class="edit-fixed">' + esc(value === null || value === undefined ? '' : (field.choices ? (field.choices.find(c => c.value === value) || {label: value}).label : value)) + '</span>';
  if (field.kind === 'pick' || field.kind === 'yes_no') {
    const choices = field.kind === 'yes_no' ? [{value: 'yes', label: 'Yes'}, {value: 'no', label: 'No'}] : field.choices;
    const chosen = field.kind === 'yes_no' ? (value === true ? 'yes' : value === false ? 'no' : '') : value;
    return '<select data-field="' + name + '">' + (chosen ? '' : '<option value="">Choose…</option>')
      + choices.map(choice => '<option value="' + esc(choice.value) + '"' + (choice.value === chosen ? ' selected' : '') + '>' + esc(choice.label) + '</option>').join('') + '</select>';
  }
  const listId = field.suggestions ? ' list="edit-list-' + name + '"' : '';
  const datalist = field.suggestions ? '<datalist id="edit-list-' + name + '">' + field.suggestions.map(item => '<option value="' + esc(item) + '">').join('') + '</datalist>' : '';
  return '<input type="text" data-field="' + name + '"' + listId + (field.kind === 'number' ? ' inputmode="decimal"' : '') + ' value="' + esc(value) + '">' + datalist;
}

function editOpenForm(state, action, key) {
  const entry = key === null ? null : state.data.entries.find(item => item.key === key);
  const fields = entry ? entry.fields : state.data.list.fields;
  state.form = {action, key, fields, entry};
  state.checked = false;
  const verb = {add: 'Add', edit: 'Edit', retire: 'Retire', restore: 'Restore'}[action];
  let body = '';
  if (action === 'retire' || action === 'restore') {
    body = '<p>' + (action === 'retire' ? 'Retiring takes it out of use. It stays in the list (grayed) and in the history, and you can restore it.'
      : 'Restoring puts it back in use.') + '</p>';
  } else {
    body = '<div class="edit-fields">' + fields.map(field => {
      const value = entry ? entry.values[field.name] : null;
      const locked = field.readonly || (field.once && action === 'edit');
      const hidden = field.only_when ? ' data-when-field="' + esc(field.only_when.field) + '" data-when-is="' + esc(field.only_when.is) + '"' : '';
      return '<label class="edit-field"' + hidden + '><span class="edit-label">' + esc(field.label) + '</span>'
        + editFieldInput(field, value, locked) + (field.help ? '<span class="cap">' + esc(field.help) + '</span>' : '') + '</label>';
    }).join('') + '</div>';
  }
  const title = entry ? verb + ': ' + entry.title : verb + ' an entry';
  const canMove = state.data.list.can_move_ratings;
  editPart(state, 'form').innerHTML = '<div class="risk-card edit-form"><h3>' + esc(title) + '</h3>' + body
    + '<label class="edit-field"><span class="edit-label">Why (the history keeps your reason)</span><textarea data-field="__reason" rows="2" maxlength="1000"></textarea></label>'
    + '<div data-edit-part="preview" aria-live="polite"></div>'
    + '<p class="edit-buttons"><button type="button" class="risk-button" data-edit="check">' + (canMove ? 'See what would move' : 'Check the change') + '</button> '
    + '<button type="button" class="risk-button primary" data-edit="save" disabled>Save</button> '
    + '<button type="button" class="risk-button" data-edit="cancel">Cancel</button> <span class="risk-error" data-edit-part="error" role="alert"></span></p></div>';
  editShowWhen(state);
  const first = editPart(state, 'form').querySelector('input,select,textarea');
  if (first) first.focus();
  editPart(state, 'form').scrollIntoView({block: 'nearest'});
}

/* A field that only applies to one kind of answer shows only then (a number for a number question). */
function editShowWhen(state) {
  const form = editPart(state, 'form');
  form.querySelectorAll('[data-when-field]').forEach(label => {
    const controller = form.querySelector('[data-field="' + label.dataset.whenField + '"]');
    const current = controller ? controller.value : null;
    label.hidden = controller !== null && current !== label.dataset.whenIs;
  });
}

function editTypedValues(state) {
  const values = {};
  editPart(state, 'form').querySelectorAll('[data-field]').forEach(input => {
    if (input.dataset.field !== '__reason' && !(input.closest('label') || {}).hidden) values[input.dataset.field] = input.value;
  });
  return values;
}

function editRequest(state) {
  const form = editPart(state, 'form');
  return {action: state.form.action, key: state.form.key === null ? '' : state.form.key, values: editTypedValues(state),
          reason: form.querySelector('[data-field="__reason"]').value};
}

function editDrawPreview(state, answer) {
  let html = '<div class="edit-preview"><h4>What this change does</h4><ul>'
    + answer.differences.map(item => '<li><b>' + esc(item.label) + '</b>: ' + (item.before !== '' ? '<span class="edit-old">' + esc(item.before) + '</span> → ' : '')
      + '<span class="edit-new">' + esc(item.after === '' ? 'empty' : item.after) + '</span></li>').join('')
    + (answer.differences.length ? '' : '<li>' + (answer.action === 'retire' ? 'It is taken out of use.' : 'It is put back in use.') + '</li>') + '</ul>';
  if (answer.can_move_ratings) {
    if (!answer.moves.length) {
      html += '<p><b>No rating would move.</b> <span class="cap">Each team’s newest assessment was rated again with this change.</span></p>';
    } else {
      html += '<h4>' + plural(answer.moves.length, 'rating would move', 'ratings would move') + '</h4>'
        + '<div class="risk-scroll"><table class="risk-table"><thead><tr><th>Team</th><th>Risk</th><th>Rating</th><th>Now</th><th>After the change</th></tr></thead><tbody>'
        + answer.moves.map(move => '<tr><td>' + esc(move.group) + '</td><td><span class="risk-code">' + esc(move.risk) + '</span> ' + esc(move.name)
          + '</td><td>' + esc(move.what) + '</td><td>' + esc(move.before) + '</td><td><b>' + esc(move.after) + '</b></td></tr>').join('')
        + '</tbody></table></div><p class="cap">Saved assessments don’t change. A team’s next Submit uses the new values.</p>';
    }
  }
  editPart(state, 'form').querySelector('[data-edit-part="preview"]').innerHTML = html + '</div>';
}

/* ---------- what happens when a person does something ---------- */

function editInput(state, event) {
  const target = event.target;
  if (target.dataset.edit === 'search') {
    if (event.type === 'change') return;                  // the table is already up to date; redrawing on blur would swallow the click on a button
    state.search = target.value;
    editDrawTable(state);
  } else if (target.dataset.edit === 'retired') {
    state.showRetired = target.checked;
    editDrawTable(state);
  } else if (state.form && target.dataset.field) {
    state.checked = false;                                // the values changed: check them again before saving
    const form = editPart(state, 'form');
    form.querySelector('[data-edit="save"]').disabled = true;
    form.querySelector('[data-edit-part="preview"]').innerHTML = '';
    editShowWhen(state);
  }
}

async function editClick(state, event) {
  const button = event.target.closest('[data-edit]');
  if (!button || button.tagName === 'INPUT' || button.tagName === 'A') return;
  const what = button.dataset.edit;
  if (['add', 'edit', 'retire', 'restore'].includes(what)) {
    state.message = '';
    editPart(state, 'message').innerHTML = '';
    editOpenForm(state, what, what === 'add' ? null : button.dataset.key);
  } else if (what === 'cancel') {
    state.form = null;
    editPart(state, 'form').innerHTML = '';
  } else if (what === 'check') {
    await editCheck(state, button);
  } else if (what === 'save') {
    await editSave(state, button);
  }
}

async function editCheck(state, button) {
  const form = editPart(state, 'form');
  const errorBox = form.querySelector('[data-edit-part="error"]');
  errorBox.textContent = '';
  button.disabled = true;
  const answer = await state.api('/api/edit/' + encodeURIComponent(state.slug) + '/preview', editRequest(state));
  button.disabled = false;
  if (!answer.ok) {
    errorBox.textContent = answer.error;
    form.querySelector('[data-edit-part="preview"]').innerHTML = '';
    return;
  }
  state.checked = true;
  editDrawPreview(state, answer);
  form.querySelector('[data-edit="save"]').disabled = false;
}

async function editSave(state, button) {
  const form = editPart(state, 'form');
  const errorBox = form.querySelector('[data-edit-part="error"]');
  errorBox.textContent = '';
  button.disabled = true;
  const answer = await state.api('/api/edit/' + encodeURIComponent(state.slug) + '/save', editRequest(state));
  if (!answer.ok) {
    errorBox.textContent = answer.error;
    button.disabled = !state.checked;
    return;
  }
  const kind = state.form.action;
  const saved = {add: 'Added', edit: 'Saved', retire: 'Retired', restore: 'Restored'}[kind];
  state.data = answer;
  state.form = null;
  state.message = saved + '. The change is in the history below.';
  editDrawAll(state);
}
