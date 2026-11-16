/* The 'Family says' marker for a family's own explanations. */
"use strict";
/* ---------- family comments: "Family says" marker ---------- */
let FPID = 0;
const GLYPH = '<svg class="gl" viewBox="0 0 16 16" width="13" height="13" aria-hidden="true" focusable="false"><path d="M2 2.5h12a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H8l-3.5 3v-3H2a1 1 0 0 1-1-1v-7a1 1 0 0 1 1-1z" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>';
function famSays(fid, mid){        // mid undefined: all comments of the family; null: family-level only; id: that metric
  const out = [], date = P().meta.current_bd ? bizDay(S.p, P().meta.current_bd) : P().meta.last_day;
  D.entries.filter(e => e.kind === 'Note' && e.family_id === fid && (e.period === S.p || (e.period < S.p && e.status !== 'Done')))
    .forEach(e => out.push({mid:e.metric_id || null, block:e.block || null, text:e.text, date:e.created}));
  COMMENTS.filter(c => c.p === S.p && c.fid === fid && c.type === 'explain').forEach(c => out.push({mid:c.mid || null, block:c.block || null, text:c.text, date:c.date || date}));
  const rank = c => c.mid ? 2 : c.block ? 1 : 0; out.sort((a, b) => rank(a) - rank(b) || String(b.date).localeCompare(String(a.date)));
  if (mid === undefined) return out;
  if (typeof mid === 'string' && mid.startsWith('rel:')) { const id = mid.slice(4), L = met(id).block;   // everything that speaks to this metric: the metric, its building block, the whole family
    return out.filter(c => c.mid === id || (!c.mid && c.block === L) || (!c.mid && !c.block)); }
  if (typeof mid === 'string' && mid.startsWith('let:')) { const L = mid.slice(4);          // comments tagged to this building block, or to a metric in it
    return out.filter(c => c.block === L || (c.mid && met(c.mid).block === L)); }
  return out.filter(c => c.mid === mid && (mid || !c.block));
}
const scopeLbl = c => c.mid ? `${esc(met(c.mid).name)} (${c.mid})` : c.block ? `${esc(BLK(c.block).name)} as a whole` : 'Whole family';
function saysMark(fid, mid, compact){
  const cs = famSays(fid, mid); if (!cs.length) return '';
  const id = 'fp' + (++FPID);
  const body = cs.map(c => `<span class="fc"><span class="cap">Family lead · ${fd(c.date)} · ${scopeLbl(c)}</span><span class="ftx">${esc(c.text)}</span></span>`).join('');
  return `<span class="fsw"><button type="button" class="fsay" data-act="say" aria-expanded="false" aria-controls="${id}">${GLYPH}<span${compact ? ' class="sr-only"' : ''}>Family says </span><span>${cs.length}</span></button><span class="fpop" id="${id}" role="group" aria-label="Family says"><span class="fbox">${body}</span></span></span>`;
}
function famSaysLines(fid, mid){
  return famSays(fid, mid).map(c => `<div class="fsl">Family says: “${esc(c.text.length > 220 ? c.text.slice(0, 217) + '…' : c.text)}”</div>`).join('');
}
function closePops(){ document.querySelectorAll('.fsw.pin').forEach(w => { w.classList.remove('pin'); const b = w.querySelector('.fsay'); if (b) b.setAttribute('aria-expanded', 'false'); }); }
function placePop(w){
  const pop = w.querySelector('.fpop'); if (!pop) return;
  pop.classList.remove('fx', 'fy');
  const r = pop.getBoundingClientRect(), wr = w.getBoundingClientRect();
  if (r.right > window.innerWidth - 8) pop.classList.add('fx');
  if (r.bottom > window.innerHeight - 8 && wr.top - r.height > 8) pop.classList.add('fy');
}
