/* МЕТЭК Сочи — каталог, поиск, форма звонка */
(function () {
  "use strict";

  // Старые закладки вида /katalog#armatura → серверный URL Sprint 1.
  if (location.pathname === "/katalog" && location.hash) {
    var slug = decodeURIComponent(location.hash.slice(1)).split(",")[0];
    if (/^[a-z0-9-]+$/.test(slug)) {
      location.replace("/katalog/" + slug);
      return;
    }
  }

  var PRICES_URL = "/api/catalog-data";
  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var NA_LABEL = "Уточняйте у менеджера";
  var _data = null, _loading = null;

  function loadPrices() {
    if (_data) return Promise.resolve(_data);
    if (_loading) return _loading;
    _loading = fetch(PRICES_URL, { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (j) { _data = j; return j; });
    return _loading;
  }

  function fmtPrice(v) {
    if (v == null || isNaN(v)) return null;
    return Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, "\u202F") + " ₽";
  }

  function allItems(data) {
    var out = [];
    data.groups.forEach(function (g) {
      g.items.forEach(function (it) {
        out.push({ g: g, it: it });
      });
    });
    return out;
  }

  function matches(name, query) {
    var hay = name.toLowerCase();
    return query.toLowerCase().split(/\s+/).filter(Boolean).every(function (w) {
      return hay.indexOf(w) !== -1;
    });
  }

  /* ── автокомплит ── */
  function initSearch(form) {
    var input = form.querySelector("input[name=q]");
    var box = form.querySelector(".sug");
    if (!input || !box) return;
    var sel = -1;

    function close() { box.hidden = true; box.innerHTML = ""; sel = -1; }

    function render(list, q) {
      if (!list.length) {
        box.innerHTML = '<div class="empty">Ничего не нашлось — привезём под заказ. ' +
          '<a href="/kontakty#zvonok">Запросить позицию</a></div>';
        box.hidden = false;
        return;
      }
      box.innerHTML = list.map(function (r) {
        var p = fmtPrice(r.it.price);
        return '<a href="/katalog?q=' + encodeURIComponent(r.it.name) + '">' +
          '<span class="thumb">' + esc(r.g.name.charAt(0)) + "</span>" +
          '<span class="nm">' + esc(r.it.name) + "</span>" +
          (p ? '<span class="pr">' + p + "</span>"
             : '<span class="pr na">уточняйте</span>') +
          "</a>";
      }).join("");
      box.hidden = false;
    }

    input.addEventListener("input", function () {
      var q = input.value.trim();
      if (q.length < 2) { close(); return; }
      loadPrices().then(function (data) {
        if (input.value.trim() !== q) return;
        var found = allItems(data).filter(function (r) { return matches(r.it.name, q); }).slice(0, 8);
        render(found, q);
      }).catch(close);
    });

    input.addEventListener("keydown", function (e) {
      var links = box.querySelectorAll("a");
      if (e.key === "ArrowDown" && links.length) {
        e.preventDefault(); sel = (sel + 1) % links.length;
      } else if (e.key === "ArrowUp" && links.length) {
        e.preventDefault(); sel = (sel - 1 + links.length) % links.length;
      } else if (e.key === "Enter" && sel >= 0 && links[sel]) {
        e.preventDefault(); location.href = links[sel].href; return;
      } else if (e.key === "Escape") { close(); return; }
      links.forEach(function (a, i) { a.classList.toggle("sel", i === sel); });
      if (sel >= 0 && links[sel]) links[sel].scrollIntoView({ block: "nearest" });
    });

    document.addEventListener("click", function (e) {
      if (!form.contains(e.target)) close();
    });
  }

  document.querySelectorAll("form[data-search]").forEach(initSearch);

  /* ── прокрутка меню стрелками (вместо полосы) ── */
  document.querySelectorAll(".hscroll").forEach(function (box) {
    var track = box.querySelector(".tabs-nav, .gtabs");
    var btns = box.querySelectorAll(".hs-btn");
    if (!track || !btns.length) return;
    function update() {
      var over = track.scrollWidth - track.clientWidth > 4;
      box.classList.toggle("has-overflow", over);
      if (!over) return;
      btns[0].disabled = track.scrollLeft <= 2;
      btns[1].disabled = track.scrollLeft + track.clientWidth >= track.scrollWidth - 2;
    }
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        track.scrollBy({ left: Number(b.dataset.dir) * Math.max(120, track.clientWidth * 0.6), behavior: "smooth" });
      });
    });
    track.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(update);
    setTimeout(update, 300);
    var active = track.querySelector(".active");
    if (active) active.scrollIntoView({ block: "nearest", inline: "center" });
  });

  /* ── каталог ── */
  var tabsBox = document.getElementById("groupTabs");
  var body = document.getElementById("priceBody");
  if (tabsBox && body) {
    var stamp = document.getElementById("stampText");
    var info = document.getElementById("searchInfo");
    var params = new URLSearchParams(location.search);
    var query = (params.get("q") || "").trim();

    loadPrices().then(function (data) {
      if (stamp) {
        var d = new Date(data.updated_at);
        stamp.textContent = isNaN(d) ? "прайс склада"
          : "прайс от " + d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
      }
      if (query) renderSearch(data, query); else renderTabs(data);
    }).catch(function () {
      body.innerHTML = '<tr><td colspan="2" style="color:var(--muted)">Не получилось загрузить прайс. ' +
        'Позвоните нам: <a href="tel:+78622910033">+7 (862) 291-00-33</a></td></tr>';
      if (stamp) stamp.textContent = "прайс временно недоступен";
    });

    function rowsHtml(rows, withGroup) {
      return rows.map(function (r) {
        var p = fmtPrice(r.it.price);
        return "<tr><td>" + esc(r.it.name) + (withGroup ? ' <span style="color:var(--muted);font-size:12px">· ' + esc(r.g.name) + "</span>" : "") +
          "</td>" +
          '<td style="text-align:right">' + (p ? '<span class="mono">' + p + "</span>"
            : '<span style="color:var(--muted);font-size:13px">' + NA_LABEL + "</span>") + "</td></tr>";
      }).join("");
    }

    function renderTabs(data) {
      if (info) info.hidden = true;
      var selBox = document.getElementById("selectedGroups");
      var searchInput = document.querySelector("form[data-search] input[name=q]");
      var selected = [];
      tabsBox.innerHTML = "";

      var fromHash = decodeURIComponent(location.hash.replace("#", "")).split(",").filter(Boolean);
      data.groups.forEach(function (g) {
        var b = document.createElement("button");
        b.type = "button"; b.setAttribute("role", "tab"); b.textContent = g.name; b.dataset.slug = String(g.slug);
        b.setAttribute("aria-pressed", "false");
        b.addEventListener("click", function () {
          if (searchInput) { searchInput.value = ""; var s = searchInput.closest("form").querySelector(".sug"); if (s) { s.hidden = true; s.innerHTML = ""; } }
          toggle(g.slug);
        });
        tabsBox.appendChild(b);
        if (fromHash.indexOf(g.slug) !== -1) selected.push(g.slug);
      });
      if (!selected.length) selected = [data.groups[0].slug];
      paint();

      function toggle(slug) {
        var i = selected.indexOf(slug);
        if (i === -1) selected.push(slug);
        else if (selected.length > 1) selected.splice(i, 1);  // хотя бы одна группа остаётся
        paint();
        history.replaceState(null, "", "#" + selected.join(","));
      }

      function paint() {
        var order = data.groups.filter(function (g) { return selected.indexOf(g.slug) !== -1; });
        tabsBox.querySelectorAll("button").forEach(function (b) {
          var on = selected.indexOf(b.dataset.slug) !== -1;
          b.classList.toggle("active", on); b.setAttribute("aria-pressed", on);
        });
        var rows = [];
        order.forEach(function (g) { g.items.forEach(function (it) { rows.push({ g: g, it: it }); }); });
        body.innerHTML = rowsHtml(rows, order.length > 1);
        if (selBox) {
          selBox.hidden = order.length < 2;
          selBox.innerHTML = order.length < 2 ? "" : order.map(function (g) {
            return '<span class="chip">' + esc(g.name) +
              '<button type="button" aria-label="Убрать ' + esc(g.name) + '" data-rm="' + esc(g.slug) + '">×</button></span>';
          }).join("");
          selBox.querySelectorAll("button[data-rm]").forEach(function (x) {
            x.addEventListener("click", function () { toggle(x.dataset.rm); });
          });
        }
      }

      window.addEventListener("hashchange", function () {
        var slugs = decodeURIComponent(location.hash.replace("#", "")).split(",").filter(Boolean);
        var valid = slugs.filter(function (s) { return data.groups.some(function (g) { return g.slug === s; }); });
        if (valid.length) { selected = valid; paint(); }
      });
    }

    function renderSearch(data, q) {
      var found = allItems(data).filter(function (r) { return matches(r.it.name, q); });
      tabsBox.innerHTML = "";
      if (info) {
        info.hidden = false;
        info.innerHTML = "Найдено <b>" + found.length + "</b> позиций по запросу «<b>" +
          esc(q) + "</b>» · <a href=\"/katalog\">Сбросить поиск</a>";
      }
      var searchInput = document.querySelector("form[data-search] input[name=q]");
      if (searchInput) searchInput.value = q;
      if (!found.length) {
        body.innerHTML = '<tr><td colspan="2"><div class="notfound">Такой позиции сейчас нет в прайсе — ' +
          'привезём под заказ. Назовите марку и сечение — найдём и посчитаем.<br><br>' +
          '<a class="btn" href="/kontakty#zvonok">Запросить позицию</a></div></td></tr>';
        return;
      }
      body.innerHTML = rowsHtml(found, true);
    }
  }

  /* ── форма обратного звонка ── */
  var form = document.getElementById("callForm");
  if (form) {
    var msg = document.getElementById("formMsg");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var name = form.name.value.trim();
      var phone = form.phone.value.trim();
      msg.className = "form-msg";
      if (name.length < 2) { msg.textContent = "Напишите имя — так менеджеру проще обратиться к вам."; msg.classList.add("err"); return; }
      var digits = phone.replace(/\D/g, "");
      if (digits.length < 10) { msg.textContent = "Проверьте телефон: нужен номер из 11 цифр, например +7 900 000-00-00."; msg.classList.add("err"); return; }
      if (form.website && form.website.value) return;
      msg.textContent = "Отправляем…";
      fetch("/api/callback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, phone: phone })
      }).then(function (r) {
        if (r.ok) {
          msg.textContent = "Спасибо! Заявка ушла менеджеру — перезвоним в рабочее время.";
          msg.classList.add("ok");
          form.reset();
        } else if (r.status === 429) {
          msg.textContent = "Слишком много заявок подряд. Позвоните нам напрямую: +7 (862) 291-00-33.";
          msg.classList.add("err");
        } else {
          return r.json().catch(function () { return {}; }).then(function (j) {
            msg.textContent = (j && j.detail) ? String(j.detail) : "Не получилось отправить. Позвоните нам: +7 (862) 291-00-33.";
            msg.classList.add("err");
          });
        }
      }).catch(function () {
        msg.textContent = "Нет связи с сервером. Позвоните нам: +7 (862) 291-00-33.";
        msg.classList.add("err");
      });
    });
  }
})();
