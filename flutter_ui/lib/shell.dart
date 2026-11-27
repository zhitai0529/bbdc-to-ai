import 'dart:async';
import 'dart:io';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'appearance.dart';
import 'bridge.dart';
import 'desktop_task.dart';
import 'exercise_page.dart';
import 'overview.dart';
import 'history_page.dart';
import 'review_levels.dart';
import 'review_page.dart';
import 'settings_page.dart';
import 'sidebar.dart';
import 'review_session.dart';

enum _SyncPhase { idle, running, stopping, finishing }

class Shell extends StatefulWidget {
  const Shell({
    super.key,
    required this.call,
    required this.smoke,
    required this.mode,
    required this.changeTheme,
  });
  final HostCall call;
  final bool smoke;
  final ThemeMode mode;
  final Future<void> Function(ThemeMode)? changeTheme;
  @override
  State<Shell> createState() => _ShellState();
}

class _ShellState extends State<Shell> {
  late final session = ReviewSession(widget.call);
  late final tasks = DesktopTasks(widget.call);
  Json? get data => session.data;
  String get content => session.content;
  bool busy = false, copied = false, saving = false;
  _SyncPhase _syncPhase = _SyncPhase.idle;
  Future<bool>? _stopRequest;
  Future<String?>? _exitDialog;
  Timer? copyFeedback;
  int page = 0;
  String status = '正在读取本机记录…', adb = '尚未检查', root = '尚未检查';
  final logs = <String>[];
  late final AppLifecycleListener lifecycle;
  @override
  void initState() {
    super.initState();
    lifecycle = AppLifecycleListener(
      onExitRequested: () async {
        if (session.hasDrafts && mounted) {
          final answer = await (_exitDialog ??= ask('关闭复习助手？', '有尚未保存的复习修改。', {
            'stay': '继续编辑',
            'exit': '放弃修改并关闭',
          }));
          _exitDialog = null;
          if (answer != 'exit') return AppExitResponse.cancel;
        }
        return AppExitResponse.exit;
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => initialize());
  }

  @override
  void dispose() {
    copyFeedback?.cancel();
    lifecycle.dispose();
    super.dispose();
  }

  Future<void> initialize() async {
    try {
      final result = await session.initialize();
      if (!mounted) return;
      setState(() => status = result.warning ?? session.loadStatus);
      if (widget.smoke) {
        await WidgetsBinding.instance.endOfFrame;
        final nextMode = widget.mode == ThemeMode.dark
            ? ThemeMode.light
            : ThemeMode.dark;
        await widget.changeTheme?.call(nextMode);
        await session.selectDay(data!['day'] as String);
        if (!mounted) return;
        setState(() => page = 1);
        await WidgetsBinding.instance.endOfFrame;
        exit(0);
      }
      if (result.export) await task(DesktopAction.export);
    } catch (e) {
      if (widget.smoke) exit(1);
      notify(e is StateError ? e.message : '$e');
    }
  }

  void notify(String msg) {
    if (!mounted) return;
    setState(() => status = msg);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(msg), behavior: SnackBarBehavior.floating),
      );
  }

  Future<void> changeTheme(ThemeMode mode) async {
    try {
      await widget.changeTheme?.call(mode);
    } catch (_) {
      notify('主题保存失败，请重试。');
    }
  }

  Future<void> perform(Future<void> Function() fn) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      await fn();
    } catch (e) {
      notify(e is StateError ? e.message : '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> refresh(String? day) async {
    await session.selectDay(day);
    if (!mounted) return;
    setState(() => status = session.loadStatus);
  }

  Future<String?> ask(String title, String body, Map<String, String> choices) =>
      showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          scrollable: true,
          content: SelectableText(body),
          actions: [
            for (final e in choices.entries)
              TextButton(
                onPressed: () => Navigator.pop(ctx, e.key),
                child: Text(e.value),
              ),
          ],
        ),
      );

  Future<void> open() async {
    try {
      await session.openFolder();
    } catch (e) {
      notify('无法打开导出目录。请在「MuMu 与设置 → 导出保存位置」重选文件夹。');
    }
  }

  Future<void> copy() async {
    try {
      await Clipboard.setData(ClipboardData(text: content));
      if (!mounted) return;
      setState(() => copied = true);
      notify('已复制复习 Prompt，可粘贴到常用的 AI。');
      copyFeedback?.cancel();
      copyFeedback = Timer(const Duration(seconds: 2), () {
        if (mounted) setState(() => copied = false);
      });
    } catch (e) {
      notify('无法复制。可在「复习预览」选中文本，或直接打开导出的 Markdown 文件。');
    }
  }

  void log(String text) {
    final time = TimeOfDay.now().format(context);
    logs.add('$time  $text');
    if (logs.length > 160) logs.removeAt(0);
  }

  Future<void> openMumuSite() => perform(tasks.openMumuSite);

  Future<void> locateMumu(DesktopAction action) async {
    if (await tasks.locateMumu()) {
      notify('已选择 MuMu 安装目录。请启动要用的 Android 15 模拟器，再点「${action.label}」。');
    }
  }

  Future<void> stopSync() async {
    if (_syncPhase != _SyncPhase.running) return;
    setState(() {
      _syncPhase = _SyncPhase.stopping;
      status = '正在停止同步…';
    });
    final request = tasks.cancelSync();
    _stopRequest = request;
    try {
      final accepted = await request;
      if (accepted || !mounted || _stopRequest != request) return;
      setState(() {
        _syncPhase = _SyncPhase.finishing;
        status = '正在读取同步结果…';
      });
    } catch (e) {
      if (!mounted || _stopRequest != request) return;
      setState(() => _syncPhase = _SyncPhase.running);
      notify(e is StateError ? e.message : '暂时无法停止同步，请重试。');
    }
  }

  Future<void> task(DesktopAction action, {String? day}) => perform(() async {
    try {
      await runTask(action, day: day);
    } finally {
      _stopRequest = null;
      _syncPhase = _SyncPhase.idle;
    }
  });

  Future<void> runTask(DesktopAction action, {String? day}) async {
    if (action == DesktopAction.setup) {
      final choice = await ask(action.label, mumuSetupInstructions, {
        'back': '返回',
        'download': '打开 MuMu 官网',
        'go': '开始配置',
      });
      if (!mounted) return;
      if (choice == 'download') {
        await tasks.openMumuSite();
        return;
      }
      if (choice != 'go') return;
    }
    var start = await tasks.start(action, day: day);
    if (!mounted) return;
    if (start['status'] == 'choose') {
      final choice = await ask('未找到 MuMu 安装位置', mumuLocationInstructions, {
        'back': '返回',
        'download': '打开 MuMu 官网',
        'locate': '选择安装目录',
      });
      if (!mounted) return;
      if (choice == 'download') {
        await tasks.openMumuSite();
        return;
      }
      if (choice != 'locate' || !await tasks.locateMumu() || !mounted) return;
      start = await tasks.start(action, day: day);
      if (!mounted) return;
    }
    if (start['status'] != 'started') {
      throw StateError(
        action == DesktopAction.export
            ? '无法启动离线导出。请重新打开助手后再试。'
            : '未在所选文件夹找到 MuMu。请从 MuMu 图标打开程序所在位置，重新选择该文件夹。',
      );
    }
    final progress = day == null ? action.progress : '正在导出 $day 的复习…';
    setState(() {
      status = progress;
      if (action == DesktopAction.sync) _syncPhase = _SyncPhase.running;
      if (action == DesktopAction.setup) adb = root = '正在检查';
      log(progress);
      final message = start['message'] as String?;
      if (message != null && message.isNotEmpty) log(message);
    });
    var adbPassed = false, rootPassed = false;
    await for (final update in tasks.watch()) {
      if (!mounted) return;
      adbPassed =
          update.adbChecked ??
          (adbPassed || update.newLines.contains('ADB 连接通过。'));
      rootPassed =
          update.rootChecked ??
          (rootPassed || update.newLines.contains('Root 检查通过。'));
      if (update.newLines.isNotEmpty) {
        setState(() => update.newLines.forEach(log));
      }
      if (update.running) continue;
      _stopRequest = null;
      if (action == DesktopAction.sync) {
        setState(() => _syncPhase = _SyncPhase.idle);
      }
      if (update.day != null) await refresh(update.day);
      if (!mounted) return;
      if (action == DesktopAction.setup) {
        final stamp = TimeOfDay.now().format(context);
        adb = adbPassed ? '通过 $stamp' : '未完成';
        root = rootPassed ? '通过 $stamp' : '未完成';
      }
      final message = update.guidance(action);
      log(message);
      notify(message);
      if (action == DesktopAction.setup ||
          (action == DesktopAction.sync &&
              !update.succeeded &&
              !update.cancelled &&
              update.status != 'no_records')) {
        final choice = await ask(
          update.succeeded ? 'MuMu 配置完成' : '${action.label}未完成',
          message,
          {
            'ok': '关闭',
            if (update.showDownloads) 'download': '打开 MuMu 官网',
            if (update.showLocation) 'locate': '选择安装目录',
          },
        );
        if (choice == 'download' && mounted) await tasks.openMumuSite();
        if (choice == 'locate' && mounted) await locateMumu(action);
      }
    }
  }

  Future<void> change() => perform(() async {
    if (await session.changeFolder()) {
      notify('导出目录已更改。后续同步和导出会使用这个文件夹。');
    }
  });

  Future<void> changeReviewLevel(String level) => perform(() async {
    await session.saveReviewLevel(level);
    notify('已保存${reviewLevelLabels[level]}难度，下次导出时生效。');
  });

  Future<void> save() => perform(() async {
    setState(() => saving = true);
    try {
      if (await session.saveDraft()) notify('修改已保存到当前的复习文件。');
    } finally {
      if (mounted) setState(() => saving = false);
    }
  });

  void edit(String text) => setState(() => session.edit(text));

  Widget syncButton(bool ready) {
    final (label, icon, action, tooltip) = switch (_syncPhase) {
      _SyncPhase.idle => (
        '同步 MuMu',
        Icons.sync,
        ready && !busy ? () => task(DesktopAction.sync) : null,
        '从 MuMu 同步学习记录',
      ),
      _SyncPhase.running => (
        '停止同步',
        Icons.stop_circle_outlined,
        stopSync,
        '停止本次同步，可稍后重新同步',
      ),
      _SyncPhase.stopping => ('正在停止…', Icons.stop, null, ''),
      _SyncPhase.finishing => ('正在收尾…', Icons.hourglass_top, null, ''),
    };
    final colors = Theme.of(context).colorScheme;
    return Tooltip(
      message: tooltip,
      child: FilledButton.icon(
        onPressed: action,
        style: _syncPhase == _SyncPhase.running
            ? FilledButton.styleFrom(
                backgroundColor: colors.errorContainer,
                foregroundColor: colors.onErrorContainer,
              )
            : null,
        icon: Icon(icon),
        label: Text(label),
      ),
    );
  }

  Widget _exercisePage(Json d) => Visibility(
    key: const ValueKey('exercise-tab'),
    visible: page == exercisePageIndex,
    maintainState: true,
    child: SingleChildScrollView(
      key: const PageStorageKey(exercisePageIndex),
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: ExercisePage(
        key: ValueKey((d['day'], d['folder'])),
        call: widget.call,
        day: d['day'],
        defaultLevel: d['review_level'] ?? 'postgrad',
        options: [
          for (final option in d['exercise_types'] as List? ?? const [])
            (
              id: option['id'] as String,
              label: option['label'] as String,
              description: option['description'] as String,
            ),
        ],
        busy: busy,
        openFolder: open,
      ),
    ),
  );

  @override
  Widget build(BuildContext context) {
    final d = data;
    final day = d?['day'] as String?;
    final wide = MediaQuery.sizeOf(context).width >= 1140;
    return Scaffold(
      body: Row(
        children: [
          ReviewSidebar(
            data: d,
            wide: wide,
            page: page,
            onPage: (i) => setState(() => page = i),
            onOpenFolder: open,
          ),
          Expanded(
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: wide ? 24 : 14,
                vertical: 12,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Wrap(
                    alignment: WrapAlignment.spaceBetween,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    spacing: 16,
                    runSpacing: 8,
                    children: [
                      Text(
                        page == 0
                            ? (d?['today'] == d?['day'] ? '今日复习看板' : '复习看板')
                            : reviewPageLabels[page],
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      Wrap(
                        spacing: 8,
                        runSpacing: 6,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          if (d != null)
                            DropdownButton<String>(
                              value: d['day'],
                              items: [
                                for (final day in d['dates'])
                                  DropdownMenuItem<String>(
                                    value: day,
                                    child: Text(day),
                                  ),
                              ],
                              onChanged: busy
                                  ? null
                                  : (v) => perform(() => refresh(v)),
                              underline: const SizedBox(),
                            ),
                          syncButton(d != null),
                          Tooltip(
                            message: day == null
                                ? '用本机记录导出复习'
                                : '用本机记录导出 $day 的复习',
                            child: FilledButton.tonalIcon(
                              onPressed: busy || day == null
                                  ? null
                                  : () => task(DesktopAction.export, day: day),
                              icon: const Icon(Icons.download_outlined),
                              label: Text(DesktopAction.export.label),
                            ),
                          ),
                          if (page != exercisePageIndex)
                            OutlinedButton.icon(
                              onPressed: content.isEmpty ? null : copy,
                              icon: Icon(
                                copied ? Icons.check : Icons.copy_outlined,
                              ),
                              label: Text(copied ? '已复制' : '复制全部内容'),
                            ),
                          ThemeMenu(
                            mode: widget.mode,
                            onChanged: widget.changeTheme == null
                                ? null
                                : changeTheme,
                          ),
                        ],
                      ),
                    ],
                  ),
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Semantics(
                      liveRegion: true,
                      child: Text(
                        status,
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ),
                  ),
                  if (busy) const LinearProgressIndicator(minHeight: 3),
                  Expanded(
                    child: d == null
                        ? Center(
                            child: TextButton(
                              onPressed: initialize,
                              child: const Text('重新读取本地记录'),
                            ),
                          )
                        : Stack(
                            fit: StackFit.expand,
                            children: [
                              if (page != exercisePageIndex) _reviewPage(d),
                              _exercisePage(d),
                            ],
                          ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _reviewPage(Json d) => SingleChildScrollView(
    key: PageStorageKey(page),
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: switch (page) {
      0 => Overview(
        d,
        () => setState(() => page = 2),
        busy ? null : (v) => perform(() => refresh(v)),
      ),
      1 => ReviewPage(
        data: d,
        content: content,
        onEdit: edit,
        onSave: busy ? null : save,
        dirty: session.hasCurrentDraft,
        saving: saving,
      ),
      2 => HistoryPage(d),
      _ => SettingsPage(
        data: d,
        logs: logs,
        adb: adb,
        root: root,
        setup: busy ? null : () => task(DesktopAction.setup),
        openSite: busy ? null : openMumuSite,
        locate: busy
            ? null
            : () => perform(() => locateMumu(DesktopAction.setup)),
        change: busy ? null : change,
        open: open,
        mode: widget.mode,
        changeTheme: widget.changeTheme == null ? null : changeTheme,
        changeReviewLevel: busy ? null : changeReviewLevel,
      ),
    },
  );
}
