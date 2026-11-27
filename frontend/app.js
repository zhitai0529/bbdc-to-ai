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
  Square,
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
  ClipboardList,
} from "lucide";
import MarkdownIt from "markdown-it";
import { byId, node, overview, trends } from "./charts";
import { mountExercise } from "./exercise";
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
  Square,
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
  ClipboardList,
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
  syncTask,
  manualDate = false,
  latestSyncedDay,
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
const exercises = mountExercise(byId("exercise"), {
  api,
  renderMarkdown: (source) => md.render(source),
  onBusyChange: controls,
});
function record(line) {
  if (!line) return;
  log.push(
    new Date().toLocaleTimeString("zh-CN", { hour12: false }) + "  " + line,
  );
  byId("logs").textContent = log.slice(-120).join("\n");
  byId("logs").scrollTop = byId("logs").scrollHeight;
}
function controls() {
  const occupied = busy || exercises.pending;
  for (const el of document.querySelectorAll("[data-action]")) {
    const a = el.dataset.action;
    if (a === "sync") {
      byId("syncLabel").textContent = syncButtonLabels[syncTask?.phase ?? "idle"];
      byId("startSyncIcon").hidden = Boolean(syncTask);
      byId("stopSyncIcon").hidden = !syncTask;
      el.disabled = !data || (syncTask ? syncTask.phase !== "running" : occupied);
      continue;
    }
    if (a === "latest") {
      el.hidden = !latestSyncedDay || latestSyncedDay === data?.day;
      el.disabled = occupied;
      el.title = latestSyncedDay ? `切换到 ${latestSyncedDay} 的复习` : "";
      continue;
    }
    el.disabled =
      a === "copy"
        ? !data || !content()
        : a === "save"
          ? occupied || !data || !drafts.has(draftKey())
          : ["setup", "export", "range", "change"].includes(a) &&
            (occupied || !data);
  }
  byId("dates").disabled = occupied || !data;
  byId("reviewLevel").disabled = occupied || !data;
  byId("dot").classList.toggle("busy", occupied);
  exercises.setBlocked(busy);
}
function choose(title, body, choices, preview = "") {
  const dialog = byId("modal");
  byId("modalTitle").textContent = title;
  byId("modalBody").textContent = body;
  const markdown = byId("modalMarkdown");
  markdown.innerHTML = preview ? md.render(preview) : "";
  markdown.hidden = !preview;
  dialog.classList.toggle("previewDialog", Boolean(preview));
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
    exercise: "分档练习",
    history: "历史与惯犯词",
    settings: "MuMu 与设置",
  };
  byId("title").textContent = titles[view];
  byId("subtitle").textContent =
    view === "exercise"
      ? "选择难度和题型，用待复习词生成 AI 出题提示词"
      : "把需要再练的单词整理成 AI 复习提示词";
  document.querySelector("[data-action=copy]").hidden = view === "exercise";
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
  exercises.update(d);
  document.querySelector('[data-action="export"]').title = `用本机记录导出 ${d.day} 的复习`;
  byId("reviewLevel").value = d.review_level ?? "postgrad";
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
const taskLabels = {
  setup: "一键配置 MuMu",
  sync: "同步 MuMu",
  export: "导出复习",
};
const syncButtonLabels = {
  idle: taskLabels.sync,
  running: "停止同步",
  stopping: "正在停止…",
  finishing: "正在收尾…",
};
async function taskResult(action, result, overwriteDraft) {
  const configured = result.status === "configured";
  const note =
    result.message ||
    (result.status === "cancelled"
      ? "同步已停止。需要时可以重新同步。"
      : configured
      ? "请在 MuMu 中打开并登录不背单词，再点「同步 MuMu」。"
      : `「${taskLabels[action]}」未完成，请重试。`);
  if (result.status === "exported" && result.day) {
    const keepDate = action === "sync" && manualDate;
    if (action === "sync") latestSyncedDay = keepDate ? result.day : undefined;
    if (
      overwriteDraft &&
      !result.copied &&
      drafts.get(overwriteDraft.key) === overwriteDraft.draft
    ) {
      drafts.delete(overwriteDraft.key);
    }
    if (action === "sync" || !result.copied) {
      apply(await api().select_day(keepDate ? data.day : result.day));
    }
  }
  record(note);
  message(note, true);
  if (action === "setup") {
    const time = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
    const adbOK = result.lines?.includes("ADB 连接通过。"),
      rootOK = result.lines?.includes("Root 检查通过。");
    setChecks(
      adbOK ? "通过 " + time : "未完成",
      rootOK ? "通过 " + time : "未完成",
    );
  }
  if (["exported", "no_records", "cancelled"].includes(result.status)) return;

  const choices = [["ok", "关闭"]];
  if (result.recovery?.includes("download")) {
    choices.push(["download", "打开 MuMu 官网"]);
  }
  if (result.recovery?.includes("locate")) {
    choices.push(["locate", "选择安装目录"]);
  }
  const choice = await choose(
    configured ? "配置完成" : `${taskLabels[action]}未完成`,
    note,
    choices,
  );
  if (choice === "download") await api().download_mumu();
  if (choice === "locate" && (await api().locate_manager())) {
    message(
      `已选择 MuMu 安装目录。启动目标 Android 15 实例后，再点「${taskLabels[action]}」。`,
      true,
    );
  }
}
async function run(action, day) {
  if (busy || exercises.pending) return;
  busy = true;
  controls();
  try {
    let overwriteDraft;
    if (action === "setup") {
      const choice = await choose(
        "一键配置 MuMu",
        "1. 打开 MuMu 多开器，启动要用的 Android 15 实例。如果新建实例时没有 Android 15 选项，请从官网更新 Windows 版 MuMu。\n\n" +
          "2. 在该实例内安装「不背单词」5.11.8 x86。\n\n" +
          "3. 结束当前学习后再开始配置。助手会检查连接和 App 版本，需要开启 Root 时会重启该实例。",
        [
          ["", "返回"],
          ["download", "打开 MuMu 官网"],
          ["yes", "开始配置"],
        ],
      );
      if (choice === "download") await api().download_mumu();
      if (choice !== "yes") return;
    }
    const key = day != null ? draftKey() : null;
    const draft = drafts.get(key);
    let result = draft
      ? await api().start(action, day, "check")
      : day
        ? await api().start(action, day)
        : await api().start(action);
    while (result.status === "confirm_export") {
      const choice = await choose(
        `重新导出 ${result.day} 的复习？`,
        [
          result.message,
          draft ? "当前还有未保存的修改。覆盖成功后，本次草稿将被清除。" : "",
        ]
          .filter(Boolean)
          .join("\n"),
        [
          ["", "取消"],
          ["overwrite", "覆盖"],
          ["copy", "另存副本"],
        ],
      );
      if (!choice) return;
      overwriteDraft = choice === "overwrite" && draft ? { key, draft } : undefined;
      result = await api().start(action, result.day, choice, result.revision);
    }
    if (result.status === "choose") {
      const choice = await choose(
        "未找到 MuMu 安装位置",
        "未安装时，请先从官网下载 Windows 版 MuMu。\n\n已安装时，右键 MuMu 桌面图标，点「打开文件所在的位置」，再选择该文件夹。",
        [
          ["", "返回"],
          ["download", "打开 MuMu 官网"],
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
    if (result.status !== "started") {
      const guidance =
        result.status === "choose"
          ? "请重新选择 MuMu 安装目录。"
          : "请关闭助手后重试。";
      throw Error(`「${taskLabels[action]}」未能启动。${guidance}`);
    }
    if (action === "sync") {
      syncTask = { phase: "running" };
      controls();
    }
    const label = {
      setup: "正在配置 MuMu 并检查连接…",
      sync: "正在打开 MuMu 并同步学习记录…",
      export: day ? `正在用本机记录导出 ${day} 的复习…` : "正在用本机记录导出复习…",
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
      syncTask = undefined;
      controls();
      await taskResult(action, r, overwriteDraft);
      break;
    }
  } finally {
    syncTask = undefined;
    busy = false;
    controls();
  }
}
async function exportRange() {
  if (!data || busy || exercises.pending) return;
  const day = data.day;
  busy = true;
  controls();
  try {
    const choice = await choose(
      "导出多日薄弱词",
      `截至 ${day}（含当天）。合并所选范围内本机记录中的错词和模糊词，每个词列出出现的学习日。`,
      [
        ["", "取消"],
        ["5", "近 5 天"],
        ["3", "近 3 天"],
      ],
    );
    if (!choice) return;
    message("正在生成多日薄弱词…");
    const result = await api().export_range_review(day, Number(choice));
    const summary = `${result.start_day} 至 ${result.end_day} · ${result.word_count} 个薄弱词`;
    const body = [summary, result.filename];
    if (result.missing_days.length) {
      body.push(`缺少本机词条的学习日：${result.missing_days.join("、")}`);
    }
    message(`已保存 ${result.filename}。`);
    const next = await choose(
      "多日薄弱词预览",
      body.join("\n"),
      [
        ["", "关闭"],
        ["open", "打开导出目录"],
        ["copy", "复制多日复习提示词"],
      ],
      result.markdown,
    );
    if (next === "open") await api().open_folder();
    if (next === "copy") {
      await api().copy(result.markdown);
      message("已复制多日复习提示词，可粘贴给 AI。", true);
    }
  } finally {
    busy = false;
    controls();
  }
}
async function stopSync() {
  const task = syncTask;
  if (task?.phase !== "running") return;
  task.phase = "stopping";
  controls();
  message("正在停止同步…");
  try {
    const result = await api().cancel_sync();
    if (syncTask === task && result.status !== "cancelling") {
      task.phase = "finishing";
      controls();
      message("同步正在收尾…");
    }
  } catch (error) {
    if (syncTask !== task) return;
    task.phase = "running";
    controls();
    report(error);
  }
}
async function dispatch(action) {
  if (action === "sync" && syncTask) return stopSync();
  if (action === "export") return run(action, data.day);
  if (action === "range") return exportRange();
  if (action === "latest") {
    if (!latestSyncedDay || busy || exercises.pending) return;
    busy = true;
    controls();
    try {
      const latest = await api().select_day(latestSyncedDay);
      manualDate = false;
      latestSyncedDay = undefined;
      view = "preview";
      apply(latest);
      message(data.warning || `已打开 ${data.day} 的复习。`);
    } finally {
      busy = false;
      controls();
    }
    return;
  }
  if (["sync", "setup"].includes(action)) return run(action);
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
    if (!draft || busy || exercises.pending) return;
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
    if (busy || exercises.pending) return;
    busy = true;
    controls();
    try {
      if (await api().change_folder()) {
        apply(await api().select_day(null));
        manualDate = false;
        latestSyncedDay = undefined;
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
  if (busy || exercises.pending) return;
  const selected = e.target.value;
  busy = true;
  controls();
  try {
    apply(await api().select_day(selected));
    manualDate = true;
    message(data.warning || "已切换至 " + selected + " 的记录。");
  } catch (err) {
    e.target.value = data.day;
    report(err);
  } finally {
    busy = false;
    controls();
  }
};
byId("reviewLevel").onchange = async (e) => {
  if (busy || exercises.pending) return;
  const select = e.target,
    level = select.value,
    label = select.selectedOptions[0].textContent;
  busy = true;
  controls();
  try {
    await api().save_review_level(level);
    data.review_level = level;
    exercises.update(data);
    message(`已保存${label}难度，下次导出时生效。`, true);
  } catch (err) {
    select.value = data.review_level ?? "postgrad";
    report(err);
  } finally {
    busy = false;
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
