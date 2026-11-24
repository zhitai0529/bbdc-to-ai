import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'appearance.dart';
import 'bridge.dart';
import 'widgets.dart';

class ReviewPage extends StatefulWidget {
  const ReviewPage({
    super.key,
    required this.data,
    required this.content,
    required this.onEdit,
    required this.onSave,
    required this.dirty,
  });
  final Json data;
  final String content;
  final ValueChanged<String> onEdit;
  final VoidCallback? onSave;
  final bool dirty;
  @override
  State<ReviewPage> createState() => _ReviewPageState();
}

class _ReviewPageState extends State<ReviewPage> {
  late final controller = TextEditingController(text: widget.content);
  bool editing = false;
  @override
  void didUpdateWidget(ReviewPage old) {
    super.didUpdateWidget(old);
    if (controller.text != widget.content) controller.text = widget.content;
  }

  @override
  void dispose() {
    controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final stats = widget.data['stats'] as Json?,
        exists = widget.data['prompt'] != null;
    final read = SelectionArea(
      child: MarkdownBody(
        data: widget.content,
        imageBuilder: (uri, title, alt) => Text(alt ?? '[图片]'),
        styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
          blockSpacing: 14,
          code: const TextStyle(fontFamily: 'Consolas'),
          tableCellsPadding: const EdgeInsets.all(7),
        ),
      ),
    );
    final edit = TextField(
      controller: controller,
      onChanged: widget.onEdit,
      maxLines: 20,
      minLines: 12,
      style: const TextStyle(
        fontFamily: 'Consolas',
        fontFamilyFallback: ['Microsoft YaHei UI'],
      ),
      decoration: const InputDecoration(
        labelText: 'Markdown 源码',
        alignLabelWithHint: true,
        border: OutlineInputBorder(),
      ),
    );
    return Section(
      '每日复习 Prompt',
      Icons.article_outlined,
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              Chip(label: Text(widget.data['day'])),
              if (stats != null)
                for (final pair in [
                  ('顽固词', 'hard'),
                  ('模糊词', 'fuzzy'),
                  ('自动提级', 'promoted'),
                ])
                  Chip(label: Text('${pair.$1} ${stats[pair.$2]}')),
            ],
          ),
          const SizedBox(height: 14),
          if (!exists)
            const Empty('该学习日还没有导出的复习文件。', icon: Icons.description_outlined)
          else ...[
            Wrap(
              spacing: 12,
              runSpacing: 8,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(
                      value: false,
                      icon: Icon(Icons.menu_book_outlined),
                      label: Text('阅读'),
                    ),
                    ButtonSegment(
                      value: true,
                      icon: Icon(Icons.edit_outlined),
                      label: Text('源码编辑'),
                    ),
                  ],
                  selected: {editing},
                  onSelectionChanged: (s) => setState(() => editing = s.first),
                ),
                if (editing)
                  FilledButton.tonalIcon(
                    onPressed: widget.dirty ? widget.onSave : null,
                    icon: const Icon(Icons.save_outlined),
                    label: const Text('保存修改'),
                  ),
                if (widget.dirty) const Text('有未保存的修改'),
              ],
            ),
            const Divider(height: 32),
            LayoutBuilder(
              builder: (context, box) => editing && box.maxWidth >= 1080
                  ? Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: edit),
                        const SizedBox(width: 18),
                        Expanded(child: read),
                      ],
                    )
                  : editing
                  ? edit
                  : read,
            ),
          ],
        ],
      ),
    );
  }
}

class HistoryPage extends StatelessWidget {
  const HistoryPage(this.data, {super.key});
  final Json data;
  @override
  Widget build(BuildContext context) {
    final repeats = (data['repeats'] as List).cast<Json>(),
        hard = (data['errors'] as List).cast<Json>(),
        codes = (data['unknown'] as List).cast<Json>();
    Widget table(
      List<String> headings,
      List<List<Object?>> rows,
      String empty,
    ) {
      if (rows.isEmpty) return Empty(empty);
      return SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: DataTable(
          columnSpacing: 30,
          headingRowHeight: 38,
          dataRowMinHeight: 38,
          dataRowMaxHeight: 52,
          columns: [for (final h in headings) DataColumn(label: Text(h))],
          rows: [
            for (final row in rows)
              DataRow(
                cells: [
                  for (final value in row)
                    DataCell(SelectableText(value?.toString() ?? '—')),
                ],
              ),
          ],
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Section(
          '跨天反复模糊或答错',
          Icons.repeat_rounded,
          table(
            ['单词', '出现学习日数', '最近一次'],
            [
              for (final r in repeats) [r['word'], r['days'], r['last_day']],
            ],
            '窗口内暂无跨天重复记录。',
          ),
          action: Text('近 ${data['window']} 天'),
        ),
        const SizedBox(height: 14),
        Section(
          '当日顽固词',
          Icons.local_fire_department_outlined,
          table(
            ['单词', '本轮错误次数', '分类'],
            [
              for (final r in hard)
                [
                  r['word'],
                  r['wrong'],
                  r['promoted'] == true ? '跨天自动提级' : '基础顽固词',
                ],
            ],
            '当日暂无顽固词记录。',
          ),
        ),
        const SizedBox(height: 14),
        Section(
          '未知编码核对',
          Icons.rule,
          table(
            ['ah', 'rh', '评分', '词数', '示例'],
            [
              for (final r in codes)
                [r['ah'], r['rh'], r['rating'], r['count'], r['examples']],
            ],
            data['codes_available'] == true ? '当日没有未知编码。' : '当日缺少词条缓存，无法核对编码。',
          ),
        ),
      ],
    );
  }
}

class SettingsPage extends StatelessWidget {
  const SettingsPage({
    super.key,
    required this.data,
    required this.logs,
    required this.adb,
    required this.root,
    required this.setup,
    required this.change,
    required this.open,
    required this.mode,
    required this.changeTheme,
  });
  final Json data;
  final String adb, root;
  final List<String> logs;
  final VoidCallback? setup, change;
  final VoidCallback open;
  final ThemeMode mode;
  final ValueChanged<ThemeMode>? changeTheme;
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
                  const SizedBox(height: 8),
                  FilledButton.icon(
                    onPressed: setup,
                    icon: const Icon(Icons.build_outlined),
                    label: const Text('一键配置 MuMu'),
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
