/* Lost and found (Tech Risk): items no file could place with a family, and claims. */
"use strict";
/* ---------- Lost and found (owner, 9 Nov 2026) ----------
   Items in the month's files that no source could place with a product family (a change by someone not in HR, an
   application whose product area matches no family...). A family lead, or Tech Risk, claims one; Tech Risk approves
   or returns the claim; an approved claim places the item from the next Update and in every later month. A claim
   never overrides a source file. Tech Risk can release an approved claim. Search and filters work in place. */
const LF = {state:'idle', month:null, data:null, q:'', feed:'', met:'', st:'', form:null, dec:null, msg:'', err:'', ferr:''};
function lfLoad(force){
  if (!force && (LF.state === 'loading' || (LF.state === 'ok' && LF.month === S.p))) return;
  LF.state = 'loading'; LF.month = S.p;
  api('/api/lost/' + encodeURIComponent(S.p)).then(j => { LF.data = j; LF.state = 'ok'; })
    .catch(e => { LF.state = 'fail'; LF.err = e.message; }).finally(() => { S.keepScroll = true; render(); });
}
const LF_ST = {draft:'Claim waiting for Tech Risk', approved:'Claim approved', returned:'Claim returned', withdrawn:'Claim withdrawn', released:'Claim released'};
const lfClaimOn = (feed, item) => ((LF.data && LF.data.claims) || []).filter(c => c.feed === feed && String(c.item) === String(item) && (c.status === 'draft' || c.status === 'approved')).slice(-1)[0] || null;
const lfFam = id => (LF.data && LF.data.families && LF.data.families[id]) || (fam(id) || {}).name || id;
const lfMayClaim = () => !ME || ME.can.run_month;   // Tech Risk only (owner, 15 Nov 2026)
function lfFamilies(){ const all = Object.keys((LF.data && LF.data.families) || {}); return all.filter(lfMayClaim).sort((a, b) => lfFam(a).localeCompare(lfFam(b))); }
function lfClaimForm(i){
  const fams = lfFamilies(), k = i.feed + '|' + i.item;
  if (!fams.length) return '<p class="cap">Only Tech Risk can claim an item.</p>';
  return `<form class="lff" data-k="${esc(k)}" aria-label="Claim ${esc(i.kind)} ${esc(i.item)}"><label>Product family <select name="family" required>${fams.length > 1 ? '<option value="">Choose…</option>' : ''}${fams.map(f => `<option value="${esc(f)}">${esc(lfFam(f))}</option>`).join('')}</select></label>
    <label style="display:block;margin-top:6px">Why it’s yours (Tech Risk reads this)<textarea name="why" rows="2" maxlength="1000" required></textarea></label>${byField('margin-top:6px;display:block')}
    <p style="margin:8px 0 0"><button type="submit" class="pri">Send the claim to Tech Risk</button> <button type="button" data-act="lf-cancel">Cancel</button></p>
    <p class="cap" style="margin:6px 0 0">Once Tech Risk approves it, the item counts for that family from the next Update of any open month, and in every month after. Locked months don’t change.</p></form>`;
}
function vLost(){
  lfLoad();
  const head = `<div class="ph"><h1>Lost and found</h1><p class="cap" style="margin:4px 0 0;max-width:none">Items in ${esc(monthLabel(S.p))}’s files that TRUST couldn’t place with a product family, so they count only in the firm’s figures. Claim an item for the family it belongs to. Once the claim is approved, the item counts for that family from the next Update, this month and every month after.</p></div>`;
  if (LF.state !== 'ok') return `<main class="wrap sheet">${head}<p class="cap" role="status">${LF.state === 'fail' ? esc(LF.err || 'The list couldn’t be loaded. Reload the page to try again.') : 'Loading…'}</p></main>`;
  const d = LF.data, its = d.items || [], cl = d.claims || [];
  if (!d.mapped) return `<main class="wrap sheet">${head}<p class="muted">${esc(monthLabel(S.p))} hasn’t been updated yet, so there is nothing to list. Upload the month’s files and press Update the scorecard.</p></main>`;
  const feeds = [...new Set(its.map(i => i.feed))], mets = [...new Set(its.flatMap(i => i.metrics))].sort();
  const kindOf = f => (its.find(i => i.feed === f) || {}).kind || f;
  const metName = id => (MET_IDS.has(id) ? met(id).name : id);
  const row = i => { const c = lfClaimOn(i.feed, i.item), k = i.feed + '|' + i.item, open = LF.form === k;
    const st = c ? (c.status === 'draft' ? 'waiting' : 'approved') : 'none';
    const cell = c ? `<span class="chip ${c.status === 'approved' ? 'ok' : 'wait'}">${c.status === 'approved' ? `Claimed by ${esc(lfFam(c.family_id))}` : `Waiting: ${esc(lfFam(c.family_id))}`}</span><div class="cap">${c.status === 'approved' ? (d.claims_used.includes(c.id) ? '' : 'Counts from the next Update') : 'Tech Risk to check'}</div>`
      : (S.snap || (ME && ME.read_only) || !lfFamilies().length ? '<span class="muted">Not claimed</span>' : `<button type="button" class="sm" data-act="lf-claim" data-k="${esc(k)}" aria-expanded="${open}">Claim it</button>`);
    const txt = [i.kind, i.item, i.names, i.why, ...i.metrics.map(metName), c ? lfFam(c.family_id) : ''].join(' ').toLowerCase();
    return `<tr class="lfr" data-txt="${esc(txt)}" data-feed="${esc(i.feed)}" data-met="${esc(i.metrics.join(' '))}" data-st="${st}"><td>${esc(i.kind)}</td><td>${safeLink(i.link) ? `<a href="${esc(safeLink(i.link))}" target="_blank" rel="noopener"><b>${esc(i.item)}</b></a>` : `<b>${esc(i.item)}</b>`}</td><td>${esc(i.names) || '<span class="muted">—</span>'}</td><td>${esc(i.why)}</td><td>${i.metrics.map(m => `<span class="tag">${esc(metName(m))}</span>`).join(' ')}</td><td>${cell}</td></tr>`
      + (open ? `<tr class="subrow lfr-f" data-for="${esc(k)}"><td colspan="6">${lfClaimForm(i)}</td></tr>` : ''); };
  const sel = (id, label, cur, opts) => `<label class="lfl">${label}<select id="${id}">${opts.map(([v, t]) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select></label>`;
  const tools = `<div class="lftools noprint" role="search"><label class="lfl lfq">Search<input type="search" id="lf-q" value="${esc(LF.q)}" placeholder="Item, person, email, repo, reason…" autocomplete="off"></label>
    ${sel('lf-feed', 'Source', LF.feed, [['', 'All sources'], ...feeds.map(f => [f, kindOf(f)])])}${sel('lf-met', 'Counts in', LF.met, [['', 'Any metric'], ...mets.map(m => [m, metName(m)])])}${sel('lf-st', 'Claim', LF.st, [['', 'Any'], ['none', 'Not claimed'], ['waiting', 'Claim waiting'], ['approved', 'Claim approved']])}
    <button type="button" class="sm" data-act="lf-clear">Clear</button></div>`;
  const nWait = cl.filter(c => c.status === 'draft').length, nAppr = cl.filter(c => c.status === 'approved').length;
  const summary = `<p class="lfsum"><b>${plural(its.length, 'item', 'items')}</b> not placed this month · ${plural(nWait, 'claim', 'claims')} waiting for Tech Risk · ${plural(nAppr, 'claim', 'claims')} approved</p>`;
  const table = its.length ? `${tools}<p class="cap" id="lf-count" role="status" aria-live="polite"></p><div class="ddscroll"><table class="dt lft"><caption class="sr-only">Items not placed with a product family</caption><colgroup><col style="width:13%"><col style="width:12%"><col style="width:20%"><col style="width:27%"><col style="width:14%"><col style="width:14%"></colgroup><thead><tr><th>Source</th><th>Item</th><th>Who or what it names</th><th>Why it wasn’t placed</th><th>Counts in</th><th>Claim</th></tr></thead><tbody>${its.map(row).join('')}</tbody></table></div><p class="cap" id="lf-none" hidden>Nothing matches. <button type="button" class="sm" data-act="lf-clear">Clear the search and filters</button></p>`
    : `<p class="muted">Every item in ${esc(monthLabel(S.p))}’s files was placed with a product family. Nothing is lost.</p>`;
  /* the claims, every month: waiting first */
  const tr = !ME || ME.can.run_month, order = {draft:0, approved:1, returned:2, withdrawn:3, released:4};
  const decideBtns = c => S.snap || (ME && ME.read_only) ? '' : c.status === 'draft' ? (tr ? `<button type="button" class="sm" data-act="lf-dec" data-id="${c.id}" data-d="approved">Approve</button> <button type="button" class="sm" data-act="lf-dec" data-id="${c.id}" data-d="returned">Return</button> ` : '') + (!ME || ME.name === c.by ? `<button type="button" class="sm" data-act="lf-dec" data-id="${c.id}" data-d="withdrawn">Withdraw</button>` : '')
    : c.status === 'approved' && tr ? `<button type="button" class="sm" data-act="lf-dec" data-id="${c.id}" data-d="released">Release</button>` : '';
  const decForm = LF.dec ? `<form class="lfd" data-id="${LF.dec.id}" data-d="${LF.dec.d}" style="margin:8px 0"><label>${{approved:'Approve', returned:'Return', withdrawn:'Withdraw', released:'Release'}[LF.dec.d]} claim ${LF.dec.id}${LF.dec.d === 'returned' || LF.dec.d === 'released' ? ': say why' : ' (a note is optional)'}<br><input name="reason" style="width:60%" maxlength="1000" ${LF.dec.d === 'returned' || LF.dec.d === 'released' ? 'required' : ''}></label> ${byField()} <button type="submit" class="pri">${{approved:'Approve', returned:'Return', withdrawn:'Withdraw', released:'Release'}[LF.dec.d]}</button> <button type="button" data-act="lf-dec-cancel">Cancel</button>${LF.dec.d === 'released' ? '<p class="cap" style="margin:4px 0 0">The item goes back to Lost and found at the next Update of each open month. Locked months don’t change.</p>' : ''}</form>` : '';
  const cRows = cl.slice().sort((a, b) => (order[a.status] - order[b.status]) || (b.id - a.id)).map(c => `<tr><td><b>${esc(c.item)}</b><div class="cap">${esc((KIND_OF[c.feed] || c.feed))} · claimed from ${esc(monthLabel(c.month))}</div></td><td>${esc(lfFam(c.family_id))}</td><td>${esc(c.why)}</td><td>${esc(c.by)}<div class="cap">${fd(c.at)}</div></td><td>${esc(LF_ST[c.status] || c.status)}${c.decided_by ? `<div class="cap">${esc(c.decided_by)} · ${fd(c.decided_at)}${c.reason ? ' · ' + esc(c.reason) : ''}</div>` : ''}</td><td class="noprint">${decideBtns(c)}</td></tr>`).join('');
  const claims = `<section class="grp" aria-labelledby="lf-ch"><h2 id="lf-ch">Claims</h2>${cl.length ? `${decForm}<table class="dt"><caption class="sr-only">Every claim, waiting first</caption><thead><tr><th>Item</th><th>Family</th><th>Why it’s theirs</th><th>Claimed by</th><th>Status</th><th class="noprint"><span class="sr-only">Decide</span></th></tr></thead><tbody>${cRows}</tbody></table><p class="cap">${tr ? 'Approving places the item from the next Update; releasing undoes it. Every decision is logged.' : 'Tech Risk approves or returns each claim. Every decision is logged.'}</p>` : '<p class="muted" style="margin:0">No claims yet.</p>'}</section>`;
  const msg = (LF.msg ? `<p class="okmsg" role="status">${esc(LF.msg)}</p>` : '') + (LF.ferr ? `<p class="ferr" role="alert">${esc(LF.ferr)}</p>` : '');
  return `<main class="wrap sheet lfp">${head}${msg}${summary}${table}${claims}</main>`;
}
const KIND_OF = {tcc:'Change (TCC)', ntcc:'Change outside TCC', actions:'Postmortem action', postmortems:'Incident', repos:'GitHub repo', cx_sast:'Checkmarx SAST project', cx_sca:'Checkmarx SCA project', itdr:'ITDR application'};
function lfFilter(){
  const q = ($('#lf-q') || {}).value || '', f = ($('#lf-feed') || {}).value || '', m = ($('#lf-met') || {}).value || '', st = ($('#lf-st') || {}).value || '';
  Object.assign(LF, {q, feed:f, met:m, st});
  const words = q.toLowerCase().split(/\s+/).filter(Boolean), rows = [...document.querySelectorAll('tr.lfr')];
  let n = 0;
  rows.forEach(r => { const ok = words.every(w => r.dataset.txt.includes(w)) && (!f || r.dataset.feed === f) && (!m || r.dataset.met.split(' ').includes(m)) && (!st || r.dataset.st === st);
    r.hidden = !ok; const fr = r.nextElementSibling; if (fr && fr.classList.contains('lfr-f')) fr.hidden = !ok; if (ok) n++; });
  const c = $('#lf-count'); if (c) c.textContent = n === rows.length ? `Showing all ${plural(rows.length, 'item', 'items')}` : `Showing ${n} of ${plural(rows.length, 'item', 'items')}`;
  const none = $('#lf-none'); if (none) none.hidden = n > 0 || !rows.length;
}
document.addEventListener('submit', e => {      // Lost and found: a claim, or a decision on one
  const f = e.target;
  if (f.matches('form.lff')) {
    e.preventDefault();
    const [feed, ...rest] = f.dataset.k.split('|'), item = rest.join('|'), it = ((LF.data && LF.data.items) || []).find(x => x.feed === feed && String(x.item) === item) || {};
    const fam_ = f.family.value, why = f.why.value.trim();
    if (!fam_ || !why) { LF.ferr = !fam_ ? 'Choose the product family.' : 'Say why it’s yours, so Tech Risk can check.'; S.keepScroll = true; render(); return; }
    apiPost('/api/claims', {by:liveName(f), month:S.p, feed, item, family:fam_, why, label:`${it.kind || ''} ${item}`.trim()})
      .then(() => { LF.form = null; LF.ferr = ''; LF.msg = `Claim sent: ${it.kind || 'item'} ${item} for ${lfFam(fam_)}. Tech Risk will check it.`; lfLoad(true); })
      .catch(err => { LF.ferr = err.message; S.keepScroll = true; render(); });
    return;
  }
  if (f.matches('form.lfd')) {
    e.preventDefault();
    const d = f.dataset.d, reason = f.reason.value.trim();
    apiPost(`/api/claims/${f.dataset.id}/decide`, {by:liveName(f), decision:d, reason})
      .then(() => { LF.dec = null; LF.ferr = ''; LF.msg = {approved:'Claim approved: the item counts for the family from the next Update.', returned:'Claim returned with your note.', withdrawn:'Claim withdrawn.', released:'Claim released: the item goes back to Lost and found at the next Update.'}[d]; lfLoad(true); })
      .catch(err => { LF.ferr = err.message; S.keepScroll = true; render(); });
  }
});
