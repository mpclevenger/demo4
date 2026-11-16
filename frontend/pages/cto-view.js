/* CTO view: the firm's score and story, and the building blocks grid. */
"use strict";
/* ---------- hero / heatmap ---------- */
function heroStats(){
  const p = P(), fams = Object.entries(p.families); let red = 0, newRed = 0, chronic = 0;
  fams.forEach(([, fr]) => Object.values(fr.metrics).forEach(x => { if (x.status === 'Red') { red++; if (x.prior_status != null && x.prior_status !== 'Red') newRed++; if (x.history.length >= 3 && streak(x.history) >= 3) chronic++; } }));
  const redFams = fams.filter(([, fr]) => Object.values(fr.blocks).some(l => l.status === 'Red')).map(([id, fr]) => `${fam(id).name} ${fr.trust}`);   // families with any Red building block
  const overdue = p.watch_list.filter(w => w.kind === 'Overdue action').length;
  const exp = missingFacts(p).expected;
  return {red, newRed, chronic, redFams, overdue, provIn: exp.filter(pr => !p.dnr.includes(pr)).length, provs: exp.length};
}
function heroHTML(strip = true, btn = false){
  const p = P(), st = heroStats(), [c,,w] = stInfo(p.firm_trust == null ? 'Not scored' : p.firm_trust >= METHOD.band_green_from ? 'Green' : p.firm_trust >= METHOD.band_amber_from ? 'Amber' : 'Red');
  return `<section class="hero" aria-label="Firm result"><div class="hl"><div class="lbl" style="font-size:28px;line-height:1.05;color:var(--text,#111)">Firm<br>TRUST</div><div class="big" aria-label="${p.firm_trust}, ${w}" title="${w}" style="color:${{Green:'#15803d',Amber:'#b45309',Red:'#b91c1c'}[w] || 'inherit'}">${p.firm_trust == null ? '<span style="font-size:28px;line-height:1.1;display:block;max-width:9em">Not scored yet</span>' : p.firm_trust}</div>
    <div class="hd"><span class="dd">${(p.firm_incomplete || !PRIOR[S.p]) ? '' : p.firm_trust_delta ? `<span class="dl ${p.firm_trust_delta > 0 ? 'up' : 'dn'}" style="font-size:16px">${p.firm_trust_delta > 0 ? '▲' : '▼'}${Math.abs(p.firm_trust_delta)}</span>` : '<span class="dl z" style="font-size:16px">0</span>'}${(p.firm_incomplete || !PRIOR[S.p]) ? '' : ` vs ${priorName()}`}</span></div></div>
    ${strip ? `<div class="hr"><div class="strip"><span>Families with a Red building block <b>${st.redFams.length}</b></span><span>Red metrics <b>${st.red}</b> (${st.newRed} new)</span><span>Providers in <b>${st.provIn} of ${st.provs}</b></span><span>Overdue actions <b>${st.overdue}</b></span></div></div>` : ''}${btn ? `<div class="hbtn noprint">${snapBtn()}</div>` : ''}</section>`;
}
const RISKCOL = {Cyber:'#b42318', Operational:'#0f766e', Change:'#1d4ed8', Strategic:'#6d28d9', Obsolescence:'#b45309', Data:'#0e7490', Model:'#9d174d', Vendor:'#4d7c0f'};
let HMF = 'measured';  // heatmap columns (owner, 4 Nov 2026; default 'scored' since 5 Nov): 'all' building blocks, 'scored' = only blocks with a score this month, or one block's code
const hmBlocks = p => { if (HMF === 'all') return D.blocks;
  if (HMF === 'measured') { const m = D.blocks.filter(l => D.metrics.some(x => x.block === l.code && metState(x.id) === 'measured')); return m.length ? m : D.blocks; }
  if (HMF !== 'scored') return D.blocks.filter(l => l.code === HMF);
  const scored = D.blocks.filter(l => Object.values(p.families).some(fr => fr.blocks[l.code] && fr.blocks[l.code].score != null) || (p.firm_blocks && p.firm_blocks[l.code] && p.firm_blocks[l.code].score != null));
  return scored.length ? scored : D.blocks; };   // nothing scored yet: show every block rather than an empty grid
let HMS = null;   // heatmap sort: {k: 'name' | building block code | 'trust', d: 1 low to high | -1 high to low}; null = usual order
function hmSorted(fs, p){   // blanks (not scored) last either way; ties keep the usual order
  if (!HMS) return fs;
  const v = f => { const fr = p.families[f.id]; if (HMS.k === 'name') return f.name;
    const x = HMS.k === 'trust' ? {score:fr.trust, status:fr.status} : fr.blocks[HMS.k];
    return x && x.score != null && SCORED.includes(x.status) ? x.score : null; };
  return fs.map((f, i) => [f, v(f), i]).sort((a, b) => a[1] === null || b[1] === null ? (a[1] === b[1] ? a[2] - b[2] : a[1] === null ? 1 : -1)
    : HMS.d * (HMS.k === 'name' ? a[1].localeCompare(b[1]) : a[1] - b[1]) || a[2] - b[2]).map(x => x[0]);
}
/* The dictionary's opening line (owner, 8 Nov 2026: in progress added): '10 measured this month. In gray: 1 in progress and 9 wanted (no data source yet). These count in no score.' */
function dictSummary(){
  const c = bMetCounts(), and = a => a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1];
  const gray = [c.progress && `${c.progress} in progress`, c.wanted && `${c.wanted} wanted (no data source yet)`].filter(Boolean);
  return `${c.measured} measured this month.` + (gray.length ? ` In gray: ${and(gray)}. ${c.progress + c.wanted === 1 ? 'It counts' : 'These count'} in no score.` : '');
}
function bMetCounts(){      // metric counts, always from the data block
  const n = s => D.metrics.filter(m => metState(m.id) === s).length;
  return {measured:n('measured'), progress:n('in progress'), wanted:n('wanted'), total:D.metrics.length};
}
function heatmapHTML(pre, noBanner){
  const p = P(), mf = missingFacts(p);
  CTOP.hl = pre ? null : ctoHL();
  /* noBanner 'gaps' (CTO view, 15 Nov 2026): say so only when data that should have arrived is missing */
  const banner = noBanner === 'gaps' ? (mf.gaps.length ? `<div class="banner" role="note">${gapsLine(mf)}. Nothing is carried over from ${priorName()}${mf.suppressed ? ', and no change in TRUST is shown while data is missing' : ''}.</div>` : '')
    : (mf.wanted.length || mf.gaps.length) && !noBanner ? `<div class="banner" role="note">${[wantedLine(mf) ? `${wantedLine(mf)}, so TRUST rests on ${NUMW[mf.scoredBlocks] || mf.scoredBlocks} of ${NUMW[D.blocks.length] || D.blocks.length} building blocks.` : '',
    mf.gaps.length ? `${gapsLine(mf)}. Nothing is carried over from ${priorName()}${mf.suppressed ? ', and no change in TRUST is shown while data is missing' : ''}.` : ''].filter(Boolean).join(' ')}</div>` : '';
  const allInc = Object.values(p.families).every(fr => fr.incomplete), anyInc = Object.values(p.families).some(fr => fr.incomplete);
  const base = Object.fromEntries(D.blocks.map(l => { const ls = Object.values(p.families).map(fr => fr.blocks[l.code]).filter(x => x && x.applicable);   // what's missing for every family
    return [l.code, ls.length ? Math.min(...ls.map(x => x.missing || 0)) : 0]; }));
  /* Owner, 4 Nov 2026: no "x of y metrics arrived" line under a block head; a small warning mark instead, whose tip
     says how many metrics arrived and which ones didn't, and why. */
  const arrived = code => { const fr0 = Object.values(p.families).find(fr => fr.blocks[code] && fr.blocks[code].applicable), x = fr0 && fr0.blocks[code];
    if (!x) return '';
    const live = D.metrics.filter(m => m.block === code && !isWanted(m)), wantedN = D.metrics.filter(m => m.block === code && isWanted(m)).length;
    const gone = live.filter(m => fr0.metrics[m.id] && fr0.metrics[m.id].status === 'DNR').length, got = live.length - gone;
    const tail = wantedN ? `${plural(wantedN, 'metric is', 'metrics are')} wanted, with no data source yet` : '';
    if (!live.length) return `None of this building block’s metrics is measured yet: ${tail}`;
    return `${got} of ${plural(live.length, 'metric', 'metrics')} arrived this month${tail ? `; ${tail}` : ''}`; };

  const warn = code => { const t = arrived(code); return t ? `<span class="warnm" tabindex="0" role="img" aria-label="${esc(t)}" data-tip="${esc(t)}">⚠</span>` : ''; };
  /* sortable heads (owner, 4 Nov 2026): families sort within their band; the Firmwide row stays last */
  const hs = (k, inner, sub = '') => { const on = HMS && HMS.k === k ? (HMS.d === 1 ? 'up' : 'dn') : '';
    return pre ? inner + sub : `<button type="button" class="sortb" data-act="hm-sort" data-k="${k}" data-on="${on}" title="${on === 'up' ? 'Sorted low to high. Click for high to low' : on === 'dn' ? 'Sorted high to low. Click to go back to the usual order' : 'Click to sort families by this column'}">${inner}${SORT_ICON}${sub}</button>`; };
  const asrt = k => HMS && HMS.k === k ? ` aria-sort="${HMS.d === 1 ? 'ascending' : 'descending'}"` : '';
  const BL = hmBlocks(p);
  /* Risk-category band above the block names (owner, 5 Nov 2026): each block's category from the risk register,
     in that category’s color. The TRUST head's explanation is a tip on hover, so every head is one line and the
     ⚠ marks sit on the same line. */
  const groups = BL.reduce((g, l) => { const last = g[g.length - 1]; if (last && last.cat === (l.risk_category || '')) last.n++; else g.push({cat: l.risk_category || '', n: 1}); return g; }, []);
  const band = `<tr class="riskrow"><th style="width:40px"></th><th style="width:158px"></th>${groups.map(g => `<th class="rk"${g.n > 1 ? ` colspan="${g.n}"` : ''} style="--rc:${RISKCOL[g.cat] || '#64748b'}">${esc(g.cat)}${g.cat ? ' risk' : ''}</th>`).join('')}<th style="width:236px"></th></tr>`;
  const head = `<thead>${band}<tr><th style="width:40px"><span class="cap" style="display:none">Band</span></th><th style="width:158px"${asrt('name')}>${hs('name', 'Family', '<span>Accountable lead</span>')}</th>${BL.map(l => `<th${asrt(l.code)}><span class="hname">${hs(l.code, l.name)}${base[l.code] ? warn(l.code) : ''}</span></th>`).join('')}<th style="width:236px"${asrt('trust')} tabindex="0" data-tip="TRUST = the average of the scored building blocks, in whole numbers. Firmwide is scored from every row the firm received, not an average of the families."><span class="hname">${hs('trust', 'TRUST')}</span></th></tr></thead>`;
  NOTREND_ALL = ![...D.families.map(f => trendVals(f.id)), trendVals(null)].some(v => v && v.length >= 2);
  const rows = band => hmSorted(D.families.filter(f => f.band === band), p).map((f, i, arr) => {
    const fr = p.families[f.id];
    const cells = BL.map(l => { const x = fr.blocks[l.code], [c] = stInfo(x.status);
      const bs = bigSwing(fr, l.code, x);
      /* Tips only where they add something (owner, 9 Nov 2026): not scored or capped = the full reason; a big
         swing = that note alone; a plain score = no tip. */
      const tip = x.score == null || x.capped ? blockTip(l, x, bs, D.metrics.filter(m => m.block === l.code).map(m => [m, fr.metrics[m.id]])) : bs;
      return `<td class="c ${c}${ctoCls(f.id, l.code)}"${tip ? ` tabindex="0" data-tip="${esc(tip)}"` : ''}>${pre ? '' : `<span class="csay">${saysMark(f.id, 'let:' + l.code, true)}</span>`}<b>${x.score == null && x.status === 'Not Tier 0/1' ? 'No Tier 0/1 apps' : pre ? scoreTxt(x.score, x.status, x.provisional) : scoreNum(x.score, x.status, x.provisional)}${(x.missing || 0) > base[l.code] ? `<span class="mstar" aria-label="missing data: ${x.applicable - x.missing} of ${plural(x.applicable, 'metric', 'metrics')} arrived">*</span>` : ''}</b>${x.delta ? `<span class="ld ${x.delta > 0 ? 'up' : 'dn'}" aria-label="${x.delta > 0 ? 'up' : 'down'} ${Math.abs(x.delta)} since ${priorName()}">${x.delta > 0 ? '▲' : '▼'}${Math.abs(x.delta)}</span>` : ''}</td>`; }).join('');
    const [tc] = stInfo(fr.status);
    return `<tr>${i === 0 ? `<td class="bd" rowspan="${arr.length}"><span>${band.toUpperCase()}</span></td>` : ''}<td class="fn">${famLink(f.id)}${pre ? '' : saysMark(f.id, null, true)}<span class="lead">${esc(f.accountable || '')}</span>${noBanner === 'gaps' ? cmkFamilyHTML(f.id) : ''}</td>${cells}
      <td class="c tr ${tc}${ctoCls(f.id, 'trust')}">${quarterHTML(trendVals(f.id), fr.incomplete, allInc, `<b>${pre ? scoreTxt(fr.trust, fr.status, false) : scoreNum(fr.trust, fr.status, false)}</b>`)}${fr.capped ? `<span class="s">capped at ${CAP().red_block_trust}</span>` : ''}</td></tr>`; }).join('');
  const clr = n => n >= METHOD.band_green_from ? 'Green' : n >= METHOD.band_amber_from ? 'Amber' : 'Red';
  /* Firmwide row: the firm's own block scores, worked out from every row the firm received (owner, 4 Nov 2026),
     not an average of the family scores. */
  const fcells = BL.map(l => { const fb = (p.firm_blocks || {})[l.code] || {score:null, status:'N/A'}, tip = esc(blockTip(l, fb, '', D.metrics.filter(m => m.block === l.code).map(m => [m, (p.firm || {})[m.id]])));
    if (fb.score == null) return `<td class="c n${ctoCls()}" tabindex="0" data-tip="${tip}"><b>Not scored</b></td>`;     // tips only when not scored or capped (owner, 9 Nov 2026)
    const [c] = stInfo(fb.status);
    return `<td class="c ${c}${ctoCls()}"${fb.capped ? ` tabindex="0" data-tip="${tip}"` : ''}><b>${pre ? scoreTxt(fb.score, fb.status, false) : scoreNum(fb.score, fb.status, false)}</b>${fb.capped ? `<span class="s">capped</span>` : ''}</td>`; }).join('');
  const fst = p.firm_trust == null ? 'Not scored' : (p.firm_status && SCORED.includes(p.firm_status) ? p.firm_status : clr(p.firm_trust)), [fc] = stInfo(fst);
  const firmRow = `<tr class="firm"><td class="bd h"><span>FIRM</span></td><td class="fn">Firmwide</td>${fcells}<td class="c tr ${fc}${ctoCls()}">${quarterHTML(trendVals(null), p.firm_incomplete, allInc, `<b>${pre ? scoreTxt(p.firm_trust, fst, false) : scoreNum(p.firm_trust, fst, false)}</b>`)}${p.firm_capped ? `<span class="s">capped at ${CAP().red_block_trust}</span>` : ''}</td></tr>`;
  const anyProv = Object.values(p.families).some(fr => Object.values(fr.blocks).some(l => l.provisional)), anyMiss = Object.values(p.families).some(fr => D.blocks.some(l => (fr.blocks[l.code].missing || 0) > base[l.code]));
  const anyNS = Object.values(p.families).some(fr => Object.values(fr.blocks).some(l => !SCORED.includes(l.status)));
  const hidden = D.blocks.length - BL.length;
  const filt = pre ? (hidden ? `<p class="cap" style="margin:0 0 6px">Showing ${HMF === 'scored' ? 'only building blocks with a score this month' : BL.map(l => l.name).join(', ')}; ${plural(hidden, 'building block', 'building blocks')} hidden.</p>` : '')
    : `<div class="hmf"><label for="hmf" class="cap">Show</label> <select id="hmf" aria-label="Which building blocks to show"><option value="measured"${HMF === 'measured' ? ' selected' : ''}>Measured blocks</option><option value="scored"${HMF === 'scored' ? ' selected' : ''}>Blocks with a score this month</option><option value="all"${HMF === 'all' ? ' selected' : ''}>All blocks</option>${D.blocks.map(l => `<option value="${l.code}"${HMF === l.code ? ' selected' : ''}>${esc(l.name)} only</option>`).join('')}</select>${hidden ? `<span class="cap"> · not shown: ${D.blocks.filter(l => !BL.includes(l)).map(l => esc(l.name)).join(', ')}</span>` : ''}</div>`;
  const heading = `<h2 id="h-bb" style="margin-top:18px">Building blocks of TRUST</h2>${pre ? `<p class="cap" style="margin:0 0 8px">What each product family is doing well, and where it isn't, on the six things that earn clients’ trust.</p>` : ''}`;
  return `${banner}${heading}${filt}<div class="hmwrap"><table class="hm"><caption style="position:absolute;left:-999px">Building blocks of TRUST by product family</caption>${head}<tbody>${rows('product')}${rows('platform')}${firmRow}</tbody></table></div>
    <div class="legend"><span>${bandWords()}</span>${D.trend && PRIOR[S.p] ? `<span class="sep">|</span><span>▲▼ change since ${priorName()}</span>` : ''}${Object.values(base).some(v => v > 0) ? '<span class="sep">|</span><span>⚠ some metrics didn’t arrive</span>' : ''}${anyMiss ? '<span class="sep">|</span><span>* fewer metrics arrived for this family</span>' : ''}${noBanner === 'gaps' ? cmkLegendHTML() : ''}</div>`;
}

/* ---------- views ---------- */
/* ----- CTO view story, firm tolerance and trend (D-77) ----- */
function trendVals(fid){                         // last 6 months up to the selected month
  const T = D.trend; if (!T) return null;
  const end = T.months.indexOf(S.p); if (end < 0) return null;
  const st = Math.max(0, end - 5), src = fid ? T.families[fid] : T.firm;
  return T.months.slice(st, end + 1).map((m, i) => ({m, v: src[st + i], inc: (T.incomplete_months || []).includes(m)}));
}
let NOTREND_ALL = false;
function quarterHTML(vals, inc, quiet, score){                // option 4 line + option 3 wording: last quarter (3 months back to now)
  if (!vals || vals.length < 2) return NOTREND_ALL ? score : `${score}<span class="s">Trend shows once earlier months are scored.</span>`;
  const q = vals.slice(-4), w = 78, h = 22, first = q[0], last = q[q.length - 1];
  const lo = Math.min(...q.map(p => p.v)), hi = Math.max(...q.map(p => p.v)), rng = Math.max(6, hi - lo);
  const xs = i => 18 + i * (w - 22) / (q.length - 1), ys = v => h - 4 - ((v - lo) / rng) * (h - 8);
  const seg = (a, b, cls) => `<line x1="${xs(a).toFixed(1)}" y1="${ys(q[a].v).toFixed(1)}" x2="${xs(b).toFixed(1)}" y2="${ys(q[b].v).toFixed(1)}" class="${cls}"/>`;
  let lines = ''; for (let i = 1; i < q.length; i++) lines += seg(i - 1, i, 'spreal');
  const lbl = q.map(p => `${monthLabel(p.m)} ${p.v}`).join(', ');
  const svg = `<svg class="qline" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="TRUST over the last quarter: ${esc(lbl)}"><text x="0" y="${(ys(first.v) + 4).toFixed(1)}" class="qst">${first.v}</text>${lines}<circle cx="${xs(q.length - 1).toFixed(1)}" cy="${ys(last.v).toFixed(1)}" r="2.8" class="${inc ? 'sphol' : 'spdot'}"/></svg>`;
  const d = last.v - first.v;
  const span = q.length < 3 ? 'prior month' : 'prior quarter';   // D-106: two months of data compare with the prior month; from three months on, with the prior quarter
  const tail = q.length < 3 ? `since ${priorName()}` : 'over the prior quarter';
  const words = inc ? (quiet ? '' : 'Missing data') : d > 0 ? `<span class="qup">Up ${d}</span> ${tail}` : d < 0 ? `<span class="qdn">Down ${-d}</span> ${tail}` : `Steady ${q.length < 3 ? 'since ' + priorName() : 'over the prior quarter'}`;
  return `<span class="qrow">${svg}${score}</span>${words ? `<span class="qw">${words}</span>` : ''}`;
}

function storyHTML(){
  const p = P(), plain = s => String(s || '').replace(/<[^>]+>/g, '');
  const tol = D.firm_tolerance, ft = p.firm_trust;
  const chg = (p.firm_incomplete || !PRIOR[S.p]) ? '' : p.firm_trust_delta ? `, ${p.firm_trust_delta > 0 ? 'up' : 'down'} ${Math.abs(p.firm_trust_delta)} since ${priorName()}` : `, unchanged since ${priorName()}`;
  const tolTxt = tol ? `, ${ft === tol.value ? 'at' : ft > tol.value ? `${ft - tol.value} above` : `${tol.value - ft} below`} our tolerance of ${tol.value}` : '';
  const s1 = `Firm TRUST is ${ft}${chg}${tolTxt}.`;
  const fams = Object.entries(p.families).filter(([, fr]) => fr.trust != null).sort((a, b) => a[1].trust - b[1].trust);
  /* A month can have no family with enough data for a TRUST score yet (building blocks needed: setting "coverage", owner 4 Nov 2026): show the building blocks on their own. */
  if (!fams.length) { const scoredBlocks = D.blocks.filter(l => Object.values(p.families).some(fr => fr.blocks[l.code] && fr.blocks[l.code].score != null)).map(l => l.name);
    const need = NEED_BLOCKS(), needTxt = need === 1 ? 'one measured building block' : `${NUMW[need] || need} measured building blocks`;
    return `<section class="story" aria-label="This month in brief"><p>No TRUST score yet for ${esc(P().meta.label)}: ${scoredBlocks.length ? `TRUST needs at least ${needTxt}, and ${scoredBlocks.length === 1 ? 'only ' : ''}${listOf(scoredBlocks)} ${scoredBlocks.length === 1 ? 'is' : 'are'} measured so far. Building block scores are below; TRUST appears once ${needTxt.replace('measured ', '')} ${need === 1 ? 'is' : 'are'} measured.` : 'no building block is measured yet.'}${p.dnr.length ? ` Not arrived yet: ${esc(listOf(p.dnr))}.` : ''}</p></section>`; }
  const [lid, lfr] = fams[0], lf = fam(lid);
  const reds = Object.entries(lfr.blocks).filter(([, l]) => l.status === 'Red').map(([c, l]) => `${BLK(c).name} ${l.score}`);
  const nr = Object.values(lfr.metrics).filter(x => x.status === 'Red' && x.prior_status != null && x.prior_status !== 'Red').length;
  const s2 = `${esc(lf.name)} is lowest at ${lfr.trust} (accountable: ${esc(lf.accountable)})${reds.length ? `: ${listOf(reds)} ${reds.length === 1 ? 'is' : 'are'} Red` : ''}${nr ? `, with ${nr} newly Red ${nr === 1 ? 'metric' : 'metrics'}` : ''}`;
  const others = fams.slice(1).filter(([, fr]) => Object.values(fr.blocks).some(l => l.status === 'Red')).length;   // A1 (design review, 5 Nov 2026): three sentences at most
  const s2b = others ? `; ${others === 1 ? 'one other family has' : `${others} other families have`} a Red block` : '';
  const mf = missingFacts(p), s3p = [];
  if (mf.wanted.length) s3p.push(`${wantedLine(mf)}, so TRUST rests on ${NUMW[mf.scoredBlocks] || mf.scoredBlocks} of ${NUMW[D.blocks.length] || D.blocks.length} building blocks`);
  if (mf.gaps.length) s3p.push(`${gapsLine(mf)}${mf.suppressed ? ', and no change in TRUST is shown while data is missing' : ''}`);
  const s3 = s3p.length ? ` ${s3p.join('; ')}.` : '';
  return `<section class="story" aria-label="This month in brief"><p>${s1} ${s2}${s2b}.${s3}</p></section>`;
}
/* ---------- top row (locked look, 15 Nov 2026): TRUST, the good news, Where to focus ----------
   Both boxes are always drawn (owner, 15 Nov 2026). The good news is what improved; when nothing improved it is
   the families whose TRUST is Green. Where to focus says so when nothing needs focus.
   A line in either box can be selected: the matching grid cells stand out, the rest fade, and a panel opens under
   the row with what is behind the line. "Open this metric" goes to the family page with that metric's row open. */
const CTOP = {sel:null, all:false, pg:0, p:null, hl:null};
const ctoCls = (fid, code) => !CTOP.hl ? '' : fid && CTOP.hl.has(fid + ':' + code) ? ' hl' : ' dim';
const CTO_RANK = {Red:0, Amber:1, Green:2};
function ctoImproved(){        // overall TRUST gains first, then building block gains where TRUST did not rise
  const p = P(); if (!PRIOR[S.p]) return [];
  const a = [], b = [];
  D.families.forEach(f => { const fr = p.families[f.id]; if (!fr) return;
    const up = D.blocks.filter(l => fr.blocks[l.code] && fr.blocks[l.code].score != null && fr.blocks[l.code].delta > 0);
    if (fr.delta > 0) a.push({k:'t:' + f.id, fid:f.id, d:fr.delta, what:`TRUST ${fr.trust}`, blocks:up.map(l => l.code), cells:['trust', ...up.map(l => l.code)]});
    else up.forEach(l => b.push({k:'b:' + f.id + ':' + l.code, fid:f.id, d:fr.blocks[l.code].delta, what:`${l.name} ${fr.blocks[l.code].score}`, blocks:[l.code], cells:[l.code]})); });
  const by = (x, y) => y.d - x.d;
  return [...a.sort(by), ...b.sort(by)];
}
function ctoGreens(){          // families whose TRUST is Green, highest first: the good news when nothing improved
  const p = P();
  const green = D.families.filter(f => p.families[f.id] && p.families[f.id].status === 'Green');
  return green.sort((x, y) => p.families[y.id].trust - p.families[x.id].trust);
}
function ctoGreenBox(){
  const p = P(), green = ctoGreens(), TOP = 3;
  const line = f => `<a class="tl" style="text-decoration:none" href="${href('/family-' + f.id)}"><b>${esc(f.name)}</b><span class="cap">${esc(f.accountable || '')}</span><span class="tv">TRUST ${p.families[f.id].trust}</span></a>`;
  const more = green.length > TOP ? `<p class="cap" style="margin:6px 8px 0">and ${green.length - TOP} more</p>` : '';
  const body = green.length ? green.slice(0, TOP).map(line).join('') + more : '<p class="cap" style="margin:6px 8px 0">No family is Green yet this month.</p>';
  return `<div class="tb"><h2>Green this month</h2>${body}</div>`;
}
function ctoNeeds(){
  const [s1, s2, s3] = buildWatch(), L = [];
  const where = a => { const n = [...new Set(a.map(x => x.who))]; return n.length <= 2 ? n.join(' and ') : `${n.length} families`; };
  const mk = (k, items, label) => { if (items.length) L.push({k:'n:' + k, items, label:label(items.length), where:where(items)}); };
  mk('new', s1.filter(x => x.mid), n => PRIOR[S.p] ? `newly Red ${n === 1 ? 'metric' : 'metrics'}` : `Red ${n === 1 ? 'metric' : 'metrics'}`);
  mk('drop', s2.filter(x => x.kind === 'Sharp drop'), n => `sharp ${n === 1 ? 'drop' : 'drops'} in TRUST`);
  mk('chronic', s2.filter(x => x.kind === 'Chronic red'), n => `${n === 1 ? 'metric' : 'metrics'} Red for 3+ months`);
  mk('lead', s3.filter(x => x.kind !== 'Behind peers'), n => `${n === 1 ? 'item needs' : 'items need'} leadership`);
  return L;
}
function ctoHL(){
  if (!CTOP.sel || S.snap) return null;
  const h = new Set();
  const im = ctoImproved().find(x => x.k === CTOP.sel);
  if (im) im.cells.forEach(c => h.add(im.fid + ':' + c));
  const nd = ctoNeeds().find(x => x.k === CTOP.sel);
  if (nd) nd.items.forEach(it => { if (it.fid) h.add(it.fid + ':' + (it.mid ? met(it.mid).block : 'trust')); });
  return h.size ? h : null;
}
function ctoMetLine(fid, mid){      // counts first, then what they come to; how far past the limit; last period's color
  const p = P(), m = met(mid), x = p.families[fid].metrics[mid], t = p.thresholds[mid], hib = m.higher_is_better;
  const ct = countText(m, x), val = fv(m, x.value), parts = [isPF(m) ? (ct || val) : ct ? `${ct} = ${val}` : val];
  if (t && m.unit === '%' && !isPF(m) && !x.override && x.value != null) {
    if (x.status === 'Red' && t.red != null) { const d = hib ? t.red - x.value : x.value - t.red; if (d > 0) parts.push(`${num1(d)} points ${hib ? 'below' : 'over'} the limit`); }
    else if (x.status === 'Green' && t.green != null) { const d = hib ? x.value - t.green : t.green - x.value; if (d > 0) parts.push(`${num1(d)} points ${hib ? 'above' : 'below'} the Green tolerance`); } }
  if (x.override) parts.push('Automatic Red rule');
  if (x.prior_status != null && CTO_RANK[x.prior_status] != null) parts.push(`Previous period: ${chip(x.prior_status)}`);
  return parts.join(' · ');
}
function ctoPanel(imp, needs){
  const im = imp.find(x => x.k === CTOP.sel), nd = needs.find(x => x.k === CTOP.sel); if (!im && !nd) return '';
  const says = (fid, mid) => famSays(fid, mid ? 'rel:' + mid : null).slice(0, 1).map(c => `<div class="fsl">${esc(fam(fid).name)} says: “${esc(c.text.length > 220 ? c.text.slice(0, 217) + '…' : c.text)}”</div>`).join('');
  const open = (fid, mid) => `<button type="button" class="sm" data-act="go-met" data-f="${fid}" data-m="${mid}">Open this metric</button>`;
  const row = (fid, mid, st, extra) => `<li class="s-${{Red:'r', Amber:'a', Green:'g'}[st] || 'n'}"><div class="cp1"><b>${esc(fam(fid).name)}</b> · ${esc(met(mid).name)}</div><div class="cp2">${extra || ctoMetLine(fid, mid)}</div>${says(fid, mid)}<div class="cp3 noprint">${open(fid, mid)}</div></li>`;
  let title, rows;
  if (im) { const fr = P().families[im.fid], f = fam(im.fid);
    title = `${esc(f.name)} · ${esc(im.what)} <span class="dl up">▲${im.d}</span>`;
    rows = D.metrics.filter(m => im.blocks.includes(m.block)).map(m => [m, fr.metrics[m.id]]).filter(([, x]) => x && CTO_RANK[x.status] != null && CTO_RANK[x.prior_status] != null && CTO_RANK[x.status] > CTO_RANK[x.prior_status])
      .map(([m, x]) => row(im.fid, m.id, x.status));
    if (!rows.length) rows = im.blocks.map(c => `<li class="s-n"><div class="cp1"><b>${esc(BLK(c).name)}</b> ${fr.blocks[c].score} <span class="dl up">▲${fr.blocks[c].delta}</span></div></li>`); }
  else { title = `${nd.items.length} ${esc(nd.label)}`;
    rows = nd.items.map(it => it.mid && it.fid ? row(it.fid, it.mid, it.st, nd.k === 'n:lead' ? esc(it.line2) : '')
      : `<li class="s-n"><div class="cp1"><b>${esc(it.who)}</b>${it.head ? ' · ' + esc(it.head) : ''}</div><div class="cp2">${esc(it.line2)}</div>${it.fid ? `<div class="cp3 noprint"><button type="button" class="sm" data-act="go-fam" data-f="${it.fid}">Open ${esc(it.who)}</button></div>` : ''}</li>`); }
  const N = rows.length, pages = Math.ceil(N / 10), pg = Math.min(Math.max(CTOP.pg, 0), Math.max(pages - 1, 0)); CTOP.pg = pg;
  const pager = pages < 2 ? '' : `<div class="itbf noprint"><span class="pgr" role="group" aria-label="Pages"><button type="button" class="sm" data-act="cto-pg" data-d="-1" ${pg === 0 ? 'disabled' : ''}>‹ Previous</button><span class="cap" aria-live="polite">${pg * 10 + 1}–${Math.min(N, pg * 10 + 10)} of ${N} · page ${pg + 1} of ${pages}</span><button type="button" class="sm" data-act="cto-pg" data-d="1" ${pg >= pages - 1 ? 'disabled' : ''}>Next ›</button></span></div>`;
  return `<section class="ctopanel" id="ctopanel" aria-label="Behind the selected line"><div class="cph"><h2>${title}</h2><button type="button" class="sm noprint" data-act="cto-close">Close</button></div><ul>${rows.slice(pg * 10, pg * 10 + 10).join('')}</ul>${pager}</section>`;
}
function ctoTopHTML(){
  if (CTOP.p !== S.p) Object.assign(CTOP, {sel:null, all:false, pg:0, p:S.p});
  const p = P(), imp = ctoImproved(), needs = ctoNeeds();
  if (CTOP.sel && ![...imp, ...needs].some(x => x.k === CTOP.sel)) CTOP.sel = null;
  const pr = k => `aria-pressed="${CTOP.sel === k}"`;
  const shown = CTOP.all ? imp : imp.slice(0, 3);
  const up = !imp.length ? ctoGreenBox() : `<div class="tb"><h2><span class="dl up">▲</span> Improved since ${priorName()}</h2>${shown.map(x => { const f = fam(x.fid);
      return `<button type="button" class="tl" data-act="cto-line" data-k="${x.k}" ${pr(x.k)}><b>${esc(f.name)}</b><span class="cap">${esc(f.accountable || '')}</span><span class="tv">${esc(x.what)} <span class="dl up">▲${x.d}</span></span></button>`; }).join('')}${imp.length > 3 ? `<button type="button" class="sm tmore" data-act="cto-all" aria-expanded="${CTOP.all}">${CTOP.all ? 'Show top 3' : `Show all ${imp.length}`}</button>` : ''}</div>`;
  const dn = !needs.length ? '<div class="tb"><h2><span class="dl dn">▼</span> Where to focus</h2><p class="cap" style="margin:6px 8px 0">Nothing needs focus this month.</p></div>' : `<div class="tb"><h2><span class="dl dn">▼</span> Where to focus</h2>${needs.map(x =>
      `<button type="button" class="tl" data-act="cto-line" data-k="${x.k}" ${pr(x.k)}><span class="cnt">${x.items.length}</span><b>${esc(x.label)}</b><span class="cap tv">${esc(x.where)}</span></button>`).join('')}</div>`;
  const tr = trendVals(null);
  return `<div class="ctop"><div class="tb">${heroHTML(false, false)}${tr && tr.length >= 2 ? `<div class="tq">${quarterHTML(tr, p.firm_incomplete, true, '')}</div>` : ''}</div>${up}${dn}</div>${ctoPanel(imp, needs)}`;
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act^="cto-"]'); if (!b) return; const a = b.dataset.act;
  if (a === 'cto-line') { CTOP.sel = CTOP.sel === b.dataset.k ? null : b.dataset.k; CTOP.pg = 0; }
  else if (a === 'cto-all') CTOP.all = !CTOP.all;
  else if (a === 'cto-close') CTOP.sel = null;
  else if (a === 'cto-pg') CTOP.pg += +b.dataset.d;
  else return;
  S.keepScroll = true; render();
  const n = a === 'cto-all' ? document.querySelector('[data-act="cto-all"]') : a === 'cto-pg' ? document.getElementById('ctopanel') : document.querySelector(`[data-act="cto-line"][data-k="${CSS.escape(CTOP.sel || b.dataset.k || '')}"]`);
  if (n && n.focus) n.focus({preventScroll:true});
});
function vScorecard(){
  if (S.snap) return snapScorecard();
  /* Locked look (15 Nov 2026): the top row replaces the story sentence and the three numbered sections. The story
     shows only when no family has a TRUST score yet; the "not yet mapped" note is for Tech Risk. */
  const none = !Object.values(P().families).some(fr => fr.trust != null);
  return `${ctoTopHTML()}${none ? storyHTML() : ''}${cmkRowHTML()}${heatmapHTML(false, 'gaps')}
    <p class="cap ctofoot"><a href="${href('/glossary-how-scores')}">How the scores are worked out (Glossary)</a><span class="noprint">${snapBtn()}</span></p>${isTR() ? unmappedNote('cto') : ''}`;
}

/* ---------- Elevated risk markers (owner, 16 Nov 2026) ----------
   Tech Risk switches a metric On or Off here. When it is On, each team whose own newest risk assessment has an Elevated
   risk that the metric watches gets a small marker beside its name in the grid. A marker points to a conversation; it
   changes no score, status or threshold. Read live from /api/cto/risk-markers, so a switch shows at once.
   What is drawn: Tech Risk sees a chip for every Measured metric (to flip it). Everyone else sees only the chips that are
   On, read only, and nothing at all when none is On (nothing to say = nothing drawn). */
const CMK = {state:null, can:false, metrics:[], markers:[], ask:null, error:'', busy:false};
function cmkLoad(){
  if (CMK.state) return;
  CMK.state = 'loading';
  api('/api/cto/risk-markers')
    .then(r => { Object.assign(CMK, {state:'ok', can:!!r.can_change, metrics:r.metrics || [], markers:r.markers || []}); })
    .catch(() => { Object.assign(CMK, {state:'fail', can:false, metrics:[], markers:[]}); })
    .then(() => { S.keepScroll = true; if (document.querySelector('.hm')) render(); });
}
const cmkShortName = name => String(name || '').replace(/\s*\(.*$/, '');
const cmkMarkersOf = fid => CMK.markers.filter(m => m.family === fid);
function cmkMetricName(metricId){ const chip = CMK.metrics.find(m => m.id === metricId); return chip ? chip.name : metricId; }
function cmkFamilyHTML(fid){
  const mine = cmkMarkersOf(fid);
  if (!mine.length) return '';
  const pill = m => { const names = m.risks.map(r => r.name).join('; '), full = cmkMetricName(m.metric),
      tip = `Elevated ${m.risks.length === 1 ? 'risk' : 'risks'} this team’s own newest assessment found, which ${esc(full)} watches: ${names}`;
    return `<span class="cmkpill" tabindex="0" role="note" data-tip="${esc(tip)}" aria-label="${esc(tip)}"><i class="cmkdot" aria-hidden="true"></i><span class="cmkname">${esc(cmkShortName(full))}</span></span>`; };
  return `<span class="cmkrow">${mine.map(pill).join('')}</span>`;
}
function cmkLegendHTML(){
  return CMK.markers.length ? '<span class="sep">|</span><span class="cmkleg"><i class="cmkdot" aria-hidden="true"></i> Elevated risk on a metric’s watched risks, from the team’s own newest assessment. A pointer to a conversation; it changes no score.</span>' : '';
}
function cmkAskHTML(){
  const chip = CMK.metrics.find(m => m.id === CMK.ask); if (!chip) return '';
  const turningOn = !chip.on;
  const nothingWatched = turningOn && chip.watches === 0 ? '<p class="cap cmknote">This metric doesn’t watch any risk yet, so nothing will be marked until the metrics file names one.</p>' : '';
  return `<form class="cmkform" aria-label="${turningOn ? 'Switch on' : 'Switch off'} Elevated risk markers for ${esc(chip.name)}">
    <p class="cmkq"><b>${turningOn ? 'Switch on' : 'Switch off'} Elevated risk markers for ${esc(chip.name)}?</b></p>
    <p class="cap cmknote">${turningOn ? 'Everyone who sees the CTO view will then see which teams have an Elevated risk this metric watches.' : 'The markers for this metric will disappear from the CTO view.'} No score changes.</p>${nothingWatched}
    <label for="cmkwhy">Why? (kept in the history of this setting)</label>
    <textarea id="cmkwhy" name="reason" maxlength="500" required></textarea>
    ${byField()}
    ${CMK.error ? `<p class="lverr" role="alert">${esc(CMK.error)}</p>` : ''}
    <div class="btns"><button class="pri" type="submit" ${CMK.busy ? 'disabled' : ''}>${CMK.busy ? 'Saving…' : 'Save'}</button> <button type="button" data-act="cmk-cancel">Cancel</button></div></form>`;
}
function cmkRowHTML(){
  if (S.snap) return '';
  cmkLoad();
  const shown = CMK.can ? CMK.metrics : CMK.metrics.filter(m => m.on);
  if (!shown.length) return '';
  const chip = m => CMK.can
    ? `<button type="button" class="cmkchip ${m.on ? 'on' : 'off noprint'}" data-act="cmk-ask" data-m="${esc(m.id)}" aria-pressed="${m.on}" aria-label="${esc(m.name)}: markers ${m.on ? 'On' : 'Off'}. Choose to switch ${m.on ? 'off' : 'on'}."><span class="cmkdot" aria-hidden="true"></span>${esc(cmkShortName(m.name))}<span class="cmkstate">${m.on ? 'On' : 'Off'}</span></button>`
    : `<span class="cmkchip on"><span class="cmkdot" aria-hidden="true"></span>${esc(cmkShortName(m.name))}<span class="cmkstate">On</span></span>`;
  const lead = CMK.can ? 'Switch a metric On to mark the teams whose own newest risk assessment has an Elevated risk that the metric watches. A marker points to a conversation and changes no score.'
    : 'These metrics mark the teams whose own newest risk assessment has an Elevated risk that the metric watches. A marker points to a conversation and changes no score.';
  return `<section class="cmk" aria-label="Elevated risk markers"><h2>Elevated risk markers</h2><p class="cap">${lead}</p><div class="cmkchips">${shown.map(chip).join('')}</div>${CMK.ask && CMK.can ? cmkAskHTML() : ''}</section>`;
}
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act^="cmk-"]'); if (!b) return;
  if (b.dataset.act === 'cmk-ask') { CMK.ask = CMK.ask === b.dataset.m ? null : b.dataset.m; CMK.error = ''; }
  else if (b.dataset.act === 'cmk-cancel') { CMK.ask = null; CMK.error = ''; }
  else return;
  S.keepScroll = true; render();
  const box = document.getElementById('cmkwhy'); if (box) box.focus({preventScroll:true});
});
document.addEventListener('submit', e => {
  const form = e.target.closest('.cmkform'); if (!form) return; e.preventDefault();
  const chip = CMK.metrics.find(m => m.id === CMK.ask); if (!chip || CMK.busy) return;
  const reason = form.elements.reason.value.trim();
  if (!reason) { CMK.error = 'Say why, so the record shows the reason for the change.'; S.keepScroll = true; render(); return; }
  const by = liveName(form);
  CMK.busy = true; CMK.error = ''; S.keepScroll = true; render();
  apiPost('/api/edit/cto-risk-markers/save', {action:'edit', key:chip.id, values:{show:chip.on ? 'no' : 'yes'}, reason, by})
    .then(() => { CMK.ask = null; CMK.state = null; })
    .catch(x => { CMK.error = x.message; })
    .finally(() => { CMK.busy = false; S.keepScroll = true; render(); });
});
