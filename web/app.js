/* AI Free Software Index - dashboard logic.
   Vanilla JS, no build step. Reads ./data/index.json produced by the aiindex pipeline. */

(function () {
  "use strict";

  var DATA_URL = "data/index.json";
  var PER_PAGE = 24;
  var STORAGE_KEY = "aiindex.theme";

  var FACET_GROUPS = [
    { key: "category", label: "Category", field: "category", open: true },
    { key: "maturity", label: "Maturity", field: "maturity", open: true },
    { key: "kind", label: "Type", field: "kind" },
    { key: "source", label: "Source", field: "sources", limit: 8 },
    { key: "language", label: "Language", field: "language", limit: 12 },
    { key: "license", label: "License", field: "license", limit: 12 },
    { key: "tag", label: "Tag", field: "tags", limit: 24 }
  ];

  var state = {
    items: [],
    stats: {},
    facets: {},
    query: "",
    sort: "score",
    minStars: 0,
    selfHostedOnly: false,
    hideArchived: false,
    selected: {},
    expanded: {},
    page: 1
  };

  FACET_GROUPS.forEach(function (group) { state.selected[group.key] = []; });

  var el = {
    stats: document.getElementById("stats"),
    generatedAt: document.getElementById("generated-at"),
    search: document.getElementById("search"),
    sort: document.getElementById("sort"),
    minStars: document.getElementById("min-stars"),
    selfHosted: document.getElementById("self-hosted"),
    hideArchived: document.getElementById("hide-archived"),
    clear: document.getElementById("clear-filters"),
    exportCsv: document.getElementById("export-csv"),
    facetGroups: document.getElementById("facet-groups"),
    facetsClear: document.getElementById("facets-clear"),
    count: document.getElementById("result-count"),
    chips: document.getElementById("active-chips"),
    grid: document.getElementById("grid"),
    loadMore: document.getElementById("load-more"),
    detail: document.getElementById("detail"),
    detailBody: document.getElementById("detail-body"),
    detailClose: document.getElementById("detail-close"),
    theme: document.getElementById("theme-toggle"),
    repoLink: document.getElementById("repo-link"),
    footerMeta: document.getElementById("footer-meta"),
    error: document.getElementById("error")
  };

  /* ---------- helpers ---------- */

  function escapeHtml(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function num(value) {
    var n = Number(value || 0);
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "k";
    return String(n);
  }

  function relTime(iso) {
    if (!iso) return "";
    var then = Date.parse(iso);
    if (isNaN(then)) return "";
    var days = Math.floor((Date.now() - then) / 86400000);
    if (days <= 0) return "today";
    if (days === 1) return "yesterday";
    if (days < 30) return days + " days ago";
    if (days < 365) return Math.floor(days / 30) + " months ago";
    return Math.floor(days / 365) + " years ago";
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments, self = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(self, args); }, wait);
    };
  }

  function showError(message) {
    el.error.textContent = message;
    el.error.hidden = false;
  }

  /* ---------- data loading ---------- */

  function load() {
    fetch(DATA_URL, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (payload) {
        state.items = payload.items || [];
        state.stats = payload.stats || {};
        state.facets = payload.facets || {};
        renderStats(payload.generated_at);
        renderFacets();
        render();
      })
      .catch(function (error) {
        el.count.textContent = "No data available.";
        el.grid.innerHTML = '<p class="empty">Could not load <code>' + DATA_URL + "</code> (" + escapeHtml(error.message) +
          ").<br>Run <code>python -m aiindex build</code> then <code>python -m aiindex serve</code>, or open the deployed site.</p>";
        showError("Dashboard data is unavailable: " + error.message);
      });
  }

  function renderStats(generatedAt) {
    var mapping = { total: "indexed", open_source: "open source", self_hostable: "self-hostable", repos: "repositories", with_discussion: "with discussion", enriched: "AI-enriched" };
    Array.prototype.forEach.call(el.stats.querySelectorAll(".stat"), function (node) {
      var key = node.querySelector(".stat-value").getAttribute("data-stat");
      if (mapping[key]) node.querySelector(".stat-value").textContent = num(state.stats[key]);
    });
    el.generatedAt.textContent = generatedAt ? new Date(generatedAt).toLocaleString() : "unknown";
    el.footerMeta.textContent = "Index built " + (generatedAt ? new Date(generatedAt).toLocaleString() : "unknown") +
      " · " + num(state.stats.total) + " entries · " + num(state.stats.enriched) + " AI-enriched.";
  }

  /* ---------- facets ---------- */

  function renderFacets() {
    var html = "";
    FACET_GROUPS.forEach(function (group) {
      var options = (state.facets[group.key] || []).slice();
      if (!options.length) return;
      var visible = state.expanded[group.key] ? options : options.slice(0, group.limit || options.length);
      var selected = state.selected[group.key];
      var rows = visible.map(function (option) {
        var value = String(option.value);
        var checked = selected.indexOf(value) >= 0 ? " checked" : "";
        return '<label class="facet-option"><input type="checkbox" data-group="' + group.key + '" value="' + escapeHtml(value) + '"' + checked + '>' +
          "<span>" + escapeHtml(value) + '</span><span class="count">' + option.count + "</span></label>";
      }).join("");
      var more = "";
      if (group.limit && options.length > group.limit) {
        more = '<button class="link facet-more" data-group="' + group.key + '" type="button">' +
          (state.expanded[group.key] ? "show less" : "+" + (options.length - group.limit) + " more") + "</button>";
      }
      html += '<details class="facet-group"' + (group.open || selected.length ? " open" : "") + ">" +
        "<summary>" + escapeHtml(group.label) + (selected.length ? " (" + selected.length + ")" : "") + "</summary>" +
        '<div class="facet-options">' + rows + "</div>" + more + "</details>";
    });
    el.facetGroups.innerHTML = html || '<p class="muted">No facets in this dataset.</p>';
  }

  /* ---------- filtering ---------- */

  function valuesFor(item, field) {
    var value = item[field];
    if (Array.isArray(value)) return value.map(String);
    if (value === null || value === undefined || value === "") return [];
    return [String(value)];
  }

  function matches(item) {
    if (state.selfHostedOnly && !item.self_hostable) return false;
    if (state.hideArchived && item.archived) return false;
    if (state.minStars && Number(item.stars || 0) < state.minStars) return false;

    for (var i = 0; i < FACET_GROUPS.length; i++) {
      var group = FACET_GROUPS[i];
      var selected = state.selected[group.key];
      if (!selected.length) continue;
      var values = valuesFor(item, group.field).map(function (v) { return v.toLowerCase(); });
      var hit = selected.some(function (choice) { return values.indexOf(choice.toLowerCase()) >= 0; });
      if (!hit) return false;
    }

    var q = state.query.trim().toLowerCase();
    if (!q) return true;
    var haystack = [
      item.name, item.description, item.summary, item.category, item.language,
      item.license, (item.tags || []).join(" "), (item.topics || []).join(" "),
      (item.sources || []).join(" ")
    ].join(" ").toLowerCase();
    return q.split(/\s+/).every(function (token) { return haystack.indexOf(token) >= 0; });
  }

  function sortItems(items) {
    var sorted = items.slice();
    switch (state.sort) {
      case "stars":
        sorted.sort(function (a, b) { return (b.stars || 0) - (a.stars || 0); }); break;
      case "updated":
        sorted.sort(function (a, b) { return String(b.pushed_at || "").localeCompare(String(a.pushed_at || "")); }); break;
      case "new":
        sorted.sort(function (a, b) { return String(b.created_at || "").localeCompare(String(a.created_at || "")); }); break;
      case "discussion":
        sorted.sort(function (a, b) { return (b.points || 0) - (a.points || 0); }); break;
      case "name":
        sorted.sort(function (a, b) { return String(a.name || "").toLowerCase().localeCompare(String(b.name || "").toLowerCase()); }); break;
      default:
        sorted.sort(function (a, b) { return (b.score || 0) - (a.score || 0); });
    }
    return sorted;
  }

  function activeFilterCount() {
    var count = FACET_GROUPS.reduce(function (total, group) { return total + state.selected[group.key].length; }, 0);
    if (state.selfHostedOnly) count++;
    if (state.hideArchived) count++;
    if (state.minStars) count++;
    return count;
  }

  /* ---------- rendering ---------- */

  function render() {
    var filtered = sortItems(state.items.filter(matches));
    var visible = filtered.slice(0, state.page * PER_PAGE);
    el.count.textContent = "Showing " + visible.length + " of " + filtered.length + " matching entries (" +
      state.items.length + " indexed)";
    el.grid.innerHTML = visible.length ? visible.map(cardHtml).join("") : '<p class="empty">Nothing matches those filters.</p>';
    el.loadMore.hidden = visible.length >= filtered.length;
    renderChips();
    renderFacets();
    syncHash();
  }

  function badge(text, kind) {
    return '<span class="badge ' + (kind || "") + '">' + escapeHtml(text) + "</span>";
  }

  function cardHtml(item) {
    var badges = [];
    if (item.stars) badges.push(badge("★ " + num(item.stars), "strong"));
    if (item.license && item.license !== "Unknown") badges.push(badge(item.license, item.license_open ? "open" : ""));
    if (item.language) badges.push(badge(item.language));
    if (item.self_hostable) badges.push(badge("self-host", "self"));
    if (item.maturity) badges.push(badge(item.maturity, item.maturity === "archived" ? "archived" : ""));
    if (item.points) badges.push(badge("HN " + num(item.points)));

    var tags = (item.tags || []).slice(0, 5).map(function (tag) {
      return '<span class="tag" data-tag="' + escapeHtml(tag) + '">#' + escapeHtml(tag) + "</span>";
    }).join("");

    var description = item.summary ? '<p class="card-desc summary">' + escapeHtml(item.summary) + "</p>" : "";
    if (!item.summary && item.description) description = '<p class="card-desc">' + escapeHtml(item.description) + "</p>";

    var owner = item.kind === "repo" ? "" : '<span class="card-owner"> · ' + escapeHtml(item.kind || "") + "</span>";

    return '<article class="card" data-id="' + escapeHtml(item.id) + '">' +
      '<div class="card-head"><h3 class="card-title"><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' +
      escapeHtml(item.name) + "</a>" + owner + "</h3></div>" +
      description +
      '<div class="badges">' + badges.join("") + "</div>" +
      (tags ? '<div class="tags">' + tags + "</div>" : "") +
      '<div class="card-foot"><span class="score" title="Index score: popularity, activity, openness, curation, discussion">' +
      '<span class="score-bar"><span style="width:' + Math.max(3, Math.round(item.score || 0)) + '%"></span></span>' +
      escapeHtml(String(Math.round(item.score || 0))) + "/100</span>" +
      '<span class="card-actions"><button class="ghost" data-action="detail" data-id="' + escapeHtml(item.id) + '">Details</button></span>' +
      "</div></article>";
  }

  function renderChips() {
    var chips = [];
    FACET_GROUPS.forEach(function (group) {
      state.selected[group.key].forEach(function (value) {
        chips.push('<span class="chip">' + escapeHtml(group.label + ": " + value) +
          '<button type="button" data-remove-group="' + group.key + '" data-remove-value="' + escapeHtml(value) + '" aria-label="Remove filter">×</button></span>');
      });
    });
    if (state.selfHostedOnly) chips.push('<span class="chip">self-hostable<button type="button" data-remove="self">×</button></span>');
    if (state.hideArchived) chips.push('<span class="chip">hide archived<button type="button" data-remove="archived">×</button></span>');
    if (state.minStars) chips.push('<span class="chip">≥ ' + num(state.minStars) + ' stars<button type="button" data-remove="stars">×</button></span>');
    if (state.query) chips.push('<span class="chip">search: ' + escapeHtml(state.query) + '<button type="button" data-remove="query">×</button></span>');
    el.chips.innerHTML = chips.join("");
  }

  function breakdownHtml(item) {
    var parts = item.score_parts || {};
    var labels = { popularity: "popularity", activity: "activity", openness: "openness", curation: "curation", discussion: "discussion" };
    var rows = Object.keys(labels).map(function (key) {
      var value = Number(parts[key] || 0);
      return '<div class="breakdown-row"><span>' + labels[key] + '</span><span class="bar"><span style="width:' +
        Math.max(2, value) + '%"></span></span><span>' + Math.round(value) + "</span></div>";
    }).join("");
    return '<div class="breakdown">' + rows + "</div>";
  }

  function detailHtml(item) {
    var meta = [
      ["Category", item.category],
      ["License", item.license],
      ["Language", item.language],
      ["Stars", item.stars ? num(item.stars) : ""],
      ["Forks", item.forks ? num(item.forks) : ""],
      ["Open issues", item.open_issues ? num(item.open_issues) : ""],
      ["Last push", item.pushed_at ? relTime(item.pushed_at) + " (" + String(item.pushed_at).slice(0, 10) + ")" : ""],
      ["Created", item.created_at ? String(item.created_at).slice(0, 10) : ""],
      ["Maturity", item.maturity],
      ["Self-hostable", item.self_hostable ? "yes" : "no"],
      ["Best for", item.target_user],
      ["Setup difficulty", item.difficulty ? item.difficulty + "/5" : ""],
      ["Sources", (item.sources || []).join(", ")],
      ["First seen", item.first_seen ? String(item.first_seen).slice(0, 10) : ""],
      ["AI enriched", item.enriched_at ? "yes (" + escapeHtml(item.enrichment_model || "") + ")" : "no"]
    ].filter(function (pair) { return pair[1]; });

    var links = '<a class="primary" href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">Open project</a>';
    if (item.homepage) links += '<a class="ghost" href="' + escapeHtml(item.homepage) + '" target="_blank" rel="noopener">Homepage</a>';
    if (item.discussion_url) links += '<a class="ghost" href="' + escapeHtml(item.discussion_url) + '" target="_blank" rel="noopener">Hacker News thread</a>';

    return "<h2>" + escapeHtml(item.name) + "</h2>" +
      '<p class="owner">' + escapeHtml(item.kind || "entry") + (item.archived ? " · archived" : "") +
      " · index score " + Math.round(item.score || 0) + "/100</p>" +
      (item.summary ? '<p class="lede">' + escapeHtml(item.summary) + "</p>" : "") +
      (item.description ? '<p class="desc">' + escapeHtml(item.description) + "</p>" : "") +
      '<div class="badges">' + (item.tags || []).map(function (tag) {
        return '<span class="tag" data-tag="' + escapeHtml(tag) + '">#' + escapeHtml(tag) + "</span>";
      }).join("") + "</div>" +
      "<h3>Details</h3><dl class=\"meta\">" + meta.map(function (pair) {
        return "<div><dt>" + escapeHtml(pair[0]) + "</dt><dd>" + escapeHtml(pair[1]) + "</dd></div>";
      }).join("") + "</dl>" +
      (item.free_tier_notes ? "<h3>Free usage</h3><p class=\"desc\">" + escapeHtml(item.free_tier_notes) + "</p>" : "") +
      "<h3>Score breakdown</h3>" + breakdownHtml(item) +
      '<div class="actions">' + links + "</div>";
  }

  function openDetail(id) {
    var item = state.items.filter(function (entry) { return entry.id === id; })[0];
    if (!item) return;
    el.detailBody.innerHTML = detailHtml(item);
    if (typeof el.detail.showModal === "function") el.detail.showModal();
    else el.detail.setAttribute("open", "open");
  }

  /* ---------- url state ---------- */

  function syncHash() {
    var params = new URLSearchParams();
    if (state.query) params.set("q", state.query);
    if (state.sort !== "score") params.set("sort", state.sort);
    if (state.minStars) params.set("stars", state.minStars);
    if (state.selfHostedOnly) params.set("self", "1");
    if (state.hideArchived) params.set("archived", "1");
    FACET_GROUPS.forEach(function (group) {
      if (state.selected[group.key].length) params.set(group.key, state.selected[group.key].join("|"));
    });
    var hash = params.toString();
    if (window.history.replaceState) {
      window.history.replaceState(null, "", hash ? "#" + hash : window.location.pathname);
    }
  }

  function readHash() {
    var raw = window.location.hash.replace(/^#/, "");
    if (!raw) return;
    var params = new URLSearchParams(raw);
    state.query = params.get("q") || "";
    state.sort = params.get("sort") || "score";
    state.minStars = Number(params.get("stars") || 0);
    state.selfHostedOnly = params.get("self") === "1";
    state.hideArchived = params.get("archived") === "1";
    FACET_GROUPS.forEach(function (group) {
      var value = params.get(group.key);
      if (value) state.selected[group.key] = value.split("|");
    });
    el.search.value = state.query;
    el.sort.value = state.sort;
    el.minStars.value = String(state.minStars);
    el.selfHosted.checked = state.selfHostedOnly;
    el.hideArchived.checked = state.hideArchived;
  }

  /* ---------- csv ---------- */

  function exportCsv() {
    var rows = sortItems(state.items.filter(matches));
    var columns = ["name", "url", "category", "license", "license_open", "stars", "language", "self_hostable", "maturity", "score", "summary", "description", "pushed_at", "sources", "tags"];
    var lines = [columns.join(",")];
    rows.forEach(function (item) {
      lines.push(columns.map(function (column) {
        var value = item[column];
        if (Array.isArray(value)) value = value.join(" ");
        if (value === null || value === undefined) value = "";
        return '"' + String(value).replace(/"/g, '""').replace(/\s+/g, " ").trim() + '"';
      }).join(","));
    });
    var blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ai-free-software-index.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  }

  /* ---------- events ---------- */

  function toggleFacet(group, value, checked) {
    var list = state.selected[group];
    var index = list.indexOf(value);
    if (checked && index < 0) list.push(value);
    if (!checked && index >= 0) list.splice(index, 1);
    state.page = 1;
    render();
  }

  function resetAll() {
    FACET_GROUPS.forEach(function (group) { state.selected[group.key] = []; });
    state.query = "";
    state.sort = "score";
    state.minStars = 0;
    state.selfHostedOnly = false;
    state.hideArchived = false;
    state.page = 1;
    el.search.value = "";
    el.sort.value = "score";
    el.minStars.value = "0";
    el.selfHosted.checked = false;
    el.hideArchived.checked = false;
    render();
  }

  function bind() {
    el.search.addEventListener("input", debounce(function (event) {
      state.query = event.target.value;
      state.page = 1;
      render();
    }, 180));

    el.sort.addEventListener("change", function (event) { state.sort = event.target.value; state.page = 1; render(); });
    el.minStars.addEventListener("change", function (event) { state.minStars = Number(event.target.value); state.page = 1; render(); });
    el.selfHosted.addEventListener("change", function (event) { state.selfHostedOnly = event.target.checked; state.page = 1; render(); });
    el.hideArchived.addEventListener("change", function (event) { state.hideArchived = event.target.checked; state.page = 1; render(); });
    el.clear.addEventListener("click", resetAll);
    el.facetsClear.addEventListener("click", resetAll);
    el.exportCsv.addEventListener("click", exportCsv);
    el.loadMore.addEventListener("click", function () { state.page += 1; render(); });

    el.facetGroups.addEventListener("change", function (event) {
      var input = event.target;
      if (input && input.matches("input[type=checkbox][data-group]")) {
        toggleFacet(input.getAttribute("data-group"), input.value, input.checked);
      }
    });

    el.facetGroups.addEventListener("click", function (event) {
      var button = event.target.closest(".facet-more");
      if (button) {
        var group = button.getAttribute("data-group");
        state.expanded[group] = !state.expanded[group];
        renderFacets();
      }
    });

    el.chips.addEventListener("click", function (event) {
      var button = event.target.closest("button[data-remove], button[data-remove-group]");
      if (!button) return;
      var group = button.getAttribute("data-remove-group");
      if (group) {
        toggleFacet(group, button.getAttribute("data-remove-value"), false);
        return;
      }
      var what = button.getAttribute("data-remove");
      if (what === "self") { state.selfHostedOnly = false; el.selfHosted.checked = false; }
      if (what === "archived") { state.hideArchived = false; el.hideArchived.checked = false; }
      if (what === "stars") { state.minStars = 0; el.minStars.value = "0"; }
      if (what === "query") { state.query = ""; el.search.value = ""; }
      state.page = 1;
      render();
    });

    el.grid.addEventListener("click", function (event) {
      var tag = event.target.closest(".tag");
      if (tag) {
        var value = tag.getAttribute("data-tag");
        var group = (state.facets.tag || []).some(function (option) { return String(option.value) === value; }) ? "tag" : null;
        if (group && state.selected.tag.indexOf(value) < 0) {
          state.selected.tag.push(value);
          state.page = 1;
          render();
        }
        return;
      }
      var button = event.target.closest("button[data-action=detail]");
      if (button) { openDetail(button.getAttribute("data-id")); return; }
      var card = event.target.closest(".card");
      if (card && !event.target.closest("a")) openDetail(card.getAttribute("data-id"));
    });

    el.detailBody.addEventListener("click", function (event) {
      var tag = event.target.closest(".tag");
      if (tag) {
        var value = tag.getAttribute("data-tag");
        if (state.selected.tag.indexOf(value) < 0) state.selected.tag.push(value);
        el.detail.close();
        state.page = 1;
        render();
      }
    });

    el.detailClose.addEventListener("click", function () { el.detail.close(); });
    el.detail.addEventListener("click", function (event) { if (event.target === el.detail) el.detail.close(); });

    document.addEventListener("keydown", function (event) {
      if (event.key === "/" && document.activeElement !== el.search) {
        event.preventDefault();
        el.search.focus();
      }
      if (event.key === "Escape" && el.detail.open) el.detail.close();
    });

    el.theme.addEventListener("click", function () {
      var next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      applyTheme(next);
    });

    window.addEventListener("hashchange", function () {
      readHash();
      state.page = 1;
      render();
    });
  }

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    el.theme.textContent = theme === "dark" ? "Light" : "Dark";
    el.theme.setAttribute("aria-pressed", theme === "light" ? "true" : "false");
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (error) { /* private mode */ }
  }

  function init() {
    var saved = null;
    try { saved = localStorage.getItem(STORAGE_KEY); } catch (error) { saved = null; }
    if (!saved && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) saved = "light";
    applyTheme(saved === "light" ? "light" : "dark");
    readHash();
    bind();
    load();
  }

  init();
})();
