(function () {
  var SEARCH_PLACEHOLDER = "Search";

  function isMacPlatform() {
    var userAgentData = navigator.userAgentData;
    var platforms = [navigator.platform];
    if (userAgentData && userAgentData.platform) {
      platforms.push(userAgentData.platform);
    }

    return /mac/i.test(platforms.join(" "));
  }

  function getSearchInput() {
    return document.querySelector("[data-md-component='search-query']");
  }

  function getSearchForm() {
    var input = getSearchInput();

    return input ? input.form : document.forms.namedItem("search");
  }

  function updateSearchPlaceholder() {
    var input = getSearchInput();
    if (!input) {
      return;
    }

    input.setAttribute("placeholder", SEARCH_PLACEHOLDER);
    input.setAttribute("aria-label", SEARCH_PLACEHOLDER);
  }

  function updateSearchShortcutHint() {
    var form = getSearchForm();
    if (!form) {
      return;
    }

    form.setAttribute("data-search-shortcut", isMacPlatform() ? "⌘K" : "Ctrl+K");
  }

  function updateSearchUi() {
    updateSearchPlaceholder();
    updateSearchShortcutHint();
  }

  function openSearch() {
    var searchToggle = document.getElementById("__search");

    if (searchToggle) {
      searchToggle.checked = true;
      searchToggle.dispatchEvent(new Event("change", { bubbles: true }));
    }

    window.setTimeout(function () {
      var input = getSearchInput();
      if (input) {
        input.focus();
        input.select();
      }
    }, 0);
  }

  function isSearchShortcut(event) {
    if (event.defaultPrevented) {
      return false;
    }

    if (event.altKey || event.shiftKey) {
      return false;
    }

    var isMac = isMacPlatform();
    if (isMac ? !event.metaKey || event.ctrlKey : !event.ctrlKey || event.metaKey) {
      return false;
    }

    if ((event.key || "").toLowerCase() !== "k") {
      return false;
    }

    var target = event.target;
    if (target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))) {
      return target === getSearchInput();
    }

    return true;
  }

  updateSearchUi();
  document.addEventListener("DOMContentLoaded", updateSearchUi);

  if (window.document$ && typeof window.document$.subscribe === "function") {
    window.document$.subscribe(updateSearchUi);
  }

  document.addEventListener("keydown", function (event) {
    if (!isSearchShortcut(event)) {
      return;
    }

    event.preventDefault();
    openSearch();
  });
})();
