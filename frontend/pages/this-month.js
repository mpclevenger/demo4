/* This month (Tech Risk): update, warnings, queries and activity. There is no month lock (owner, 17 Nov 2026). */
"use strict";
function vConsoleLive(){
  const p = P(), pid = S.p, st = LIVE.state[pid] || {feeds:{}, events:[]}, mon = monthLabel(pid);
  liveLoad(pid);
  const nrec = Object.keys(st.feeds || {}).length;
  const wsAll = st.warnings || [], ws = wsAll.filter(w => !w.info), wInfo = wsAll.filter(w => w.info), wopen = ws.filter(w => !w.ack), wfeeds = [...new Set(ws.map(w => w.feed))];   // info warnings are listed apart and never need acknowledging
  const RW = may('run_month');
  const wname = f => f === 'general' ? 'The month as a whole' : ((inFeed(f) || {}).name || f);
  const warnSec = `<h2 id="lvwarn">Warnings from the checks${wopen.length ? ` · ${wopen.length} to acknowledge` : ''}</h2>
  <p class="cap">Read each warning and acknowledge it to show it has been seen. Warnings never stop an upload or an update.${RW ? '' : ' Acknowledging them is Tech Risk’s part.'}</p>
  ${!ws.length ? '<p class="cap">No warnings to acknowledge for this month.</p>' : ''}
  ${RW && wopen.length ? `<label for="lvackwhy">Why it's acceptable (optional; recorded with each acknowledgement)</label><input id="lvackwhy" maxlength="500" style="display:block;width:100%;max-width:640px;margin:4px 0 8px">` : ''}
  ${wfeeds.map(f => { const its = ws.filter(w => w.feed === f), op = its.filter(w => !w.ack);
    return `<h3>${esc(wname(f))}${op.length ? ` <span class="cap">· ${op.length} to acknowledge</span>` : ' <span class="cap">· all acknowledged</span>'}</h3>
    <ul class="cnl">${its.map(w => `<li>${esc(niceNote(w.note))} ${w.ack ? `<span class="cap">✓ acknowledged by ${esc(w.ack.by)}, ${when(w.ack.at)}${w.ack.reason ? ` — ${esc(w.ack.reason)}` : ''}</span>` : !RW ? '' : `<button type="button" class="sm" data-act="lv-ack" data-k="${esc(w.key)}">Acknowledge</button>`}</li>`).join('')}</ul>
    ${RW && op.length > 1 ? `<div class="btns"><button type="button" class="sm" data-act="lv-ack-feed" data-f="${esc(f)}">Acknowledge all ${op.length} for ${esc(wname(f))}</button></div>` : ''}`; }).join('')}
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
  <div class="cnhead"><p style="margin:0"><b>${RW ? 'Update the scorecard whenever new files arrive.' : 'Where this month stands.'}</b></p>
  ${ME ? `<p class="cnas noprint cap">Signed in as ${esc(ME.name)} (${esc(ME.role_names.join(', '))}). This is recorded on what you do.</p>` : `<p class="cnas noprint"><label for="liveby" class="cap">Your name (recorded on what you do)</label> <input id="liveby" value="${esc(LIVE.by)}" autocomplete="name" maxlength="100"></p>`}</div>
  ${cnMonths()}
  ${liveMsgHTML()}
  <h2>Files for ${esc(mon)}</h2>
  ${(() => { const fn = p.files_needed || {needed:[], received:[], missing:[], optional_received:[]}, nn = (fn.needed || []).length, got = (fn.received || []).length, opt = (fn.optional_received || []).length, miss = fn.missing || [];
    return `<p>${got} of ${plural(nn, 'file', 'files')} this month’s metrics need ${got === 1 ? 'has' : 'have'} arrived${opt ? `; ${plural(opt, 'optional file', 'optional files')} also received` : ''}.${miss.length ? ` Missing: ${esc(miss.map(feedLbl).join(', '))}.` : ''} <a href="${href('/datasources')}">${RW ? 'See and upload them' : 'See them'} on Data sources</a>.</p>`; })()}
  ${RW ? `<h2>Update the scorecard</h2>
  <p class="cap">Reads the newest file of every feed, places every row, scores and publishes. Run it after uploading.</p>
  <div class="btns"><label class="sr-only" for="lvmonth">Month to update</label><input type="month" id="lvmonth" value="${pid}"> <button class="pri" type="button" data-act="lv-update" ${LIVE.busy ? 'disabled' : ''}>${LIVE.busy ? 'Working…' : 'Update the scorecard'}</button></div>` : `<p class="cap">${esc(roSay())}</p>`}
  ${warnSec}
  <h2>Open data queries and actions</h2>${inbox}
  <h2>Recent activity</h2>${ev ? `<ul class="cnl cnlog">${ev}</ul>` : '<p class="cap">Nothing yet this month.</p>'}</div>`;
}
function liveAct(a, b){
  const by = liveName();
  const need = () => { if (!by) { liveSay(false, 'Type your name first (at the top of this page), so the record shows who did this.'); S.keepScroll = true; render(); liveFocusMsg(); return false; } return true; };
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
  if (a === 'lv-ack' || a === 'lv-ack-feed') {
    const ws = (LIVE.state[S.p] || {}).warnings || [], why = (document.getElementById('lvackwhy') || {}).value || '';
    const keys = a === 'lv-ack' ? [b.dataset.k] : ws.filter(w => !w.ack && !w.info && w.feed === b.dataset.f).map(w => w.key);
    return liveRun(async () => { const r = await apiPost('/api/acknowledge', {month:S.p, by, keys, reason:why}); liveSay(true, `Acknowledged ${r.acknowledged} ${r.acknowledged === 1 ? 'warning' : 'warnings'}.`); await liveLoad(S.p, true); }); }
  if (a === 'lv-reply') { const id = +b.dataset.id, t = document.getElementById('lvr-' + id).value, s = document.getElementById('lvs-' + id).value;
    return liveComment({by, family:b.dataset.f, reply_to:id, text:t, status:s}); }
}
/* ---------- Tech Risk console ---------- */

const CN = {s:{}};                           // per-month state for This month
const cn = () => CN.s[S.p] || (CN.s[S.p] = {ticks:{}, waived:{}, acks:{}, closed:{}, read:{}, appr:{}, prepared:null, signed:null, waiving:null, log:[], reminded:{}});

function cnMonths(){
  return `<ul class="cnstrip" aria-label="Months">${Object.values(D.periods).map(x => { const m = x.meta, on = m.id === S.p;
    return `<li><button type="button" data-act="cn-month" data-p="${m.id}" ${on ? 'aria-current="true"' : ''} class="${on ? 'on' : ''}"><b>${m.label}</b></button></li>`; }).join('')}</ul>`;
}

function vConsole(){
  {return vConsoleLive();}
}
