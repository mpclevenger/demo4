/* The input files TRUST reads (their layouts), and the tabs shared by the Tech Risk pages. */
"use strict";
/* ---------- Tech Risk: data sources ---------- */

function subtabs(cur){ return `<div class="subtabs"><a href="${href('/console')}" ${cur === 'console' ? 'aria-current="page"' : ''}>This month</a><a href="${href('/datasources')}" ${cur === 'datasources' ? 'aria-current="page"' : ''}>Data sources</a></div>`; }
/* ---------- Input files (D-82, D-83): providers send raw exports, Tech Risk uploads them, TRUST counts. Checks run on the real file, in the browser. ---------- */
const LAYOUTS = JSON.parse(document.getElementById('layouts').textContent).feeds.filter(f => !D.feeds || D.feeds.includes(f.id));      // live data lists the feeds the back end knows
const IN = {res:null, msg:null, acc:{}, rep:{}, rej:{}, focus:null};      // what the Data sources page has open; files are kept by the server
const inFeed = id => LAYOUTS.find(f => f.id === id);
const feedLbl = k => (inFeed(k) || {}).name || k;
/* Log notes start with a feed id: show its display name. The two .replace lines after it shorten the back end's wording for the page. */
const niceNote = n => String(n || '').replace(/^([a-z][a-z0-9_]*):/, (m, k) => inFeed(k) ? inFeed(k).name + ':' : m)
  .replace(/Working rules until Change Management answers:.*?never counted as approved \(Q-NTCC-04\)\.?/s, 'Non-TCC changes are read with working rules until Change Management confirms them (details in the data-sources wiki page).')
  .replace(/(\d+) of (\d+) (Checkmarx repos?) matched to a GitHub repo \((\d+) same name, 0 same repo name, 0 close spelling\)/, (m, a, b, c, d) => a === d ? `${a} of ${b} ${c} matched to a GitHub repo` : m);
