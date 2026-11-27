import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

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
    required this.saving,
  });
  final Json data;
  final String content;
  final ValueChanged<String> onEdit;
  final VoidCallback? onSave;
  final bool dirty;
  final bool saving;
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

  void saveWithKeyboard() {
    if (widget.dirty && !widget.saving) widget.onSave?.call();
  }

  @override
  Widget build(BuildContext context) {
    final stats = widget.data['stats'] as Json?;
    final exists = widget.data['prompt'] != null || widget.dirty;
    final colors = Theme.of(context).colorScheme;
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
    final preview = _Pane(
      icon: Icons.menu_book_outlined,
      title: '渲染预览',
      trailing: '可选择文本',
      child: read,
    );
    final editor = _Pane(
      icon: Icons.code,
      title: 'Markdown 源码',
      trailing: 'Ctrl + S 保存',
      child: TextField(
        controller: controller,
        readOnly: widget.saving,
        onChanged: widget.onEdit,
        maxLines: 22,
        minLines: 14,
        style: const TextStyle(
          fontFamily: 'Consolas',
          fontFamilyFallback: ['Microsoft YaHei UI'],
          height: 1.55,
        ),
        decoration: const InputDecoration(
          hintText: '在这里编辑 Markdown…',
          alignLabelWithHint: true,
          border: OutlineInputBorder(),
        ),
      ),
    );
    return CallbackShortcuts(
      bindings: {
        const SingleActivator(LogicalKeyboardKey.keyS, control: true):
            saveWithKeyboard,
      },
      child: Section(
        '每日复习 Prompt',
        Icons.article_outlined,
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Chip(
                  avatar: const Icon(Icons.calendar_today_outlined, size: 17),
                  label: Text(widget.data['day']),
                ),
                if (stats != null)
                  for (final pair in [
                    ('顽固词', 'hard'),
                    ('模糊词', 'fuzzy'),
                    ('自动提级', 'promoted'),
                  ])
                    Chip(label: Text('${pair.$1} ${stats[pair.$2] ?? '—'}')),
              ],
            ),
            const SizedBox(height: 16),
            if (!exists)
              Empty(
                widget.data['codes_available'] == true
                    ? '这一天还没有复习文件。点「导出复习」可用本机记录生成。'
                    : '这一天还没有复习文件。可切换学习日，或点「同步 MuMu」获取最新学习记录。',
                icon: Icons.description_outlined,
              )
            else ...[
              Wrap(
                spacing: 12,
                runSpacing: 10,
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
                    onSelectionChanged: (s) =>
                        setState(() => editing = s.first),
                  ),
                  if (editing)
                    Tooltip(
                      message: '保存修改（Ctrl + S）',
                      child: FilledButton.tonalIcon(
                        onPressed: widget.dirty && !widget.saving
                            ? widget.onSave
                            : null,
                        icon: const Icon(Icons.save_outlined),
                        label: Text(widget.saving ? '正在保存…' : '保存修改'),
                      ),
                    ),
                  if (widget.dirty)
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 7,
                          height: 7,
                          decoration: BoxDecoration(
                            color: colors.tertiary,
                            shape: BoxShape.circle,
                          ),
                        ),
                        const SizedBox(width: 7),
                        const Text('有未保存的修改'),
                      ],
                    ),
                ],
              ),
              const Divider(height: 30),
              LayoutBuilder(
                builder: (context, box) {
                  if (editing && box.maxWidth >= 800) {
                    return Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(child: editor),
                        const SizedBox(width: 16),
                        Expanded(child: preview),
                      ],
                    );
                  }
                  if (editing) return editor;
                  return preview;
                },
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _Pane extends StatelessWidget {
  const _Pane({
    required this.icon,
    required this.title,
    required this.trailing,
    required this.child,
  });

  final IconData icon;
  final String title;
  final String trailing;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return InsetPanel(
      padding: EdgeInsets.zero,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            child: Row(
              children: [
                Icon(icon, size: 17, color: colors.primary),
                const SizedBox(width: 7),
                Expanded(
                  child: Text(
                    title,
                    style: Theme.of(context).textTheme.labelLarge,
                  ),
                ),
                Text(trailing, style: Theme.of(context).textTheme.labelSmall),
              ],
            ),
          ),
          Divider(height: 1, color: colors.outlineVariant),
          Padding(padding: const EdgeInsets.all(14), child: child),
        ],
      ),
    );
  }
}
