/* 主题切换、复制反馈。无第三方依赖。 */
(function () {
  "use strict";

  var root = document.documentElement;
  var STORAGE_KEY = "bbdc-to-ai.home.appearance";
  var buttons = Array.prototype.slice.call(
    document.querySelectorAll("[data-appearance]")
  );
  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  var metaTheme = document.querySelector('meta[name="theme-color"]');

  function remember(preference) {
    try {
      window.localStorage.setItem(STORAGE_KEY, preference);
    } catch (error) {
      /* 隐私模式下忽略，本次会话仍然生效 */
    }
  }

  function resolve(preference) {
    if (preference === "light" || preference === "dark") return preference;
    return systemDark.matches ? "dark" : "light";
  }

  function apply(preference) {
    var theme = resolve(preference);
    root.dataset.preference = preference;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    if (metaTheme) {
      metaTheme.setAttribute("content", theme === "dark" ? "#141A26" : "#FBF8FD");
    }
    buttons.forEach(function (button) {
      button.setAttribute(
        "aria-pressed",
        button.dataset.appearance === preference ? "true" : "false"
      );
    });
  }

  // <head> 里的内联脚本已在首次绘制前写入 data-theme，这里接管后续切换。
  apply(root.dataset.preference || "system");

  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      var preference = button.dataset.appearance;
      remember(preference);
      apply(preference);
    });
  });

  var onSystemChange = function () {
    if (root.dataset.preference === "system") apply("system");
  };

  if (typeof systemDark.addEventListener === "function") {
    systemDark.addEventListener("change", onSystemChange);
  } else if (typeof systemDark.addListener === "function") {
    systemDark.addListener(onSystemChange);
  }

  /* ---------- 复制反馈 ---------- */
  var toast = document.querySelector(".toast");
  var toastTimer = 0;

  function announce(message) {
    if (!toast) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.dataset.visible = "true";
    toastTimer = window.setTimeout(function () {
      toast.dataset.visible = "false";
    }, 2600);
  }

  function fallbackCopy(text) {
    var previousFocus = document.activeElement;
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.top = "-1000px";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    var copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    } finally {
      area.remove();
      if (previousFocus) previousFocus.focus({ preventScroll: true });
    }
    return copied;
  }

  function copy(text, done, failed) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {
        if (fallbackCopy(text)) done();
        else failed();
      });
      return;
    }
    if (fallbackCopy(text)) done();
    else failed();
  }

  var copyFeedback = new WeakMap();
  function flash(button, label) {
    var feedback = copyFeedback.get(button);
    var original = feedback ? feedback.original : button.textContent;
    if (feedback) window.clearTimeout(feedback.timer);
    button.textContent = label;
    button.dataset.copied = "true";
    var timer = window.setTimeout(function () {
      button.textContent = original;
      delete button.dataset.copied;
      copyFeedback.delete(button);
    }, 2400);
    copyFeedback.set(button, { original: original, timer: timer });
  }

  var promptButton = document.querySelector("[data-copy-prompt]");
  var promptSource = document.getElementById("prompt-source");

  if (promptButton && promptSource) {
    promptButton.addEventListener("click", function () {
      var text = promptSource.content
        ? promptSource.content.textContent
        : promptSource.textContent;
      text = text.replace(/^\n+/, "").replace(/\s+$/, "");
      copy(
        text,
        function () {
          flash(promptButton, "已复制");
          announce("已复制完整 Prompt，共 " + text.length + " 个字符，可直接粘贴给 AI。");
        },
        function () {
          announce("浏览器未允许自动复制。请在仓库里打开 examples/synthetic_review.md 手动复制。");
        }
      );
    });
  }

  var linkButtons = Array.prototype.slice.call(
    document.querySelectorAll("[data-copy-link]")
  );

  var canonical = document.querySelector('link[rel="canonical"]');
  linkButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var url = canonical ? canonical.href : window.location.href;
      copy(
        url,
        function () {
          flash(button, "链接已复制");
          announce("链接已复制。请在电脑浏览器打开本页，再前往 GitHub 下载 Windows 版。");
        },
        function () {
          announce("请手动复制地址栏链接，在电脑上打开本页。");
        }
      );
    });
  });
})();
