import 'dart:async';
import 'dart:io';
import 'dart:ui' show AppExitResponse;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'bridge.dart';
import 'desktop_task.dart';
import 'exercise_page.dart';
import 'overview.dart';
import 'history_page.dart';
import 'review_levels.dart';
import 'review_page.dart';
import 'settings_page.dart';
import 'sidebar.dart';
import 'shell_header.dart';
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

  void notify(String msg, {SnackBarAction? action}) {
    if (!mounted) return;
    setState(() => status = msg);
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(msg),
          behavior: SnackBarBehavior.floating,
          action: action,
        ),
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

  Future<void> refresh(String? day, {bool? pin}) async {
    await session.selectDay(day, pin: pin);
    if (!mounted) return;
    setState(() => status = session.loadStatus);
  }

  Future<void> pickDay(String? day) => perform(() => refresh(day, pin: true));

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
    Draft? overwriteDraft;
    final hasDraft =
        action == DesktopAction.export &&
        day == data?['day'] &&
        session.hasCurrentDraft;
    var start = await tasks.start(
      action,
      day: day,
      decision: hasDraft ? 'check' : null,
    );
    if (!mounted) return;
    while (start['status'] == 'confirm_export') {
      final exportDay = start['day'] as String;
      final reason =
          start['message'] as String? ?? '$exportDay 的复习文件已有修改或来自旧版。';
      final reviewDecision = await ask(
        '重新导出 $exportDay 的复习',
        '$reason\n\n另存副本会把新生成的 Prompt 写入另一个文件。'
            '${hasDraft ? '\n当前还有未保存草稿。选择覆盖后，确认时的草稿会在新文件写入成功后丢弃。' : ''}',
        const {'cancel': '取消', 'overwrite': '覆盖', 'copy': '另存副本'},
      );
      if (!mounted || reviewDecision == null || reviewDecision == 'cancel')
        return;
      overwriteDraft = reviewDecision == 'overwrite'
          ? session.currentDraft
          : null;
      start = await tasks.start(
        action,
        day: exportDay,
        decision: reviewDecision,
        revision: start['revision'] as String,
      );
      if (!mounted) return;
    }
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
      final finishedDay = update.day;
      final pinned = action == DesktopAction.sync ? session.pinnedDay : null;
      final offerLatest =
          update.succeeded &&
          pinned != null &&
          finishedDay != null &&
          pinned != finishedDay;
      if (finishedDay != null &&
          (action == DesktopAction.sync || !update.copied)) {
        if (action == DesktopAction.export &&
            update.succeeded &&
            overwriteDraft != null) {
          session.discardCurrentDraft(overwriteDraft);
        }
        await refresh(pinned ?? finishedDay);
      }
      if (!mounted) return;
      if (action == DesktopAction.setup) {
        final stamp = TimeOfDay.now().format(context);
        adb = adbPassed ? '通过 $stamp' : '未完成';
        root = rootPassed ? '通过 $stamp' : '未完成';
      }
      final message = update.copied && action == DesktopAction.export
          ? '新复习已另存为 ${update.filename ?? '独立文件'}。'
          : update.guidance(action);
      log(message);
      notify(
        message,
        action: offerLatest
            ? SnackBarAction(
                label: '查看最新',
                onPressed: () =>
                    perform(() => refresh(finishedDay, pin: false)),
              )
            : update.copied
            ? SnackBarAction(label: '打开导出目录', onPressed: open)
            : null,
      );
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

  Future<void> exportRange(String day) => perform(() async {
    final days = await ask(
      '多日薄弱词',
      '以 $day 为截止学习日（含当天），合并本机记录里的顽固词和模糊词。',
      const {'cancel': '取消', '3': '近 3 天', '5': '近 5 天'},
    );
    if (!mounted || days == null || days == 'cancel') return;
    setState(() => status = '正在合并近 $days 天的薄弱词…');
    final result = await tasks.exportRange(day, int.parse(days));
    if (!mounted) return;
    final filename = result['filename'] as String;
    final missing = (result['missing_days'] as List).cast<String>();
    notify('已导出 ${result['word_count']} 个薄弱词。');
    final next = await ask(
      '薄弱词已合并',
      '${result['start_day']} 至 ${result['end_day']} · ${result['word_count']} 个薄弱词\n'
          '$filename${missing.isEmpty ? '' : '\n缺少本机词条缓存：${missing.join('、')}'}',
      const {'close': '关闭', 'folder': '打开导出目录', 'copy': '复制合并 Prompt'},
    );
    if (!mounted) return;
    if (next == 'folder') await open();
    if (next == 'copy') {
      try {
        await Clipboard.setData(
          ClipboardData(text: result['markdown'] as String),
        );
        notify('已复制合并复习 Prompt，可粘贴到常用的 AI。');
      } catch (_) {
        notify('无法复制。请打开导出目录查看 $filename。');
      }
    }
  });

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
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 28),
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
                horizontal: wide ? 24 : 16,
                vertical: 18,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  WorkspaceHeader(
                    title: page == 0
                        ? (d?['today'] == d?['day'] ? '今日复习看板' : '复习看板')
                        : reviewPageLabels[page],
                    mode: widget.mode,
                    onThemeChanged: widget.changeTheme == null
                        ? null
                        : changeTheme,
                  ),
                  const SizedBox(height: 18),
                  ReviewActionBar(
                    day: day,
                    today: d?['today'] as String?,
                    dates: [
                      for (final date in d?['dates'] as List? ?? const [])
                        date as String,
                    ],
                    busy: busy,
                    copied: copied,
                    rangeAvailable: (page == 0 || page == 1) && day != null,
                    copyAvailable: page != exercisePageIndex,
                    syncButton: syncButton(d != null),
                    onDay: busy || d == null ? null : pickDay,
                    onExport: busy || day == null
                        ? null
                        : () => task(DesktopAction.export, day: day),
                    onRange: busy || day == null
                        ? null
                        : () => exportRange(day),
                    onCopy: content.isEmpty ? null : copy,
                    status: status,
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: d == null
                        ? Center(
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  Icons.cloud_off_outlined,
                                  size: 36,
                                  color: Theme.of(context).colorScheme.outline,
                                ),
                                const SizedBox(height: 12),
                                const Text('还没有读取到本机复习记录'),
                                const SizedBox(height: 8),
                                TextButton(
                                  onPressed: initialize,
                                  child: const Text('重新读取本地记录'),
                                ),
                              ],
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
    padding: const EdgeInsets.fromLTRB(0, 8, 0, 28),
    child: switch (page) {
      0 => Overview(d, () => setState(() => page = 2), busy ? null : pickDay),
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
