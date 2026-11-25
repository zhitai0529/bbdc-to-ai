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
    final c = Theme.of(context).colorScheme;
    final side = d?['sidebar'] as Json?, total = side?['total'] ?? 0;
    final pct = total == 0 ? null : (side!['mastered'] ?? 0) / total;
    return Container(
      width: wide ? 204 : 92,
      color: c.surfaceContainer,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 20),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircleAvatar(
                  backgroundColor: c.primaryContainer,
                  child: Icon(Icons.auto_stories, color: c.primary),
                ),
                if (wide) ...[
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '不背单词复习助手',
                          style: TextStyle(fontWeight: FontWeight.bold),
                        ),
                        Text(
                          d == null ? '' : 'v${d['version']}',
                          style: Theme.of(context).textTheme.labelSmall,
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
                  minWidth: 92,
                  minExtendedWidth: 204,
                  labelType: wide
                      ? NavigationRailLabelType.none
                      : NavigationRailLabelType.all,
                  selectedIndex: page,
                  onDestinationSelected: onPage,
                  destinations: [
                    for (var i = 0; i < reviewPageLabels.length; i++)
                      NavigationRailDestination(
                        icon: Icon(icons[i]),
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
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '今日掌握率　${pct == null ? '—' : '${(100 * pct).round()}%'}',
                  ),
                  const SizedBox(height: 8),
                  LinearProgressIndicator(value: pct ?? 0),
                  const SizedBox(height: 6),
                  Text(
                    'App 最新记录时间\n${side?['latest']?.toString().replaceFirst('T', ' ').split('.').first ?? '—'}',
                    style: Theme.of(context).textTheme.labelSmall,
                  ),
                ],
              ),
            ),
          const Divider(),
          Tooltip(
            message: d?['folder'] ?? '导出目录',
            child: TextButton.icon(
              onPressed: d == null ? null : onOpenFolder,
              icon: const Icon(Icons.folder_open),
              label: Text(wide ? '导出目录' : '目录'),
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
