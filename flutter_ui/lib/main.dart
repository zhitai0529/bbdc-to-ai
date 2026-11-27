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
          seedColor: const Color(0xff1e65ff),
          brightness: brightness,
        ).copyWith(
          primary: Color(dark ? 0xffaec6ff : 0xff1e65ff),
          onPrimary: Color(dark ? 0xff102f63 : 0xffffffff),
          primaryContainer: Color(dark ? 0xff234b88 : 0xffdfe9ff),
          surface: Color(dark ? 0xff111a29 : 0xfff8fafc),
          surfaceContainerLowest: Color(dark ? 0xff0f172a : 0xfff8fafc),
          surfaceContainerLow: Color(dark ? 0xff16202f : 0xffffffff),
          surfaceContainer: Color(dark ? 0xff1c2737 : 0xfff1f5f9),
          surfaceContainerHigh: Color(dark ? 0xff263449 : 0xffe7edf4),
          surfaceContainerHighest: Color(dark ? 0xff324158 : 0xffdfe7f0),
        );
    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      fontFamily: 'Microsoft YaHei UI',
      fontFamilyFallback: const ['Segoe UI', 'Microsoft YaHei', 'sans-serif'],
      scaffoldBackgroundColor: scheme.surfaceContainerLowest,
      focusColor: scheme.primary.withValues(alpha: .1),
      hoverColor: scheme.primary.withValues(alpha: .045),
      navigationRailTheme: NavigationRailThemeData(
        backgroundColor: scheme.surfaceContainerLow,
        indicatorColor: scheme.primaryContainer,
        indicatorShape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        selectedIconTheme: IconThemeData(color: scheme.onPrimaryContainer),
        unselectedIconTheme: IconThemeData(color: scheme.onSurfaceVariant),
        selectedLabelTextStyle: TextStyle(
          color: scheme.onSurface,
          fontWeight: FontWeight.w700,
        ),
        unselectedLabelTextStyle: TextStyle(color: scheme.onSurfaceVariant),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: scheme.surfaceContainerLowest,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      dividerTheme: DividerThemeData(
        color: scheme.outlineVariant.withValues(alpha: .75),
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
