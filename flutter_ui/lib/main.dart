import 'dart:async';
import 'dart:io';
import 'dart:ui' show AppExitResponse;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'appearance.dart';
import 'bridge.dart';
import 'overview.dart';
import 'pages.dart';

void main(List<String> args) {
  WidgetsFlutterBinding.ensureInitialized();
  final mode = ThemeMode.values.firstWhere(
    (mode) => args.contains('--theme=${mode.name}'),
    orElse: () => ThemeMode.system,
  );
  runApp(
    ReviewApp(
      call: PythonBridge().call,
      smoke: args.contains('--smoke'),
      initialMode: mode,
    ),
  );
}

class ReviewApp extends StatefulWidget {
  const ReviewApp({
    super.key,
    required this.call,
    this.smoke = false,
    this.initialMode = ThemeMode.system,
  });
  final HostCall call;
  final bool smoke;
  final ThemeMode initialMode;

  @override
  State<ReviewApp> createState() => _ReviewAppState();
}

class _ReviewAppState extends State<ReviewApp> {
  late ThemeMode mode = widget.initialMode;
  bool saving = false;

  Future<void> changeTheme(ThemeMode next) async {
    if (mode == next || saving) return;
    final previous = mode;
    setState(() {
      mode = next;
      saving = true;
    });
    try {
      await widget.call('save_theme', [next.name]);
    } catch (_) {
      if (mounted) setState(() => mode = previous);
      rethrow;
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  ThemeData theme(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final scheme =
        ColorScheme.fromSeed(
          seedColor: const Color(0xff0e58c8),
          brightness: brightness,
        ).copyWith(
          primary: Color(dark ? 0xffaec6ff : 0xff0e58c8),
          onPrimary: Color(dark ? 0xff002e6c : 0xffffffff),
          primaryContainer: Color(dark ? 0xff004397 : 0xffd8e2ff),
          surface: Color(dark ? 0xff1a2130 : 0xfffbf8fd),
          surfaceContainerLow: Color(dark ? 0xff202a3a : 0xfff5f2f7),
          surfaceContainer: Color(dark ? 0xff232d40 : 0xffefecf1),
          surfaceContainerHighest: dark ? const Color(0xff354155) : null,
        );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'Microsoft YaHei UI',
      fontFamilyFallback: const ['Segoe UI', 'Microsoft YaHei', 'sans-serif'],
      scaffoldBackgroundColor: scheme.surface,
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: scheme.surfaceContainer,
        indicatorColor: scheme.primaryContainer,
      ),
    );
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    debugShowCheckedModeBanner: false,
    title: '不背单词复习助手',
    theme: theme(Brightness.light),
    darkTheme: theme(Brightness.dark),
    themeMode: mode,
    locale: const Locale('zh', 'CN'),
    supportedLocales: const [Locale('zh', 'CN')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    home: Shell(
      call: widget.call,
      smoke: widget.smoke,
      mode: mode,
      changeTheme: saving ? null : changeTheme,
    ),
  );
}

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
  Json? data;
  bool busy = false, copied = false;
  int page = 0;
  String status = '正在读取本机记录…', adb = '尚未检查', root = '尚未检查';
  final logs = <String>[];
  final drafts = <String, ({String original, String text})>{};
  String get draftKey => '${data?['folder']}\n${data?['day']}';
  String get content => drafts[draftKey]?.text ?? data?['prompt'] ?? '';
  static const labels = ['复习总览', '复习预览', '历史与惯犯词', 'MuMu 与设置'];
  static const icons = [
    Icons.dashboard_outlined,
    Icons.menu_book_outlined,
    Icons.history,
    Icons.tune,
  ];
  late final AppLifecycleListener lifecycle;
  @override
  void initState() {
    super.initState();
    lifecycle = AppLifecycleListener(
      onExitRequested: () async {
        if (drafts.isNotEmpty && !busy && mounted) {
          final answer = await ask('关闭复习助手？', '有尚未保存的复习修改。', {
            'stay': '继续编辑',
            'exit': '放弃修改并关闭',
          });
          if (answer != 'exit') return AppExitResponse.cancel;
        }
        return AppExitResponse.exit;
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) => initialize());
  }

  @override
  void dispose() {
    lifecycle.dispose();
    super.dispose();
  }

  Future<void> initialize() async {
    try {
      final r = await widget.call('initialize') as Json;
      if (!mounted) return;
      setState(() {
        data = r['data'];
        status =
            r['warning'] ??
            (data!['warning'] != ''
                ? data!['warning']
                : data!['stats'] == null
                ? '当前学习日暂无本机记录。'
                : '本地记录已载入。');
      });
      if (widget.smoke) {
        await WidgetsBinding.instance.endOfFrame;
        final nextMode = widget.mode == ThemeMode.dark
            ? ThemeMode.light
            : ThemeMode.dark;
        await widget.changeTheme?.call(nextMode);
        await widget.call('select_day', [data!['day']]);
        if (!mounted) return;
        setState(() => page = 1);
        await WidgetsBinding.instance.endOfFrame;
        exit(0);
      }
      if (r['export'] == true) await task('export');
    } catch (e) {
      if (widget.smoke) exit(1);
      notify('$e');
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
      notify('$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> refresh(String? day) async {
    final fresh = await widget.call('select_day', [day]) as Json;
    if (mounted) setState(() => data = fresh);
    if (fresh['warning'] != '') notify(fresh['warning']);
  }

  Future<String?> ask(String title, String body, Map<String, String> choices) =>
      showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: Text(body),
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
      await widget.call('open_folder');
    } catch (e) {
      notify('$e');
    }
  }

  Future<void> copy() async {
    try {
      await Clipboard.setData(ClipboardData(text: content));
      if (!mounted) return;
      setState(() => copied = true);
      notify('已复制，可直接发给 AI');
      await Future<void>.delayed(const Duration(seconds: 2));
      if (mounted) setState(() => copied = false);
    } catch (e) {
      notify('$e');
    }
  }

  void log(String text) {
    final time = TimeOfDay.now().format(context);
    logs.add('$time  $text');
    if (logs.length > 160) logs.removeAt(0);
  }

  Future<void> task(String action) => perform(() async {
    if (action == 'setup' &&
        await ask(
              '一键配置 MuMu',
              '将检查 ADB、Root 和 App 版本。开启 Root 可能需要重启当前实例，请先结束正在进行的学习。',
              {'back': '返回', 'go': '开始配置'},
            ) !=
            'go')
      return;
    var r = await widget.call('start', [action]) as Json;
    if (r['status'] == 'choose') {
      final choice = await ask('查找 MuMu 安装位置', '已安装时，可右键 MuMu 图标查看安装目录。', {
        'back': '返回',
        'download': '官网下载',
        'locate': '选择安装目录',
      });
      if (choice == 'download') {
        await widget.call('download_mumu');
        return;
      }
      if (choice != 'locate' || await widget.call('locate_manager') != true)
        return;
      r = await widget.call('start', [action]) as Json;
    }
    if (r['status'] != 'started') throw StateError('未能定位 MuMu，请重新选择安装目录。');
    final label = {
      'sync': '正在同步 MuMu 学习记录…',
      'setup': '正在配置 MuMu…',
      'export': '正在用本机记录导出今日复习…',
    }[action]!;
    setState(() {
      status = label;
      log(label);
      if (r['message'] != '') log(r['message']);
    });
    var seen = 0;
    while (mounted) {
      await Future<void>.delayed(const Duration(milliseconds: 280));
      if (!mounted) return;
      final result = await widget.call('poll') as Json;
      if (!mounted) return;
      final lines = (result['lines'] as List? ?? []).cast<String>();
      if (lines.length > seen)
        setState(() {
          for (final line in lines.skip(seen)) {
            log(line);
          }
          seen = lines.length;
        });
      if (result['status'] == 'running') continue;
      var msg = result['message'] as String? ?? '任务已结束。';
      if (result['status'] == 'app_missing')
        msg += ' 请在该 MuMu 实例中安装并登录不背单词后重试。';
      if (result['status'] == 'configured')
        msg = '配置完成。请在 MuMu 中登录不背单词，再点「同步 MuMu」。';
      if (result['day'] != null) await refresh(result['day']);
      if (!mounted) return;
      if (action == 'setup') {
        final stamp = TimeOfDay.now().format(context);
        adb = lines.contains('ADB 连接通过。') ? '通过 $stamp' : '未确认';
        root = lines.contains('Root 检查通过。') ? '通过 $stamp' : '未确认';
      }
      log(msg);
      notify(msg);
      if (action == 'setup' ||
          ['app_missing', 'mumu_missing'].contains(result['status'])) {
        await ask('MuMu 检查结果', msg, {'ok': '知道了'});
      }
      break;
    }
  });
  Future<void> change() => perform(() async {
    if (await widget.call('change_folder') == true) {
      await refresh(null);
      notify('已更新导出目录。');
    }
  });
  Future<void> save() => perform(() async {
    final key = draftKey, draft = drafts[key], day = data!['day'];
    if (draft == null) return;
    await widget.call('save_prompt', [day, draft.original, draft.text]);
    final current = drafts[key];
    if (current == draft) {
      drafts.remove(key);
    } else if (current != null) {
      drafts[key] = (original: draft.text, text: current.text);
    }
    await refresh(day);
    notify('修改已保存到复习文件。');
  });
  void edit(String text) {
    final current = data!['prompt'] as String;
    setState(() {
      if (text == current) {
        drafts.remove(draftKey);
      } else {
        drafts[draftKey] = (
          original: drafts[draftKey]?.original ?? current,
          text: text,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final d = data,
        c = Theme.of(context).colorScheme,
        wide = MediaQuery.sizeOf(context).width >= 1140;
    final side = d?['sidebar'] as Json?, total = side?['total'] ?? 0;
    final pct = total == 0 ? null : (side!['mastered'] ?? 0) / total;
    return Scaffold(
      body: Row(
        children: [
          Container(
            width: wide ? 204 : 92,
            color: c.surfaceContainer,
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 20,
                  ),
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
                        onDestinationSelected: (i) => setState(() => page = i),
                        destinations: [
                          for (var i = 0; i < 4; i++)
                            NavigationRailDestination(
                              icon: Icon(icons[i]),
                              label: Text(
                                wide ? labels[i] : ['总览', '预览', '历史', '设置'][i],
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
                    onPressed: d == null ? null : open,
                    icon: const Icon(Icons.folder_open),
                    label: Text(wide ? '导出目录' : '目录'),
                  ),
                ),
                const SizedBox(height: 8),
              ],
            ),
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
                            : labels[page],
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
                          FilledButton.icon(
                            onPressed: busy || d == null
                                ? null
                                : () => task('sync'),
                            icon: const Icon(Icons.sync),
                            label: const Text('同步 MuMu'),
                          ),
                          FilledButton.tonalIcon(
                            onPressed: busy || d == null
                                ? null
                                : () => task('export'),
                            icon: const Icon(Icons.download_outlined),
                            label: const Text('导出今日复习'),
                          ),
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
                    child: Text(
                      status,
                      style: Theme.of(context).textTheme.bodySmall,
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
                        : SingleChildScrollView(
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
                                dirty: drafts.containsKey(draftKey),
                              ),
                              2 => HistoryPage(d),
                              _ => SettingsPage(
                                data: d,
                                logs: logs,
                                adb: adb,
                                root: root,
                                setup: busy ? null : () => task('setup'),
                                change: busy ? null : change,
                                open: open,
                                mode: widget.mode,
                                changeTheme: widget.changeTheme == null
                                    ? null
                                    : changeTheme,
                              ),
                            },
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
}
