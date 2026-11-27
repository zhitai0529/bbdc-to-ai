(function () {
  "use strict";

  var root = document.documentElement;
  var storageKey = "bbdc-to-ai.home.appearance";
  var appearanceButtons = Array.prototype.slice.call(document.querySelectorAll("[data-appearance]"));
  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  var metaTheme = document.querySelector('meta[name="theme-color"]');

  function resolveTheme(preference) {
    if (preference === "light" || preference === "dark") return preference;
    return systemDark.matches ? "dark" : "light";
  }

  function applyAppearance(preference) {
    var theme = resolveTheme(preference);
    root.dataset.preference = preference;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    if (metaTheme) metaTheme.setAttribute("content", theme === "dark" ? "#10151D" : "#F7F9FC");
    appearanceButtons.forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.appearance === preference ? "true" : "false");
    });
  }

  function rememberAppearance(preference) {
    try { window.localStorage.setItem(storageKey, preference); } catch (error) {}
  }

  applyAppearance(root.dataset.preference || "system");

  appearanceButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var preference = button.dataset.appearance;
      rememberAppearance(preference);
      applyAppearance(preference);
    });
  });

  function onSystemThemeChange() {
    if (root.dataset.preference === "system") applyAppearance("system");
  }

  if (typeof systemDark.addEventListener === "function") systemDark.addEventListener("change", onSystemThemeChange);
  else if (typeof systemDark.addListener === "function") systemDark.addListener(onSystemThemeChange);

  var toast = document.querySelector(".toast");
  var toastTimer = 0;

  function announce(message) {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.dataset.visible = "true";
    toastTimer = window.setTimeout(function () { toast.dataset.visible = "false"; }, 3000);
  }

  function fallbackCopy(text) {
    var previousFocus = document.activeElement;
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.setAttribute("aria-hidden", "true");
    area.style.position = "fixed";
    area.style.left = "-9999px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var copied = false;
    try { copied = document.execCommand("copy"); } catch (error) { copied = false; }
    area.remove();
    if (previousFocus) previousFocus.focus({ preventScroll: true });
    return copied;
  }

  function copyText(text, onSuccess, onFailure) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(onSuccess, function () {
        if (fallbackCopy(text)) onSuccess();
        else onFailure();
      });
      return;
    }
    if (fallbackCopy(text)) onSuccess();
    else onFailure();
  }

  var promptButton = document.querySelector("[data-copy-prompt]");
  var promptSource = document.getElementById("prompt-source");
  var feedbackTimer = 0;

  function showCopySuccess() {
    var label = promptButton.querySelector("[data-copy-label]");
    if (!label) return;
    window.clearTimeout(feedbackTimer);
    label.textContent = "已复制完整 Prompt";
    promptButton.dataset.copied = "true";
    feedbackTimer = window.setTimeout(function () {
      label.textContent = "复制公开示例 Prompt";
      delete promptButton.dataset.copied;
    }, 2600);
  }

  if (promptButton && promptSource) {
    promptButton.addEventListener("click", function () {
      var source = promptSource.content ? promptSource.content.textContent : promptSource.textContent;
      var text = source.replace(/^\n+/, "").replace(/\s+$/, "");
      copyText(text, function () {
        showCopySuccess();
        announce("已复制完整公开示例 Prompt，可直接粘贴给你常用的 AI。");
      }, function () {
        announce("浏览器未允许自动复制，请打开页面中的“查看完整合成词表”手动复制。");
      });
    });
  }
})();
