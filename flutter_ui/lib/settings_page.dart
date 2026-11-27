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
    final c = Theme.of(context).colorScheme;
    return Align(
      alignment: Alignment.topLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 840),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Section(
              '复习难度',
              Icons.school_outlined,
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
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
                  const SizedBox(height: 10),
                  const Text(
                    '难度从下次生成 Prompt 起生效。要更新已有文件，选中对应学习日，再点「导出复习」。',
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Section(
              '外观主题',
              Icons.palette_outlined,
              SegmentedButton<ThemeMode>(
                showSelectedIcon: false,
                segments: [
                  for (final option in [
                    ThemeMode.light,
                    ThemeMode.dark,
                    ThemeMode.system,
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
                    runSpacing: 6,
                    children: [
                      Chip(label: Text('ADB · $adb')),
                      Chip(label: Text('Root · $root')),
                    ],
                  ),
                  const SizedBox(height: 12),
                  const Text(
                    '同步需要 MuMu 的 Android 15 模拟器，以及在该模拟器里安装的「不背单词」5.11.8 x86。',
                  ),
                  const SizedBox(height: 8),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      FilledButton.icon(
                        onPressed: setup,
                        icon: const Icon(Icons.build_outlined),
                        label: const Text('一键配置 MuMu'),
                      ),
                      TextButton.icon(
                        onPressed: openSite,
                        icon: const Icon(Icons.open_in_new),
                        label: const Text('打开 MuMu 官网'),
                      ),
                      TextButton.icon(
                        onPressed: locate,
                        icon: const Icon(Icons.folder_open_outlined),
                        label: const Text('选择 MuMu 安装目录'),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  Container(
                    constraints: const BoxConstraints(maxHeight: 220),
                    padding: const EdgeInsets.all(14),
                    width: double.infinity,
                    decoration: BoxDecoration(
                      color: c.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: SingleChildScrollView(
                      reverse: true,
                      child: SelectableText(
                        logs.isEmpty ? '等待配置或同步。' : logs.join('\n'),
                        style: Theme.of(context).textTheme.bodySmall,
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
                  SelectableText(data['folder']),
                  const SizedBox(height: 14),
                  Wrap(
                    spacing: 10,
                    runSpacing: 8,
                    children: [
                      OutlinedButton.icon(
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
