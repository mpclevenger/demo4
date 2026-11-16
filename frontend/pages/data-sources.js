/* Data sources (Tech Risk): the files for the month and uploading them. */
"use strict";
const inShort = iso => fd(iso).replace(/ \d{4}$/, '');
const inProvs = f => f.provider.split(' / ');      // "Arch / ITDR" is two providers; HR and Tech Risk send no submission of their own

function inAccAll(pid){      // files received for a month, by feed (from the server)
  {return liveAcc(pid);}
}
function inCodes(f){      // metric codes a feed feeds: listed ones, and ones covered by a range such as "RE-01 to RE-03"
  const ex = new Set(), rg = new Set(), rest = (f.feeds_metrics || '').replace(/([A-Z]{2})-(\d{2}) to \1-(\d{2})/g, (m, L, a, b) => { for (let i = +a; i <= +b; i++) rg.add(L + '-' + String(i).padStart(2, '0')); return ''; });
  (rest.match(/[A-Z]{2}-\d{2}/g) || []).forEach(c => ex.add(c)); return {ex, rg};
}
function inNotes(pid){      // the provider's "checks needing attention" -> one short line on the input row they belong to (each file's own notes)
  const out = {};
  D.periods[pid].submissions.filter(s => s.status === 'Accepted' && s.warnings.length).forEach(s => {
    if (s.feed) { (out[s.feed] = out[s.feed] || []).push(...s.warnings.map(w => `${w.rule}: ${w.detail}`)); return; }      // live: the file's own notes
    const mine = LAYOUTS.filter(f => inProvs(f).includes(s.provider));
    s.warnings.forEach(w => { const codes = w.detail.match(/[A-Z]{2}-\d{2}/g) || [];
      const hit = mine.find(f => codes.some(c => inCodes(f).ex.has(c))) || mine.find(f => codes.some(c => inCodes(f).rg.has(c))) || mine[0];
      if (hit) (out[hit.id] = out[hit.id] || []).push(`${w.rule}: ${w.detail}`); });
  });
  return out;
}
function inStatus(f){      // -> {chip, sub, ok}
  const pid = S.p, a = inAccAll(pid)[f.id], r = (IN.rep[pid] || {})[f.id], j = (IN.rej[pid] || {})[f.id];
  if (a) {
    const txt = `Received ${inShort(a.when)}`;
    return {ok:true, chip:chip(a.late ? 'Amber' : 'Green', txt), sub:a.replaces ? `Re-uploaded by ${a.by} · replaces the file from ${inShort(a.replaces.when)}` : ''};
  }
  if (j) return {ok:false, chip:chip('Red', 'Rejected'), sub:'The last file did not pass the checks.'};
  return {ok:false, chip:chip('Red', 'Not received')};
}

const cV2Note = 'Jira and GitHub will be pulled automatically in v2.';
/* "What it feeds" as metric-name chips, like the Data dictionary; prose stays for the files that feed everything */
const cInFeeds = f => { const t = String(f.feeds_metrics || ''), c = inCodes(f), ids = [...c.ex, ...c.rg].sort();
  if (f.id === 'app_inventory') return esc(t.replace(/\s*\(.*\)\s*$/, ''));
  return ids.length && ids.every(id => met(id)) ? ids.map(metChip).join(' ') : esc(t); };
function inSection(){
  const locked = isLocked(), canUp = !locked && may('run_month'), mon = FULLMON[+S.p.slice(5) - 1], notes = inNotes(S.p), sts = LAYOUTS.map(inStatus);
  const fnd = P().files_needed || {needed:[], received:[], missing:[], optional_received:[]}, nOpt = (fnd.optional_received || []).length, nNeed = fnd.needed.length;
  const asm = LAYOUTS.filter(f => f.layout_assumed).map(f => f.name);
  const rows = LAYOUTS.map((f, i) => { const st = sts[i];
    const btn = !canUp ? '' : `<td class="noprint"><button type="button" class="sm" data-act="in-upload" data-f="${f.id}" aria-label="Upload ${esc(f.name)}">Upload</button></td>`;
    return `<tr data-f="${f.id}"><td><b>${esc(f.name)}</b></td><td>${bTeam(f.provider)}</td><td>${tagW(f.file)}</td><td>${cInFeeds(f)}</td><td>${st.chip}${st.sub ? `<div class="cap">${esc(st.sub)}</div>` : ''}${notes[f.id] ? `<div class="cap">Needs a look · ${esc(notes[f.id].join(' · '))}</div>` : ''}</td>${btn}</tr>`; }).join('');
  return `<p style="margin:0 0 8px"><b>${fnd.received.length} of ${nNeed} ${nNeed === 1 ? 'file' : 'files'} this month’s metrics need ${nNeed === 1 ? 'has' : 'have'} arrived</b>${nOpt ? `, ${plural(nOpt, 'optional file', 'optional files')} also received` : ''}${fnd.missing.length ? ` · Missing: ${fnd.missing.map(k => esc(feedTitle(k))).join(', ')}` : ''}</p>
  ${IN.msg ? `<div class="sr-only" role="status" id="inmsg" tabindex="-1">${esc(IN.msg)}</div>` : ''}
  <table class="dt inft"><caption class="sr-only">Input files for ${monthLabel(S.p)}</caption><colgroup><col style="width:17%"><col style="width:13%"><col style="width:10%"><col style="width:22%"><col style="width:${canUp ? 28 : 38}%">${canUp ? '<col style="width:10%">' : ''}</colgroup><thead><tr><th>Input file</th><th>Provider</th><th>File type</th><th>What it feeds</th><th>${mon}</th>${canUp ? '<th></th>' : ''}</tr></thead><tbody>${rows}</tbody></table>
  ${locked ? `<p class="cap" style="margin:6px 0 0">${mon} is locked. To change anything, reopen it with a reason on This month, then lock it again.</p>` : !canUp ? `<p class="cap" style="margin:6px 0 0">${esc(roSay())}</p>` : ''}
  ${asm.length ? `<p class="cap" style="margin:6px 0 0">Layout assumed for: ${asm.map(esc).join(', ')}. Their real file hasn’t been seen yet.</p>` : ''}
  <p class="cap" style="margin:6px 0 0">${cV2Note}</p>`;
}
function vInUpload(id){
  const f = inFeed(id), n = (f.columns || []).length;
  const lay = f.file === 'JSON' ? `A JSON report from Checkmarx${f.id === 'cx_sca' ? ' (same layout as the SAST report, with SCA policies)' : ''}.` : f.file === 'Excel' ? `${plural(n, 'column', 'columns')}, Excel (.xlsx)${f.id === 'itdr' ? ', header over rows 1 and 2' : ''}.` : f.file === 'CSV or JSON' ? `JSON (product_line, owner_email, optional band) or a CSV with the same ${plural(n, 'column', 'columns')}.` : `${plural(n, 'column', 'columns')}, CSV.`;
  return `<p style="margin:0 0 6px"><a href="${href('/datasources')}">← Back to input files</a></p>
  <h1>Upload ${esc(f.name)}</h1>
  <p style="margin:0">${bTeam(f.provider)} <span class="cap">${f.id === 'app_owner_members' || f.id === 'ntcc' ? esc(bFeedsText(f)) : 'Feeds ' + esc(bFeedsText(f))}</span></p>
  <p class="cap" style="margin:6px 0 10px">Expected layout: ${lay} ${f.layout_assumed ? tagW('Layout assumed, not yet confirmed') : ''}</p>
  ${(inFormLive(f))}`;
}

/* --- readers --- */

/* --- the checks: four layers, as in the intake design (file, rows, matching, totals) --- */

/* --- result display --- */

function dsTabs(cur){ return `<div class="subtabs" role="navigation" aria-label="Data sources"><a href="${href('/datasources')}" ${cur === 'files' ? 'aria-current="page"' : ''}>Input files</a><a href="${href('/datasources/systems')}" ${cur === 'systems' ? 'aria-current="page"' : ''}>Source systems</a></div>`; }
function vDataSources(arg){
  if (arg && arg.startsWith('upload-')) return vInUpload(arg.slice(7));
  if (arg !== 'systems') return `<h1>Data sources</h1>${dsTabs('files')}${inSection()}`;
  IN.msg = null;
  {return vSystemsLive();}
}
function vSystemsLive(){      // live: the input files TRUST reads, from the layouts; automated feeds are v2
  const rows = LAYOUTS.map(f => `<tr><td><b>${esc(f.name)}</b><div class="cap">${esc(f.file || '')}</div></td><td>${bTeam(f.provider)}</td><td>${esc(bFeedsText(f))}</td><td>${tagW('Upload')}</td><td>${f.layout_assumed ? tagW('Layout assumed') : 'From the real file'}</td></tr>`).join('');
  return `<h1>Data sources</h1>${dsTabs('systems')}
  <p class="muted" style="margin:0 0 8px;max-width:860px">The files our metrics come from. Tech Risk uploads each provider’s own export; whether this month’s files have arrived is on <a href="${href('/datasources')}">Input files</a>. ${cV2Note}</p>
  <div class="panel" style="overflow-x:auto"><table class="dt"><caption class="sr-only">Input files</caption><thead><tr><th>Input file</th><th>Provider</th><th>What it feeds</th><th>Method</th><th>Layout</th></tr></thead><tbody>${rows}</tbody></table></div>
  <p class="cap">Layout assumed: no real file has arrived yet, so the column names are a best guess until it does.</p>`;
}
