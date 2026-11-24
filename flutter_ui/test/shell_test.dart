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
            return {'data': sample('2026-11-24'), 'export': false};
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
