/* Small text helpers shared by the TRUST site and the Risk site: safe text for the page, dates, plurals, lists, links. */
"use strict";

/* Makes any value safe to put inside HTML. Nothing (null or undefined) becomes empty text, never the word "null". */
const esc = value => String(value === null || value === undefined ? '' : value)
  .replace(/[&<>"]/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[character]));

/* "2026-11-15T14:03:00+00:00" becomes "15 Nov 2026, 2:03 PM": day first, in the viewer's own time. */
function when(isoText) {
  if (!isoText) return '';
  const moment = new Date(isoText);
  if (isNaN(moment)) return esc(isoText);
  const day = moment.toLocaleDateString('en-GB', {day: 'numeric', month: 'short', year: 'numeric'});
  const time = moment.toLocaleTimeString('en-US', {hour: 'numeric', minute: '2-digit'});
  return day + ', ' + time;
}

/* A count with its unit: plural(1, 'risk', 'risks') is "1 risk", plural(3, 'risk', 'risks') is "3 risks". */
const plural = (count, one, many) => count + ' ' + (count === 1 ? one : many);

/* "a, b and c". With a limit, the rest are counted: listOf(['a', 'b', 'c', 'd'], 3) is "a, b, c and 1 more". */
function listOf(items, limit) {
  if (limit && items.length > limit) return items.slice(0, limit).join(', ') + ' and ' + (items.length - limit) + ' more';
  if (items.length < 3) return items.join(' and ');
  return items.slice(0, -1).join(', ') + ' and ' + items[items.length - 1];
}

/* A web address that is safe to link to: only http or https. Anything else gives empty text. */
function safeLink(address) {
  return /^https?:\/\//i.test(address || '') ? address : '';
}

/* The page address after the #, split at the slashes: "#/group/lending/results" gives ['group', 'lending', 'results'].
   Each part is decoded; a part with a stray % that cannot be decoded is kept as it is. */
function hashParts() {
  return location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(part => {
    try { return decodeURIComponent(part); } catch (problem) { return part; }
  });
}
