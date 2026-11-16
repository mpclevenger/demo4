/* Talking to TRUST's back end: who is signed in and what they may do, loading and saving, uploads and comments. */
"use strict";
/* ---- Live data (owner, 3 Nov 2026): on the real site the page talks to TRUST's back end. ----
   Anyone who gets past the company's access add-on can upload, update, comment, lock and reopen; they
   type their name, which is recorded. The name is remembered in this browser only, for convenience. */
const LIVE = ({state:{}, comments:{}, msg:null, err:null, checks:null, busy:false, confirmLock:false,
  by:(() => { try { return localStorage.getItem('trust_by') || ''; } catch (e) { return ''; } })()});
const ME = (D.access) && D.access.enforced ? D.access.me : null;      // signed in through the add-on: roles come from the server
if (ME) { LIVE.by = ME.name; if (!ME.can.run_month || !(() => { try { return sessionStorage.getItem('trust_view'); } catch (_) { return null; } })()) S.r = ME.page_role; }   // Tech Risk keeps the View as role they chose across a refresh (owner, 9 Nov 2026)
const byField = st => ME ? `<input type="hidden" name="by" value="${esc(ME.name)}">` : `<label${st ? ` style="${st}"` : ''}>Your name<input name="by" value="${esc(LIVE.by)}" autocomplete="name" maxlength="100" required></label>`;
/* What this person may do (mirrors backend/trust/access.py `can`). Roles off (ME is null): everything, as before. */
const may = (action, fid) => {
  if (!ME) return true;
  const c = ME.can || {}, tr = !!c.run_month;
  if (action === 'run_month' || action === 'propose' || action === 'decide') return !!c[action];
  if (action === 'console_read') return !!c.console;
  if (action === 'close') return tr;
  if (action === 'download') return tr || (ME.roles || []).some(r => r !== 'family_lead' && r !== 'family_member') || (fid ? ME.lead_of.includes(fid) || ME.member_of.includes(fid) : ME.lead_of.length + ME.member_of.length > 0);   // owner, 9 Nov 2026: whoever can see it can export it
  if (action === 'reply') return tr || (fid ? ME.lead_of.includes(fid) : ME.lead_of.length > 0);
  if (action === 'comment') return tr || (fid ? ME.lead_of.includes(fid) || ME.member_of.includes(fid) : ME.lead_of.length + ME.member_of.length > 0);
  return false;
};
const canDl = fid => may('download', fid);
const roSay = () => !ME || may('run_month') ? '' : ME.read_only ? 'Read only: you can see everything here but not change it.' : 'You can read this page. Changes are made by Tech Risk.';
function liveSetBy(v){ LIVE.by = String(v || '').trim(); try { localStorage.setItem('trust_by', LIVE.by); } catch (e) {} }
function liveName(f){ const i = (f && f.querySelector('input[name=by]')) || document.getElementById('liveby'); if (i) liveSetBy(i.value); return LIVE.by; }
async function api(path, opts){
  const r = await fetch(path, opts); let j = {};
  try { j = await r.json(); } catch (e) {}
  if (!r.ok || j.ok === false) throw new Error(j.error || `Something went wrong (${r.status}). Nothing was changed.`);
  return j;
}
const apiPost = (path, body) => api(path, {method:'POST', headers:{'X-TRUST':'1', 'Content-Type':'application/json'}, body:JSON.stringify(body)});
const LV_KIND = {explanation:'explain', query:'query', action:'action'};
async function liveLoad(pid, force){
  if (((!force && LIVE.state[pid]))) return;
  LIVE.state[pid] = LIVE.state[pid] || {loading:true, feeds:{}, events:[], status:{status:'open'}};
  try {
    const [s, c] = await Promise.all([may('console_read') ? api('/api/month/' + pid) : Promise.resolve({feeds:{}, events:[], status:{status:'open'}}), api('/api/comments/' + pid)]);
    LIVE.state[pid] = s; LIVE.comments[pid] = c.comments;
    for (let i = COMMENTS.length - 1; i >= 0; i--) if (COMMENTS[i].p === pid) COMMENTS.splice(i, 1);
    c.comments.filter(x => !x.reply_to).forEach(x => COMMENTS.push({p:pid, fid:x.family, mid:x.metric, block:x.block,
      date:String(x.at).slice(0, 10), text:x.text, type:LV_KIND[x.kind] || 'explain', by:x.by, id:x.id, after_lock:x.after_lock}));
  } catch (e) { LIVE.state[pid] = {error:e.message, feeds:{}, events:[], status:{status:'open'}}; }
  S.keepScroll = true; render();
}
function liveAcc(pid){      // received files for a month, by feed, from the back end
  liveLoad(pid);
  const out = {};
  Object.entries((LIVE.state[pid] || {}).feeds || {}).forEach(([k, e]) => { out[k] = {feed:k, month:pid, hash:e.original_sha256 || '',
    by:e.uploaded_by, when:String(e.uploaded_at || '').slice(0, 10), live:true, uploads:e.uploads}; });
  return out;
}
/* After an upload: what the file's checks found, and what to do next. checks = the warnings; an empty list means all passed. */
function liveChecksHTML(){
  if (!LIVE.checks) return '';
  const count = LIVE.checks.length;
  const found = count
    ? ` <b>Checks: ${plural(count, 'thing', 'things')} to look at</b> (you'll acknowledge ${count === 1 ? 'it' : 'them'} before the lock):<ul class="cnl">${LIVE.checks.map(x => `<li>${esc(x)}</li>`).join('')}</ul>`
    : ' <b>Checks passed.</b> ';
  return `${found}When this month's files are in, choose <b>Update the scorecard</b> on <a href="${href('/console')}">This month</a>.`;
}
function liveMsgHTML(){
  return `<div id="lvmsg" role="status" aria-live="polite" tabindex="-1">${LIVE.err ? `<p class="lverr"><b>Not done.</b> ${esc(LIVE.err)}</p>` : LIVE.msg ? `<p class="lvok">${esc(LIVE.msg)}${liveChecksHTML()}</p>` : ''}</div>`;
}
/* Say what happened, in plain text (it is made safe for the page when shown). checks is only for the upload message. */
function liveSay(ok, text, checks){ LIVE.err = ok ? null : text; LIVE.msg = ok ? text : null; LIVE.checks = ok && checks ? checks : null; }
function liveFocusMsg(){ const m = document.getElementById('lvmsg'); if (m) m.focus({preventScroll:false}); }
async function liveRun(fn){      // one change at a time; say what happened in plain words
  if (LIVE.busy) return; LIVE.busy = true; LIVE.err = LIVE.msg = null; S.keepScroll = true; render();
  try { await fn(); } catch (e) { liveSay(false, e.message); }
  LIVE.busy = false; S.keepScroll = true; render(); liveFocusMsg();
}
function inFormLive(f){
  return `<form class="cf inf" data-kind="liveup" data-f="${f.id}" aria-label="Upload ${esc(f.name)}" novalidate>
    <label>File (${f.file === 'JSON' ? '.json' : f.file === 'Excel' ? '.xlsx or .csv' : f.file === 'CSV or JSON' ? '.json or .csv' : '.csv'})<input type="file" name="file" required accept="${f.file === 'JSON' ? '.json,application/json' : f.file === 'CSV or JSON' ? '.json,.csv,application/json,text/csv' : f.file === 'Excel' ? '.xlsx,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv' : '.csv,text/csv'}"></label>
    <label>Month the file is for<input type="month" name="month" value="${S.p}" required></label>
    ${byField()}
    <label>SharePoint link to the original (optional)<input type="url" name="link"></label>
    <p class="cap" style="margin:8px 0">TRUST keeps only the columns it uses from this file and records the file's fingerprint (SHA-256). Uploading doesn't change the scorecard: when the month's files are in, choose <b>Update the scorecard</b> on <a href="${href('/console')}">This month</a>.</p>
    <div class="btns"><button class="pri" type="submit" ${LIVE.busy ? 'disabled' : ''}>${LIVE.busy ? 'Uploading…' : 'Upload'}</button> <button type="button" data-act="in-cancel">Cancel</button></div>
    ${liveMsgHTML()}</form>`;
}
function liveUpload(f){
  const by = liveName(f), file = f.querySelector('input[name=file]').files[0], month = f.querySelector('input[name=month]').value;
  if (!file) { liveSay(false, 'Choose a file to upload.'); S.keepScroll = true; render(); liveFocusMsg(); return; }
  const fdat = new FormData(); fdat.append('feed', f.dataset.f); fdat.append('month', month); fdat.append('by', by);
  fdat.append('link', f.querySelector('input[name=link]').value); fdat.append('file', file);
  liveRun(async () => {
    const r = await api('/api/upload', {method:'POST', headers:{'X-TRUST':'1'}, body:fdat});
    const w = (r.checks && r.checks.warnings) || [];
    liveSay(true, `Uploaded for ${monthLabel(month)}: ${niceNote(r.note)}.`, w.map(niceNote));
    if (!D.periods[month]) {   // a month the list doesn't have yet: reload so it appears, and open on it (owner, 4 Nov 2026)
      try { sessionStorage.setItem('trust_open_month', month); } catch (e) {}
      location.reload(); return;
    }
    await liveLoad(month, true);
  });
}
function liveComment(body, done){
  if (!body.by) { liveSay(false, 'Type your name first, so the record shows who wrote this.'); S.keepScroll = true; render(); liveFocusMsg(); return; }
  liveRun(async () => { await apiPost('/api/comments', {month:S.p, ...body}); liveSay(true, 'Saved. It never changes a score.'); await liveLoad(S.p, true); if (done) done(); });
}
function lvThreads(pid){      // queries and actions with their replies; status = the latest row's
  const all = LIVE.comments[pid] || [], tops = all.filter(c => !c.reply_to && c.kind !== 'explanation');
  return tops.map(t => { const rs = all.filter(c => c.reply_to === t.id), last = rs.length ? rs[rs.length - 1] : t; return {t, rs, status:last.status || 'open'}; });
}
