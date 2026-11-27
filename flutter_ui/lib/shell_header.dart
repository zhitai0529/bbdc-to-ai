import 'package:flutter/material.dart';

import 'appearance.dart';

class WorkspaceHeader extends StatelessWidget {
  const WorkspaceHeader({
    super.key,
    required this.title,
    required this.mode,
    required this.onThemeChanged,
  });

  final String title;
  final ThemeMode mode;
  final ValueChanged<ThemeMode>? onThemeChanged;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Row(
      children: [
        Expanded(
          child: Text(
            title,
            style: text.headlineSmall?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(width: 10),
        ThemeMenu(mode: mode, onChanged: onThemeChanged),
      ],
    );
  }
}

class ReviewActionBar extends StatelessWidget {
  const ReviewActionBar({
    super.key,
    required this.day,
    required this.today,
    required this.dates,
    required this.busy,
    required this.copied,
    required this.rangeAvailable,
    required this.copyAvailable,
    required this.syncButton,
    required this.onDay,
    required this.onExport,
    required this.onRange,
    required this.onCopy,
    required this.status,
  });

  final String? day;
  final String? today;
  final List<String> dates;
  final bool busy;
  final bool copied;
  final bool rangeAvailable;
  final bool copyAvailable;
  final Widget syncButton;
  final ValueChanged<String>? onDay;
  final VoidCallback? onExport;
  final VoidCallback? onRange;
  final VoidCallback? onCopy;
  final String status;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final compactMenu = MenuAnchor(
      menuChildren: [
        MenuItemButton(
          leadingIcon: const Icon(Icons.date_range_outlined),
          onPressed: onRange,
          child: const Text('多日薄弱词'),
        ),
      ],
      builder: (context, controller, child) => OutlinedButton.icon(
        onPressed: onRange == null
            ? null
            : () => controller.isOpen ? controller.close() : controller.open(),
        icon: const Icon(Icons.more_horiz),
        label: const Text('更多操作'),
      ),
    );
    final export = FilledButton.tonalIcon(
      onPressed: onExport,
      icon: const Icon(Icons.download_outlined),
      label: const Text('导出复习'),
    );
    final copy = OutlinedButton.icon(
      onPressed: onCopy,
      icon: Icon(copied ? Icons.check : Icons.copy_outlined),
      label: Text(copied ? '已复制' : '复制全部内容'),
    );
    final range = OutlinedButton.icon(
      onPressed: onRange,
      icon: const Icon(Icons.date_range_outlined),
      label: const Text('多日薄弱词'),
    );
    final date = _DaySelector(
      day: day,
      today: today,
      dates: dates,
      onDay: onDay,
    );
    return Card.filled(
      margin: EdgeInsets.zero,
      color: colors.surfaceContainerLow,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(color: colors.outlineVariant.withValues(alpha: .7)),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          LayoutBuilder(
            builder: (context, box) {
              final stacked = box.maxWidth < 820;
              final collapseRange = box.maxWidth < 760;
              final secondary = <Widget>[
                export,
                if (rangeAvailable) collapseRange ? compactMenu : range,
                if (copyAvailable) copy,
              ];
              return Padding(
                padding: const EdgeInsets.all(14),
                child: stacked
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            children: [
                              Expanded(child: date),
                              const SizedBox(width: 10),
                              syncButton,
                            ],
                          ),
                          if (secondary.isNotEmpty) ...[
                            const SizedBox(height: 12),
                            Wrap(
                              spacing: 8,
                              runSpacing: 8,
                              children: secondary,
                            ),
                          ],
                        ],
                      )
                    : Row(
                        children: [
                          date,
                          const Spacer(),
                          for (final action in secondary) ...[
                            action,
                            const SizedBox(width: 8),
                          ],
                          syncButton,
                        ],
                      ),
              );
            },
          ),
          if (busy) const LinearProgressIndicator(minHeight: 3),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            decoration: BoxDecoration(
              color: colors.surfaceContainerLowest,
              border: Border(
                top: BorderSide(
                  color: colors.outlineVariant.withValues(alpha: .7),
                ),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  busy ? Icons.sync : Icons.info_outline,
                  size: 16,
                  color: busy ? colors.primary : colors.onSurfaceVariant,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Semantics(
                    liveRegion: true,
                    child: Text(
                      status,
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DaySelector extends StatelessWidget {
  const _DaySelector({
    required this.day,
    required this.today,
    required this.dates,
    required this.onDay,
  });

  final String? day;
  final String? today;
  final List<String> dates;
  final ValueChanged<String>? onDay;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final historical = day != null && today != null && day != today;
    return Container(
      constraints: const BoxConstraints(minWidth: 176),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
      decoration: BoxDecoration(
        color: colors.surfaceContainerLowest,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colors.outlineVariant),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.calendar_month_outlined, size: 20, color: colors.primary),
          const SizedBox(width: 9),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('学习日', style: Theme.of(context).textTheme.labelSmall),
              if (day == null)
                Text('暂无记录', style: Theme.of(context).textTheme.bodyMedium)
              else
                DropdownButton<String>(
                  value: day,
                  isDense: true,
                  items: [
                    for (final date in dates)
                      DropdownMenuItem<String>(value: date, child: Text(date)),
                  ],
                  onChanged: onDay == null
                      ? null
                      : (value) {
                          if (value != null) onDay!(value);
                        },
                  underline: const SizedBox(),
                ),
            ],
          ),
          if (historical)
            Tooltip(
              message: '正在查看历史学习日',
              child: Padding(
                padding: const EdgeInsets.only(left: 6),
                child: Icon(Icons.history, size: 18, color: colors.tertiary),
              ),
            ),
        ],
      ),
    );
  }
}
