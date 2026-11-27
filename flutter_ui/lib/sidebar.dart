import 'package:flutter/material.dart';

import 'bridge.dart';

const exercisePageIndex = 4;
const reviewPageLabels = ['复习总览', '复习预览', '历史与惯犯词', 'MuMu 与设置', '分档练习'];

class ReviewSidebar extends StatelessWidget {
  const ReviewSidebar({
    super.key,
    required this.data,
    required this.wide,
    required this.page,
    required this.onPage,
    required this.onOpenFolder,
  });

  final Json? data;
  final bool wide;
  final int page;
  final ValueChanged<int> onPage;
  final VoidCallback onOpenFolder;

  static const compactLabels = ['总览', '预览', '历史', '设置', '练习'];
  static const icons = [
    Icons.dashboard_outlined,
    Icons.menu_book_outlined,
    Icons.history,
    Icons.tune,
    Icons.quiz_outlined,
  ];

  @override
  Widget build(BuildContext context) {
    final d = data;
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final side = d?['sidebar'] as Json?;
    final total = side?['total'] ?? 0;
    final pct = total == 0 ? null : (side!['mastered'] ?? 0) / total;
    return Container(
      width: wide ? 204 : 92,
      decoration: BoxDecoration(
        color: colors.surfaceContainerLow,
        border: Border(
          right: BorderSide(
            color: colors.outlineVariant.withValues(alpha: .75),
          ),
        ),
      ),
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: wide ? 16 : 12,
              vertical: 18,
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircleAvatar(
                  radius: 20,
                  backgroundColor: colors.primaryContainer,
                  child: Icon(
                    Icons.auto_stories_outlined,
                    color: colors.onPrimaryContainer,
                  ),
                ),
                if (wide) ...[
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          '不背单词复习助手',
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: text.titleSmall?.copyWith(
                            fontWeight: FontWeight.w700,
                            height: 1.3,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          d == null ? '本机复习工具' : 'v${d['version']} · 本机复习工具',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: text.labelSmall?.copyWith(
                            color: colors.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
          Expanded(
            child: SingleChildScrollView(
              child: IntrinsicHeight(
                child: NavigationRail(
                  extended: wide,
                  minWidth: 90,
                  minExtendedWidth: 200,
                  groupAlignment: -1,
                  labelType: wide
                      ? NavigationRailLabelType.none
                      : NavigationRailLabelType.all,
                  selectedIndex: page,
                  onDestinationSelected: onPage,
                  destinations: [
                    for (var i = 0; i < reviewPageLabels.length; i++)
                      NavigationRailDestination(
                        icon: Tooltip(
                          message: reviewPageLabels[i],
                          child: Icon(icons[i]),
                        ),
                        label: Text(
                          wide ? reviewPageLabels[i] : compactLabels[i],
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),
          if (wide && d != null)
            Container(
              margin: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: colors.surfaceContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(child: Text('今日掌握率', style: text.labelMedium)),
                      Text(
                        pct == null ? '—' : '${(100 * pct).round()}%',
                        style: text.titleSmall?.copyWith(
                          color: colors.primary,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 9),
                  LinearProgressIndicator(
                    value: pct ?? 0,
                    minHeight: 5,
                    borderRadius: BorderRadius.circular(99),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'App 最近记录\n${side?['latest']?.toString().replaceFirst('T', ' ').split('.').first ?? '—'}',
                    style: text.labelSmall?.copyWith(
                      color: colors.onSurfaceVariant,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          Divider(height: 1, color: colors.outlineVariant),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            child: Tooltip(
              message: d?['folder'] ?? '导出目录',
              child: TextButton.icon(
                onPressed: d == null ? null : onOpenFolder,
                icon: const Icon(Icons.folder_open_outlined),
                label: Text(wide ? '导出目录' : '目录'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
