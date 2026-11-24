import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'bridge.dart';
import 'shell.dart';

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
