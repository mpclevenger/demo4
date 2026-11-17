/* Glossary. */
"use strict";
function vGlossary(){
  return `<div class="method"><h1>Glossary</h1>
  <h2>Words you’ll see on the scorecard</h2><dl>
  <dt>Automatic Red rule</dt><dd>A rule that forces a metric to Red whatever its rate, such as an overdue critical secret. It caps the building block at ${CAP().automatic_red_block}.</dd>
  <dt>Behind peers</dt><dd>A metric well worse than the typical (median) value across L3 teams.</dd>
  <dt>Building block</dt><dd>One of the six things that earn clients’ trust, such as Security or Stability. Each is scored from its metrics.</dd>
  <dt>Cap</dt><dd>A limit on a score. A Red metric caps its building block at ${CAP().red_metric_block}; an automatic Red rule caps it at ${CAP().automatic_red_block}; a Red building block caps TRUST at ${CAP().red_block_trust}.</dd>
  <dt>Chronic Red</dt><dd>A metric that has been Red for three months in a row.</dd>
  <dt id="data-contract">Data contract</dt><dd>The written agreement between the team that sends a file and Tech Risk: which columns TRUST may read and which metrics the file may be used for. A file whose columns change is flagged until the provider confirms.</dd>
  <dt>Declining</dt><dd>A building block score that fell two months in a row.</dd>
  <dt>Firm tolerance</dt><dd>The firm TRUST score we have agreed to stay at or above. ${D.firm_tolerance ? `Set at ${D.firm_tolerance.value}.` : 'Not set yet: it appears once the Head of Tech Risk and the CTO agree a number.'}</dd>
  <dt>Flags</dt><dd>A flag is a note on the watch list; it never changes a color or points. Behind peers needs at least 5 L3 teams that can be scored, and the gap used is shown on each metric’s card. Pass/fail and information-only metrics are never flagged, nor are metrics whose colors are already set by the median.</dd>
  <dt>Lock</dt><dd>Tech Risk locks a month on This month; the figures and the page are then frozen until someone reopens it with a reason.</dd>
  <dt>Missing data</dt><dd>A provider’s file did not arrive. Its metrics are left out and nothing is carried over from the month before.</dd>
  <dt>Newly Red</dt><dd>A metric that is Red this month and was not Red last month, or has no comparable last month.</dd>
  <dt>Not Tier 0/1</dt><dd>The L3 team owns no Tier 0/1 (most critical) application, so a metric about them does not apply and is not scored.</dd>
  <dt>Overdue action</dt><dd>An action that is not done and is past its due date.</dd>
  <dt>Pass/fail metric</dt><dd>A metric scored on a rule rather than a rate, such as CyberArk vaulting: Green when every eligible item is done, Amber when any is not, Red when any Tier 0/1 item is not. It has no tolerance thresholds.</dd>
  <dt>Wanted metric</dt><dd>A metric we want but that has no data source yet. It counts in no score.</dd>
  <dt>In progress metric</dt><dd>A metric with an agreed data source that is being built. It counts in no score yet.</dd>
  <dt id="prevailing-median">Prevailing median</dt><dd>The middle value across all L3 teams for a metric. Until Tech Risk calibrates a metric, its limits come from each month’s own results: Green is at or better than the median, Amber is worse by up to the usual spread between L3 teams, Red is worse than that.</dd>
  <dt>Retired metric</dt><dd>Kept in history, excluded from scoring from the effective month; building blocks re-average over the remaining metrics.</dd>
  <dt>Sharp drop</dt><dd>An L3 team’s TRUST fell 10 points or more.</dd>
  <dt>TCC</dt><dd>Technology Change Control, the firm’s approval route for production changes. A Non-TCC change went through another route. TE-01 measures what share of an L3 team’s deployed changes went through TCC.</dd>
  <dt>Tier 0/1 app</dt><dd>An application in the most critical tiers (Tier 0 or 1) of the ITDR application file. Several metrics turn Red when a Tier 0/1 app is affected, whatever the overall rate.</dd>
  <dt>Tolerance threshold</dt><dd>The pair of limits for one metric: the Green tolerance is the level a result must reach to be Green, the Red limit is where Red starts, and between them is Amber.</dd>
  <dt>TRUST score</dt><dd>An L3 team’s score out of 100: the average of its scored building blocks. Green is ${METHOD.band_green_from} and over, Amber ${METHOD.band_amber_from} to ${METHOD.band_green_from - 1}, Red below ${METHOD.band_amber_from}.</dd>
  <dt>Usual spread between L3 teams (Amber band)</dt><dd>How far apart L3 teams normally are on a metric: the distance across the middle half of them, times 1.5 and never less than 5 points. It sets how wide Amber is.</dd>
  <dt>Watch list</dt><dd>What is newly Red, what is chronic and what needs leadership. On the CTO view these are the lines under Where to focus. It never changes a color or points.${cplSeeTheCode((D.code_places || {}).watch_list, 'How items get onto the watch list, including Behind peers and the trend rules. An item on the watch list never changes a color or a score.')}</dd>
</dl>
  <h2 id="how-scores">How the scores are worked out</h2><p>Each metric scores by its color: ${pointsWords(', ')}. A building block is the average of its scored metrics, and TRUST is the average of the scored building blocks, in whole numbers. Anything with no data is left out. Caps can hold a score lower. The firm’s scores use every row received, so they are not an average of the L3 team scores.</p>
  <h2>Key indicators</h2><table class="dt nosort"><colgroup><col style="width:22%"><col style="width:34%"><col style="width:34%"><col style="width:10%"></colgroup><thead><tr><th>Type</th><th>What it tells you</th><th>Why it matters</th><th>Metrics</th></tr></thead><tbody>${D.method.indicator_types.map(r => `<tr><td><b>${esc(r.name)}</b></td><td>${esc(r.tells)}</td><td>${esc(r.why)}</td><td>${indCount(r.code)}</td></tr>`).join('')}</tbody></table>
  <h2>Legend of labels</h2><p>The same label styles are used on every page.</p>
  <dl class="legl"><dt>${bTeam('Arch')}</dt><dd>Team bubble (slate tint): an L3 team, sub-team or provider, such as Cyber or Ops.</dd>
  <dt>${bSrc('GitHub Enterprise Server')}</dt><dd>Data-source bubble (blue tint, database icon): the system of record or connector a number comes from.</dd>
  <dt>${tagW('Higher is better')}</dt><dd>Word tag: a plain descriptor, such as a direction, a basis, a version or a method. Neutral outline.</dd>
  <dt>${ltag(D.blocks[0].code)}</dt><dd>Building block tag: the block a metric belongs to, in that block’s own color (below), which is never a status color.</dd>
  <dt>${chip('Green', 'Green')}</dt><dd>Status chip: the result against its tolerance thresholds. Status chips are the only red, amber and green labels.</dd></dl>
  <h3 style="font-size:16px;margin:16px 0 4px">Building block colors</h3><div class="lrow">${D.blocks.map(l => ltag(l.code)).join('')}</div><p class="cap" style="margin:4px 0 0">Used on building block tags and Metric dictionary headings, never on the grid, which carries status colors.</p>
  <h2>Monthly rhythm</h2><p>Providers send their files in the first week after month end; Tech Risk updates the scorecard as files arrive and locks the month when it is right. Definitions are frozen at approval; a change is a new version approved by the Head of Tech Risk, requested from the metric’s card.</p></div>`;
}
