import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';

import 'bridge.dart';
import 'review_levels.dart';
import 'widgets.dart';

typedef ExerciseOption = ({String id, String label, String description});

class ExercisePage extends StatefulWidget {
  const ExercisePage({
    super.key,
    required this.call,
    required this.day,
    required this.defaultLevel,
    required this.options,
    required this.busy,
    required this.openFolder,
  });

  final HostCall call;
  final String day;
  final String defaultLevel;
  final List<ExerciseOption> options;
  final bool busy;
  final VoidCallback openFolder;

  @override
  State<ExercisePage> createState() => _ExercisePageState();
}

class _ExercisePageState extends State<ExercisePage> {
  String? _level, _kind, _error;
  ({String filename, String markdown, int wordCount})? _result;
  bool _generating = false;

  String get _selectedLevel => _level ?? widget.defaultLevel;
  String? get _selectedKind => _kind ?? widget.options.firstOrNull?.id;

  void _changeSelection({String? level, String? kind}) {
    setState(() {
      _level = level ?? _level;
      _kind = kind ?? _kind;
      _error = null;
      _result = null;
    });
  }

  Future<void> _export() async {
    final kind = _selectedKind;
    if (kind == null || _generating || widget.busy) return;
    setState(() {
      _generating = true;
      _error = null;
      _result = null;
    });
    try {
      final result =
          await widget.call('export_exercise', [
                widget.day,
                _selectedLevel,
                kind,
              ])
              as Json;
      if (!mounted) return;
      setState(() {
        _result = (
          filename: result['filename'] as String,
          markdown: result['markdown'] as String,
          wordCount: result['word_count'] as int,
        );
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = error is StateError ? error.message : '生成失败，请重试。';
      });
    } finally {
      if (mounted) setState(() => _generating = false);
    }
  }

  Future<void> _copy(String markdown) async {
    final messenger = ScaffoldMessenger.of(context);
    String message;
    try {
      await Clipboard.setData(ClipboardData(text: markdown));
      message = '已复制练习提示词。';
    } on PlatformException {
      message = '无法复制。可在导出目录打开练习文件。';
    }
    if (!mounted) return;
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  Widget build(BuildContext context) {
    final disabled = widget.busy || _generating;
    final result = _result;
    final error = _error;
    final kind = _selectedKind;
    return Align(
      alignment: Alignment.topLeft,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 960),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Section(
              '按题型生成练习',
              Icons.quiz_outlined,
              widget.options.isEmpty
                  ? const Empty('暂时无法读取题型。请重启助手后再试。')
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('学习日 ${widget.day} · 使用当天待复习词'),
                        const SizedBox(height: 12),
                        const Text('难度'),
                        const SizedBox(height: 4),
                        SegmentedButton<String>(
                          segments: [
                            for (final level in reviewLevelLabels.entries)
                              ButtonSegment(
                                value: level.key,
                                label: Text(level.value),
                              ),
                          ],
                          selected: {_selectedLevel},
                          onSelectionChanged: disabled
                              ? null
                              : (selection) =>
                                    _changeSelection(level: selection.single),
                        ),
                        const SizedBox(height: 16),
                        const Text('题型'),
                        const SizedBox(height: 4),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            for (final option in widget.options)
                              ChoiceChip(
                                label: Text(option.label),
                                selected: option.id == kind,
                                onSelected: disabled
                                    ? null
                                    : (selected) {
                                        if (selected) {
                                          _changeSelection(kind: option.id);
                                        }
                                      },
                              ),
                          ],
                        ),
                        for (final option in widget.options)
                          if (option.id == kind)
                            Padding(
                              padding: const EdgeInsets.only(top: 8),
                              child: Text(option.description),
                            ),
                        const SizedBox(height: 16),
                        FilledButton.icon(
                          onPressed: disabled || kind == null ? null : _export,
                          icon: const Icon(Icons.file_download_outlined),
                          label: Text(_generating ? '正在生成…' : '生成练习 Markdown'),
                        ),
                        if (_generating) ...[
                          const SizedBox(height: 12),
                          const LinearProgressIndicator(),
                        ],
                        if (error != null)
                          Padding(
                            padding: const EdgeInsets.only(top: 12),
                            child: Text(
                              error,
                              style: TextStyle(
                                color: Theme.of(context).colorScheme.error,
                              ),
                            ),
                          ),
                      ],
                    ),
            ),
            if (result != null) ...[
              const SizedBox(height: 16),
              Section(
                '练习提示词',
                Icons.description_outlined,
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SelectableText(result.filename),
                    Text('候选词 ${result.wordCount} 个'),
                    const SizedBox(height: 8),
                    const Text('把提示词粘贴给 AI。它会先出题，等你作答后再讲解。'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: [
                        FilledButton.tonalIcon(
                          onPressed: () => _copy(result.markdown),
                          icon: const Icon(Icons.copy_outlined),
                          label: const Text('复制练习提示词'),
                        ),
                        TextButton.icon(
                          onPressed: widget.openFolder,
                          icon: const Icon(Icons.folder_open_outlined),
                          label: const Text('打开导出目录'),
                        ),
                      ],
                    ),
                    const Divider(height: 24),
                    SelectionArea(
                      child: MarkdownBody(
                        data: result.markdown,
                        imageBuilder: (uri, title, alt) => Text(alt ?? '[图片]'),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
