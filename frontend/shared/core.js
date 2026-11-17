/* The page's data, the month and role being viewed, and the small helpers every page uses. */
"use strict";
const D = JSON.parse(document.getElementById('data').textContent);
/* Per-metric wording comes from config/metrics.json (each card's 'wording'; owner, 8 Nov 2026). */
const MW = k => Object.fromEntries(Object.entries((D.dictionary && D.dictionary.metrics) || {}).filter(([, x]) => x.wording && x.wording[k]).map(([id, x]) => [id, x.wording[k]]));
const PIDS = Object.keys(D.periods).sort();                                   // months in the data, oldest first
const PSCORED = PIDS.filter(p => !D.periods[p].meta.not_scored);              // months with a score (others only have uploads, or nothing yet)
const PTEAMS = PSCORED.filter(p => !D.periods[p].meta.no_teams && Object.keys(D.periods[p].families || {}).length);   // scored months that have L3 teams (a month scored without HR has none)
const START_MONTH = PTEAMS[PTEAMS.length - 1] || PSCORED[PSCORED.length - 1] || PIDS[PIDS.length - 1];   // open on the newest month with a score, else the newest month in the data (every month is open: no month lock, owner 17 Nov 2026)
const OPEN_MONTH = (() => { try { const m = sessionStorage.getItem('trust_open_month'); sessionStorage.removeItem('trust_open_month'); return m; } catch (e) { return null; } })();
const S = {p:(OPEN_MONTH && D.periods[OPEN_MONTH]) ? OPEN_MONTH : START_MONTH, r:(D.families || []).length ? 'cto' : 'tr', form:null, lastFam:null, snap:false};   // no families yet: open on Tech Risk, where files are uploaded (owner, 4 Nov 2026)
// Type trustCheck() in the browser console (F12) to see what the page received: each month, whether it is scored,
// how many L3 teams it has, and which month and role are showing. Reads only; changes nothing (owner, 17 Nov 2026).
const PAGE_CODE = 'clean72';     // the page code's version; the server's is D.code_version (config/version.txt). Change both together.
window.trustCheck = () => {
  const runs = D.last_runs || {}, scoredAt = (runs.score || {});
  const rows = PIDS.map(m => ({month: m, scored: !D.periods[m].meta.not_scored, 'L3 teams': D.periods[m].meta.no_teams ? '0 (no HR this month)' : Object.keys(D.periods[m].families || {}).length,
    'firm TRUST': D.periods[m].firm_trust == null ? 'not scored' : D.periods[m].firm_trust,
    'last updated': scoredAt[m] ? `${scoredAt[m].at} by ${scoredAt[m].by || '?'}` : '—'}));
  const same = D.code_version === PAGE_CODE;
  console.log(`Page code ${PAGE_CODE}, server code ${D.code_version || 'unknown'}${same ? '' : ' (DIFFERENT: refresh with Ctrl+F5; if it stays, the server is running an older deploy)'}.`);
  console.log(`Last published: ${runs.publish ? `${runs.publish.at} by ${runs.publish.by || '?'}` : 'not recorded'}.`);
  console.log(`L3 teams listed: ${(D.families || []).length}. Showing ${S.p} as ${S.r}. Opens on ${START_MONTH}.`);
  console.table(rows);
  return 'Done: copy the lines above and send them on.';
};
/* A refresh keeps the month and the "View as" role (owner, 9 Nov 2026): kept in this browser tab only. The page
   (route) is already in the address. parse() still checks the role against what the person may see. */
try { const v = JSON.parse(sessionStorage.getItem('trust_view') || 'null');
  if (v && v.p && D.periods[v.p]) S.p = v.p;
  if (v && typeof v.r === 'string' && v.r) S.r = v.r; } catch (_) {}
const keepView = () => { try { sessionStorage.setItem('trust_view', JSON.stringify({p:S.p, r:S.r})); } catch (_) {} };
const COMMENTS = [];                       // this month's comments, loaded from the server (liveLoad)
const $ = s => document.querySelector(s);
/* one chip vocabulary: team bubble (families, sub-teams, providers), data-source bubble (systems of record), word tag (descriptors); status chips are chip() */
const DBG = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false"><ellipse cx="8" cy="3.5" rx="5.5" ry="2" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M2.5 3.5v9c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-9M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" fill="none" stroke="currentColor" stroke-width="1.4"/></svg>';
const bTeam = (t, cls) => `<span class="bub-team${cls ? ' ' + cls : ''}">${esc(t)}</span>`;
const bSrc = t => `<span class="bub-src">${DBG}<span>${esc(t)}</span></span>`;
const tagW = t => `<span class="tag">${esc(t)}</span>`;
const MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const FULLMON = ['January','February','March','April','May','June','July','August','September','October','November','December'];
const monthLabel = pid => FULLMON[+pid.slice(5) - 1] + ' ' + pid.slice(0, 4);   // "2026-11" becomes "November 2026"
const nfmt = n => Number(n).toLocaleString('en-US', {maximumFractionDigits:1});
const lcFirst = s => /^Tier /.test(s) ? s : s.charAt(0).toLowerCase() + s.slice(1);   // "Releases" becomes "releases"; "Tier 0/1 apps" stays
const fd = iso => { const [y,m,d] = iso.slice(0,10).split('-'); return `${+d} ${MON[m-1]} ${y}`; };
const P = () => D.periods[S.p];
const fam = id => D.families.find(f => f.id === id);
const met = id => D.metrics.find(m => m.id === id);
const BLK = c => D.blocks.find(l => l.code === c);
const monthOf = pid => D.periods[pid].meta.label.split(' ')[0];
const PRIOR = Object.fromEntries(PIDS.slice(1).map((p, i) => [p, PIDS[i]]));   // previous month in the data (none for the first month)
const priorName = () => FULLMON[(+S.p.slice(5) - 2 + 12) % 12];                  // name of the calendar month before the selected one
const isWanted = m => { const dm = (D.dictionary.metrics || {})[m.id] || {}; return !!(m.not_measured || m.wanted_shown || dm.not_measured || dm.wanted_shown); };   // not measured yet: wanted (no data source) or in progress
/* What is missing this month, split in two (owner review, 5 Nov 2026): a metric that is WANTED (no data source yet) is not the same as a
   provider's file that was EXPECTED and did not arrive. Used by the story, the print banner and the provider count. */
function missingFacts(p){
  const fr0 = Object.values(p.families)[0], wanted = [], gaps = [], provs = new Set();
  if (!fr0) return {wanted, gaps, provs:[], suppressed:false, expected:[], scoredBlocks:0};
  D.blocks.forEach(l => { const live = D.metrics.filter(m => m.block === l.code && !isWanted(m));
    if (!live.length) { wanted.push(l); return; }
    const gone = live.filter(m => fr0.metrics[m.id] && fr0.metrics[m.id].status === 'DNR');
    if (gone.length) { gone.forEach(m => provs.add(m.provider)); gaps.push({block:l, got:live.length - gone.length, of:live.length}); } });
  const expected = D.providers_all.filter(pr => D.metrics.some(m => m.provider === pr && !isWanted(m)));
  const scoredBlocks = D.blocks.filter(l => Object.values(p.families).some(fr => fr.blocks[l.code] && fr.blocks[l.code].score != null)).length;
  return {wanted, gaps, provs:[...provs], suppressed: !!(p.firm_incomplete && PRIOR[S.p]), expected, scoredBlocks};
}
/* Short form of the not-received facts (5 Nov 2026): blocks with nothing arrived are named once as "not scored";
   only blocks with some metrics in get a count. */
const gapsLine = mf => { if (!mf.gaps.length) return '';
  const none = mf.gaps.filter(g => !g.got), part = mf.gaps.filter(g => g.got);
  const bits = [none.length ? `${listOf(none.map(g => g.block.name))} ${none.length === 1 ? 'isn’t' : 'aren’t'} scored` : '',
                part.length ? listOf(part.map(g => `${g.block.name} rests on ${g.got} of ${plural(g.of, 'metric', 'metrics')}`)) : ''].filter(Boolean);
  return `${listOf(mf.provs)}’s ${monthOf(S.p)} ${mf.provs.length === 1 ? 'file' : 'files'} did not arrive, so ${bits.join(' and ')}`; };
const wantedLine = mf => mf.wanted.length ? `${listOf(mf.wanted.map(l => l.name))} ${mf.wanted.length === 1 ? 'isn’t' : 'aren’t'} measured yet (no data source)` : '';
const num1 = v => Number(v).toFixed(1);
const fv = (m, v) => m.wanted_shown ? 'Wanted' : v == null ? 'No data' : m.pass_fail ? Math.round(v) + ' ' + m.unit : m.unit === '%' ? num1(v) + '%' : num1(v) + ' ' + m.unit;
/* Pass/fail metrics (owner decision O-14: CyberArk vaulting, SailPoint governance): counted in accounts or apps, not rates; no tolerance thresholds.
   Green = every eligible item is done; Amber = any is not; Red = a Tier 0/1 app (or an account of one) is not. The status is computed in data.json. */
const isPF = m => !!(m && m.pass_fail);
const PFW = {'SE-04':{done:'vaulted', todo:'not yet vaulted', all:'All vaulted', t01:'account of a Tier 0/1 app'}, 'SE-05':{done:'governed', todo:'not yet governed', all:'All governed', t01:'Tier 0/1 app'}};
const pfUnder = (m, o) => { const u = Math.round(o.denominator) - Math.round(o.numerator); return u <= 0 ? PFW[m.id].all : u + ' ' + PFW[m.id].todo; };
/* One-line tip for a building block cell (owner, 4 Nov 2026): name the metrics behind the score, and for each one
   that isn't counted say in a few words why. Nothing else. */
const WHY_SHORT = (y, m) => {
  const r = y.reason || '';
  if (y.status === 'DNR') { const dm = (D.dictionary.metrics || {})[m.id] || {}; return /switched on/i.test(r) ? 'not switched on' : dm.not_measured ? 'wanted, no source yet' : 'no data arrived'; }
  if (y.status === 'Low confidence') return 'too few items to score';
  if (y.status === 'Info only') return 'information only';
  if (y.status === 'Wanted') return 'wanted';
  if (y.status === 'Not Tier 0/1') return 'not Tier 0/1';
  if (/tolerance threshold/i.test(r)) { const n = r.match(/(\d+) are needed/); return `no tolerance threshold yet${n ? ` (needs ${n[1]} L3 teams)` : ''}`; }
  if (/not placed|No .* placed/i.test(r)) return 'nothing placed with this L3 team yet';
  if (/^No /.test(r)) return 'nothing to count';
  return 'not scored';
};
const blockTip = (l, x, extra, ms) => {
  const parts = [], rest = [];
  const byWhy = new Map();      // metrics not counted, grouped by the reason, so the line stays short
  (ms || []).forEach(([m, y]) => {
    if (!y) return;
    if (SCORED.includes(y.status)) parts.push(`${m.name} ${y.status}${y.override && y.status === 'Red' ? ' (automatic rule)' : ''}`);
    else { const w = WHY_SHORT(y, m); byWhy.set(w, [...(byWhy.get(w) || []), m]); }
  });
  byWhy.forEach((ms1, w) => rest.push(ms1.length === 1 ? `${ms1[0].name}: ${w}` : `${ms1.length} metrics: ${w}`));
  let t;
  if (x.score == null) t = `${l.name} not scored — ${x.status === 'Not Tier 0/1' ? 'no Tier 0/1 apps' : rest.join('; ') || 'nothing arrived'}`;
  else t = `${l.name} ${x.score}, ${x.status} — ${parts.join(', ')}${x.capped ? (x.score === CAP().automatic_red_block ? `; held at ${x.score} by the automatic Red rule` : `; held at ${x.score} because a metric is Red`) : ''}${rest.length ? `; not counted: ${rest.join('; ')}` : ''}`;
  if (x.delta) t += `; ${x.delta > 0 ? 'up' : 'down'} ${Math.abs(x.delta)} since ${priorName()}`;
  return extra ? `${t}. ${extra}` : t;
};
const resTxt = (m, y) => isPF(m) ? (y.numerator == null ? 'No data' : countText(m, y)) : fv(m, y.value);
const PF_BASIS_TXT = 'Pass/fail (not calibrated)';
const BASIS = {Policy:'Policy', Calibrated:'Prevailing median', Placeholder:'Placeholder'};
/* D-99: where the median sets only the Red limit (Green stays at policy) the threshold record carries sets:'red' */
const basisName = t => (t.basis === 'Policy' && t.set_from ? 'Fixed (from median)' : BASIS[t.basis] || t.basis) + (t.basis === 'Calibrated' && t.sets === 'red' ? ' (Red limit)' : '');
/* score caps are settings (owner, 3 Nov 2026): each month shows the caps it was scored with */
const BLOCKS_NEEDED_BEFORE_ANY_MONTH = 3;   // used only until a month brings its own setting; the same default as the back end (scoring.py COVERAGE)
const NEED_BLOCKS = () => { let c = {}; try { c = (D.periods[S.p] || {}).coverage || {}; } catch (e) {} return c.trust_min_blocks || BLOCKS_NEEDED_BEFORE_ANY_MONTH; };   // building blocks a TRUST score needs (setting "coverage")
const NUMW = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven'];
/* The scoring numbers the page shows in words (points, bands, caps) come from the method parameters, never typed here. */
const METHOD = D.method.parameters;
/* Words for the score bands and the points, written from the method parameters: "Green 80+ · Amber 50–79 · Red below 50". */
const bandWords = () => `Green ${METHOD.band_green_from}+ · Amber ${METHOD.band_amber_from}–${METHOD.band_green_from - 1} · Red below ${METHOD.band_amber_from}`;
const pointsWords = joiner => ['Green', 'Amber', 'Red'].map(status => `${status} ${METHOD.points[status]}`).join(joiner);   // "Green 100, Amber 50, Red 0"
const CAP = () => { let pc = {}; try { pc = (D.periods[S.p] || {}).caps || {}; } catch (e) {}
  const fromMethod = {automatic_red_block:METHOD.cap_block_automatic_rule, red_metric_block:METHOD.cap_block_any_red_metric, red_block_trust:METHOD.cap_trust_any_red_block};
  return Object.assign(fromMethod, D.caps || {}, pc); };
const RULE_TEXT = {'TE-02':{phrase:'Release with client impact', of:'of releases without a revert'}, 'SE-03':{phrase:'Critical secret overdue', of:'of open secrets past SLA'}, 'SE-06':{phrase:'End-of-life component on a Tier 0/1 internet-facing app', of:'of hosted apps affected'}};
const RULE = {client_impact:'a release with client impact', critical_secret:'an overdue critical secret', t01_internet_eol:'an end-of-life component on a Tier 0/1 internet-facing app'};
const SCORED = ['Green','Amber','Red'];
const RANK = {Green:0, Amber:1, Red:2};
