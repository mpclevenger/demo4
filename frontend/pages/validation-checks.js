/* Validation checks (Tech Risk): is this month right and up to date. */
"use strict";
/* ---------- Tech Risk: auditor evidence ---------- */


/* Validation checks, live (owner, 4 Nov 2026): Tech Risk's own page for "is this month right and up to date?".
   Plain checklist, one files table, and the detail folded away. Everything comes from TRUST's records. */
/* Plain words for what the activity log records (an action not listed here is shown as it was logged). */
const ACTION_WORDS = {upload:'Uploaded a file', map:'Placed rows with L3 teams', score:'Worked out the scores', publish:'Published the scorecard',
  acknowledge:'Acknowledged a warning', 'update started':'Update started', 'update finished':'Update finished', 'update failed':'Update failed',
  comment:'Comment', download:'Download', view:'Viewed', decision:'Decision', proposal:'Proposal', contract:'Data contract', retention:'Cleared old months'};
function vAuditorLive(){
  const pid = S.p, st = LIVE.state[pid] || {feeds:{}}, p = P();
  liveLoad(pid);
  const pl = (n, one, many) => `${nfmt(n)} ${n === 1 ? one : many}`;
  const feedName = k => (inFeed(k) || {}).name || k, fp = h => h ? `<code class="hx">${esc(String(h).slice(0, 12))}</code>` : '<span class="muted">—</span>';
  const fileCounts = p.file_counts || {}, feeds = st.feeds || {}, subs = (p.submissions || []).filter(x => x.status === 'Accepted'), subOf = k => subs.find(x => x.feed === k);
  const ws = (st.warnings || []).filter(w => !w.info), open = ws.filter(w => !w.ack), run = st.runs && st.runs.scored;
  const fnd = p.files_needed || {needed:[], received:[], missing:[]}, needed = fnd.needed, missing = fnd.missing;
  const lastUp = Object.values(feeds).map(e => e.uploaded_at).filter(Boolean).sort().pop();
  const stale = !!(lastUp && run && run.at && new Date(lastUp) > new Date(run.at)), never = !run;
  const unm = subs.filter(x => x.unattributed_pct > 0).sort((x, y) => y.unattributed_pct - x.unattributed_pct);
  const measured = D.metrics.filter(m => m.scored && Object.values(p.families || {}).some(fr => fr.metrics[m.id] && SCORED.includes(fr.metrics[m.id].status) || (fr.metrics[m.id] && fr.metrics[m.id].value != null)));
  const noThr = measured.filter(m => !(p.thresholds || {})[m.id]), monthly = Object.values(p.thresholds || {}).filter(t => t.basis === 'Calibrated').length;
  /* what still needs doing for this month */
  const block = [never ? 'the scorecard hasn’t been updated yet' : stale ? 'a file arrived after the last update' : null, open.length ? `${pl(open.length, 'warning', 'warnings')} to acknowledge` : null].filter(Boolean);
  const head = block.length ? `<div class="vready no"><b>Still to do:</b> ${listOf(block)}.</div>` : `<div class="vready ok"><b>Up to date.</b> Everything the checks look for is in place.</div>`;
  /* tiles */
  const tile = (n, l, k) => `<div class="vt-${k}"><div class="vtn">${n}</div><div class="vtl">${l}</div></div>`;
  const tiles = `<div class="vtiles">${tile(`${needed.length - missing.length} of ${needed.length}`, needed.length === 1 ? 'file this month’s metrics need' : 'files this month’s metrics need', missing.length ? 'w' : 'g')}${tile(open.length, open.length === 1 ? 'warning to acknowledge' : 'warnings to acknowledge', open.length ? 'w' : 'g')}${tile(unm.length ? num1(unm[0].unattributed_pct) + '%' : '0%', unm.length ? `highest share not yet mapped (${esc(feedName(unm[0].feed))})` : 'not yet mapped', unm.length ? 'w' : 'g')}${tile(run ? fd(String(run.at).slice(0, 10)) : '—', run ? `last updated by ${esc(run.by || '')}` : 'not updated yet', stale || never ? 'w' : 'g')}</div>`;
  /* checklist */
  const go = (h, t) => `<a href="${href(h)}">${t}</a>`;
  const row = (ok, name, detail, act) => `<tr><td class="vst">${ok === true ? chip('Green', 'Done') : ok === false ? chip('Amber', 'To do') : chip('Info only', 'Note')}</td><td><b>${name}</b><div class="cap">${detail}</div></td><td class="vact">${act || ''}</td></tr>`;
  const checks = [
    row(!missing.length, 'Files received', missing.length ? `Missing: ${esc(listOf(missing.map(feedName)))}` : `All ${needed.length} ${needed.length === 1 ? 'file' : 'files'} the measured metrics need ${needed.length === 1 ? 'is' : 'are'} in.`, missing.length && may('run_month') ? go('/datasources', 'Upload on Data sources') : ''),
    row(!(stale || never), 'Scorecard up to date', never ? 'Nothing has been worked out for this month yet.' : stale ? `A file arrived ${when(lastUp)}, after the last update (${when(run.at)}).` : `Updated ${when(run.at)} by ${esc(run.by || '')}, after the newest file.`, (stale || never) && may('run_month') ? go('/console', 'Update on This month') : ''),
    row(!open.length, 'Warnings acknowledged', ws.length ? `${ws.length - open.length} of ${pl(ws.length, 'warning', 'warnings')} acknowledged.` : 'The checks raised no warnings.', open.length && may('run_month') ? go('/console', 'Acknowledge on This month') : ''),
    row(unm.length ? null : true, 'Rows placed with L3 teams', unm.length ? `Some rows couldn’t be placed with an L3 team: ${esc(listOf(unm.map(x => `${feedName(x.feed)} ${num1(x.unattributed_pct)}%`)))}. They count in firm totals, not in any L3 team.` : 'Every row was placed with an L3 team.', unm.length ? go('/firm', 'What’s needed, on Firm position') : ''),
    row(noThr.length ? null : true, 'Tolerance thresholds in place', `${noThr.length ? `No tolerance threshold yet for ${esc(listOf(noThr.map(m => m.id)))} (too few L3 team results).` : `Every measured metric has one.`}${monthly ? ` ${pl(monthly, 'is', 'are')} worked out from this month’s results until Tech Risk calibrates them.` : ''}`, go('/dictionary/table', 'See the table'))];
  const ckTable = `<table class="dt vck"><caption class="sr-only">Readiness checks</caption><colgroup><col style="width:92px"><col><col style="width:220px"></colgroup><tbody>${checks.join('')}</tbody></table>`;
  /* files */
  const keys = [...new Set([...needed, ...Object.keys(feeds)])];
  const frows = keys.map(k => { const e = feeds[k], sb = subOf(k), w = ws.filter(x => x.feed === k), wo = w.filter(x => !x.ack).length;
    if (!e) return `<tr class="vmiss"><td><b>${esc(feedName(k))}</b></td><td colspan="5" class="muted" data-sv="">Not received</td></tr>`;
    return `<tr><td><b>${esc(feedName(k))}</b><div class="cap">${esc(e.original_name || '')}</div></td><td data-sv="${esc(e.uploaded_at || '')}">${esc(e.uploaded_by || '')}<div class="cap">${when(e.uploaded_at)}${e.uploads > 1 ? ` · ${e.uploads} uploads, newest used` : ''}</div></td><td class="tn">${fileCounts[k] && fileCounts[k].rows != null ? nfmt(fileCounts[k].rows) : '—'}</td><td class="tn">${fileCounts[k] && fileCounts[k].unattributed_pct != null ? num1(fileCounts[k].unattributed_pct) + '%' : '—'}</td><td class="tn" data-sv="${wo}">${w.length ? (wo ? `${wo} open` : 'All acknowledged') : 'None'}</td><td>${fp(e.original_sha256)}</td></tr>`; }).join('');
  const fTable = `<table class="dt vfiles"><caption class="sr-only">Files for ${esc(monthLabel(pid))}</caption><thead><tr><th>File</th><th>Received</th><th class="tn">Rows</th><th class="tn">Not yet mapped</th><th class="tn">Warnings</th><th>Fingerprint</th></tr></thead><tbody>${frows}</tbody></table>`;
  /* folded detail */
  const det = (t, body) => `<details class="vdet" open><summary>${t}</summary><div>${body}</div></details>`;
  const thr = Object.entries(p.thresholds || {}).map(([id, t]) => { const m = met(id); return m ? `<tr><td><b>${id}</b> ${esc(m.name)}</td><td>${tagW(basisName(t))}</td><td class="tn">${gTxt(m, t)}</td><td class="tn">${rTxt(m, t)}</td><td class="cap">${esc(t.reason || '')}</td></tr>` : ''; }).join('');
  const dl = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
  const runRec = `<dl class="dd audrun">${run ? dl('Last update', `${esc(run.by || '')}, ${when(run.at)}`) + dl('Code version', run.git_sha ? fp(run.git_sha) : '<span class="muted">Not recorded</span>') + dl('Settings fingerprint', fp(run.settings_sha256)) : dl('Last update', 'Not updated yet')}</dl>`;
  const ev = (st.events || []).map(e => `<tr><td class="nw" data-sv="${esc(e.at || '')}">${when(e.at)}</td><td>${esc(e.by)}</td><td>${esc(ACTION_WORDS[e.action] || e.action)}${e.note ? ` · <span class="muted">${esc(niceNote(e.note))}</span>` : ''}</td></tr>`).join('');
  const folded = det(`Tolerance thresholds used (${Object.keys(p.thresholds || {}).length})`, thr ? `<table class="dt"><thead><tr><th>Metric</th><th>Basis</th><th class="tn">Green tolerance</th><th class="tn">Red limit</th><th>How it was set</th></tr></thead><tbody>${thr}</tbody></table>` : '<p class="cap">None yet.</p>')
    + det('Calculation record', runRec)
    + det('Recent activity', ev ? `<table class="dt"><thead><tr><th>When</th><th>Who</th><th>What</th></tr></thead><tbody>${ev}</tbody></table><p class="cap">The newest 30 entries; nothing in the log is ever edited.</p>` : '<p class="cap">Nothing recorded yet.</p>');
  return `<div class="titlebar"><div><h1>Validation checks · ${esc(monthLabel(pid))}</h1>
    <p class="muted" style="margin:0;max-width:860px">Is this month right, and up to date? Everything here comes from TRUST’s own records.</p></div></div>
    ${head}${tiles}<h2 class="vh">Checks</h2>${ckTable}<h2 class="vh">Files</h2>${fTable}<p class="cap">Fingerprint: the first 12 characters of each file’s SHA-256, taken when it arrived. TRUST keeps a copy of every file as received. Rows: the rows TRUST kept from the file. Not yet mapped: the share of those rows not placed with an L3 team. A dash (—) means the file doesn’t place rows with L3 teams, or isn’t here yet.</p>
    <div class="vfold">${folded}</div>`;
}
function vAuditor(){
  {return vAuditorLive();}
}
