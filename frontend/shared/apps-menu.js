/* The Apps menu: a small "Apps" button that opens a list of the three connected sites (TRUST, Risk, TRAC).
   It uses only shared/text.js (safeLink), so the Risk site's front end can load this same file and call
   appsMenuMount(element, 'Risk'). The addresses come from the back end: GET /api/apps. */
"use strict";
const APPSM_ORDER = ['TRUST', 'Risk', 'TRAC'];
let appsmAddressesPromise = null;     // the addresses are asked for once per page load

/* Ask the back end for the three addresses. If that fails, the menu shows nothing. */
function appsmAddresses(){
  if (!appsmAddressesPromise) {
    appsmAddressesPromise = fetch('/api/apps', {headers: {'Accept': 'application/json'}})
      .then(response => response.ok ? response.json() : {})
      .catch(() => ({}));
  }
  return appsmAddressesPromise;
}

/* Clicking anywhere outside a menu closes it. Set up once, however many times a menu is drawn. */
document.addEventListener('click', event => {
  document.querySelectorAll('.appsm').forEach(menu => {
    if (menu.contains(event.target)) return;
    const list = menu.querySelector('.appsm-list'), button = menu.querySelector('.appsm-btn');
    if (list) list.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
  });
});

/* Draw the button and its menu into the element. currentAppName is the site we are on: it shows as "current" and is not a link. */
function appsMenuMount(containerElement, currentAppName){
  if (!containerElement) return;
  appsmAddresses().then(addresses => {
    const names = APPSM_ORDER.filter(name => name === currentAppName || safeLink(addresses[name]));
    if (!names.length) { containerElement.textContent = ''; return; }
    containerElement.textContent = '';
    containerElement.classList.add('appsm');

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'appsm-btn';
    button.setAttribute('aria-expanded', 'false');
    button.setAttribute('aria-haspopup', 'true');
    button.innerHTML = 'Apps <svg viewBox="0 0 10 6" width="10" height="6" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M1 1l4 4 4-4"/></svg>';

    const list = document.createElement('ul');
    list.className = 'appsm-list';
    list.hidden = true;
    names.forEach(name => {
      const item = document.createElement('li');
      if (name === currentAppName) {
        const here = document.createElement('span');
        here.className = 'appsm-here';
        here.setAttribute('aria-current', 'true');
        here.textContent = name + ' (current)';
        item.appendChild(here);
      } else {
        const link = document.createElement('a');
        link.className = 'appsm-link';
        link.href = safeLink(addresses[name]);
        link.textContent = name;
        item.appendChild(link);
      }
      list.appendChild(item);
    });

    const setOpen = open => { list.hidden = !open; button.setAttribute('aria-expanded', String(open)); };
    button.addEventListener('click', () => setOpen(list.hidden));
    containerElement.addEventListener('keydown', event => { if (event.key === 'Escape' && !list.hidden) { setOpen(false); button.focus(); } });

    containerElement.appendChild(button);
    containerElement.appendChild(list);
  });
}

/* Links to a TRAC page: write <a data-trac-path="/guides/..." hidden>…</a> on any page. Once TRAC's address is known
   the link gets it and shows. With no TRAC address set, the link stays hidden (nothing to say = nothing drawn). */
function appsmFillTracLinks(){
  const waiting = document.querySelectorAll('a[data-trac-path]:not([href])');
  if (!waiting.length) return;
  appsmAddresses().then(addresses => {
    const tracAddress = (addresses.TRAC || '').replace(/\/+$/, '');
    if (!tracAddress) return;
    waiting.forEach(link => { link.href = tracAddress + link.getAttribute('data-trac-path'); link.hidden = false; });
  });
}
new MutationObserver(appsmFillTracLinks).observe(document.documentElement, {childList: true, subtree: true});
