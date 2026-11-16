/* Starts the page. Loaded last. */
"use strict";
window.addEventListener('hashchange', () => { S.snap = false; render(); });
render();
