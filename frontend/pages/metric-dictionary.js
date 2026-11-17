/* Metric dictionary: every metric's card, the table view, proposals and retirement. */
"use strict";
/* ---------- Metric dictionary ---------- */
const DICT = {q:'', form:null, sent:null, focus:null, panel:null, hist:null, fv:null, pf:false, pv:null, pc:null, ret:null, showRet:false, sentProp:null};
const DX = id => D.dictionary.metrics[id];
const SCALE = {'%':100, 'per 10 apps':10, 'per 100 releases':100};
const prevPid = pid => { let [y, m] = pid.split('-').map(Number); if (--m === 0) { m = 12; y--; } return y + '-' + String(m).padStart(2, '0'); };
const dirWord = m => m.higher_is_better ? 'Higher is better' : 'Lower is better';
const OVERRIDE_WORDS = {
  client_impact:`Any release with client impact makes this metric Red, whatever the rate. The building block is then capped at ${CAP().automatic_red_block}.`,
  critical_secret:`Any overdue Emergency or Critical secret makes this metric Red, whatever the rate. The building block is then capped at ${CAP().automatic_red_block}.`,
  t01_internet_eol:`Any end-of-support component on an app that is both Tier 0/1 and internet-facing makes this metric Red, whatever the rate. The building block is then capped at ${CAP().automatic_red_block}.`};
const DICT_FIELDS = ['Calculation (formula)','Population','Exclusions','Counting rules','When it counts','Minimum population','Green tolerance or Red limit','Risk it watches','Known limitations','Other'];
const dRow = (k, v) => `<dt>${k}</dt><dd>${v}</dd>`;
const dBullets = a => a.length ? `<ul class="dbul">${a.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : '<p class="muted" style="margin:0">None recorded.</p>';

function dictRow(m, sel){
  const st = metState(m.id);
  return `<div class="dictrow${sel ? ' sel' : ''}${st === 'measured' ? '' : ' wanted'}" role="option" tabindex="0" aria-selected="${sel ? 'true' : 'false'}" data-act="dict-select" data-id="${m.id}"><span class="dr1"><span class="id">${m.id}</span> · <b>${esc(m.name)}</b>${st === 'measured' ? '' : ` <span class="mchip gray" style="cursor:default">${st}</span>`}${isTR() && RET[m.id] ? ' ' + tagW('Retirement proposed') : ''}</span></div>`;
}
function dictFilter(){
  const inp = $('#dsearch'); if (!inp) return;
  const q = inp.value.trim().toLowerCase(); DICT.q = inp.value; let n = 0;
  document.querySelectorAll('.dictrow').forEach(r => { const m = met(r.dataset.id), ok = !q || r.dataset.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q); r.hidden = !ok; if (ok) n++; });
  document.querySelectorAll('.dgl').forEach(l => { const any = !!l.querySelector('.dictrow:not([hidden])'); l.hidden = !any; const h = $('#dg-' + l.dataset.l); if (h) h.hidden = !any; });
  $('#dcount').textContent = `${n} ${n === 1 ? 'metric' : 'metrics'}`; $('#dnone').hidden = n > 0;
}
/* ---------- The dictionary card, short form (owner, 15 Nov 2026): three step lines, one colored scale, plain rows ---------- */
/* A threshold in plain words, with its unit: "95%" or "4 per 10 apps". */
function dictThresholdText(m, value){
  const unit_suffix = m.unit === '%' ? '%' : ' ' + m.unit;
  return nfmt(value) + unit_suffix;
}
/* The Compare line: where Green, Amber and Red start, in words. Empty when the metric has no tolerance threshold. */
function dictCompareText(m, threshold){
  const unit_note = m.unit === '%' ? '' : ` (${m.unit})`;
  const number_text = value => m.unit === '%' ? nfmt(value) + '%' : nfmt(value);
  const green_text = number_text(threshold.green);
  const red_text = number_text(threshold.red);
  const has_amber_band = threshold.green !== threshold.red;
  if (m.higher_is_better){
    const amber_part = has_amber_band ? ` · Amber down to ${red_text}` : '';
    return `Green ${green_text} or better${amber_part} · Red below ${red_text}${unit_note}`;
  }
  const amber_part = has_amber_band ? ` · Amber up to ${red_text}` : '';
  return `Green ${green_text} or lower${amber_part} · Red above ${red_text}${unit_note}`;
}
/* One step line. The full wording sits in the tooltip, so a long line can be cut with an ellipsis and nothing is lost. */
function dictStepLine(number, title, text, full_text){
  return `<li class="dstep" data-tip="${esc(full_text || text)}"><span class="dsn">${number}</span><b class="dsh">${title}</b><span class="dst">${esc(text)}</span></li>`;
}
function dictSteps(m, x, threshold, count_labels){
  const longest_line = 56;                       // characters that fit on one line at 1280 wide
  const lower_case_second = lcFirst(count_labels[1]);
  const count_full = `Count ${lcFirst(count_labels[0])}`;
  const count_text = count_full.length > longest_line ? 'Count the items this metric is about' : count_full;
  const scale_number = SCALE[m.unit];
  const unit_note = m.unit === '%' ? '' : ` (${m.unit})`;
  const calculate_full = x.pass_fail ? `A count, not a rate: out of ${lower_case_second}` : `Divide by ${lower_case_second}, × ${scale_number}${unit_note}`;
  const calculate_text = calculate_full.length > longest_line ? (x.pass_fail ? 'A count, not a rate' : `Divide by the total, × ${scale_number}${unit_note}`) : calculate_full;
  const compare_full = x.pass_fail ? x.pass_fail_rule
    : !m.scored ? 'Shown, not scored'
    : threshold ? dictCompareText(m, threshold)
    : 'No tolerance threshold yet, so it is not scored';
  const compare_text = x.pass_fail ? 'Pass or fail; the rule is under More detail' : compare_full;
  return `<ol class="dsteps">${dictStepLine(1, 'Count', count_text, count_full)}${dictStepLine(2, 'Calculate', calculate_text, calculate_full)}${dictStepLine(3, 'Compare', compare_text, compare_full)}</ol>`;
}
/* The colored scale: Red, Amber and Green bands from the tolerance thresholds, and a marker where the firm's result sits.
   The scale zooms in around the thresholds so all three bands can be seen. */
function dictScale(m, threshold, firm_result, month_label){
  const gap_between_thresholds = Math.abs(threshold.green - threshold.red) || Math.abs(threshold.green) * 0.1 || 1;
  const widest_allowed = m.unit === '%' ? 100 : Infinity;
  const lowest_threshold = Math.min(threshold.green, threshold.red);
  const highest_threshold = Math.max(threshold.green, threshold.red);
  /* If a threshold sits on the edge of what the unit allows (100%, or 0), leave a little room so its band can still be seen. */
  const room_at_the_edge = gap_between_thresholds * 0.6;
  const axis_start = lowest_threshold <= 0 ? -room_at_the_edge : Math.max(0, lowest_threshold - gap_between_thresholds * 2);
  const axis_end = highest_threshold >= widest_allowed ? widest_allowed + room_at_the_edge : Math.min(widest_allowed, highest_threshold + gap_between_thresholds * 2);
  const axis_length = axis_end - axis_start;
  const position_of = value => Math.min(100, Math.max(0, (value - axis_start) / axis_length * 100));
  const low_edge = position_of(lowest_threshold);
  const high_edge = position_of(highest_threshold);
  const bands = m.higher_is_better
    ? [['dsr', 'Red', 0, low_edge], ['dsa', 'Amber', low_edge, high_edge], ['dsg', 'Green', high_edge, 100]]
    : [['dsg', 'Green', 0, low_edge], ['dsa', 'Amber', low_edge, high_edge], ['dsr', 'Red', high_edge, 100]];
  const bands_html = bands.filter(b => b[3] > b[2]).map(b => `<span class="dsb ${b[0]}" style="flex-basis:${b[3] - b[2]}%">${b[1]}</span>`).join('');
  const edges_html = [low_edge, high_edge].filter((e, i, all) => all.indexOf(e) === i).map(e => `<span class="dse" style="left:${e}%">${dictThresholdText(m, e === low_edge ? lowest_threshold : highest_threshold)}</span>`).join('');
  const has_result = firm_result && firm_result.value != null;
  const marker_position = has_result ? position_of(firm_result.value) : 0;
  const marker_html = has_result ? `<span class="dsm${marker_position > 80 ? ' right' : marker_position < 20 ? ' left' : ''}" style="left:${marker_position}%"><span class="dsml">Firm ${esc(fv(m, firm_result.value))}</span></span>` : '';
  const caption = has_result ? `Firm result in ${esc(month_label)}: ${esc(fv(m, firm_result.value))}${firm_result.status ? ' · ' + esc(firm_result.status) : ''}.` : `No firm result in ${esc(month_label)}.`;
  return `<div class="dscale"><div class="dsarea">${marker_html}<div class="dsbar" role="img" aria-label="${esc(dictCompareText(m, threshold))}. ${caption}">${bands_html}</div><div class="dsedges">${edges_html}</div></div><p class="cap dscap">${caption}</p></div>`;
}
/* A plain row: a label, then the answer. */
const dictPlainRow = (label, body) => `<div class="dpr"><dt>${label}</dt><dd>${body}</dd></div>`;

function dictCard(id, all){
  const m = met(id), x = DX(id), p = P(), t = p.thresholds[id], sc = SCALE[m.unit], pfm = !!x.pass_fail;
  const cur = t ? x.thresholds.find(v => v.version === t.version) : null;
  const chips = [ltag(m.block), bTeam(m.provider), bSrc(x.source_system)].join('');
  const MINF = D.min_families_for_threshold || 5;
  const basisTxt = pfm ? esc(x.threshold_basis) : !t ? ((m.scored) && !x.not_measured ? `Prevailing median, once at least ${MINF} L3 teams have a result. Not enough L3 teams have a result in ${esc(p.meta.label)}, so there is no tolerance threshold this month and it isn’t scored.` : '') : t.basis === 'Policy' && t.set_from ? `Fixed: set from the ${esc(t.set_from)}${t.set_on ? ' on ' + fd(t.set_on) : ''}, and reviewed each quarter by Tech Risk` : t.basis === 'Policy' && t.set_by ? (() => { const u = m.unit === '%' ? '%' : ' ' + m.unit, hb = m.higher_is_better; return `A fixed tolerance threshold, the same for every L3 team (set by ${esc(t.set_by)}${t.set_on ? ' on ' + fd(t.set_on) : ''}). Green: ${nfmt(t.green)}${u} or ${hb ? 'better' : 'lower'}. Amber: from ${nfmt(t.red)}${u} to ${hb ? 'under' : 'over'} ${nfmt(t.green)}${u}. Red: ${hb ? 'below' : 'above'} ${nfmt(t.red)}${u}.`; })() : t.basis === 'Policy' ? 'Policy: set by a firm standard'
    : t.basis === 'Calibrated' ? (t.sets === 'red' ? `Green tolerance from policy; Red limit from the <a href="${href('/glossary/prevailing-median')}">prevailing median</a>, worked out each month.` : `Compared each month with the middle L3 team (the <a href="${href('/glossary/prevailing-median')}">prevailing median</a>).${t.band != null ? (() => { const bw = m.unit === '%' ? nfmt(t.band) + ' percentage points' : nfmt(t.band) + ' ' + m.unit; return ` Green: as good as the middle L3 team or better. Amber: up to ${bw} worse. Red: more than ${bw} worse.`; })() : ''}`) : 'Placeholder: to be calibrated';
  const gapTxt = x.peer_flag_gap == null ? null : m.unit === '%' ? nfmt(x.peer_flag_gap) + ' percentage points' : Number(x.peer_flag_gap).toFixed(1).replace(/\.0$/, '') + ' ' + m.unit;
  const minPop = x.min_pop <= 1 ? 'Scored from the first item.' : `Fewer than ${x.min_pop} ${esc(lcFirst(m.denominator_label))}: shown, not scored.`;
  const zero = x.zero_text ? esc(x.zero_text) : x.zero_rule === 'BEST' ? `Best (${fv(m, 0)}) only when the provider confirms coverage; otherwise not scored.` : 'Not scored. No Best result is given.';
  const histOpen = !all && DICT.hist === id, histOk = isTR() && !all && x.thresholds.length && t;
  const histBtn = histOk ? `<button type="button" data-act="dict-hist" data-id="${id}" aria-expanded="${histOpen}" aria-controls="dhist-${id}">Version history ${histOpen ? '▴' : '▾'}</button>` : '';
  const histPanel = histOk ? `<div id="dhist-${id}" class="dhist noprint" ${histOpen ? '' : 'hidden'}>${histOpen ? verTable(x.thresholds.map(v => [m, v]), false) : ''}</div>` : '';
  const endDot = z => String(z).replace(/\.\s*$/, '') + '.';
  const pop = x.population || x.scope, exc = x.exclusions_text || x.exclusions;
  const it = IND[x.indicator_type];
  /* risk it watches */
  /* owner, 9 Nov 2026: the risks from the risk assessment (config/risks/), linked in config/metrics.json card.risks */
  const rk = (x.risks_detail || []).filter(r => !r.missing);
  const elLine = '';   // owner, 16 Nov 2026: no "Elevated for these families" line; a risk is only ever shown on its own family's page
  /* risk row (plain): the risks from the risk assessment; if none are linked, the card's own risk sentence; if neither, no row */
  const riskRowBody = rk.length ? `<ul class="rlist dprl">${rk.map(r => `<li><b>${esc(r.name)}</b> <span class="cap">${esc([r.domain, r.category].filter(Boolean).join(' · '))}</span>${r.description ? `<div>${esc(r.description)}</div>` : ''}</li>`).join('')}</ul>` : x.risk || x.why ? `<p style="margin:0">${esc(x.risk || x.why)}</p>` : '';
  const riskRow = riskRowBody ? dictPlainRow(rk.length > 1 ? 'Risks it watches' : 'Risk it watches', riskRowBody + elLine) : '';
  const indicatorLine = it ? `<div class="bubs" style="margin:12px 0 0">${tagW(it[0])}</div>` : '';
  /* how it is calculated: formula, then one consistent list */
  const formula = pfm ? `<div class="formula">Result = ${esc(cardLbl(m)[0])}, out of ${esc(lcFirst(cardLbl(m)[1]))}</div><div class="cap" style="margin-top:4px">A count, not a rate.</div>`
    : `<div class="formula">Value = ${esc(cardLbl(m)[0])} ÷ ${esc(cardLbl(m)[1])} × ${sc} (${esc(m.unit)})</div><div class="cap" style="margin-top:4px">Compared at 1 decimal place.</div>`;
  const pl = k => k + ((x.proposed_fields || []).includes(k) ? ' ' + tagW('Proposed') : '');   // D-69: wording awaiting approval
  const calc = `<dl class="dd" style="margin-top:10px">${dRow(pl('Population'), esc(endDot(pop)))}
    ${CR[id] ? dRow('Counting rules', CR[id].map(r => esc(endDot(r))).join('<br>')) : ''}
    ${m.scored && !x.not_measured ? dRow('Minimum population', minPop) : ''}${dRow('None to measure', zero)}
    ${x.tier01_only ? dRow('Applies to', 'L3 teams that own Tier 0/1 apps; others show “Not Tier 0/1”.') : ''}</dl>`;
  /* owner, 3 Nov 2026: the checks sit under the formula, folded, so the formula reads with what it counts */
  const checks = x.checks ? `<details class="exs" style="margin-top:8px"${S.snap ? ' open' : ''}><summary>The ${x.checks.length} hygiene checks</summary><p class="cap" style="margin:8px 0 6px">One point for each check a repo passes, so 4 of ${x.checks.length} = ${Math.round(4 / x.checks.length * 100)}%. An L3 team's result is all checks passed ÷ all checks possible across its active repos.</p><dl class="dd">${x.checks.map(c => dRow(esc(c.name), esc(c.rule))).join('')}</dl>${x.info_checks && x.info_checks.length ? `<p class="cap" style="margin:6px 0 0">Shown, not scored: ${x.info_checks.map(esc).join('; ')}.</p>` : ''}</details>` : '';
  /* how it is scored: no threshold numbers (they are in the Table view) */
  /* owner, 9 Nov 2026: Basis first, right under Risk it watches; no Scored, Points or Weight rows */
  const scoreRows = (basisTxt ? dRow('Basis', basisTxt) : '') + (pfm ? dRow('Rule', esc(x.pass_fail_rule)) : x.rule_text ? dRow('Rule', esc(x.rule_text)) : '')
    + (x.item_allowance != null ? dRow('Item allowance', `Amber up to ${itemsTxt(allowOf(id), x.item_allowance)} short of Green, even below the Red limit. Red needs more than ${itemsTxt(allowOf(id), x.item_allowance)} short and a result beyond the Amber band. The allowance is a setting and applies to L3 teams only.`) : '')
    + (x.override_rule && D.automatic_red_rules !== false ? dRow('Automatic Red', OVERRIDE_WORDS[x.override_rule]) : '');   // setting automatic_red_rules (owner, 9 Nov 2026)
  const scoreSec = scoreRows ? `<section class="dsec"><h3>How it is scored</h3><dl class="dd">${scoreRows}</dl></section>` : '';
  /* flags (owner, 8 Nov 2026: hidden while the setting behind_peers_flag is off) */
  const flagged = p.watch_list.filter(w => w.kind === 'Behind peers' && w.metric_id === id).map(w => fam(w.family_id).name);
  const flagSec = `<section class="dsec"><h3>Flags</h3><p style="margin:0 0 6px">A flag puts an L3 team on the watch list as <b>Behind peers</b>. It never changes a color or points.</p><dl class="dd">
    ${pfm || !gapTxt || !m.scored || x.not_measured || (t && t.basis === 'Calibrated') ? dRow('This metric', pfm ? 'Not flagged. Pass/fail metrics are not compared with peers.' : x.not_measured ? 'Not flagged until the metric is measured.' : t && t.basis === 'Calibrated' ? 'Not flagged. Its color already compares each L3 team with the prevailing median, so a flag would say the same thing twice.' : m.scored ? 'Not flagged. Only metrics with a policy tolerance threshold are compared with peers.' : 'Not flagged. Information-only metrics are not compared with peers.')
      : dRow('Raised when', `An L3 team is at least ${gapTxt} worse than the median L3 team, and at least 5 L3 teams can be scored.`) + dRow(monthOf(S.p), flagged.length ? 'Flagged for ' + (flagged.length < 3 ? flagged.join(' and ') : flagged.slice(0, -1).join(', ') + ' and ' + flagged[flagged.length - 1]) + '.' : 'No L3 team flagged.')}</dl></section>`;
  /* limitations and mitigations */
  const lt = x.limitations_table || x.limitations.map((l, i) => ({limitation:l, mitigation:x.countermeasures[i] || '', status:x.countermeasures[i] ? 'Partly mitigated' : 'No mitigation yet'}));
  const stCls = s => s === 'Mitigated' ? 'g' : s === 'No mitigation yet' ? 'r' : 'a';
  const limSec = !lt.length ? '' : `<section class="dsec">${lt.length ? `<details class="exs"${S.snap ? ' open' : ''}><summary>Known limitations (${lt.length})</summary><table class="dt nosort"><colgroup><col style="width:37%"><col style="width:42%"><col style="width:21%"></colgroup><thead><tr><th>Limitation</th><th>Mitigation or risk acceptance</th><th>Status</th></tr></thead><tbody>${lt.map(r => `<tr><td>${esc(r.limitation)}</td><td>${esc(r.mitigation) || '—'}</td><td><span class="lst ${stCls(r.status)}">${esc(r.status)}</span></td></tr>`).join('')}</tbody></table></details>` : ''}</section>`;
  /* See the code (owner, 5 Nov 2026): links to the functions behind this metric, with the lines highlighted,
     pinned to the deployed commit. Always shown; links once config/settings.json has code_repo_url. */
  const cl = D.code_links && D.code_links.metrics && D.code_links.metrics[id];
  const hasUrl = !!(D.code_links && D.code_links.repo);
  const codeSec = cl && cl.length ? `<section class="dsec"><details class="exs"${S.snap ? ' open' : ''}><summary>See the code: ${plural(cl.length, 'place', 'places')} in the repository</summary>
    <p class="cap" style="margin:4px 0 6px">${hasUrl ? `Each link opens the deployed code (commit <code>${esc(String(D.code_links.ref).slice(0, 12))}</code>) with the lines highlighted. Shared steps (thresholds, status, building block and TRUST maths) are the same for every metric.` : `Where this is worked out in TRUST's code. These become links once the repo address is set (code_repo_url in config/settings.json).`}</p>
    <table class="dt nosort"><colgroup><col style="width:44%"><col style="width:56%"></colgroup><thead><tr><th>What it does</th><th>Where</th></tr></thead><tbody>${cl.map(r => `<tr><td>${esc(r.what)}</td><td>${(t => r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">${t}</a>` : t)(`${esc(r.file)} · <code>${esc(r.function)}()</code> lines ${r.from}–${r.to}`)}</td></tr>`).join('')}</tbody></table></details></section>` : '';
  /* footer: version + request a change */
  const form = DICT.form === id && may('propose') ? `<form class="cf dictf" data-id="${id}" aria-label="Request a change to ${id}">
    <label>What should change<br><select name="f" style="max-width:100%">${DICT_FIELDS.map(f => `<option>${f}</option>`).join('')}</select></label>
    <label>Proposed wording or calculation<textarea name="wording" required></textarea></label><label>Reason for the change<textarea name="reason" required></textarea></label>
    ${(`${byField()}${DICT.err ? `<p class="ferr" role="alert">${esc(DICT.err)}</p>` : ''}<p class="cap">Goes to Tech Risk. An approved change takes effect from the next unlocked month; nothing changes until then.</p>`)}<button class="pri" type="submit">Send request</button> <button type="button" data-act="dict-cancel">Cancel</button></form>` : '';
  const foot = `<div class="dfoot"><span class="cap">${t && cur ? `Version ${t.version} · effective from ${monthLabel(cur.effective_from)}` : ''}</span>
    ${all ? '' : `<div class="noprint dbtns" style="margin:0">${may('propose') ? `<button data-act="dict-propose" data-id="${id}">Request a change to this metric</button>` : ''}${retHTML(id, all, 'btn')}${histBtn}</div>`}</div>
    ${DICT.sent === id ? `<div class="banner" role="status">${('Sent to Tech Risk. It is listed under Proposals with the decision on it.')}</div>` : ''}${(!all) ? liveOpenFor(id) : ''}${form}${retHTML(id, all, 'body')}${histPanel}`;
  const sourceDate = (p.submissions || []).find(sub => sub.status === 'Accepted' && (sub.metrics || []).includes(id));
  const sourceText = x.source_system ? esc(x.source_system) + (sourceDate && sourceDate.data_as_of ? `, data as of ${fd(sourceDate.data_as_of)}` : '') : '';
  const exclusionsRow = exc ? dictPlainRow(pl('Exclusions'), esc(endDot(exc))) : '';
  const sourceRow = sourceText ? dictPlainRow('Data source', sourceText) : '';
  const firmResult = p.firm[id];
  const showScale = !x.not_measured && !pfm && m.scored && t;
  const stepsHtml = dictSteps(m, x, t, cardLbl(m));
  const scaleHtml = showScale ? dictScale(m, t, firmResult, p.meta.label) : '';
  /* everything the short card has no place for stays here, closed */
  const moreDetail = `<details class="exs dmore"${S.snap || all ? ' open' : ''}><summary>More detail</summary>${indicatorLine}${scoreSec}<section class="dsec"><h3>How it is calculated</h3>${formula}${checks}${calc}</section>${D.behind_peers_flag === false ? '' : flagSec}${limSec}</details>`;
  return `<article class="dcard dcardshort" id="${all ? 'dc-' + id : 'dict-card'}" aria-labelledby="dh-${id}">
    <h2 id="dh-${id}" tabindex="-1">${id} · ${esc(m.name)}</h2><div class="bubs dchips">${chips}</div>
    ${x.not_measured ? `<div class="thr-note gray" role="note"><b>${x.status === 'In progress' ? 'In progress.' : 'Wanted, not measured yet.'}</b> ${m.wanted_shown ? 'We want this number but there is no source for it yet, so it counts in no score and shows as Wanted.' : x.status === 'In progress' ? 'This metric is being built. It counts in no score yet and shows as No data on every page until it is switched on.' : 'We want this number but its data source hasn’t been onboarded (see the <a href="' + href('/datadict') + '">Data dictionary</a>), so it counts in no score and shows as No data on every page.'} What follows is the design; it will be checked against real data when the source arrives.</div>` : ''}${stepsHtml}${scaleHtml}<dl class="dpl">${riskRow}${exclusionsRow}${sourceRow}</dl>
    ${moreDetail}${codeSec}
    <section class="dsec">${foot}</section></article>`;
}

const IND = Object.fromEntries(D.method.indicator_types.map(r => [r.code, [r.name, lcFirst(r.tells)]]));

const lastIn = v => v.effective_to ? monthLabel(prevPid(v.effective_to)) : 'Open-ended';
const gTxt = (m, v) => `${m.higher_is_better ? '≥' : '≤'} ${fv(m, v.green)}`, rTxt = (m, v) => `${m.higher_is_better ? '<' : '>'} ${fv(m, v.red)}`;
/* rows = [[metric, version record], ...]; withMetric adds a Metric column (the all-metrics panel) */
function verTable(rows, withMetric){
  const W = withMetric ? [20, 8, 12, 11, 13, 13, 23] : [10, 13, 12, 15, 17, 15, 18], nw = withMetric ? ' nw' : '';
  const cols = W.map(w => `<col style="width:${w}%">`).join('');
  const head = (withMetric ? '<th>Metric</th>' : '') + '<th class="tn">Version</th><th class="tn">Green tolerance</th><th class="tn">Red limit</th>' + (withMetric ? '' : '<th>Basis</th>') + '<th>Effective from</th><th>Effective to</th><th>Approved by</th>';
  const body = rows.map(([m, v]) => `<tr>${withMetric ? `<td><a href="${href('/dictionary/' + m.id)}">${esc(m.name)}</a> <span class="id">${m.id}</span></td>` : ''}<td class="tn">${v.version}</td><td class="tn${nw}">${gTxt(m, v)}</td><td class="tn${nw}">${rTxt(m, v)}</td>${withMetric ? '' : `<td>${tagW(basisName(v))}</td>`}<td class="${nw.trim()}">${monthLabel(v.effective_from)}</td><td class="${nw.trim()}">${lastIn(v)}</td><td>${esc(v.approved_by)}, <span class="nw">${fd(v.approved_at)}</span>${v.ref ? `<div class="cap">${esc(v.ref)}</div>` : ''}</td></tr>`).join('');
  return `<table class="dt nosort"><caption class="sr-only">Threshold versions${withMetric ? '' : ' for ' + esc(rows[0][0].id)}</caption><colgroup>${cols}</colgroup><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table><p class="cap" style="margin:4px 0 0">Every version is kept.</p>`;
}

function dictTable(){
  const p = P();
  const rows = D.metrics.map(m => {
    const t = p.thresholds[m.id], sc = m.scored && t, cur = sc ? (DX(m.id).thresholds.find(v => v.version === t.version) || {}) : {}, L = BLK(m.block);
    const dash = '<span class="muted">—</span>', dxm = DX(m.id);
    if (dxm.pass_fail) return `<tr><td><a href="${href('/dictionary/' + m.id)}"><b>${esc(m.name)}</b></a> <span class="id">${m.id}</span></td><td>${ltag(m.block)}</td>
      <td class="dirc">${tagW('Pass/fail')}</td><td colspan="2">${esc(dxm.pass_fail_rule)}</td><td>${tagW(dxm.threshold_basis)}</td><td class="tn">${dash}</td><td>${dash}</td><td>${dash}</td><td>${dash}</td></tr>`;
    return `<tr><td><a href="${href('/dictionary/' + m.id)}"><b>${esc(m.name)}</b></a> <span class="id">${m.id}</span></td><td>${ltag(m.block)}</td>
      <td${m.scored ? ' class="dirc"' : ''}>${tagW(!m.scored ? 'Information only' : dirWord(m))}</td>
      <td class="tn">${sc ? gTxt(m, t) : dash}</td><td class="tn">${sc ? rTxt(m, t) : dash}</td><td>${tagW(sc ? basisName(t) : 'No threshold')}</td>
      <td class="tn">${cur.version ? cur.version : dash}</td><td>${cur.effective_from ? monthLabel(cur.effective_from) : dash}</td>
      <td>${cur.approved_by ? esc(cur.approved_by) + ', <span class="nw">' + fd(cur.approved_at) + '</span>' : dash}</td><td>${cur.ref ? esc(cur.ref) : dash}</td></tr>`; }).join('');
  const op = k => DICT.panel === k;
  return `<div class="thr-note">Policy thresholds are set in the scorecard's settings. Prevailing-median thresholds are worked out afresh each month from that month's results. Thresholds have not been through formal approval yet, so there are no versions or approval records to show.</div>
    <div class="panel" style="margin-top:8px;overflow-x:auto"><table class="dt thr"><caption class="sr-only">Tolerance thresholds in force for ${p.meta.label}</caption><colgroup><col style="width:164px"><col style="width:116px"><col style="width:132px"><col style="width:124px"><col style="width:112px"><col style="width:144px"><col style="width:64px"><col style="width:116px"><col style="width:124px"><col style="width:100px"></colgroup>
    <thead><tr><th>Metric</th><th>Building block</th><th>Direction</th><th class="tn">Green tolerance</th><th class="tn">Red limit</th><th>Basis</th><th class="tn">Version</th><th>Effective from</th><th>Approved by</th><th>Reference</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function vDictionary(arg){
  const p = P(), view = arg === 'table' && isTR(), pview = arg === 'proposals' && isTR();
  if (arg === 'all') return `<div class="dictall"><div class="titlebar"><div><h1>Metric dictionary</h1><p class="muted" style="margin:0">All ${D.metrics.length} metrics · ${p.meta.label} · ${esc(D.dictionary.version)}. Once approved, definitions are frozen and any change creates a new version approved by the Head of Tech Risk.</p></div>
    <div class="noprint"><span class="muted">To print, use your browser’s Print (Ctrl+P, or Cmd+P on a Mac).</span> <a href="${href('/dictionary')}" style="margin-left:8px">Back to the dictionary</a></div></div>${D.metrics.map(m => dictCard(m.id, true)).join('')}</div>`;
  const sel = arg && DX(arg) ? arg : null;
  const sw = isTR() ? `<div class="sgm" role="group" aria-label="Dictionary view"><button type="button" data-act="dict-view" data-v="cards" aria-pressed="${!view && !pview}">Cards</button><button type="button" data-act="dict-view" data-v="table" aria-pressed="${view}">Table</button><button type="button" data-act="dict-view" data-v="proposals" aria-pressed="${pview}">Proposals</button></div>` : '';
  const pb = isTR() && may('propose') ? `<button type="button" class="pri" data-act="pf-open" aria-expanded="${DICT.pf}" aria-controls="pformwrap">Propose a new metric</button>` : '';
  const top = `<div class="titlebar"><div><h1>Metric dictionary ${tagW(D.dictionary.version)}</h1><p class="muted" style="margin:0;max-width:820px">${pview ? (('Change requests, proposed new metrics and retirements, with the decision on each. Nothing changes in the scorecard until a decision is made and applied.')) : view ? `The Green tolerance and Red limit each scored metric is measured against in ${p.meta.label}. Anything between the two is Amber.` : `How each metric is calculated and scored. ${dictSummary()}`}</p></div>
    <div class="noprint dtools">${pb}${sw}${view || pview ? '' : `<a href="${href('/dictionary/all')}">Print dictionary</a>`}</div></div>`;
  const cProp = !view && !pview && may('propose') ? `<p class="noprint cap" style="margin:6px 0 0"><a href="${href('/dictionary' + (sel ? '/' + sel : ''))}" data-act="dict-propose" data-id="${sel || D.metrics[0].id}">Propose a change or a new metric</a></p>` : '';
  if (view) return top + pfPanel() + dictTable();
  if (pview) return top + pfPanel() + propView();
  const idx = D.blocks.map(l => `<h2 class="dgh" id="dg-${l.code}" style="--lc:${LCOL[l.code]}">${l.name}<span class="cap" style="font-weight:400;margin-left:8px">${esc(l.question)}</span></h2>
    <div class="dgl" data-l="${l.code}" role="listbox" aria-labelledby="dg-${l.code}">${D.metrics.filter(m => m.block === l.code).map(m => dictRow(m, m.id === sel)).join('')}</div>`).join('');
  return `${top}${pfPanel()}${cProp}
    <div class="dictwrap"><div class="dictside noprint"><input type="search" id="dsearch" class="dsearch" placeholder="Find a metric" aria-label="Find a metric by ID or name" aria-controls="dictidx" autocomplete="off" value="${esc(DICT.q || '')}"><p class="cap dcount" id="dcount" role="status" aria-live="polite">${D.metrics.length} metrics</p>
    <label class="dretchk noprint"><input type="checkbox" id="dretired"${DICT.showRet ? ' checked' : ''}> Show retired</label><p class="muted dnone" id="dretnote" role="status" ${DICT.showRet ? '' : 'hidden'}>No retired metrics</p>
    <nav class="dictindex" id="dictidx" aria-label="Metrics by building block">${idx}<p class="muted dnone" id="dnone" hidden>No metric matches.</p></nav></div>
    <div>${sel ? dictCard(sel, false) : '<div class="dcard empty"><p class="muted" style="margin:0">Select a metric on the left to see how it is calculated, how it is scored, and how we know it is complete and accurate.</p></div>'}</div></div>`;
}

/* ---------- Metric lifecycle: building block colors, intake (proposals), retirement. Saved by the server (/api/proposals). ---------- */
const LCOL = {SEC:'#9d174d', RES:'#0f766e', STA:'#4338ca', REL:'#334155', ACC:'#1d4ed8', MOD:'#b45309'};      // per-block colors, deliberately not status colours
const hexMix = (h, a) => '#' + [1, 3, 5].map(i => Math.round(parseInt(h.slice(i, i + 2), 16) * a + 255 * (1 - a)).toString(16).padStart(2, '0')).join('');
const ltag = (code, label) => LCOL[code] ? `<span class="tag ltag" style="--lc:${LCOL[code]};--lb:${hexMix(LCOL[code], .5)};--lg:${hexMix(LCOL[code], .08)}">${esc(label || BLK(code).name)}</span>` : tagW(label || 'Building block not chosen');
const NOTE_PROPOSALS = ('Proposals are saved for the Head of Tech Risk’s review. Nothing changes in the scorecard until a decision is made and applied.');
const PF_UNITS = ['%', 'per 10 apps', 'per 100 releases'], PF_TIMES = ['Snapshot', 'Flow', 'Rolling 3 months'], PF_BASIS = ['Policy', 'Prevailing median', 'Placeholder'];
const PF_ZERO = {NS:'Not scored — no coverage', BEST:'Best only when the provider confirms coverage'};
const PF_TESTS = [['Answers the building block\'s question', 'A Green result would tell leaders something true about the building block\'s question.'],
  ['A system of record exists with L3 team attribution', 'Every item can be traced to an L3 team in a named system.'],
  ['An owner will sign a data contract', 'The provider team has agreed to supply the data every month.'],
  ['A policy basis exists, or it can be calibrated', 'The Green tolerance comes from a policy, or from the median of L3 team values.'],
  ['Hard to game', 'The limitations and counter-measures above show how the number could be gamed and how we would notice.'],
  ['Not a duplicate of an existing metric', 'No current metric already answers the same question.']];
const PROP_STATUS = {'Wanted':'n', Proposed:'i', Returned:'a', Approved:'g', Declined:'r', Draft:'n', Withdrawn:'n'};

const PROPS = [];                                 // proposals come from the server (LIVE.props)
const RET = {};                                  // retirement proposals by metric id (in memory)
const lines = s => String(s || '').split(/\n+/).map(x => x.trim()).filter(Boolean);
const nextId = c => { if (!LCOL[c]) return ''; const pre = (D.metrics.find(m => m.block === c) || {id:c.slice(0, 2) + '-'}).id.slice(0, 2); const ns = [...D.metrics.map(m => m.id), ...PROPS.map(p => p.id)].filter(i => i && i.startsWith(pre + '-')).map(i => +i.slice(3) || 0); return pre + '-' + String((ns.length ? Math.max(...ns) : 0) + 1).padStart(2, '0'); };
const nextPid = pid => { let [y, m] = pid.split('-').map(Number); if (++m === 13) { m = 1; y++; } return y + '-' + String(m).padStart(2, '0'); };
const retMonths = () => { const pv = Object.values(D.periods).find(x => x.meta.status === 'Preview'), a = pv ? pv.meta.id : Object.keys(D.periods).sort().pop(); return [a, nextPid(a)]; };
const fvU = (u, v) => v === '' || v == null || isNaN(+v) ? '—' : u === '%' ? num1(v) + '%' : num1(v) + ' ' + u;

const CR = MW('counting_rules')   /* only rules not already stated in Population or Exclusions: wording.counting_rules */;
const CL = MW('card_labels')   /* card formula labels: wording.card_labels */;
const cardLbl = m => CL[m.id] || [m.numerator_label.replace(/^Prod /, 'Production '), m.denominator_label.replace(/^Prod /, 'Production ')];

/* ----- retirement (on the dictionary card, Tech Risk only) ----- */
function retHTML(id, all, part){
  if (!isTR() || all || !may('propose')) return '';
  const lr = (liveProps().find(p => p.live.kind === 'retire' && p.live.metric === id && p.live.status === 'open'));
  const r = ((lr ? {reason:lr.live.detail.reason, repl:lr.live.detail.replacement || '', from:lr.live.detail.effective, by:lr.by} : null));
  if (part === 'btn') return r ? '' : `<button type="button" data-act="ret-open" data-id="${id}" aria-expanded="${DICT.ret === id}">Retire this metric</button>`;
  if (r) return `<div class="dretire noprint"><p class="retline" id="ret-${id}" role="status" tabindex="-1">Retirement proposed — awaiting the Head of Tech Risk</p>
    <p class="cap" style="margin:0 0 8px">Effective from ${monthLabel(r.from)}${r.repl ? ' · Replacement: ' + esc(r.repl + ' ' + met(r.repl).name) : ''} · Reason: ${esc(r.reason)}</p>
    ${(`<p class="cap" style="margin:0">Proposed by ${esc(r.by)}. The Head of Tech Risk decides under <a href="${href('/dictionary/proposals')}">Proposals</a>.</p>`)}</div>`;
  if (DICT.ret === id) return `<div class="dretire noprint"><form class="retf" data-id="${id}" novalidate aria-label="Retire ${id}">
    <label>Reason for retiring this metric<textarea name="reason" rows="3" aria-describedby="rer-${id}"></textarea><span class="ferr" id="rer-${id}" style="display:block" hidden></span></label>
    <label>Replacement metric (optional)<select name="repl"><option value="">None</option>${D.metrics.filter(o => o.id !== id).map(o => `<option value="${o.id}">${o.id} · ${esc(o.name)}</option>`).join('')}</select></label>
    <label>Effective from<select name="from">${retMonths().map(q => `<option value="${q}">${monthLabel(q)}</option>`).join('')}</select></label>
    ${(`${byField()}${DICT.err ? `<p class="ferr" role="alert">${esc(DICT.err)}</p>` : ''}`)}<p class="cap">A retired metric is kept in history and excluded from scoring from the effective month; building blocks re-average over the remaining metrics. ${NOTE_PROPOSALS}</p>
    <button class="pri" type="submit">Submit for approval</button> <button type="button" data-act="ret-cancel" data-id="${id}">Cancel</button></form></div>`;
  return '';
}

/* ----- intake form (side panel) ----- */
function pfSnap(){
  const f = $('#pform'); if (!f || !DICT.pf) return;
  const o = {}; for (const el of f.elements) { if (!el.name) continue; if (el.type === 'checkbox') o[el.name] = el.checked; else if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; } else o[el.name] = el.value; }
  DICT.pv = o;
}
function pfPanel(){
  if (!DICT.pf || !isTR()) return '';
  const V = DICT.pv || {}, v = k => esc(V[k] ?? '');
  const sel = (k, opts, ph, dflt) => `<select id="pf-${k}" name="${k}" aria-describedby="pe-${k}">${ph ? `<option value="">${ph}</option>` : ''}${opts.map(([val, lab]) => `<option value="${esc(val)}"${(V[k] ?? dflt) === val ? ' selected' : ''}>${esc(lab)}</option>`).join('')}</select>`;
  const txt = k => `<input type="text" id="pf-${k}" name="${k}" value="${v(k)}" aria-describedby="pe-${k}" autocomplete="off">`;
  const num = k => `<input type="number" id="pf-${k}" name="${k}" value="${v(k)}" step="any" min="0" inputmode="decimal" aria-describedby="pe-${k}">`;
  const area = (k, rows, max) => `<textarea id="pf-${k}" name="${k}" rows="${rows}"${max ? ` maxlength="${max}"` : ''} aria-describedby="pe-${k}${max ? ' pc-' + k : ''}">${v(k)}</textarea>`;
  const fld = (k, label, ctl, hint, extra) => `<div class="pfld"><label for="pf-${k}">${label}</label>${hint ? `<span class="cap" id="ph-${k}">${hint}</span>` : ''}${ctl}${extra || ''}<p class="ferr" id="pe-${k}" hidden></p></div>`;
  const today = fd(new Date().toISOString());
  const blockOpts = D.blocks.map(l => [l.code, l.name]), provs = D.providers_all.map(x => [x, x]);
  const why = String(V.why || '').length;
  return `<section class="pform noprint" id="pformwrap" role="region" aria-labelledby="pf-h"><form id="pform" novalidate>
    <div class="ph"><h2 id="pf-h" tabindex="-1">Propose a new metric</h2><p class="cap">${NOTE_PROPOSALS}</p></div>
    <div class="pb"><div class="pfsum" id="pf-sum" role="alert" tabindex="-1" hidden></div>
    <fieldset class="psec"><legend>Identity</legend>
      ${fld('name', 'Metric name', txt('name'))}
      ${fld('building block', 'Building block', sel('block', blockOpts, 'Choose a building block', ''))}
      ${fld('provider', 'Provider team', sel('provider', provs, 'Choose a team', ''))}
      ${fld('system', 'System of record', txt('system'), 'The system the numbers come from.')}
      ${fld('id', 'Proposed ID', txt('id') + `<input type="hidden" name="idtouched" value="${v('idtouched')}">`, 'Suggested from the building block; you can change it.')}
    </fieldset>
    <fieldset class="psec"><legend>Why it matters</legend>
      ${fld('why', 'Why does leadership need this number?', area('why', 4, 400), '', `<span class="cap" id="pc-why"><span id="pc-n">${why}</span> of 400 characters</span>`)}
    </fieldset>
    <fieldset class="psec"><legend>Calculation</legend>
      ${fld('num', 'Numerator label', txt('num'), 'What is counted, for example “Open findings past their deadline”.')}
      ${fld('den', 'Denominator label', txt('den'), 'What it is measured against, for example “Open findings”.')}
      ${fld('unit', 'Unit', sel('unit', PF_UNITS.map(u => [u, u]), '', '%'))}
      <fieldset class="pfld"><legend>Direction</legend><label class="inl"><input type="radio" name="dir" value="higher"${V.dir === 'higher' ? ' checked' : ''}> Higher is better</label><label class="inl"><input type="radio" name="dir" value="lower"${V.dir === 'lower' ? ' checked' : ''}> Lower is better</label><p class="ferr" id="pe-dir" hidden></p></fieldset>
      ${fld('time', 'Time basis', sel('time', PF_TIMES.map(u => [u, u]), '', 'Snapshot'))}
      ${fld('minpop', 'Minimum population', num('minpop'), 'Fewer items than this are shown but not scored.')}
      ${fld('zero', 'Zero-denominator rule', sel('zero', Object.entries(PF_ZERO), '', 'NS'), 'What happens when there is nothing to measure.')}
    </fieldset>
    <fieldset class="psec"><legend>Tolerance thresholds</legend>
      <div class="prow2">${fld('green', 'Green tolerance', num('green'), 'As good as this is Green.')}${fld('red', 'Red limit', num('red'), 'Worse than this is Red.')}</div>
      ${fld('basis', 'Basis', sel('basis', PF_BASIS.map(u => [u, u]), 'Choose a basis', ''))}
      ${fld('policy', 'Policy reference', txt('policy'), 'Required when the basis is Policy.')}
    </fieldset>
    <fieldset class="psec"><legend>Considerations</legend>
      ${fld('limits', 'Known limitations', area('limits', 3), 'One per line.')}
      ${fld('counters', 'Counter-measures', area('counters', 3), 'One per line.')}
      ${fld('info', 'Information counters the provider must supply', area('info', 2), 'Optional. Counts shown beside the rate, such as exceptions or downgrades.')}
    </fieldset>
    <fieldset class="psec"><legend>Selection test</legend><p class="cap" style="margin:0 0 8px">All six must be true before the proposal is submitted for review.</p>
      ${PF_TESTS.map(([t, h], i) => `<label class="chk"><input type="checkbox" name="t${i}"${V['t' + i] ? ' checked' : ''} aria-describedby="pe-tests"><span><b>${t}</b><span class="cap">${h}</span></span></label>`).join('')}
      <p class="ferr" id="pe-tests" hidden></p>
    </fieldset>
    <fieldset class="psec"><legend>Owner</legend>${(`${byField()}${DICT.err ? `<p class="ferr" role="alert">${esc(DICT.err)}</p>` : ''}<dl class="dd" style="margin:0"><dt>Date</dt><dd>${today}</dd></dl>`)}</fieldset>
    </div>
    <div class="pfoot"><button type="submit" class="pri">Submit for review</button><button type="button" data-act="pf-cancel">Cancel</button></div>
  </form></section>`;
}
function pfCheck(o, draft){
  const E = {}, blank = k => !String(o[k] ?? '').trim(), n = k => o[k] !== '' && o[k] != null && !isNaN(+o[k]);
  if (blank('name')) E.name = 'Enter a name for the metric.';
  const id = String(o.id || '').trim();
  const taken = id && [...D.metrics.map(m => m.id), ...PROPS.map(p => p.id)].includes(id);
  if (draft) { if (taken) E.id = 'This ID is already used by a metric or a proposal. Choose another.'; return E; }
  if (blank('block')) E.block = 'Choose the building block this metric belongs to.';
  if (blank('provider')) E.provider = 'Choose the team that will provide the data.';
  if (blank('system')) E.system = 'Name the system of record the numbers come from.';
  if (!id) E.id = 'Enter a proposed ID, for example SE-07.';
  else if (!/^[A-Z]{2}-\d{2}$/.test(id)) E.id = 'Use two capital letters, a hyphen and two digits, for example SE-07.';
  else if (taken) E.id = 'This ID is already used by a metric or a proposal. Choose another.';
  if (blank('why')) E.why = 'Say in a sentence or two why leadership needs this number.'; else if (String(o.why).length > 400) E.why = 'Shorten this to 400 characters or fewer.';
  if (blank('num')) E.num = 'Say what is counted in the numerator.';
  if (blank('den')) E.den = 'Say what the numerator is measured against.';
  if (!o.dir) E.dir = 'Choose whether a higher or a lower value is better.';
  if (!(n('minpop') && +o.minpop >= 1 && Number.isInteger(+o.minpop))) E.minpop = 'Enter the smallest population that can be scored, as a whole number of 1 or more.';
  if (!n('green')) E.green = 'Enter the Green tolerance as a number in the chosen unit.';
  if (!n('red')) E.red = 'Enter the Red limit as a number in the chosen unit.';
  if (n('green') && n('red') && o.dir && (o.dir === 'higher' ? +o.green < +o.red : +o.green > +o.red)) E.red = o.dir === 'higher' ? 'For a metric where higher is better, the Red limit must not be above the Green tolerance.' : 'For a metric where lower is better, the Red limit must not be below the Green tolerance.';
  if (blank('basis')) E.basis = 'Choose the basis for the tolerance thresholds.';
  else if (o.basis === 'Policy' && blank('policy')) E.policy = 'Name the policy that sets the tolerance threshold.';
  if (blank('limits')) E.limits = 'List at least one known limitation, even if it is minor.';
  if (blank('counters')) E.counters = 'List at least one counter-measure against gaming or error.';
  const open = PF_TESTS.filter((_, i) => !o['t' + i]).length;
  if (open) E.tests = `${open} of the six statements ${open === 1 ? 'is' : 'are'} not ticked. Tick all six, or save a draft and come back.`;
  return E;
}
function pfShow(E){
  document.querySelectorAll('#pform .ferr').forEach(p => { p.hidden = true; p.textContent = ''; });
  document.querySelectorAll('#pform [aria-invalid]').forEach(c => c.removeAttribute('aria-invalid'));
  const ks = Object.keys(E); if (!ks.length) { $('#pf-sum').hidden = true; return; }
  let first = null;
  for (const k of ks) { const p = $('#pe-' + k); if (p) { p.textContent = E[k]; p.hidden = false; }
    const c = k === 'tests' ? document.querySelector('#pform [name=t0]') : k === 'dir' ? document.querySelector('#pform [name=dir]') : $('#pf-' + k);
    if (c) { if (k !== 'dir') c.setAttribute('aria-invalid', 'true'); if (!first) first = c; } }
  const sm = $('#pf-sum'); sm.textContent = `Please correct ${ks.length} ${ks.length === 1 ? 'item' : 'items'} below before submitting.`; sm.hidden = false;
  const ord = ['name','building block','provider','system','id','why','num','den','dir','minpop','green','red','basis','policy','limits','counters','tests'];
  const k0 = ord.find(k => E[k]); const c0 = k0 === 'tests' ? document.querySelector('#pform [name=t0]') : k0 === 'dir' ? document.querySelector('#pform [name=dir]') : $('#pf-' + k0);
  (c0 || first).focus();
}

/* ----- Proposals view and read-only proposal card ----- */
const propChip = s => `<span class="chip ${PROP_STATUS[s] || 'n'}">${esc(s)}</span>`;
function propTable(){
  const rows = liveProps().map(pr => `<tr data-act="prop-open" data-k="${pr.k}"><td class="nw"><b>${pr.id ? esc(pr.id) : '<span class="muted">Not set</span>'}</b></td>
    <td><button type="button" class="linkbtn pn" data-act="prop-open" data-k="${pr.k}">${esc(pr.name)}</button></td><td>${ltag(pr.block)}</td><td>${pr.provider ? bTeam(pr.provider) : '<span class="muted">—</span>'}</td>
    <td>${esc(pr.by)}</td><td class="nw">${fd(pr.date)}</td><td>${propChip(pr.status)}</td></tr>`).join('');
  return `<div class="thr-note">${('Select one to read it and see the decision.')}</div>
    ${DICT.sentProp ? `<div class="banner" role="status" id="prop-sent" tabindex="-1">${esc(DICT.sentProp)}</div>` : ''}
    <div class="panel" style="margin-top:8px;overflow-x:auto"><table class="dt prop"><caption class="sr-only">${('Proposals')}</caption><colgroup><col style="width:80px"><col style="width:auto"><col style="width:132px"><col style="width:120px"><col style="width:136px"><col style="width:116px"><col style="width:112px"></colgroup>
    <thead><tr><th>ID</th><th>Metric</th><th>Building block</th><th>Provider</th><th>Proposed by</th><th>Date</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}
function propCard(k){
  const pr = liveProps().find(x => x.k === k); if (!pr) return propTable();
  if (pr.live && pr.live.kind !== 'new_metric') return liveReqCard(pr);
  const u = pr.unit, sc = SCALE[u] || 100, hi = pr.dir === 'higher', na = '<span class="muted">Not provided</span>';
  const chips = [ltag(pr.block), pr.provider ? bTeam(pr.provider) : '', pr.system ? bSrc(pr.system) : ''].filter(Boolean).join('');
  const li = s => lines(s).length ? dBullets(lines(s)) : `<p style="margin:0">${na}</p>`;
  const thr = `<dl class="dd">${dRow('Green tolerance', pr.green === '' ? na : `<b>${hi ? '≥' : '≤'} ${fvU(u, pr.green)}</b>`)}${dRow('Red limit', pr.red === '' ? na : `<b>${hi ? '<' : '>'} ${fvU(u, pr.red)}</b>`)}${dRow('Basis', pr.basis ? esc(pr.basis) + (pr.policy ? ': ' + esc(pr.policy) : '') : na)}
    ${dRow('Minimum population', pr.minpop === '' ? na : `Fewer than ${esc(pr.minpop)} items: shown, not scored.`)}${dRow('Zero denominator', esc(PF_ZERO[pr.zero] || PF_ZERO.NS))}</dl>`;
  return `<p class="noprint" style="margin:8px 0"><button type="button" data-act="prop-back">← Back to proposals</button></p>
  <article class="dcard" id="prop-card" aria-labelledby="ph-${pr.k}"><h2 id="ph-${pr.k}" tabindex="-1" style="margin:0 0 6px">${pr.id ? esc(pr.id) + ' · ' : ''}${esc(pr.name)}</h2><div class="bubs" style="margin:0 0 4px">${chips}</div>
    <p class="cap" style="margin:8px 0 0">Proposal · ${propChip(pr.status)} · proposed by ${esc(pr.by)} on ${fd(pr.date)} · read-only</p>
    <section class="dsec"><h3>Why it matters</h3><p style="margin:0">${pr.why ? esc(pr.why) : na}</p></section>
    <section class="dsec"><h3>How it is calculated</h3><div class="formula">Value = ${pr.num ? esc(pr.num) : '…'} ÷ ${pr.den ? esc(pr.den) : '…'} × ${sc} (${esc(u)})</div>
      <div class="cap" style="margin-top:4px">Compared at 1 decimal place, rounded half up.</div><dl class="dd" style="margin-top:8px">${dRow('Time basis', esc(pr.time))}</dl>${pr.checks ? `<h4 class="dh4">A repo counts only when it passes every check</h4><dl class="dd">${pr.checks.map(([n, r]) => dRow(esc(n), esc(r))).join('')}</dl>` : ''}${pr.note ? `<p class="cap" style="margin:6px 0 0">${esc(pr.note)}</p>` : ''}</section>
    ${pr.how ? `<section class="dsec"><h3>How we will check it</h3><p style="margin:0">${esc(pr.how)}</p></section>` : ''}
    <section class="dsec"><h3>How it is scored</h3><dl class="dd">${dRow('Direction', pr.dir ? (hi ? 'Higher is better' : 'Lower is better') : na)}${dRow('Scored', 'Not yet — a proposal is not scored until approved')}</dl>${thr}</section>
    <section class="dsec"><h3>What we take into account</h3><h4 class="dh4">Known limitations</h4>${li(pr.limits)}<h4 class="dh4">Counter-measures</h4>${li(pr.counters)}<h4 class="dh4">Information counters the provider must supply</h4>${li(pr.info)}</section>
    <section class="dsec"><h3>Selection test</h3><ul class="dbul" style="list-style:none;padding:0">${PF_TESTS.map(([t], i) => `<li><b>${pr.tests[i] ? 'Confirmed' : 'Not confirmed'}</b> · ${esc(t)}</li>`).join('')}</ul></section>
    ${pr.live ? liveReview(pr) + '</article>' : `<section class="dsec"><div class="panel dchg" style="margin:0"><h3 style="text-transform:none;letter-spacing:0;font-size:16px;color:var(--text)">Review</h3>
      <div class="noprint"><button type="button" disabled aria-describedby="rv-${pr.k}">Approve</button> <button type="button" disabled aria-describedby="rv-${pr.k}">Return with note</button> <button type="button" disabled aria-describedby="rv-${pr.k}">Decline</button></div>
      <p class="cap" id="rv-${pr.k}" style="margin:8px 0 0">Requires the Head of Tech Risk role; approval is applied through the approved procedure and creates the draft metric version. It is not scored until a data contract is signed and a dry run has passed.</p></div></section></article>`}`;
}
/* live: proposals, change requests and retirements are saved in TRUST's back end */
const PST = {open:'Proposed', returned:'Returned', approved:'Approved', declined:'Declined', withdrawn:'Withdrawn'};
function liveProps(){
  
  if (!may('console_read')) return [];      // the proposals list is for Tech Risk and auditors
  if (!LIVE.props) {
    if (!LIVE.propsLoading) { LIVE.propsLoading = true;
      api('/api/proposals').then(j => { LIVE.props = j.proposals; }).catch(x => { LIVE.props = []; LIVE.propsErr = x.message; })
        .finally(() => { LIVE.propsLoading = false; S.keepScroll = true; render(); }); }
    return [];
  }
  return LIVE.props.map(P => { const d = P.detail || {}, m = P.metric ? D.metrics.find(x => x.id === P.metric) : null;
    const base = P.kind === 'new_metric' ? {...d, id:String(d.id || ''), block:d.block || '', provider:d.provider || '', system:d.system || '', why:d.why || '', num:d.num || '', den:d.den || '', unit:d.unit || '%', dir:d.dir || '', time:d.time || 'Snapshot',
      minpop:d.minpop ?? '', zero:d.zero || 'NS', green:d.green ?? '', red:d.red ?? '', basis:d.basis || '', policy:d.policy || '', limits:d.limits || '', counters:d.counters || '', info:d.info || '', tests:PF_TESTS.map((_, i) => !!d['t' + i])}
      : {id:P.metric || '', block:m ? m.block : '', provider:m ? m.provider : ''};
    return {...base, name:P.title, k:'L' + P.id, live:P, by:P.by, date:String(P.at).slice(0, 10), status:PST[P.status] || P.status}; });
}
function liveOpenFor(id){          // open requests on this metric, shown on its card
  const open = liveProps().filter(p => p.live.metric === id && p.live.status === 'open');
  return open.length ? `<p class="cap noprint" style="margin:8px 0 0">Waiting for a decision: ${open.map(p => `${esc(p.live.kind === 'retire' ? 'retirement' : 'change request')} by ${esc(p.by)}, ${fd(p.date)}`).join('; ')}.${isTR() ? ` <a href="${href('/dictionary/proposals')}">See Proposals</a>` : ''}</p>` : '';
}
function liveReview(pr){
  const P = pr.live, ds = (P.decisions || []).map(d => `<li>${esc(PST[d.decision] || d.decision)} by ${esc(d.by)}, ${when(d.at)}${d.reason ? ' · ' + esc(d.reason) : ''}</li>`).join('');
  const mayDec = may('decide'), mayWd = may('propose');
  const form = P.status === 'open' && (mayDec || mayWd) ? `<form class="propdec" data-id="${P.id}" aria-label="Decide on this proposal" novalidate>${byField()}
    <label>Reason (needed to return or decline)<textarea name="reason" rows="2" maxlength="2000"></textarea></label>
    <div class="noprint" style="margin-top:6px">${mayDec ? '<button type="submit" class="pri" value="approved">Approve</button> <button type="submit" value="returned">Return with note</button> <button type="submit" value="declined">Decline</button> ' : ''}${mayWd ? '<button type="submit" value="withdrawn">Withdraw</button>' : ''}</div></form>` : '';
  return `<section class="dsec"><div class="panel dchg" style="margin:0"><h3 style="text-transform:none;letter-spacing:0;font-size:16px;color:var(--text)">Review</h3>
    ${ds ? `<ul class="cnl">${ds}</ul>` : '<p class="cap" style="margin:0 0 8px">No decision yet.</p>'}${form}${LIVE.propMsg ? `<p class="ferr" role="alert">${esc(LIVE.propMsg)}</p>` : ''}
    <p class="cap" style="margin:8px 0 0">The decision is the Head of Tech Risk’s. Approving records the decision only: the dictionary and the scoring are changed separately, with the owner’s agreement, from the next unlocked month.</p></div></section>`;
}
function liveReqCard(pr){
  const P = pr.live, d = P.detail || {}, m = D.metrics.find(x => x.id === P.metric), r = d.replacement ? D.metrics.find(x => x.id === d.replacement) : null;
  const rows = P.kind === 'retire' ? dRow('Reason', esc(d.reason)) + dRow('Effective from', esc(d.effective ? monthLabel(d.effective) : '')) + dRow('Replacement', r ? `${esc(r.id)} · ${esc(r.name)}` : 'None')
    : dRow('What should change', esc(d.field)) + dRow('Proposed wording or calculation', esc(d.wording)) + dRow('Reason', esc(d.reason));
  return `<p class="noprint" style="margin:8px 0"><button type="button" data-act="prop-back">← Back to proposals</button></p>
  <article class="dcard" id="prop-card" aria-labelledby="ph-${pr.k}"><h2 id="ph-${pr.k}" tabindex="-1" style="margin:0 0 6px">${esc(P.title)}</h2><div class="bubs" style="margin:0 0 4px">${pr.block ? ltag(pr.block) : ''}${pr.provider ? bTeam(pr.provider) : ''}</div>
    <p class="cap" style="margin:8px 0 0">${P.kind === 'retire' ? 'Retirement' : 'Change request'} · ${propChip(pr.status)} · by ${esc(P.by)} on ${fd(pr.date)}${m ? ` · about <a href="${href('/dictionary/' + m.id)}">${esc(m.id)} ${esc(m.name)}</a>` : ''}</p>
    <section class="dsec"><h3>What is asked</h3><dl class="dd">${rows}</dl></section>${liveReview(pr)}</article>`;
}
document.addEventListener('submit', e => {
  const f = e.target;
  if (f.id === 'ddform') { e.preventDefault(); const fe = f.elements, metrics = [...f.querySelectorAll('input[name=metrics]:checked')].map(x => x.value);
    DD.form = {feed:fe.feed.value, provider:fe.provider.value, contact:fe.contact.value, cadence:fe.cadence.value, what:fe.what.value, columns:fe.columns.value, note:fe.note.value, metrics};
    apiPost('/api/contracts', {by:liveName(f), ...DD.form}).then(j => { DD.form = null; DD.err = null; DD.msg = null; contractsLoad(true); go('/datadict/' + j.contract.feed); })
      .catch(x => { DD.err = x.message; S.keepScroll = true; render(); }); return; }
  if (f.classList.contains('ddf')) { e.preventDefault(); const reason = f.elements.reason.value.trim();
    apiPost(`/api/contracts/${f.dataset.id}/decide`, {by:liveName(f), decision:f.dataset.d, reason}).then(j => { DD.decide = {}; DD.err = null; DD.msg = null; contractsLoad(true); })
      .catch(x => { DD.err = x.message; S.keepScroll = true; render(); }); return; } if ((!f.matches('form.propdec'))) return; e.preventDefault();
  const dec = (e.submitter && e.submitter.value) || 'approved', id = f.dataset.id;
  apiPost(`/api/proposals/${encodeURIComponent(id)}/decide`, {by:liveName(f), decision:dec, reason:f.elements.reason.value.trim()})
    .then(() => { LIVE.props = null; LIVE.propMsg = null; }).catch(x => { LIVE.propMsg = x.message; }).finally(() => { S.keepScroll = true; render(); });
});
function propView(){ return DICT.pc ? propCard(DICT.pc) : propTable(); }

/* ----- events for the lifecycle features ----- */
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]'); if (!b) return; const a = b.dataset.act;
  if (a === 'pf-open') { if (DICT.pf) { $('#pf-h').focus(); return; } DICT.pf = true; DICT.pv = null; S.keepScroll = true; render(); const h = $('#pf-h'); if (h) h.focus({preventScroll:true}); return; }
  if (a === 'pf-cancel') { DICT.pf = false; DICT.pv = null; S.keepScroll = true; render(); const o = document.querySelector('[data-act=pf-open]'); if (o) o.focus({preventScroll:true}); return; }
  
  if (a === 'prop-open') { DICT.pc = b.dataset.k; DICT.sentProp = null; render(); const h = document.querySelector('#prop-card h2'); if (h) h.focus({preventScroll:true}); return; }
  if (a === 'prop-back') { const k = DICT.pc; DICT.pc = null; render(); const o = document.querySelector(`button[data-k="${k}"]`); if (o) o.focus({preventScroll:true}); return; }
  if (a === 'ret-open') { DICT.ret = b.dataset.id; S.keepScroll = true; render(); const t = document.querySelector('.retf textarea'); if (t) t.focus(); return; }
  if (a === 'ret-cancel') { DICT.ret = null; S.keepScroll = true; render(); const o = document.querySelector('[data-act=ret-open]'); if (o) o.focus({preventScroll:true}); return; }
});
document.addEventListener('submit', e => {
  const f = e.target;
  if (f.matches('#pform')) { e.preventDefault(); pfSnap(); const E = pfCheck(DICT.pv, false); pfShow(E); if (Object.keys(E).length) return;
    { const o = DICT.pv; apiPost('/api/proposals', {by:liveName(f), kind:'new_metric', metric:null, title:String(o.name || '').trim(), detail:o})
      .then(j => { LIVE.props = null; DICT.pf = false; DICT.pv = null; DICT.pc = null; DICT.err = null; DICT.sentProp = `Proposal “${j.proposal.title}” submitted for review.`; go('/dictionary/proposals'); })
      .catch(x => { DICT.err = x.message; S.keepScroll = true; render(); }); return; } }
  if (f.classList.contains('retf')) { e.preventDefault(); const id = f.dataset.id, reason = f.elements.reason.value.trim(), er = $('#rer-' + id);
    if (!reason) { er.textContent = 'Give a reason for retiring this metric.'; er.hidden = false; f.elements.reason.setAttribute('aria-invalid', 'true'); f.elements.reason.focus(); return; }
    { const m = met(id); apiPost('/api/proposals', {by:liveName(f), kind:'retire', metric:id, title:`Retire ${id} ${m.name}`, detail:{reason, replacement:f.elements.repl.value, effective:f.elements.from.value}})
      .then(() => { LIVE.props = null; DICT.ret = null; DICT.err = null; }).catch(x => { DICT.err = x.message; }).finally(() => { S.keepScroll = true; render(); }); return; } }
});
document.addEventListener('change', e => {
  const t = e.target;
  if (t.id === 'dd-feed') { const f = t.form.elements; DD.form = {feed:t.value, contact:f.contact.value, cadence:f.cadence.value, what:f.what.value, note:f.note.value}; S.keepScroll = true; render(); const n = $('#dd-feed'); if (n) n.focus({preventScroll:true}); return; }
  if (t.id === 'pf-block') { const i = $('#pf-id'), h = document.querySelector('#pform [name=idtouched]'); if (i && h && h.value !== '1') i.value = nextId(t.value); }
  if (t.id === 'dretired') { DICT.showRet = t.checked; const n = $('#dretnote'); if (n) n.hidden = !t.checked; }
});
document.addEventListener('input', e => {
  const t = e.target;
  if (t.id === 'pf-id') { const h = document.querySelector('#pform [name=idtouched]'); if (h) h.value = '1'; }
  if (t.id === 'pf-why') { const n = $('#pc-n'); if (n) n.textContent = t.value.length; }
});

/* Completeness and accuracy: text fixed so each card stands alone (no "as SE-01" references, no threshold mentions) */

/* (CX retired 8 Nov 2026: every card has its own population and exclusions in config/metrics.json.) */
