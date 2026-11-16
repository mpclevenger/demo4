/*
 * The risk and control calendar's pop-up (page /calendar/).
 *   [data-riskcal-open="id"]   a button that opens the pop-up with the content of <template id="riskcal-id">;
 *                              the template's data-title is the pop-up's heading
 *   [data-riskcal-from="id"]   on a button inside a day's list: the pop-up gets a "Back" button to that list
 * The templates are part of the page, so opening a pop-up needs no request. After HTMX swaps in another
 * month, the heading is read out by the status line (#riskcal-status).
 */
(function () {
  "use strict";
  var element = document.getElementById("riskcal-modal");
  if (!element) return;
  var modal = bootstrap.Modal.getOrCreateInstance(element);
  var heading = document.getElementById("riskcal-modal-title");
  var body = document.getElementById("riskcal-modal-body");

  function show(id, from) {
    var template = document.getElementById("riskcal-" + id);
    if (!template) return;
    heading.textContent = template.getAttribute("data-title");
    body.replaceChildren(template.content.cloneNode(true));
    if (from) {
      var back = document.createElement("button");
      back.type = "button";
      back.className = "btn btn-sm btn-outline-primary mt-3";
      back.textContent = "Back to the day's list";
      back.setAttribute("data-riskcal-open", from);
      body.appendChild(back);
    }
    if (element.classList.contains("show")) heading.focus();  // the button that was pressed is gone, so keep focus inside
    else modal.show();
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-riskcal-open]");
    if (button) show(button.getAttribute("data-riskcal-open"), button.getAttribute("data-riskcal-from"));
  });

  document.body.addEventListener("htmx:afterSwap", function () {
    var month = document.getElementById("riskcal-month");
    if (month) document.getElementById("riskcal-status").textContent = "Showing " + month.textContent;
  });
})();
