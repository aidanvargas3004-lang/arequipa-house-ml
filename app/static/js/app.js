(function () {
  "use strict";
  var csrf = document.querySelector('meta[name="csrf-token"]');
  window.CSRF_TOKEN = csrf ? csrf.getAttribute("content") : "";

  // Menú móvil
  var btn = document.getElementById("menu-btn");
  var menu = document.getElementById("menu");
  if (btn && menu) {
    btn.addEventListener("click", function () {
      menu.classList.toggle("hidden");
      menu.classList.toggle("flex");
    });
  }

  // Confirmación en formularios y enlaces con data-confirm
  document.addEventListener("submit", function (ev) {
    var msg = ev.target.getAttribute("data-confirm");
    if (msg && !window.confirm(msg)) ev.preventDefault();
  });

  // Evita doble envío
  document.addEventListener("submit", function (ev) {
    if (ev.defaultPrevented) return;
    var b = ev.target.querySelector('button[type="submit"][data-once], button[data-once]');
    if (b) setTimeout(function () { b.disabled = true; }, 0);
  });

  // Cierra el menú de usuario al hacer clic fuera
  document.addEventListener("click", function (ev) {
    document.querySelectorAll("header details[open]").forEach(function (d) {
      if (!d.contains(ev.target)) d.removeAttribute("open");
    });
  });

  window.formatSoles = function (n) {
    return "S/ " + Number(n).toLocaleString("en-US", { maximumFractionDigits: 0 });
  };
})();
