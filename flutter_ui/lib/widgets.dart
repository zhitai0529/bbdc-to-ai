import 'package:flutter/material.dart';

class Section extends StatelessWidget {
  const Section(this.title, this.icon, this.child, {super.key, this.action});
  final String title;
  final IconData icon;
  final Widget child;
  final Widget? action;
  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final heading = Row(
      children: [
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            color: colors.primaryContainer.withValues(alpha: .65),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Icon(icon, color: colors.onPrimaryContainer, size: 19),
        ),
        const SizedBox(width: 11),
        Expanded(
          child: Text(
            title,
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
      ],
    );
    return Card.filled(
      margin: EdgeInsets.zero,
      color: colors.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: colors.outlineVariant.withValues(alpha: .65)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            LayoutBuilder(
              builder: (context, box) {
                if (action == null) return heading;
                if (box.maxWidth < 460) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [heading, const SizedBox(height: 12), action!],
                  );
                }
                return Row(
                  children: [
                    Expanded(child: heading),
                    const SizedBox(width: 12),
                    action!,
                  ],
                );
              },
            ),
            const SizedBox(height: 16),
            SizedBox(width: double.infinity, child: child),
          ],
        ),
      ),
    );
  }
}

class Empty extends StatelessWidget {
  const Empty(this.label, {super.key, this.icon = Icons.inbox_outlined});
  final String label;
  final IconData icon;
  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 26, horizontal: 16),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 46,
              height: 46,
              decoration: BoxDecoration(
                color: colors.surfaceContainer,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Icon(icon, color: colors.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Text(
                label,
                textAlign: TextAlign.center,
                style: TextStyle(color: colors.onSurfaceVariant),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class InsetPanel extends StatelessWidget {
  const InsetPanel({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(14),
  });
  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: padding,
      decoration: BoxDecoration(
        color: colors.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.outlineVariant.withValues(alpha: .75)),
      ),
      child: child,
    );
  }
}

String iso(DateTime d) => d.toIso8601String().substring(0, 10);
String offsetDay(String day, int delta) =>
    iso(DateTime.parse('${day}T12:00:00Z').add(Duration(days: delta)));

class Trend extends StatelessWidget {
  const Trend(
    this.lines,
    this.colors, {
    super.key,
    this.height = 130,
    this.percent = false,
    this.mini = false,
    this.dates = const [],
  });
  final List<List<double?>> lines;
  final List<Color> colors;
  final double height;
  final bool percent, mini;
  final List<String> dates;
  @override
  Widget build(BuildContext context) {
    final numbers = lines.expand((line) => line.whereType<double>()).toList();
    if (numbers.isEmpty && !mini)
      return ConstrainedBox(
        constraints: BoxConstraints(minHeight: height),
        child: const Center(child: Empty('所选时段暂无记录')),
      );
    final max = percent
        ? 100.0
        : numbers.fold<double>(1, (a, b) => a > b ? a : b);
    final label = percent ? '%' : '';
    final chart = CustomPaint(
      size: Size(double.infinity, height),
      painter: _Plot(
        lines,
        colors,
        Theme.of(context).colorScheme.outlineVariant,
        max,
        mini,
      ),
    );
    if (mini) return ExcludeSemantics(child: chart);
    return Semantics(
      label: '${dates.first} 至 ${dates.last}，最大刻度 ${max.ceil()}$label',
      child: Column(
        children: [
          Row(
            children: [
              SizedBox(
                width: 36,
                height: height,
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      '${max.ceil()}$label',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                    Text(
                      '0$label',
                      style: Theme.of(context).textTheme.labelSmall,
                    ),
                  ],
                ),
              ),
              Expanded(
                child: LayoutBuilder(
                  builder: (context, box) => Stack(
                    children: [
                      chart,
                      Positioned.fill(
                        child: Row(
                          children: [
                            for (var i = 0; i < dates.length; i++)
                              Expanded(
                                child: Tooltip(
                                  message:
                                      '${dates[i]} · ${lines.map((l) => l[i] == null ? '—' : '${l[i]!.round()}$label').join(' / ')}',
                                  child: const SizedBox.expand(),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              for (final d in [
                dates.first,
                dates[dates.length ~/ 2],
                dates.last,
              ])
                Text(
                  d.substring(5),
                  style: Theme.of(context).textTheme.labelSmall,
                ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Plot extends CustomPainter {
  _Plot(this.lines, this.colors, this.grid, this.max, this.mini);
  final List<List<double?>> lines;
  final List<Color> colors;
  final Color grid;
  final double max;
  final bool mini;
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height - 6;
    if (!mini)
      for (var i = 0; i <= 3; i++) {
        final y = 3 + i * h / 3;
        canvas.drawLine(
          Offset(0, y),
          Offset(w, y),
          Paint()..color = grid.withValues(alpha: .6),
        );
      }
    for (var j = 0; j < lines.length; j++) {
      final line = lines[j], color = colors[j];
      var points = <Offset>[];
      void draw() {
        if (points.isEmpty) return;
        final path = Path()..moveTo(points.first.dx, points.first.dy);
        for (final p in points.skip(1)) {
          path.lineTo(p.dx, p.dy);
        }
        if (j == 0 && points.length > 1) {
          final fill = Path.from(path)
            ..lineTo(points.last.dx, h + 3)
            ..lineTo(points.first.dx, h + 3)
            ..close();
          canvas.drawPath(
            fill,
            Paint()
              ..shader = LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  color.withValues(alpha: .23),
                  color.withValues(alpha: .01),
                ],
              ).createShader(Offset.zero & size),
          );
        }
        canvas.drawPath(
          path,
          Paint()
            ..color = color
            ..strokeWidth = mini ? 1.6 : 2.4
            ..style = PaintingStyle.stroke
            ..strokeJoin = StrokeJoin.round,
        );
        if (points.length == 1)
          canvas.drawCircle(points.first, 2.8, Paint()..color = color);
        points = [];
      }

      for (var i = 0; i < line.length; i++) {
        final v = line[i];
        if (v == null) {
          draw();
          continue;
        }
        points.add(
          Offset(
            3 + (w - 6) * i / (line.length < 2 ? 1 : line.length - 1),
            3 + h * (1 - v / max),
          ),
        );
      }
      draw();
    }
  }

  @override
  bool shouldRepaint(_Plot old) => true;
}
