/* This month (Tech Risk): update, warnings, lock and reopen, queries and activity. */
"use strict";
function vConsoleLive(){
  const p = P(), pid = S.p, st = LIVE.state[pid] || {feeds:{}, events:[]}, locked = isLocked(), mon = monthLabel(pid);
  liveLoad(pid);
  const nrec = Object.keys(st.feeds || {}).length, seal = p.seal || (st.status || {}).seal;
  const wsAll = st.warnings || [], ws = wsAll.filter(w => !w.info), wInfo = wsAll.filter(w => w.info), wopen = ws.filter(w => !w.ack), wfeeds = [...new Set(ws.map(w => w.feed))];   // A5: info warnings are listed apart and never block the lock
  const RW = may('run_month');
  const lockSec = !RW && !locked ? `<section id="lock-record" tabindex="-1"><h2>Lock ${esc(mon)}</h2><p>${esc(mon)} is not locked yet.</p></section>`
    : locked
    ? `<section id="lock-record" tabindex="-1"><h2>Lock record</h2>
       <p><b>${esc(mon)} is locked</b> — by ${esc(p.meta.locked_by)}, ${fd(p.meta.locked_at)}. Uploads and updates for this month are refused until it is reopened. Comments are still taken, marked “received after lock”; they never change the figures.</p>
       ${seal ? `<table class="dt nosort"><caption class="sr-only">What the lock sealed</caption><thead><tr><th>Sealed</th><th>Fingerprint (SHA-256, first 12 characters)</th></tr></thead><tbody>
         <tr><td>Scored result</td><td><code>${esc(String(seal.scored_sha256).slice(0, 12))}…</code></td></tr>
         <tr><td>Mapped result</td><td><code>${esc(String(seal.mapped_sha256).slice(0, 12))}…</code></td></tr>
         ${(seal.files || []).map(x => `<tr><td>${esc(x.file || x.feed)} <span class="cap">(${esc(x.feed)}, uploaded by ${esc(x.uploaded_by || '')})</span></td><td><code>${esc(String(x.original_sha256 || '').slice(0, 12))}…</code></td></tr>`).join('')}
         <tr><td>Settings, tolerance thresholds and column names</td><td><code>${esc(String(seal.settings_sha256).slice(0, 12))}…</code></td></tr>
         <tr><td>Comments (${plural(seal.comments || 0, 'comment', 'comments')} at the lock)</td><td><code>${esc(String(seal.comments_sha256).slice(0, 12))}…</code></td></tr>
         <tr><td>Code version (git commit)</td><td><code>${esc(String(seal.git_sha || 'not known').slice(0, 12))}</code></td></tr></tbody></table>` : ''}
       ${RW ? `<h3>Reopen ${esc(mon)}</h3>
       <p class="cap">Reopening lets files be uploaded and the scorecard updated again; lock it again when done. The reason and the earlier seal stay in the record.</p>
       <label for="lvreason"><b>Why is it being reopened?</b></label><textarea id="lvreason" maxlength="500"></textarea>
       <div class="btns"><button type="button" data-act="lv-reopen" ${LIVE.busy ? 'disabled' : ''}>Reopen ${esc(mon)}</button></div>` : ''}</section>`
    : `<section id="lock-record" tabindex="-1"><h2>Lock ${esc(mon)}</h2>
       <p>Locking makes ${esc(mon)} official. It seals what people see now: the scored result, every file used, the settings and the comments so far, each by its fingerprint. After the lock, uploads and updates for ${esc(mon)} are refused until someone reopens it with a reason.</p>
       <p class="cap">The lock is done by hand for now. If a newer file arrived after the last update, the lock will ask you to update the scorecard first.${wopen.length ? ` <b>${wopen.length} ${wopen.length === 1 ? 'warning is' : 'warnings are'} still to acknowledge</b> (<button type="button" class="linkbtn" data-act="lv-towarn">see the list</button>).` : ''}</p>
       ${LIVE.confirmLock
         ? `<p><b>Lock ${esc(mon)} now?</b></p><div class="btns"><button class="pri" type="button" data-act="lv-lock-yes" ${LIVE.busy ? 'disabled' : ''}>Yes, lock ${esc(mon)}</button> <button type="button" data-act="lv-lock-no">Cancel</button></div>`
         : `<div class="btns"><button class="pri" type="button" data-act="lv-lock">Lock ${esc(mon)}…</button></div>`}</section>`;
  const wname = f => f === 'general' ? 'The month as a whole' : ((inFeed(f) || {}).name || f);
  const warnSec = `<h2 id="lvwarn">Warnings from the checks${wopen.length ? ` · ${wopen.length} to acknowledge` : ''}</h2>
  <p class="cap">Read each warning and acknowledge it; the lock needs every one acknowledged.${RW ? '' : ' Acknowledging them is Tech Risk’s part.'}</p>
  ${!ws.length ? '<p class="cap">No warnings to acknowledge for this month.</p>' : ''}
  ${RW && !locked && wopen.length ? `<label for="lvackwhy">Why it's acceptable (optional; recorded with each acknowledgement)</label><input id="lvackwhy" maxlength="500" style="display:block;width:100%;max-width:640px;margin:4px 0 8px">` : ''}
  ${wfeeds.map(f => { const its = ws.filter(w => w.feed === f), op = its.filter(w => !w.ack);
    return `<h3>${esc(wname(f))}${op.length ? ` <span class="cap">· ${op.length} to acknowledge</span>` : ' <span class="cap">· all acknowledged</span>'}</h3>
    <ul class="cnl">${its.map(w => `<li>${esc(niceNote(w.note))} ${w.ack ? `<span class="cap">✓ acknowledged by ${esc(w.ack.by)}, ${when(w.ack.at)}${w.ack.reason ? ` — ${esc(w.ack.reason)}` : ''}</span>` : locked || !RW ? '' : `<button type="button" class="sm" data-act="lv-ack" data-k="${esc(w.key)}">Acknowledge</button>`}</li>`).join('')}</ul>
    ${RW && !locked && op.length > 1 ? `<div class="btns"><button type="button" class="sm" data-act="lv-ack-feed" data-f="${esc(f)}">Acknowledge all ${op.length} for ${esc(wname(f))}</button></div>` : ''}`; }).join('')}
  ${wInfo.length ? `<h3 id="lvinfo">For information (no acknowledgement needed)</h3><ul class="cnl cap">${wInfo.map(w => `<li>${esc(wname(w.feed))}: ${esc(niceNote(w.note))}</li>`).join('')}</ul>` : ''}`;
  const th = lvThreads(pid).filter(x => x.status !== 'closed');
  const inbox = th.length ? `<ul class="cnl">${th.map(x => `<li><b>${esc(fam(x.t.family) ? fam(x.t.family).name : x.t.family)}</b>${x.t.metric ? ` · ${esc(x.t.metric)}` : ''} · ${x.t.kind === 'query' ? 'Data query' : 'Action'} from ${esc(x.t.by)} (${fd(String(x.t.at).slice(0, 10))}, ${esc(x.status)}): ${esc(x.t.text)}
      ${x.rs.map(r => `<div class="cap">↳ ${esc(r.by)}: ${esc(r.text)} (${esc(r.status || '')})</div>`).join('')}
      ${may('reply', x.t.family) ? `<div class="lvrep"><label class="sr-only" for="lvr-${x.t.id}">Reply</label><input id="lvr-${x.t.id}" placeholder="Reply" maxlength="600">
      <select id="lvs-${x.t.id}" aria-label="Status after this reply"><option value="answered">Answered</option><option value="open">Still open</option>${may('close') ? '<option value="closed">Closed</option>' : ''}</select>
      <button type="button" class="sm" data-act="lv-reply" data-id="${x.t.id}" data-f="${esc(x.t.family)}">Send</button></div>` : ''}</li>`).join('')}</ul>`
    : '<p class="cap">No open data queries or actions this month.</p>';
  const ev = (st.events || []).map(e => `<li><span class="cap">${when(e.at)}</span> ${esc(e.by)}: ${esc(e.action === 'upload' && e.detail && e.detail.refused ? 'tried to upload a file TRUST refused' : ({upload:'uploaded', map:'mapped', score:'scored', publish:'published', lock:'locked the month', reopen:'reopened the month', comment:'commented', acknowledge:'acknowledged warnings', 'update started':'started updating the scorecard', 'update finished':'finished updating the scorecard', 'update failed':'update stopped with a problem'}[e.action] || e.action))}${e.note ? ` — ${esc(niceNote(e.note))}` : ''}</li>`).join('');
  return `<div class="cn"><h1>This month</h1>${subtabs('console')}
  <div class="cnhead"><p style="margin:0"><b>${RW ? 'Update the scorecard, then lock the month when it\'s right.' : 'Where this month stands.'}</b></p>
  ${ME ? `<p class="cnas noprint cap">Signed in as ${esc(ME.name)} (${esc(ME.role_names.join(', '))}). This is recorded on what you do.</p>` : `<p class="cnas noprint"><label for="liveby" class="cap">Your name (recorded on what you do)</label> <input id="liveby" value="${esc(LIVE.by)}" autocomplete="name" maxlength="100"></p>`}</div>
  ${cnMonths()}
  ${liveMsgHTML()}
  <h2>Files for ${esc(mon)}</h2>
  ${(() => { const fn = p.files_needed || {needed:[], received:[], missing:[], optional_received:[]}, nn = (fn.needed || []).length, got = (fn.received || []).length, opt = (fn.optional_received || []).length, miss = fn.missing || [];
    return `<p>${got} of ${plural(nn, 'file', 'files')} this month’s metrics need ${got === 1 ? 'has' : 'have'} arrived${opt ? `; ${plural(opt, 'optional file', 'optional files')} also received` : ''}.${miss.length ? ` Missing: ${esc(miss.map(feedLbl).join(', '))}.` : ''} <a href="${href('/datasources')}">${RW ? 'See and upload them' : 'See them'} on Data sources</a>.</p>`; })()}
  ${RW ? `<h2>Update the scorecard</h2>
  <p class="cap">Reads the newest file of every feed, places every row, scores and publishes. Run it after uploading.</p>
  ${locked ? `<p class="cap">${esc(mon)} is locked, so it can't be updated until it is reopened (below). You can still update another month.</p>` : ''}
  <div class="btns"><label class="sr-only" for="lvmonth">Month to update</label><input type="month" id="lvmonth" value="${pid}"> <button class="pri" type="button" data-act="lv-update" ${LIVE.busy ? 'disabled' : ''}>${LIVE.busy ? 'Working…' : 'Update the scorecard'}</button></div>` : `<p class="cap">${esc(roSay())}</p>`}
  ${warnSec}
  ${lockSec}
  <h2>Open data queries and actions</h2>${inbox}
  <h2>Recent activity</h2>${ev ? `<ul class="cnl cnlog">${ev}</ul>` : '<p class="cap">Nothing yet this month.</p>'}</div>`;
}
function liveAct(a, b){
  const by = liveName();
  const need = () => { if (!by) { liveSay(false, 'Type your name first (at the top of this page), so the record shows who did this.'); S.keepScroll = true; render(); liveFocusMsg(); return false; } return true; };
  if (a === 'lv-lock') { LIVE.confirmLock = true; S.keepScroll = true; render(); const y = document.querySelector('[data-act=lv-lock-yes]'); if (y) y.focus(); return; }
  if (a === 'lv-towarn') { const h = document.getElementById('lvwarn'); if (h) { h.setAttribute('tabindex', '-1'); h.scrollIntoView(); h.focus({preventScroll:true}); } return; }
  if (a === 'lv-lock-no') { LIVE.confirmLock = false; S.keepScroll = true; render(); return; }
  if (!need()) return;
  if (a === 'lv-update') { const m = document.getElementById('lvmonth').value;
    // The update runs in the background on the server (owner, 4 Nov 2026), so it never hits the platform's time limit; ask how it is going every few seconds.
    return liveRun(async () => {
      let s = await apiPost('/api/update', {month:m, by}); const t0 = Date.now(), secs = n => `${n} ${n === 1 ? 'second' : 'seconds'}`;
      while (s.state === 'running') {
        const n = Math.round((Date.now() - t0) / 1000);
        liveSay(true, `Updating ${monthLabel(m)}… ${n >= 5 ? secs(n) + ' so far. ' : ''}This can take a few minutes. Keep this page open.`); S.keepScroll = true; render();
        await new Promise(res => setTimeout(res, 3000));
        try { s = await api(`/api/update/${encodeURIComponent(m)}/${encodeURIComponent(s.job)}`); }
        catch (e) { if (Date.now() - t0 > 30 * 60 * 1000) throw e; }          // a network blip: ask again
      }
      if (s.state !== 'finished') throw new Error(s.message || 'The update didn’t finish. Press Update the scorecard again.');
      liveSay(true, `${monthLabel(m)} updated and published${s.seconds ? ` in ${secs(s.seconds)}` : ''}. Reloading to show it…`); setTimeout(() => location.reload(), 900);
    }); }
  if (a === 'lv-lock-yes') { LIVE.confirmLock = false;
    return liveRun(async () => { await apiPost('/api/lock', {month:S.p, by}); liveSay(true, `${monthLabel(S.p)} is locked. Reloading to show it…`); setTimeout(() => location.reload(), 900); }); }
  if (a === 'lv-reopen') { const reason = document.getElementById('lvreason').value;
    return liveRun(async () => { await apiPost('/api/reopen', {month:S.p, by, reason}); liveSay(true, `${monthLabel(S.p)} is open again. Reloading…`); setTimeout(() => location.reload(), 900); }); }
  if (a === 'lv-ack' || a === 'lv-ack-feed') {
    const ws = (LIVE.state[S.p] || {}).warnings || [], why = (document.getElementById('lvackwhy') || {}).value || '';
    const keys = a === 'lv-ack' ? [b.dataset.k] : ws.filter(w => !w.ack && !w.info && w.feed === b.dataset.f).map(w => w.key);
    return liveRun(async () => { const r = await apiPost('/api/acknowledge', {month:S.p, by, keys, reason:why}); liveSay(true, `Acknowledged ${r.acknowledged} ${r.acknowledged === 1 ? 'warning' : 'warnings'}.`); await liveLoad(S.p, true); }); }
  if (a === 'lv-reply') { const id = +b.dataset.id, t = document.getElementById('lvr-' + id).value, s = document.getElementById('lvs-' + id).value;
    return liveComment({by, family:b.dataset.f, reply_to:id, text:t, status:s}); }
}
/* ---------- Tech Risk console (D-78): what stands between this month and a defensible lock ---------- */
/* mode: auto = the system decides; person = someone ticks it; atlock = the lock run checks it when the month is signed. never = cannot be waived. */

const CN = {s:{}};                           // per-month state for This month
const cn = () => CN.s[S.p] || (CN.s[S.p] = {ticks:{}, waived:{}, acks:{}, closed:{}, read:{}, appr:{}, prepared:null, signed:null, waiving:null, log:[], reminded:{}});
const isLocked = () => P().meta.status !== 'Preview';

function cnMonths(){
  return `<ul class="cnstrip" aria-label="Months">${Object.values(D.periods).map(x => { const m = x.meta, on = m.id === S.p, lk = m.status !== 'Preview';
    return `<li><button type="button" data-act="cn-month" data-p="${m.id}" ${on ? 'aria-current="true"' : ''} class="${on ? 'on' : ''}"><b>${m.label}</b><span class="pchip ${lk ? 'lk' : 'pv'}">${lk ? 'Locked ' + fd(m.locked_at) : 'Preview'}</span></button></li>`; }).join('')}</ul>`;
}

function vConsole(){
  {return vConsoleLive();}
}
function lockLine(){
  const m = P().meta; if (m.status === 'Preview') return '';
  {return `<p class="lockline">Locked by ${esc(m.locked_by)}, ${fd(m.locked_at)}${isTR() ? ` · <a href="${href('/console/lock-record')}">Lock record</a>` : ''}</p>`;}
}
