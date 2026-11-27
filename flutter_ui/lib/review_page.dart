import 'package:flutter/material.dart';
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

  @override
  Widget build(BuildContext context) {
    final stats = widget.data['stats'] as Json?,
        exists = widget.data['prompt'] != null || widget.dirty;
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
      readOnly: widget.saving,
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
                  Chip(label: Text('${pair.$1} ${stats[pair.$2] ?? '—'}')),
            ],
          ),
          const SizedBox(height: 14),
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
