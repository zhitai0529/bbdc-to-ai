import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:review_ui/bridge.dart';
import 'package:review_ui/main.dart';

Json sample(String day) => {
  'day': day,
  'today': '2026-11-24',
  'dates': ['2026-11-24', '2026-11-23'],
  'version': '1.4.0',
  'folder': 'test-output',
  'warning': '',
  'prompt': '# 每日提示词',
  'stats': {'total': 4, 'hard': 2, 'fuzzy': 1, 'promoted': 1, 'mastered': 1},
  'sidebar': {'total': 4, 'mastered': 1, 'latest': null},
  'series': [
    {
      'day': day,
      'total': 4,
      'hard': 2,
      'fuzzy': 1,
      'promoted': 1,
      'mastered': 1,
    },
  ],
  'errors': [
    {'word': 'abstract', 'wrong': 1, 'promoted': false},
  ],
  'repeats': [],
  'unknown': [],
  'codes_available': true,
  'window': 7,
};
void main() {
  testWidgets(
    'Theme changes keep the active Markdown draft and sync both controls',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1200, 800);
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.dark;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);

      final saved = <String>[];
      Future<dynamic> host(
        String method, [
        List<dynamic> args = const [],
      ]) async {
        if (method == 'initialize') return {'data': sample('2026-11-24')};
        if (method == 'save_theme') {
          saved.add(args.single as String);
          return null;
        }
        throw UnsupportedError(method);
      }

      await tester.pumpWidget(
        ReviewApp(call: host, initialMode: ThemeMode.light),
      );
      await tester.pumpAndSettle();
      Brightness brightness() =>
          Theme.of(tester.element(find.byType(Scaffold))).brightness;
      expect(brightness(), Brightness.light);

      await tester.tap(find.text('复习预览'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('源码编辑'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '# 未保存草稿');
      await tester.pump();

      await tester.tap(find.byTooltip('切换主题 · 日间模式'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('夜间模式'));
      await tester.pumpAndSettle();
      expect(brightness(), Brightness.dark);
      expect(find.text('# 未保存草稿'), findsOneWidget);
      expect(find.text('有未保存的修改'), findsOneWidget);

      await tester.tap(find.text('MuMu 与设置'));
      await tester.pumpAndSettle();
      final selector = find.byType(SegmentedButton<ThemeMode>);
      expect(tester.widget<SegmentedButton<ThemeMode>>(selector).selected, {
        ThemeMode.dark,
      });
      await tester.tap(find.text('跟随系统'));
      await tester.pumpAndSettle();
      expect(find.byTooltip('切换主题 · 跟随系统'), findsOneWidget);
      expect(brightness(), Brightness.dark);
      tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
      await tester.pumpAndSettle();
      expect(brightness(), Brightness.light);
      expect(saved, ['dark', 'system']);
    },
  );

  for (final width in [860.0, 1200.0, 1500.0]) {
    testWidgets('Native dashboard and preview at width $width', (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = Size(width, 800);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final calls = <String>[];
      var prompt = '# 每日提示词';
      Future<dynamic> host(
        String method, [
        List<dynamic> args = const [],
      ]) async {
        calls.add(method);
        switch (method) {
          case 'initialize':
            final today = sample('2026-11-24');
            today['series'] = [
              {
                'day': '2026-11-23',
                'total': 5,
                'hard': 2,
                'fuzzy': 2,
                'mastered': 1,
                'promoted': null,
                'export_summary': true,
              },
              ...today['series'] as List,
            ];
            return {'data': today, 'export': false};
          case 'start':
            expect(args, ['export']);
            return {'status': 'started', 'message': ''};
          case 'poll':
            return {
              'status': 'exported',
              'message': '离线导出成功',
              'day': '2026-11-24',
            };
          case 'select_day':
            return sample(args.first)..['prompt'] = prompt;
          case 'save_prompt':
            expect(args[1], '# 每日提示词');
            prompt = args[2];
            return null;
          default:
            throw UnsupportedError(method);
        }
      }

      await tester.pumpWidget(ReviewApp(call: host));
      await tester.pumpAndSettle();
      expect(find.text('每日词量与纠结词趋势'), findsOneWidget);
      expect(find.text('较昨日　-1 / —'), findsOneWidget);
      expect(find.text('部分历史日期的统计来自已导出的 Markdown。'), findsOneWidget);
      expect(find.text('每日复习 Prompt'), findsNothing);
      expect(calls, ['initialize']);
      await tester.tap(find.text('导出今日复习'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pumpAndSettle();
      expect(calls, containsAllInOrder(['start', 'poll', 'select_day']));
      await tester.tap(find.text(width >= 1140 ? '复习预览' : '预览'));
      await tester.pumpAndSettle();
      expect(find.text('每日复习 Prompt'), findsOneWidget);
      await tester.tap(find.text('源码编辑'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '# 修改');
      await tester.pump();
      await tester.tap(find.text('保存修改'));
      await tester.pumpAndSettle();
      expect(prompt, '# 修改');
      await tester.tap(find.text(width >= 1140 ? '历史与惯犯词' : '历史').first);
      await tester.pumpAndSettle();
      expect(find.text('跨天反复模糊或答错'), findsOneWidget);
      await tester.tap(find.text(width >= 1140 ? 'MuMu 与设置' : '设置').first);
      await tester.pumpAndSettle();
      await tester.tap(find.text('一键配置 MuMu'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.tap(find.text('返回'));
      await tester.pumpAndSettle();
      expect(calls.where((m) => m == 'start').length, 1);
      expect(tester.takeException(), isNull);
    });
  }
}
