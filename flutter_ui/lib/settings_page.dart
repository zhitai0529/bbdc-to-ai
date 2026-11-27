import 'package:flutter/material.dart';

import 'appearance.dart';
import 'bridge.dart';
import 'review_levels.dart';
import 'widgets.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({
    super.key,
    required this.data,
    required this.logs,
    required this.adb,
    required this.root,
    required this.setup,
    required this.openSite,
    required this.locate,
    required this.change,
    required this.open,
    required this.mode,
    required this.changeTheme,
    required this.changeReviewLevel,
  });
  final Json data;
  final String adb, root;
  final List<String> logs;
  final VoidCallback? setup, openSite, locate, change;
  final VoidCallback open;
  final ThemeMode mode;
  final ValueChanged<ThemeMode>? changeTheme;
  final ValueChanged<String>? changeReviewLevel;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    return Align(
      alignment: Alignment.topLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 960),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Section(
              '复习偏好',
              Icons.school_outlined,
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('阅读与练习难度', style: text.titleSmall),
                  const SizedBox(height: 5),
                  Text(
                    '从下次生成 Prompt 起生效。要更新已有文件，选中对应学习日，再点「导出复习」。',
                    style: text.bodySmall?.copyWith(
                      color: colors.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 14),
                  SegmentedButton<String>(
                    segments: [
                      for (final level in reviewLevelLabels.entries)
                        ButtonSegment(
                          value: level.key,
                          label: Text(level.value),
                        ),
                    ],
                    selected: {data['review_level'] as String? ?? 'postgrad'},
                    onSelectionChanged: changeReviewLevel == null
                        ? null
                        : (selection) => changeReviewLevel!(selection.single),
                  ),
                  const SizedBox(height: 22),
                  Text('外观主题', style: text.titleSmall),
                  const SizedBox(height: 5),
                  Text(
                    '跟随系统会在 Windows 切换明暗外观时自动更新。',
                    style: text.bodySmall?.copyWith(
                      color: colors.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 14),
                  SegmentedButton<ThemeMode>(
                    showSelectedIcon: false,
                    segments: [
                      for (final option in [
                        ThemeMode.system,
                        ThemeMode.light,
                        ThemeMode.dark,
                      ])
                        ButtonSegment(
                          value: option,
                          icon: Icon(option.icon),
                          label: Text(option.label),
                        ),
                    ],
                    selected: {mode},
                    onSelectionChanged: changeTheme == null
                        ? null
                        : (selection) => changeTheme!(selection.single),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Section(
              'MuMu 模拟器环境',
              Icons.computer,
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _StateChip(label: 'ADB · $adb'),
                      _StateChip(label: 'Root · $root'),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Text(
                    '同步需要 MuMu 的 Android 15 模拟器，以及在该模拟器里安装的「不背单词」5.11.8 x86。',
                    style: text.bodyMedium?.copyWith(
                      color: colors.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      FilledButton.icon(
                        onPressed: setup,
                        icon: const Icon(Icons.build_outlined),
                        label: const Text('一键配置 MuMu'),
                      ),
                      OutlinedButton.icon(
                        onPressed: locate,
                        icon: const Icon(Icons.folder_open_outlined),
                        label: const Text('选择安装目录'),
                      ),
                      TextButton.icon(
                        onPressed: openSite,
                        icon: const Icon(Icons.open_in_new),
                        label: const Text('MuMu 官网'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  Row(
                    children: [
                      Icon(Icons.terminal, size: 18, color: colors.primary),
                      const SizedBox(width: 8),
                      Expanded(child: Text('运行日志', style: text.titleSmall)),
                      Text('${logs.length} 条', style: text.labelSmall),
                    ],
                  ),
                  const SizedBox(height: 10),
                  InsetPanel(
                    padding: EdgeInsets.zero,
                    child: Container(
                      constraints: const BoxConstraints(maxHeight: 230),
                      child: SingleChildScrollView(
                        reverse: true,
                        padding: const EdgeInsets.all(14),
                        child: SelectableText(
                          logs.isEmpty ? '等待配置或同步。' : logs.join('\n'),
                          style: text.bodySmall?.copyWith(height: 1.65),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Section(
              '导出保存位置',
              Icons.folder_open_outlined,
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  InsetPanel(
                    child: Row(
                      children: [
                        Icon(Icons.folder_outlined, color: colors.primary),
                        const SizedBox(width: 12),
                        Expanded(child: SelectableText(data['folder'])),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      FilledButton.tonalIcon(
                        onPressed: change,
                        icon: const Icon(Icons.drive_file_move_outlined),
                        label: const Text('更改保存位置'),
                      ),
                      TextButton.icon(
                        onPressed: open,
                        icon: const Icon(Icons.folder_open),
                        label: const Text('打开导出目录'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StateChip extends StatelessWidget {
  const _StateChip({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final passed = label.contains('通过');
    final incomplete = label.contains('未完成');
    final tone = passed
        ? colors.primary
        : incomplete
        ? colors.error
        : colors.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
      decoration: BoxDecoration(
        color: tone.withValues(alpha: .09),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: tone.withValues(alpha: .25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            passed
                ? Icons.check_circle_outline
                : incomplete
                ? Icons.error_outline
                : Icons.pending_outlined,
            size: 16,
            color: tone,
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.labelMedium?.copyWith(color: tone),
          ),
        ],
      ),
    );
  }
}
