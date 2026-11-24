import 'package:flutter/material.dart';
import 'bridge.dart';
import 'widgets.dart';

class Overview extends StatefulWidget {
  const Overview(this.data, this.onHistory, this.onDay, {super.key});
  final Json data;
  final VoidCallback onHistory;
  final ValueChanged<String>? onDay;
  @override
  State<Overview> createState() => _OverviewState();
}

class _OverviewState extends State<Overview> {
  int volume = 7, rate = 30;
  @override
  Widget build(BuildContext context) {
    final d = widget.data,
        day = d['day'] as String,
        stats = d['stats'] as Json?;
    final rows = {
      for (final r in (d['series'] as List).cast<Json>()) r['day'] as String: r,
    };
    List<String> dates(int n) =>
        List.generate(n, (i) => offsetDay(day, i - n + 1));
    List<double?> values(List<String> days, num Function(Json) metric) => days
        .map((k) => rows[k] == null ? null : metric(rows[k]!).toDouble())
        .toList();
    final c = Theme.of(context).colorScheme,
        dark = Theme.of(context).brightness == Brightness.dark;
    final tones = [
      c.primary,
      dark ? const Color(0xff79dcba) : const Color(0xff087859),
      dark ? const Color(0xffffbc80) : const Color(0xffa3520d),
      dark ? const Color(0xffc7b6ff) : const Color(0xff7254aa),
    ];
    const keys = ['total', 'mastered', 'hard', 'fuzzy'];
    const names = ['去重词汇', '已掌握 / 已剔除', '顽固词', '模糊词 / 惯犯提级'];
    const icons = [
      Icons.layers_outlined,
      Icons.check_circle_outline,
      Icons.local_fire_department_outlined,
      Icons.replay_rounded,
    ];
    final yesterday = rows[offsetDay(day, -1)];
    final fromExport = stats?['export_summary'] == true;
    final includesExports = rows.values.any(
      (row) => row['export_summary'] == true,
    );
    final promoted = stats?['promoted'] as num?;
    final previousPromoted = yesterday?['promoted'] as num?;
    final metrics = List<Widget>.generate(4, (i) {
      final key = keys[i], v = stats?[key], y = yesterday?[key];
      String signed(num n) => n > 0 ? '+$n' : '$n';
      final delta = (v == null || y == null)
          ? '较昨日　暂无对比'
          : '较昨日　${signed(v - y)}${i == 3 ? ' / ${promoted == null || previousPromoted == null ? '—' : signed(promoted - previousPromoted)}' : ''}';
      return Card.filled(
        margin: EdgeInsets.zero,
        color: Color.alphaBlend(
          tones[i].withValues(alpha: .065),
          c.surfaceContainerLow,
        ),
        child: Padding(
          padding: const EdgeInsets.all(14),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icons[i], color: tones[i], size: 20),
                  const SizedBox(width: 7),
                  Expanded(
                    child: Text(
                      names[i],
                      style: Theme.of(context).textTheme.labelLarge,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                v == null
                    ? '—'
                    : i == 3
                    ? '$v / ${promoted ?? '—'}'
                    : '$v',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontFeatures: [const FontFeature.tabularFigures()],
                ),
              ),
              Text(delta, style: Theme.of(context).textTheme.labelSmall),
              Trend(
                [values(dates(14), (r) => r[key])],
                [tones[i]],
                height: 26,
                mini: true,
              ),
            ],
          ),
        ),
      );
    });
    Widget toggle(int n, ValueChanged<int> f) => SegmentedButton<int>(
      showSelectedIcon: false,
      style: const ButtonStyle(visualDensity: VisualDensity.compact),
      segments: const [
        ButtonSegment(value: 7, label: Text('7 天')),
        ButtonSegment(value: 30, label: Text('30 天')),
      ],
      selected: {n},
      onSelectionChanged: (s) => setState(() => f(s.first)),
    );
    final vd = dates(volume), rd = dates(rate);
    final trend = Section(
      '每日词量与纠结词趋势',
      Icons.show_chart,
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.horizontal_rule, color: c.primary),
              const Text('去重词汇'),
              const SizedBox(width: 14),
              Icon(Icons.horizontal_rule, color: tones[3]),
              const Text('顽固与模糊词'),
            ],
          ),
          const SizedBox(height: 8),
          Trend(
            [
              values(vd, (r) => r['total']),
              values(vd, (r) => r['hard'] + r['fuzzy']),
            ],
            [c.primary, tones[3]],
            dates: vd,
          ),
        ],
      ),
      action: toggle(volume, (v) => volume = v),
    );
    final mastery = Section(
      '掌握率趋势',
      Icons.trending_up,
      Trend(
        [values(rd, (r) => 100 * r['mastered'] / r['total'])],
        [c.primary],
        percent: true,
        dates: rd,
      ),
      action: toggle(rate, (v) => rate = v),
    );
    final errors = (d['errors'] as List).cast<Json>();
    final top = Section(
      '高频错词速览',
      Icons.format_list_numbered,
      errors.isEmpty
          ? Empty(fromExport ? '词表见「复习预览」' : '当日暂无顽固词记录')
          : Column(
              children: [
                for (var i = 0; i < errors.length && i < 5; i++)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(
                      children: [
                        SizedBox(width: 26, child: Text('${i + 1}')),
                        Expanded(
                          child: Text(
                            errors[i]['word'],
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 10),
                        SizedBox(
                          width: 58,
                          child: LinearProgressIndicator(
                            value:
                                (errors[i]['wrong'] ?? 0) /
                                (errors.first['wrong'] == null ||
                                        errors.first['wrong'] == 0
                                    ? 1
                                    : errors.first['wrong']),
                            borderRadius: BorderRadius.circular(5),
                          ),
                        ),
                        SizedBox(
                          width: 46,
                          child: Text(
                            errors[i]['wrong'] == null
                                ? '—'
                                : '${errors[i]['wrong']} 次',
                            textAlign: TextAlign.end,
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
      action: TextButton(
        onPressed: widget.onHistory,
        child: const Text('查看全部'),
      ),
    );
    final heat = Section(
      '近期学习热力图',
      Icons.calendar_month_outlined,
      _Heat(day, rows, widget.onDay),
      action: const Text('近 24 周'),
    );
    return LayoutBuilder(
      builder: (context, box) {
        final wide = box.maxWidth >= 850, cols = box.maxWidth >= 700 ? 4 : 2;
        Widget pair(Widget a, Widget b) => wide
            ? Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(flex: 6, child: a),
                  const SizedBox(width: 14),
                  Expanded(flex: 5, child: b),
                ],
              )
            : Column(children: [a, const SizedBox(height: 14), b]);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: 12,
              runSpacing: 12,
              children: [
                for (final card in metrics)
                  SizedBox(
                    width: (box.maxWidth - (cols - 1) * 12) / cols - .1,
                    child: card,
                  ),
              ],
            ),
            if (includesExports)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  fromExport
                      ? '当日统计来自已导出的 Markdown。'
                      : '部分历史日期的统计来自已导出的 Markdown。',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            const SizedBox(height: 16),
            pair(trend, top),
            const SizedBox(height: 14),
            pair(heat, mastery),
          ],
        );
      },
    );
  }
}

class _Heat extends StatelessWidget {
  const _Heat(this.day, this.rows, this.onDay);
  final String day;
  final Map<String, Json> rows;
  final ValueChanged<String>? onDay;
  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme;
    final start = offsetDay(day, -23 * 7 - DateTime.parse(day).weekday + 1);
    final active = rows.entries
        .where((r) => r.key.compareTo(start) >= 0 && r.key.compareTo(day) <= 0)
        .toList();
    final max = active.fold<num>(
      1,
      (a, r) => r.value['total'] > a ? r.value['total'] : a,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < 7; i++)
          Row(
            children: [
              SizedBox(
                width: 20,
                child: Text(
                  ['一', '', '三', '', '五', '', '日'][i],
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
              for (var j = 0; j < 24; j++)
                Expanded(
                  child: Builder(
                    builder: (context) {
                      final key = offsetDay(start, j * 7 + i),
                          n = rows[key]?['total'] as int?;
                      final color = key.compareTo(day) > 0
                          ? Colors.transparent
                          : n == null
                          ? c.surfaceContainerHighest
                          : Color.lerp(
                              c.primaryContainer,
                              c.primary,
                              (n / max).clamp(.12, 1).toDouble(),
                            )!;
                      return Tooltip(
                        message: '$key · ${n == null ? '无记录' : '$n 个词'}',
                        child: InkWell(
                          onTap: n == null || onDay == null
                              ? null
                              : () => onDay!(key),
                          child: Container(
                            height: 13,
                            margin: const EdgeInsets.all(1.5),
                            decoration: BoxDecoration(
                              color: color,
                              borderRadius: BorderRadius.circular(3),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                ),
            ],
          ),
        const SizedBox(height: 8),
        Text(
          '${start.substring(5)} — ${day.substring(5)}　·　${active.length} 个有记录的学习日',
          style: Theme.of(context).textTheme.labelSmall,
        ),
      ],
    );
  }
}
