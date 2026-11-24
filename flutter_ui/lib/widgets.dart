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
    return Card.filled(
      margin: EdgeInsets.zero,
      color: colors.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: colors.outlineVariant.withValues(alpha: .5)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: colors.primary, size: 20),
                const SizedBox(width: 9),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                if (action != null) action!,
              ],
            ),
            const SizedBox(height: 14),
            child,
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
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 22),
    child: Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Theme.of(context).colorScheme.outline),
          const SizedBox(height: 8),
          Text(label, textAlign: TextAlign.center),
        ],
      ),
    ),
  );
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
      return SizedBox(height: height, child: const Empty('所选时段暂无记录'));
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
