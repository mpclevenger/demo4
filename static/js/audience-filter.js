/* Library category pages: the "Show guidance for" pills filter every line by its audience
 * (Platform admins or Platform users). One pill on shows only that audience; no pill on shows both.
 * Lines carry data-audience="admins" or "users". Without scripts, each pill is a link that reloads
 * the page with ?audience=... and the server marks the lines. */
(function () {
  "use strict";

  var OFF = "is-audience-off";

  // The audience key switched on, or "" for both.
  function chosen() {
    var pressed = document.querySelector('[data-audience-toggle][aria-pressed="true"]');
    return pressed ? pressed.getAttribute("data-audience-toggle") : "";
  }

  // Hide the lines for the other audience, then hide any list or box whose every line is hidden.
  function apply() {
    var key = chosen();
    document.querySelectorAll("[data-audience]").forEach(function (line) {
      line.classList.toggle(OFF, key !== "" && line.getAttribute("data-audience") !== key);
    });
    document.querySelectorAll(".place-guidance ul, .platform-specific").forEach(function (group) {
      var lines = group.querySelectorAll("li");
      var allOff = lines.length > 0 && Array.prototype.every.call(lines, function (li) { return li.classList.contains(OFF); });
      group.classList.toggle(OFF, allOff);
    });
  }

  document.addEventListener("click", function (event) {
    var pill = event.target.closest("[data-audience-toggle]");
    if (!pill) return;
    event.preventDefault();
    var turnOn = pill.getAttribute("aria-pressed") !== "true";
    document.querySelectorAll("[data-audience-toggle]").forEach(function (other) {
      other.setAttribute("aria-pressed", other === pill && turnOn ? "true" : "false");
    });
    apply();
    var params = new URLSearchParams(window.location.search);
    params.delete("audience");
    if (turnOn) params.set("audience", pill.getAttribute("data-audience-toggle"));
    var query = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (query ? "?" + query : "") + window.location.hash);
  });

  apply();
})();
