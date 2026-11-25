import 'dart:async';
import 'dart:ui' show AppExitResponse;

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
  'review_level': 'postgrad',
  'exercise_types': [
    {'id': 'main_clause', 'label': '找主干', 'description': '找出主语与谓语。'},
    {'id': 'cloze', 'label': '语境填空', 'description': '在句子中选择合适的词。'},
  ],
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
    'Exercises use the selected options and keep daily review separate',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(860, 800);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final requests = <List<dynamic>>[];
      Future<dynamic> host(
        String method, [
        List<dynamic> args = const [],
      ]) async {
        switch (method) {
          case 'initialize':
            return {
              'data': {...sample('2026-11-24'), 'review_level': 'cet6'},
            };
          case 'export_exercise':
            requests.add(args);
            if (args.last == 'main_clause') {
              throw StateError('当天没有词条缓存。');
            }
            return {
              'filename': '2026-11-24_bbdc_exercise_cet4_cloze.md',
              'markdown': '# 今日练习',
              'word_count': 3,
            };
          default:
            throw UnsupportedError(method);
        }
      }

      await tester.pumpWidget(ReviewApp(call: host));
      await tester.pumpAndSettle();
      await tester.tap(find.text('练习'));
      await tester.pumpAndSettle();
      expect(find.text('分档练习'), findsOneWidget);
      expect(find.text('复制全部内容'), findsNothing);
      await tester.tap(find.text('生成练习 Markdown'));
      await tester.pumpAndSettle();
      expect(requests.single, ['2026-11-24', 'cet6', 'main_clause']);
      expect(find.text('当天没有词条缓存。'), findsOneWidget);
      expect(find.text('复制练习提示词'), findsNothing);

      await tester.tap(find.text('四级'));
      await tester.tap(find.text('语境填空'));
      await tester.pumpAndSettle();
      expect(find.text('在句子中选择合适的词。'), findsOneWidget);
      await tester.tap(find.text('生成练习 Markdown'));
      await tester.pumpAndSettle();
      expect(requests.last, ['2026-11-24', 'cet4', 'cloze']);
      expect(find.text('候选词 3 个'), findsOneWidget);
      expect(
        find.text('2026-11-24_bbdc_exercise_cet4_cloze.md'),
        findsOneWidget,
      );
      expect(find.text('复制练习提示词'), findsOneWidget);

      await tester.tap(find.text('预览'));
      await tester.pumpAndSettle();
      expect(find.text('复制练习提示词'), findsNothing);
      await tester.tap(find.text('练习'));
      await tester.pumpAndSettle();
      expect(find.text('复制练习提示词'), findsOneWidget);
      expect(
        tester
            .widget<ChoiceChip>(find.widgetWithText(ChoiceChip, '语境填空'))
            .selected,
        isTrue,
      );
      expect(requests, hasLength(2));

      await tester.tap(find.text('找主干'));
      await tester.pumpAndSettle();
      expect(find.text('复制练习提示词'), findsNothing);
      await tester.tap(find.text('预览'));
      await tester.pumpAndSettle();
      expect(find.text('复制全部内容'), findsOneWidget);
      expect(find.text('每日复习 Prompt'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('Changing the study date drops a pending exercise preview', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1200, 800);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final export = Completer<Json>();
    var started = 0;
    Future<dynamic> host(String method, [List<dynamic> args = const []]) async {
      switch (method) {
        case 'initialize':
          return {'data': sample('2026-11-24')};
        case 'export_exercise':
          started++;
          return export.future;
        case 'select_day':
          return sample(args.single as String);
        default:
          throw UnsupportedError(method);
      }
    }

    await tester.pumpWidget(ReviewApp(call: host));
    await tester.pumpAndSettle();
    await tester.tap(find.text('分档练习'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('生成练习 Markdown'));
    await tester.pump();
    expect(started, 1);
    expect(find.text('正在生成…'), findsOneWidget);
    tester
        .widget<DropdownButton<String>>(find.byType(DropdownButton<String>))
        .onChanged!('2026-11-23');
    await tester.pumpAndSettle();
    export.complete({
      'filename': 'wrong-date.md',
      'markdown': '# 旧日期的练习',
      'word_count': 3,
    });
    await tester.pumpAndSettle();
    expect(find.textContaining('学习日 2026-11-23'), findsOneWidget);
    expect(find.text('wrong-date.md'), findsNothing);
    expect(find.text('复制练习提示词'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Review difficulty loads and updates after a successful save', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1200, 800);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final saved = <String>[];
    Future<dynamic> host(String method, [List<dynamic> args = const []]) async {
      switch (method) {
        case 'initialize':
          return {
            'data': {...sample('2026-11-24'), 'review_level': 'cet6'},
          };
        case 'save_review_level':
          final selection = args.single as String;
          if (selection == 'postgrad') throw StateError('无法保存复习难度。');
          saved.add(selection);
          return null;
        default:
          throw UnsupportedError(method);
      }
    }

    SegmentedButton<String> selector() => tester.widget(
      find.byWidgetPredicate((widget) => widget is SegmentedButton<String>),
    );
    await tester.pumpWidget(ReviewApp(call: host));
    await tester.pumpAndSettle();
    await tester.tap(find.text('MuMu 与设置'));
    await tester.pumpAndSettle();
    expect(selector().selected, {'cet6'});

    await tester.tap(find.text('四级'));
    await tester.pumpAndSettle();
    expect(saved, ['cet4']);
    expect(selector().selected, {'cet4'});
    expect(find.textContaining('下次导出时生效'), findsWidgets);

    await tester.tap(find.text('考研'));
    await tester.pumpAndSettle();
    expect(selector().selected, {'cet4'});
    expect(find.text('无法保存复习难度。'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'MuMu setup discloses requirements and shows the backend diagnostic and next step',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1200, 800);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final calls = <String>[];
      const guidance =
          '当前是 Android 12。请在 MuMu 多开器中启动 Android 15 模拟器，再点「一键配置 MuMu」。';
      Future<dynamic> host(
        String method, [
        List<dynamic> args = const [],
      ]) async {
        calls.add(method);
        switch (method) {
          case 'initialize':
            return {'data': sample('2026-11-24')};
          case 'start':
            expect(args, ['setup']);
            return {'status': 'started'};
          case 'poll':
            return {
              'status': 'error',
              'reason': 'android_unsupported',
              'recovery': ['download'],
              'message': guidance,
            };
          case 'download_mumu':
            return null;
          default:
            throw UnsupportedError(method);
        }
      }

      await tester.pumpWidget(ReviewApp(call: host));
      await tester.pumpAndSettle();
      await tester.tap(find.text('MuMu 与设置'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('一键配置 MuMu'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.textContaining('5.11.8 x86'), findsAtLeastNWidgets(1));
      expect(calls, ['initialize']);
      await tester.tap(find.text('开始配置'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 300));
      final dialog = find.byType(AlertDialog);
      expect(
        find.descendant(of: dialog, matching: find.text(guidance)),
        findsOneWidget,
      );
      await tester.tap(
        find.descendant(of: dialog, matching: find.text('打开 MuMu 官网')),
      );
      await tester.pumpAndSettle();
      expect(calls, ['initialize', 'start', 'poll', 'download_mumu']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'A failed MuMu sync keeps the selected date and unsaved review draft',
    (tester) async {
      tester.view.devicePixelRatio = 1;
      tester.view.physicalSize = const Size(1200, 800);
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      const day = '2026-11-23';
      final calls = <String>[];
      Future<dynamic> host(
        String method, [
        List<dynamic> args = const [],
      ]) async {
        calls.add(method);
        switch (method) {
          case 'initialize':
            return {'data': sample(day)};
          case 'start':
            expect(args, ['sync']);
            return {'status': 'started'};
          case 'poll':
            return {
              'status': 'error',
              'reason': 'android_unsupported',
              'message': '请启动 Android 15 实例。',
            };
          default:
            throw UnsupportedError(method);
        }
      }

      await tester.pumpWidget(ReviewApp(call: host));
      await tester.pumpAndSettle();
      await tester.tap(find.text('复习预览'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('源码编辑'));
      await tester.pumpAndSettle();
      const draft = '# 当前复习草稿';
      await tester.enterText(find.byType(TextField), draft);
      await tester.pump();
      await tester.tap(find.text('同步 MuMu'));
      await tester.pump(const Duration(milliseconds: 350));
      await tester.pump(const Duration(milliseconds: 350));
      final dialog = find.byType(AlertDialog);
      expect(
        find.descendant(of: dialog, matching: find.text('请启动 Android 15 实例。')),
        findsOneWidget,
      );
      await tester.tap(find.descendant(of: dialog, matching: find.text('关闭')));
      await tester.pumpAndSettle();
      expect(calls, ['initialize', 'start', 'poll']);
      expect(find.text(draft), findsOneWidget);
      expect(find.text('有未保存的修改'), findsOneWidget);
      expect(find.widgetWithText(Chip, day), findsOneWidget);
    },
  );

  testWidgets('The sync button stops once and allows another sync', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1200, 800);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const day = '2026-11-23';
    final calls = <String>[];
    final stop = Completer<Json>();
    var stopped = false;
    var starts = 0;
    Future<dynamic> host(String method, [List<dynamic> args = const []]) async {
      calls.add(method);
      switch (method) {
        case 'initialize':
          return {'data': sample(day)};
        case 'start':
          expect(args, ['sync']);
          starts++;
          return {'status': 'started'};
        case 'cancel_sync':
          expect(args, isEmpty);
          return stop.future;
        case 'poll':
          if (starts == 2) {
            return {'status': 'no_records', 'message': '暂无新记录。'};
          }
          return {'status': stopped ? 'cancelled' : 'running'};
        default:
          throw UnsupportedError(method);
      }
    }

    await tester.pumpWidget(ReviewApp(call: host));
    await tester.pumpAndSettle();
    await tester.tap(find.text('复习预览'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('源码编辑'));
    await tester.pumpAndSettle();
    const draft = '# 未保存的复习草稿';
    await tester.enterText(find.byType(TextField), draft);
    await tester.pump();

    await tester.tap(find.text('同步 MuMu'));
    await tester.pump();
    expect(find.text('停止同步'), findsOneWidget);
    final close = WidgetsBinding.instance.handleRequestAppExit();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text('有尚未保存的复习修改。'), findsOneWidget);
    await tester.tap(find.text('继续编辑'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(await close, AppExitResponse.cancel);
    await tester.tap(find.text('停止同步'));
    await tester.pump();
    final stopping = find.ancestor(
      of: find.text('正在停止…'),
      matching: find.byWidgetPredicate((widget) => widget is FilledButton),
    );
    expect(tester.widget<FilledButton>(stopping).onPressed, isNull);
    await tester.tap(stopping);
    expect(calls.where((name) => name == 'cancel_sync'), hasLength(1));

    stop.complete({'status': 'cancelling'});
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    expect(stopping, findsOneWidget);
    stopped = true;
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();
    expect(find.byType(AlertDialog), findsNothing);
    expect(find.textContaining('同步已停止'), findsWidgets);
    expect(find.text(draft), findsOneWidget);
    expect(find.widgetWithText(Chip, day), findsOneWidget);

    await tester.tap(find.text('同步 MuMu'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();
    expect(starts, 2);
    expect(calls, isNot(contains('select_day')));
    expect(tester.takeException(), isNull);
  });

  testWidgets('A late cancel acknowledgement leaves a completed sync visible', (
    tester,
  ) async {
    tester.view.devicePixelRatio = 1;
    tester.view.physicalSize = const Size(1200, 800);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final stop = Completer<Json>();
    final calls = <String>[];
    Future<dynamic> host(String method, [List<dynamic> args = const []]) async {
      calls.add(method);
      switch (method) {
        case 'initialize':
          return {'data': sample('2026-11-23')};
        case 'start':
          return {'status': 'started'};
        case 'cancel_sync':
          return stop.future;
        case 'poll':
          return {
            'status': 'exported',
            'day': '2026-11-24',
            'message': '已同步到今日记录。',
          };
        case 'select_day':
          return sample(args.single as String);
        default:
          throw UnsupportedError(method);
      }
    }

    await tester.pumpWidget(ReviewApp(call: host));
    await tester.pumpAndSettle();
    await tester.tap(find.text('同步 MuMu'));
    await tester.pump();
    await tester.tap(find.text('停止同步'));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.pumpAndSettle();
    expect(calls, ['initialize', 'start', 'cancel_sync', 'poll', 'select_day']);
    stop.complete({'status': 'idle'});
    await tester.pumpAndSettle();
    expect(find.text('已同步到今日记录。'), findsWidgets);
    expect(find.text('同步 MuMu'), findsOneWidget);
    expect(find.text('正在读取同步结果…'), findsNothing);
    expect(tester.takeException(), isNull);
  });

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
