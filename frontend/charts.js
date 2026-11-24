import {
  Chart,
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
} from "chart.js";
Chart.register(
  LineController,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  Filler,
  Tooltip,
);
Chart.defaults.font.family = '"Segoe UI", "Microsoft YaHei UI", sans-serif';
Chart.defaults.color = "#98a6bf";
const plots = new Map();
const purple = "#b590fc",
  blue = "#66b4e4";
const metrics = [
  ["total", "去重词汇", "layers-3", purple],
  ["mastered", "已掌握 / 已剔除", "circle-check-big", "#59d8ad"],
  ["hard", "顽固词", "flame", "#f3b76b"],
  ["fuzzy", "模糊词 / 惯犯提级", "scan-line", "#6db9f4"],
];
export const byId = (id) => document.getElementById(id);
export function node(tag, text, cls) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
}
export function offset(iso, days) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
function line(canvas, dates, specs, mini = false, percent = false) {
  plots.get(canvas.id)?.destroy();
  const ctx = canvas.getContext("2d");
  const hasData = specs.some((s) => s.values.some((v) => v != null));
  canvas.parentElement.querySelector(".plotEmpty")?.remove();
  if (!hasData && !mini)
    canvas.parentElement.append(
      node("span", "所选时段暂无学习记录", "plotEmpty"),
    );
  const datasets = specs.map(({ name, color, values }, i) => ({
    label: name,
    data: values,
    borderColor: color,
    borderWidth: mini ? 1.5 : 2.1,
    pointRadius: (context) => {
      const i = context.dataIndex;
      return values[i] != null && values[i - 1] == null && values[i + 1] == null
        ? 2.7
        : 0;
    },
    pointHoverRadius: 4,
    pointBackgroundColor: color,
    pointBorderWidth: 0,
    fill: i === 0,
    tension: 0.32,
    spanGaps: false,
    backgroundColor: ({ chart }) => {
      const area = chart.chartArea;
      const g = ctx.createLinearGradient(
        0,
        area?.top ?? 0,
        0,
        area?.bottom ?? chart.height,
      );
      g.addColorStop(0, color + "88");
      g.addColorStop(1, color + "04");
      return g;
    },
  }));
  plots.set(
    canvas.id,
    new Chart(canvas, {
      type: "line",
      data: { labels: dates, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        normalized: true,
        interaction: { mode: "index", intersect: false },
        layout: { padding: mini ? 3 : 2 },
        plugins: { tooltip: { enabled: !mini } },
        scales: {
          x: {
            display: !mini,
            border: { display: false },
            grid: { display: false },
            ticks: {
              maxTicksLimit: 6,
              maxRotation: 0,
              font: { size: 10 },
              callback: (_, i) => dates[i].slice(5),
            },
          },
          y: {
            display: !mini,
            beginAtZero: true,
            max: percent ? 100 : undefined,
            border: { display: false },
            grid: { color: "#9ca4d214" },
            ticks: {
              maxTicksLimit: 5,
              precision: 0,
              font: { size: 10 },
              callback: (v) => (percent ? v + "%" : v),
            },
          },
        },
      },
    }),
  );
}
function series(data, days) {
  const rows = new Map(data.series.map((r) => [r.day, r]));
  const dates = Array.from({ length: days }, (_, i) =>
    offset(data.day, i - days + 1),
  );
  return {
    dates,
    values: (fn) => dates.map((d) => (rows.has(d) ? fn(rows.get(d)) : null)),
  };
}
export function trends(data) {
  const a = series(data, +byId("volumeRange").value),
    b = series(data, +byId("rateRange").value);
  line(byId("volume"), a.dates, [
    { name: "去重词汇", color: purple, values: a.values((r) => r.total) },
    {
      name: "顽固与模糊词",
      color: blue,
      values: a.values((r) => r.hard + r.fuzzy),
    },
  ]);
  line(
    byId("rate"),
    b.dates,
    [
      {
        name: "掌握率 (%)",
        color: purple,
        values: b.values((r) => Math.round((100 * r.mastered) / r.total)),
      },
    ],
    false,
    true,
  );
}
function heatmap(data) {
  const box = byId("heat"),
    grid = node("div", undefined, "heatgrid");
  const weekday = (new Date(data.day + "T00:00:00Z").getUTCDay() + 6) % 7;
  const start = offset(data.day, -23 * 7 - weekday);
  const rows = new Map(data.series.map((r) => [r.day, r.total]));
  const max = Math.max(
    1,
    ...data.series.filter((r) => r.day >= start).map((r) => r.total),
  );
  let active = 0;
  for (let d = 0; d < 7; d++) {
    grid.append(node("small", ["一", "", "三", "", "五", "", "日"][d]));
    for (let w = 0; w < 24; w++) {
      const day = offset(start, 7 * w + d),
        count = rows.get(day);
      const cell = node("span", undefined, "heatcell");
      if (day > data.day) cell.classList.add("future");
      else if (count) {
        cell.style.background = ["#3c3562", "#645195", "#886ac1", "#ba91fa"][
          Math.ceil((count / max) * 4) - 1
        ];
        active++;
      }
      cell.title = day + " · " + (count ? count + " 个词" : "无记录");
      grid.append(cell);
    }
  }
  const months = node("div", undefined, "heatmonths");
  for (let col = 0; col < 24; col += 5)
    months.append(node("span", offset(start, col * 7).slice(5)));
  box.replaceChildren(months, grid);
  byId("activeDays").textContent = active + " 个学习日有记录";
}
function ranking(rows) {
  const box = byId("ranking");
  box.replaceChildren();
  if (!rows.length) {
    box.append(node("p", "当日暂无顽固词记录", "empty"));
    return;
  }
  const head = node("div", undefined, "rankRow rankHead");
  for (const label of ["#", "单词", "", "错误数"])
    head.append(node("span", label));
  box.append(head);
  const max = Math.max(...rows.map((r) => r.wrong || 0), 1);
  rows.slice(0, 5).forEach((r, i) => {
    const row = node("div", undefined, "rankRow"),
      track = node("span", undefined, "track"),
      bar = node("i");
    bar.style.width = ((r.wrong || 0) / max) * 100 + "%";
    track.append(bar);
    row.append(
      node("small", String(i + 1).padStart(2, "0")),
      node("b", r.word),
      track,
      node("small", r.wrong == null ? "—" : r.wrong + " 次"),
    );
    box.append(row);
  });
}
export function overview(data) {
  const grid = byId("kpis");
  grid.replaceChildren();
  const previous = data.series.find((r) => r.day === offset(data.day, -1));
  const s = series(data, 14),
    current = data.stats;
  for (const [key, label, icon, color] of metrics) {
    const card = node("article", undefined, "kpi"),
      top = node("div", undefined, "kpiTop"),
      badge = node("span", undefined, "kpiIcon");
    card.style.setProperty("--tone", color);
    const glyph = node("i");
    glyph.dataset.lucide = icon;
    badge.append(glyph);
    const val = node("div"),
      qty = current
        ? key === "fuzzy"
          ? current.fuzzy + " / " + current.promoted
          : current[key]
        : "—";
    val.append(
      node("div", label, "metricLabel"),
      node("div", qty, "metricValue"),
    );
    top.append(badge, val);
    const delta = (n) => (n > 0 ? "+" + n : String(n));
    let change = "较昨日　暂无对比";
    if (current && previous)
      change =
        "较昨日　" +
        delta(current[key] - previous[key]) +
        (key === "fuzzy"
          ? " / " + delta(current.promoted - previous.promoted)
          : "") +
        " 个";
    const spark = node("div", undefined, "spark"),
      canvas = node("canvas");
    canvas.id = "spark-" + key;
    spark.append(canvas);
    card.append(top, node("div", change, "delta"), spark);
    grid.append(card);
    line(
      canvas,
      s.dates,
      [{ name: label, color, values: s.values((r) => r[key]) }],
      true,
    );
  }
  trends(data);
  ranking(data.errors);
  heatmap(data);
}
