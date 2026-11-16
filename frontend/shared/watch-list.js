/* The watch list: what needs attention this month, and why. */
"use strict";
/* ---------- watch list ---------- */
/* Where the watch list's sums come from. */
const MS_PER_DAY = 24 * 60 * 60 * 1000;
const MS_PER_MONTH = 2629800000;        // an average month: 30.4375 days
const EXPIRY_WARNING_MONTHS = 6;         // an accepted risk shows on the watch list when it ends within this many months
const WATCH_NAMES_SHOWN = 3;             // a watch list line names this many families, then counts the rest
const bLimitWords = (m, t) => !m.higher_is_better && wholeUnit(m) ? `Red at ${Math.floor(t.red + 1e-9) + 1} or more` : `limit ${fv(m, t.red)}`;   // counts are whole numbers, as on the family page
function buildWatch(){
  const p = P(), s1 = [], s2 = [], s3 = [], used = new Set(), last = p.meta.last_day;
  const mr = (f, m) => p.families[f].metrics[m];
  const lim = (id, x) => isPF(met(id)) ? `${countText(met(id), x)}${x.t01_unmet ? ` · ${x.t01_unmet} on ${x.t01_unmet === 1 ? 'a Tier 0/1 app' : 'Tier 0/1 apps'}` : ''}` : `${fv(met(id), x.value)}${p.thresholds[id] ? ` (${bLimitWords(met(id), p.thresholds[id])})` : ''}`;
  let K = '';
  const add = (arr, fid, mid, who, line2, cv, st, head) => arr.push({fid, mid, who, line2, cv, st: st || (fid && mid && mr(fid, mid) ? mr(fid, mid).status : null), head: head || null, kind:K});
  const seenDecl = new Set();
  for (const w of p.watch_list) {
    K = w.kind;
    const f = w.family_id, id = w.metric_id;
    if (w.kind === 'Override red') { const x = mr(f, id); used.add(f + id);
      add(s1, f, id, fam(f).name, `${RULE_TEXT[id] ? `${RULE_TEXT[id].phrase} — ${fv(met(id), x.value)} ${RULE_TEXT[id].of}${p.thresholds[id] ? ` (${bLimitWords(met(id), p.thresholds[id])})` : ''}` : `Automatic Red rule: ${RULE[met(id).override_rule]} · ${lim(id, x)}`}${x.provisional ? ` · ${monthOf(x.carried_from)} result reused` : ''}`, cover(f, id), x.status); }
    else if (w.kind === 'New red') { const x = mr(f, id); used.add(f + id);
      add(s1, f, id, fam(f).name, `${lim(id, x)} · was ${stInfo(x.prior_status)[2]} in ${priorName()}`, cover(f, id), x.status); }
    else if (w.kind === 'Chronic red') { const x = mr(f, id); used.add(f + id);
      add(s2, f, id, fam(f).name, `${lim(id, x)} · Chronic Red, ${streak(x.history)} months in a row`, cover(f, id), x.status); }
    else if (w.kind === 'Sharp drop') { const fr = p.families[f];
      add(s2, f, null, fam(f).name, `Now ${fr.trust} · ${whyDrop(f)}`, null, null, `TRUST fell ${Math.abs(fr.delta)} points`); }
    else if (w.kind === 'Declining' && !seenDecl.has(f)) { seenDecl.add(f); const fr = p.families[f];
      add(s2, f, null, fam(f).name, whyDeclining(f), null, null, `${fr.declining.map(c => BLK(c).name).join(' and ')} fell two months in a row`); }
    else if (w.kind === 'Overdue action') { const e = D.entries.find(e => e.kind === 'Action' && e.family_id === f && e.metric_id === id && e.status !== 'Done' && e.due < last);
      if (e) add(s2, f, id, fam(f).name, `Action due ${fd(e.due)} · ${Math.round((new Date(last) - new Date(e.due)) / MS_PER_DAY)} days overdue · ${e.owner}`, null); }
  }
  if (!PRIOR[S.p]) { K = 'Red now';   // first month scored: nothing is "new" or "chronic" yet, so list every Red metric (owner review, 5 Nov 2026)
    D.families.forEach(f0 => D.metrics.forEach(m0 => { const x = p.families[f0.id] && p.families[f0.id].metrics[m0.id];
      if (x && x.status === 'Red' && !used.has(f0.id + m0.id)) { used.add(f0.id + m0.id); add(s1, f0.id, m0.id, f0.name, `${lim(m0.id, x)}`, cover(f0.id, m0.id), x.status); } })); }
  K = 'risk'; D.entries.filter(e => e.kind === 'Accepted risk' && e.status === 'Approved' && e.period <= S.p && e.due >= last).forEach(e => {
    const monthsLeft = Math.round((new Date(e.due) - new Date(last)) / MS_PER_MONTH);
    if (monthsLeft <= EXPIRY_WARNING_MONTHS) add(s3, e.family_id, e.metric_id, fam(e.family_id).name, `Expires ${fd(e.due)} · renewal or remediation decision needed`, {k:'ok', t:`Risk accepted until ${fd(e.due)}`}); });
  K = 'query'; D.entries.filter(e => e.kind === 'Data query' && e.status !== 'Done' && e.period <= S.p).forEach(e =>
    add(s3, e.family_id, e.metric_id, fam(e.family_id).name, `Needs a Tech Risk ruling · raised by ${e.owner}`, {k:'ok', t:'Data query open'}));
  lvThreads(S.p).filter(x => x.t.kind === 'query' && x.status !== 'closed' && p.families[x.t.family]).forEach(x =>   // live: families' data queries not yet closed (owner, 3 Nov 2026)
    add(s3, x.t.family, x.t.metric || null, fam(x.t.family).name, `Needs a Tech Risk ruling · raised by ${x.t.by}`, {k:'ok', t:'Data query open'}));
  K = 'Behind peers'; for (const w of p.watch_list) if (w.kind === 'Behind peers' && !used.has(w.family_id + w.metric_id)) {
    const x = mr(w.family_id, w.metric_id), id = w.metric_id;
    add(s3, w.family_id, id, fam(w.family_id).name, `${fv(met(id), x.value)} · typical ${fv(met(id), x.typical)}`, x.status === 'Red' ? cover(w.family_id, id) : null, x.status); }
  return [s1, s2, s3];
}

/* The top 10 on the CTO view are filled by importance (CTO review, 3 Nov 2026): leadership's asks, then newly Red,
   then chronic, then peer gaps; the sections are still shown in WORDER. */
function capWatchShown(secs0, limit = 10){
  const ask = secs0[2].filter(x => x.kind !== 'Behind peers'), peer = secs0[2].filter(x => x.kind === 'Behind peers');
  const keep = new Set(); let left = limit;
  [ask, secs0[0], secs0[1], peer].forEach(a => a.forEach(x => { if (left > 0) { keep.add(x); left--; } }));
  const secs = WORDER.map(k => secs0[k].filter(x => keep.has(x)));
  const rest = WORDER.flatMap(k => secs0[k].filter(x => !keep.has(x)));
  return {secs, hidden:rest.length, rest, restBy:WORDER.map(k => secs0[k].filter(x => !keep.has(x))), counts:WORDER.map(k => secs0[k].length)};
}
function coverTxt(cv){
  if (!cv) return '';
  const short = d => d.replace(/ \d{4}$/, '');
  const locked = P().meta.status === 'Locked';
  if (cv.k === 'none') return '';                          // owner 1 Nov: no text when the family has not commented
  if (/^(Family note on file|Explanation submitted)/.test(cv.t)) return '';   // comments show as the "Family says" bubble instead
  let t = cv.t, m;
  if ((m = /^Action owned by .* due (.*?)( \(overdue\))?$/.exec(t))) t = `Action owned · due ${short(m[1])}${m[2] || ''}`;
  else if ((m = /^Risk accepted until (.*)$/.exec(t))) t = `Risk accepted until ${short(m[1])}`;
  else if (/^Data query open/.test(t)) t = 'Data query open';
  return `<span class="wcv">${esc(t)}</span>`;
}
function liHTML(it, full){
  const who = it.fid && !full ? `<button type="button" class="bub-team wfam" data-act="go-fam" data-f="${it.fid}">${esc(it.who)}</button>` : `<span class="bub-team wfam">${esc(it.who)}</span>`;
  const sc = {Red:'r', Amber:'a', Green:'g'}[it.st] || 'n';
  const hd = it.mid && it.fid && !full ? `<button type="button" class="wgo" data-act="go-met" data-f="${it.fid}" data-m="${it.mid}" aria-label="Open ${esc(met(it.mid).name)} on the ${esc(it.who)} page">${esc(met(it.mid).name)}</button>`
    : it.mid ? esc(met(it.mid).name) : esc(it.head || '');
  const code = it.mid ? `<span class="wid">${it.mid}</span>` : '';
  const sr = sc !== 'n' ? `<span class="sr-only">${stInfo(it.st)[2]}: </span>` : '';
  const says = !full && it.fid ? saysMark(it.fid, it.mid ? 'rel:' + it.mid : null) : '';
  return `<li class="wi s-${sc}"><div class="w1">${who}<b class="wh">${sr}${hd}</b>${code}</div><div class="w2"><span>${esc(it.line2)}</span><span class="w2r">${coverTxt(it.cv)}${says}</span></div></li>`;
}
const SEC = ["What’s newly Red", "What’s chronic", "What needs leadership"];
const WORDER = [2, 0, 1];      // CTO review, 3 Nov 2026: the asks of leadership come first, open
const secT = i => i === 0 && !PRIOR[S.p] ? 'What’s Red' : SEC[i];
const secS = i => !PRIOR[S.p] && i === 0 ? 'Red this month (first month scored, so nothing is new or chronic yet)' : !PRIOR[S.p] && i === 1 ? 'Chronic means Red three months in a row, so it needs three months of results' : SEC_SUB[i];
const SEC_SUB = ["Automatic Red rules and metrics that turned Red this month", "Chronic Red, sharp drops, declining building blocks and overdue actions", "Asks, accepted risks nearing expiry, peer gaps and data quality"];
function watchSyn(i, items, total = items.length){
  if (!items.length && i === 2) return `nothing needs your decision this month${total ? `; ${plural(total, 'item', 'items')} on the family pages` : ''}`;   // A2
  if (!items.length) return total ? `nothing this month; ${plural(total, 'item', 'items')} on the family pages` : 'Nothing to report';
  const cnt = k => items.filter(x => x.kind === k).length, nn = (k, one, many) => { const c = cnt(k); return c ? `${c} ${c === 1 ? one : many}` : null; };
  const list = names => listOf(names.map(esc), WATCH_NAMES_SHOWN);
  if (i === 0 && !PRIOR[S.p]) { const ov = items.filter(x => x.kind === 'Override red').length;
    return `${items.length} Red ${items.length === 1 ? 'metric' : 'metrics'}${ov ? ` (${ov} by an automatic rule)` : ''} across ${list([...new Set(items.map(x => x.who))])}`; }
  if (i === 0) { const pr = x => { const m = x.fid && x.mid && P().families[x.fid].metrics[x.mid]; return m ? m.prior_status : null; };
    const isNew = x => x.kind === 'New red' || (pr(x) != null && pr(x) !== 'Red'), nw = items.filter(isNew), ov = items.filter(x => x.kind !== 'New red'), ovNew = ov.filter(isNew).length, ovOld = ov.length - ovNew;
    const head = nw.length ? `${nw.length} newly Red${ovNew ? ` (${ovNew} by an automatic rule)` : ''}` : '', tail = ovOld ? `${ovOld} still Red by an automatic rule` : '';
    return `${[head, tail].filter(Boolean).join(' and ')} across ${list([...new Set(items.map(x => x.who))])}`; }
  const cap3 = a => a.length > WATCH_NAMES_SHOWN ? a.slice(0, WATCH_NAMES_SHOWN).join(', ') + ` and ${a.length - WATCH_NAMES_SHOWN} more` : a.join(', ');
  if (i === 1) { const ch = items.filter(x => x.kind === 'Chronic red');   // A2: say what the chronic items are
    let lead = null;
    if (ch.length) { const fs = [...new Set(ch.map(x => x.fid))], by = {}; ch.forEach(x => { const b = x.mid && met(x.mid) ? BLK(met(x.mid).block).name : null; if (b) by[b] = (by[b] || 0) + 1; });
      const top = Object.entries(by).sort((a, b) => b[1] - a[1]), uniq = top.length && (top.length === 1 || top[0][1] > top[1][1]);
      lead = `${ch.length} ${ch.length === 1 ? 'metric' : 'metrics'} Red for 3+ months ${fs.length === 1 ? 'in ' + esc(fam(fs[0]).name) : 'across ' + fs.length + ' families'}${uniq && ch.length > 1 ? `, ${top[0][1] * 2 > ch.length ? 'mostly' : 'mainly'} ${top[0][0]}` : ''}`; }
    return cap3([lead, nn('Sharp drop', 'sharp drop', 'sharp drops'), nn('Declining', 'declining building block', 'declining building blocks'), nn('Overdue action', 'overdue action', 'overdue actions')].filter(Boolean)); }
  const dn = items.filter(x => x.kind === 'dnr').map(x => x.who);
  return cap3([nn('risk', 'accepted risk nearing expiry', 'accepted risks nearing expiry'), dn.length ? `${list(dn)} data not received` : null,
    nn('query', 'data query needing a ruling', 'data queries needing a ruling'), nn('Behind peers', 'peer gap', 'peer gaps')].filter(Boolean));
}
function moreWatch(rest){
  const by = new Map(); rest.forEach(it => { if (it.fid) by.set(it.fid, (by.get(it.fid) || 0) + 1); });
  const links = [...by].map(([f, n]) => `<button type="button" class="bub-team wfam" data-act="go-fam" data-f="${f}">${esc(fam(f).name)} (${n})</button>`).join(' ');
  return `<p class="more">On the family pages: ${links}</p>`;
}
function watchHTML(full, only){
  let secs0 = buildWatch(); if (only) secs0 = secs0.map(s => s.filter(i => i.fid === only));
  const secs = WORDER.map(k => secs0[k]);
  const c = full || only ? {secs, hidden:0, rest:[], restBy:[[], [], []], counts:secs.map(s => s.length)} : capWatchShown(secs0);
  const html = c.secs.map((s, pos) => { const i = WORDER[pos], n = `${pos + 1}. `;
    const list = s.length ? `<ul>${s.map(it => liHTML(it, full)).join('')}</ul>` : c.counts[pos] > 0 ? '' : `<ul><li class="none">${full && i === 2 ? 'Nothing needs your decision this month.' : 'Nothing to report.'}</li></ul>`;
    const cut = c.restBy[pos].length, more = cut ? moreWatch(c.restBy[pos]) : '';
    if (full) return `<h2 id="w${i + 1}">${n}${secT(i)}<small>${secS(i)}</small></h2>${list}`;
    return `<details class="wsec"${pos < 2 || S.snap ? ' open' : ''}><summary><h2 id="w${i + 1}"><span class="wt">${n}${secT(i)}</span><span class="wsyn"> — ${watchSyn(i, s, c.counts[pos])}${cut && s.length ? `; ${cut} more on the family pages` : ''}</span></h2></summary><p class="cap wsub">${secS(i)}</p>${list}${more}</details>`; }).join('');
  return `<section class="watch" aria-label="Watch list">${html}</section>`;
}
