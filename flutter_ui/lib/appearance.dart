import 'package:flutter/material.dart';

extension Appearance on ThemeMode {
  String get label => switch (this) {
    ThemeMode.light => '日间模式',
    ThemeMode.dark => '夜间模式',
    ThemeMode.system => '跟随系统',
  };

  IconData get icon => switch (this) {
    ThemeMode.light => Icons.light_mode_outlined,
    ThemeMode.dark => Icons.dark_mode_outlined,
    ThemeMode.system => Icons.brightness_auto_outlined,
  };
}

class ThemeMenu extends StatelessWidget {
  const ThemeMenu({super.key, required this.mode, required this.onChanged});
  final ThemeMode mode;
  final ValueChanged<ThemeMode>? onChanged;

  @override
  Widget build(BuildContext context) => MenuAnchor(
    menuChildren: [
      for (final option in ThemeMode.values)
        RadioMenuButton<ThemeMode>(
          value: option,
          groupValue: mode,
          onChanged: onChanged == null ? null : (_) => onChanged!(option),
          child: Text(option.label),
        ),
    ],
    builder: (context, controller, child) => IconButton.outlined(
      tooltip: '切换主题 · ${mode.label}',
      icon: Icon(mode.icon),
      onPressed: onChanged == null
          ? null
          : () => controller.isOpen ? controller.close() : controller.open(),
    ),
  );
}
