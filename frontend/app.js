import {
  createIcons,
  BookOpen,
  LayoutDashboard,
  FileText,
  History,
  Settings2,
  FolderOpen,
  ChevronRight,
  CalendarDays,
  RefreshCw,
  Download,
  Copy,
  Activity,
  Flame,
  CalendarRange,
  ChartNoAxesCombined,
  BookOpenText,
  Save,
  Repeat2,
  ListFilter,
  Monitor,
  Layers3,
  CircleCheckBig,
  ScanLine,
  Check,
} from "lucide";
import MarkdownIt from "markdown-it";
import { byId, node, overview, trends } from "./charts";
const glyphs = {
  BookOpen,
  LayoutDashboard,
  FileText,
  History,
  Settings2,
  FolderOpen,
  ChevronRight,
  CalendarDays,
  RefreshCw,
  Download,
  Copy,
  Activity,
  Flame,
  CalendarRange,
  ChartNoAxesCombined,
  BookOpenText,
  Save,
  Repeat2,
  ListFilter,
  Monitor,
  Layers3,
  CircleCheckBig,
  ScanLine,
  Check,
};
const icons = () => createIcons({ icons: glyphs });
const md = new MarkdownIt({ html: false, linkify: false }).disable([
  "image",
  "link",
  "autolink",
]);
const api = () => window.pywebview.api;
let data,
  view = "overview",
  editing = false,
  busy = false,
  toastTimer,
  copyTimer;
const drafts = new Map(),
  log = [];
const draftKey = () => JSON.stringify([data.folder, data.day]);
const content = () => drafts.get(draftKey())?.text ?? data.prompt ?? "";
function message(text, toast = false) {
  byId("status").textContent = text;
  if (!toast) return;
  byId("toast").textContent = text;
  byId("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (byId("toast").hidden = true), 3900);
}
function report(e) {
  message(e?.message || String(e), true);
}
function record(line) {
  if (!line) return;
  log.push(
    new Date().toLocaleTimeString("zh-CN", { hour12: false }) + "  " + line,
  );
  byId("logs").textContent = log.slice(-120).join("\n");
  byId("logs").scrollTop = byId("logs").scrollHeight;
}
function controls() {
  for (const el of document.querySelectorAll("[data-action]")) {
    const a = el.dataset.action;
    el.disabled =
      a === "copy"
        ? !data || !content()
        : a === "save"
          ? busy || !data || !drafts.has(draftKey())
          : ["sync", "setup", "export", "change"].includes(a) &&
            (busy || !data);
  }
  byId("dates").disabled = busy || !data;
  byId("dot").classList.toggle("busy", busy);
}
function choose(title, body, choices) {
  const dialog = byId("modal");
  byId("modalTitle").textContent = title;
  byId("modalBody").textContent = body;
  const buttons = byId("choices");
  buttons.replaceChildren();
  for (const [value, label] of choices) {
    const btn = node("button", label);
    btn.onclick = () => dialog.close(value);
    buttons.append(btn);
  }
  buttons.lastChild.classList.add("primary");
  dialog.returnValue = "";
  dialog.showModal();
  return new Promise((resolve) =>
    dialog.addEventListener("close", () => resolve(dialog.returnValue), {
      once: true,
    }),
  );
}
function table(id, headers, rows, empty) {
  const box = byId(id);
  box.replaceChildren();
  if (!rows.length) {
    box.append(node("p", empty, "empty"));
    return;
  }
  const wrapper = node("div", undefined, "scrolltable"),
    t = node("table", undefined, "dataTable"),
    h = t.createTHead().insertRow();
  headers.forEach((v) => h.append(node("th", v)));
  const body = t.createTBody();
  for (const vals of rows) {
    const row = body.insertRow();
    vals.forEach((v) => row.append(node("td", v ?? "—")));
  }
  wrapper.append(t);
  box.append(wrapper);
}
function preview() {
  const available = data.prompt !== null || drafts.has(draftKey());
  byId("sourceMode").disabled = !available;
  byId("sourceMode").setAttribute("aria-pressed", String(editing && available));
  byId("renderMode").setAttribute(
    "aria-pressed",
    String(!editing || !available),
  );
  byId("editor").hidden = !editing || !available;
  byId("markdown").hidden = !byId("editor").hidden;
  if (editing && available) byId("source").value = content();
  else if (available) byId("markdown").innerHTML = md.render(content());
  else byId("markdown").textContent = "所选日期还没有导出的复习文件。";
  const stats = data.stats,
    pills = byId("pills");
  pills.replaceChildren(node("span", data.day));
  if (stats)
    for (const [name, n] of [
      ["顽固词", stats.hard],
      ["模糊词", stats.fuzzy],
      ["自动提级", stats.promoted],
    ])
      pills.append(node("span", name + " " + (n ?? "—")));
  if (drafts.has(draftKey())) pills.append(node("span", "有未保存的修改"));
}
function renderView() {
  const titles = {
    overview: data?.day === data?.today ? "今日复习看板" : "复习看板",
    preview: "复习预览",
    history: "历史与惯犯词",
    settings: "MuMu 与设置",
  };
  byId("title").textContent = titles[view];
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== view));
  for (const button of document.querySelectorAll("[data-view]")) {
    if (button.dataset.view === view)
      button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  if (!data) return;
  if (view === "overview") {
    overview(data);
    byId("exportSummary").hidden = !data.series.some((r) => r.export_summary);
  }
  if (view === "preview") preview();
  if (view === "history") {
    byId("windowDays").textContent =
      "截至 " + data.day + " · 近 " + data.window + " 天";
    table(
      "repeats",
      ["单词", "出现学习日数", "最近一次"],
      data.repeats.map((r) => [r.word, r.days, r.last_day]),
      "窗口内暂无跨天反复模糊或答错的词。",
    );
    table(
      "hardList",
      ["单词", "本轮错误次数", "分类"],
      data.errors.map((r) => [
        r.word,
        r.wrong,
        r.promoted ? "跨天自动提级" : "基础顽固词",
      ]),
      data.stats?.export_summary ? "当日词表见「复习预览」。" : "当日暂无顽固词记录。",
    );
    table(
      "codes",
      ["ah", "rh", "评分", "词数", "示例"],
      data.unknown.map((r) => [r.ah, r.rh, r.rating, r.count, r.examples]),
      data.codes_available
        ? "当日没有未知编码。"
        : "缺少当日词条缓存，无法核对编码。",
    );
  }
  icons();
  controls();
}
function apply(d) {
  data = d;
  byId("version").textContent = "v" + d.version;
  byId("dates").replaceChildren(
    ...d.dates.map((day) => new Option(day, day, false, day === d.day)),
  );
  const pathParts = d.folder.split(/[\\/]/).filter(Boolean);
  byId("shortPath").textContent =
    pathParts.length > 2 ? "…\\" + pathParts.slice(-2).join("\\") : d.folder;
  byId("shortPath").title = d.folder;
  byId("path").value = d.folder;
  const side = d.sidebar,
    rate = side?.total ? Math.round((side.mastered / side.total) * 100) : null;
  byId("sideRate").textContent = rate == null ? "—" : rate + "%";
  byId("rateBar").value = rate ?? 0;
  byId("latest").textContent =
    "App 最新记录时间 · " +
    (side?.latest?.slice(5, 16).replace("T", " ").replace("-", "/") ?? "—");
  renderView();
  if (d.warning) message(d.warning, true);
}
function setChecks(adb, root) {
  for (const [id, name, value] of [
    ["adb", "ADB", adb],
    ["rootStatus", "Root", root],
  ]) {
    const el = byId(id);
    el.textContent = name + " · " + value;
    el.className = value.startsWith("通过")
      ? "ok"
      : value === "检查失败"
        ? "fail"
        : "";
  }
}
async function run(action) {
  if (busy) return;
  busy = true;
  controls();
  try {
    if (
      action === "setup" &&
      (await choose(
        "一键配置 MuMu",
        "将检查 ADB、Root 与 App 版本。开启 Root 可能需要重启当前实例，请先结束正在进行的学习。",
        [
          ["", "返回"],
          ["yes", "开始配置"],
        ],
      )) !== "yes"
    )
      return;
    let result = await api().start(action);
    if (result.status === "choose") {
      const choice = await choose(
        "查找 MuMu 安装位置",
        "已安装时，右键 MuMu 桌面图标，点「打开文件所在的位置」，再选择该文件夹。",
        [
          ["", "返回"],
          ["download", "官网下载"],
          ["locate", "选择安装目录"],
        ],
      );
      if (choice === "download") {
        await api().download_mumu();
        return;
      }
      if (choice !== "locate" || !(await api().locate_manager())) return;
      result = await api().start(action);
    }
    if (result.status !== "started")
      throw Error("未能启动任务，请重新选择 MuMu 安装目录。");
    const label = {
      setup: "正在配置 MuMu 并检查连接…",
      sync: "正在打开 MuMu 并同步学习记录…",
      export: "正在使用本机记录导出今日复习…",
    }[action];
    message(label);
    record(label);
    record(result.message);
    let seen = 0;
    for (;;) {
      await new Promise((r) => setTimeout(r, 280));
      const r = await api().poll();
      for (const line of (r.lines ?? []).slice(seen)) record(line);
      seen = (r.lines ?? []).length;
      if (r.status === "running") continue;
      if (r.status === "idle") break;
      let note = r.message || "任务已结束。";
      if (r.status === "configured")
        note = "配置完成。请在 MuMu 中登录不背单词，再点「同步 MuMu」。";
      if (r.status === "app_missing")
        note += " 请在刚才打开的 MuMu 实例内安装并登录不背单词后重试。";
      if (r.day) apply(await api().select_day(r.day));
      record(note);
      message(note, true);
      if (action === "setup") {
        const time = new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
        });
        const adbOK = r.lines?.includes("ADB 连接通过。"),
          rootOK = r.lines?.includes("Root 检查通过。");
        setChecks(
          adbOK ? "通过 " + time : "未确认",
          rootOK ? "通过 " + time : "未确认",
        );
      }
      if (
        action === "setup" ||
        ["app_missing", "mumu_missing"].includes(r.status)
      )
        await choose(
          r.status === "configured" ? "配置完成" : "MuMu 检查结果",
          note,
          [["ok", "知道了"]],
        );
      break;
    }
  } finally {
    busy = false;
    controls();
  }
}
async function dispatch(action) {
  if (["sync", "export", "setup"].includes(action)) return run(action);
  if (action === "open") return api().open_folder();
  if (action === "all") {
    view = "history";
    renderView();
    return;
  }
  if (action === "copy") {
    await api().copy(content());
    message("已复制，可直接发给 AI", true);
    const btn = document.querySelector("[data-action=copy]");
    const swapped = (icon, label) => {
      const i = node("i");
      i.dataset.lucide = icon;
      btn.replaceChildren(i, node("span", label));
      icons();
    };
    swapped("check", "已复制");
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => swapped("copy", "复制全部内容"), 1800);
  }
  if (action === "save") {
    const key = draftKey(),
      draft = drafts.get(key);
    if (!draft || busy) return;
    busy = true;
    controls();
    try {
      await api().save_prompt(data.day, draft.original, draft.text);
      if (drafts.get(key) === draft) drafts.delete(key);
      else if (drafts.has(key)) drafts.get(key).original = draft.text;
      apply(await api().select_day(data.day));
      message("修改已保存到复习文件。", true);
    } finally {
      busy = false;
      controls();
    }
  }
  if (action === "change") {
    if (busy) return;
    busy = true;
    controls();
    try {
      if (await api().change_folder()) {
        apply(await api().select_day(null));
        message("已更新导出目录。", true);
      }
    } finally {
      busy = false;
      controls();
    }
  }
}
document.addEventListener("click", (e) => {
  const button = e.target.closest("button");
  if (!button) return;
  if (button.dataset.view) {
    view = button.dataset.view;
    renderView();
  }
  if (button.dataset.action) dispatch(button.dataset.action).catch(report);
});
byId("dates").onchange = async (e) => {
  const selected = e.target.value;
  e.target.disabled = true;
  try {
    apply(await api().select_day(selected));
    message(data.warning || "已切换至 " + selected + " 的记录。");
  } catch (err) {
    e.target.value = data.day;
    report(err);
  } finally {
    controls();
  }
};
byId("sourceMode").onclick = () => {
  editing = true;
  preview();
};
byId("renderMode").onclick = () => {
  editing = false;
  preview();
};
byId("source").oninput = (e) => {
  const key = draftKey(),
    text = e.target.value;
  if (text === data.prompt) drafts.delete(key);
  else
    drafts.set(key, {
      original: drafts.get(key)?.original ?? data.prompt,
      text,
    });
  controls();
  message(
    drafts.has(key)
      ? "正在编辑，点击「保存修改」写入文件。"
      : "与已保存文件一致。",
  );
};
for (const id of ["volumeRange", "rateRange"])
  byId(id).onchange = () => trends(data);
icons();
controls();
window.addEventListener(
  "pywebviewready",
  async () => {
    try {
      const init = await api().initialize();
      apply(init.data);
      message(
        init.warning ||
          data.warning ||
          (data.stats
            ? "本地记录已载入"
            : "今天暂无本地学习记录，可同步 MuMu 或选择历史日期。"),
      );
      if (init.export) await run("export");
    } catch (e) {
      report(e);
    }
  },
  { once: true },
);
