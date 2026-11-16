/* The Risk site: start-up. Loaded last. */
"use strict";

async function riskStart() {
  const me = await riskApi('/api/risk/me');
  if (!me.ok) {
    riskShowProblem(me.error || 'The site could not say who you are.');
    return;
  }
  riskState.me = me;
  riskDrawTopBar();
  window.addEventListener('hashchange', riskOpenPage);
  riskOpenPage();
}

riskStart();
