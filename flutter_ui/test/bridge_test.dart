import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:review_ui/bridge.dart';

void main() {
  test(
    'A pending poll and stop request serialize writes, not replies',
    () async {
      final replies = StreamController<String>();
      addTearDown(replies.close);
      final firstFlush = Completer<void>();
      final sent = <String>[];
      final bridge = PythonBridge(
        replies: replies.stream,
        send: (line) async {
          sent.add(line);
          if (sent.length == 1) await firstFlush.future;
        },
      );

      final poll = bridge.call('poll');
      final stop = bridge.call('cancel_sync');
      await Future<void>.delayed(Duration.zero);
      expect(sent.map((line) => jsonDecode(line)['method']), ['poll']);
      firstFlush.complete();
      await Future<void>.delayed(Duration.zero);
      expect(sent.map((line) => jsonDecode(line)['method']), [
        'poll',
        'cancel_sync',
      ]);
      replies.add('{"id":2,"result":true}');
      replies.add('{"id":1,"result":"running"}');
      expect(await poll, 'running');
      expect(await stop, true);
    },
  );

  test('A malformed reply fails in-flight and future requests', () async {
    final replies = StreamController<String>();
    addTearDown(replies.close);
    final bridge = PythonBridge(replies: replies.stream, send: (_) async {});
    final outcome = expectLater(
      bridge.call('poll'),
      throwsA(
        isA<StateError>().having(
          (error) => error.message,
          'message',
          contains('无法读取'),
        ),
      ),
    );
    replies.add('{"id":1,"unexpected":"running"}');
    await outcome;
    await expectLater(bridge.call('poll'), throwsStateError);
  });

  test('A broken write fails pending requests without writing again', () async {
    final replies = StreamController<String>();
    addTearDown(replies.close);
    var writes = 0;
    final bridge = PythonBridge(
      replies: replies.stream,
      send: (_) async {
        writes++;
        throw StateError('broken pipe');
      },
    );

    final first = expectLater(bridge.call('poll'), throwsStateError);
    final second = expectLater(bridge.call('cancel_sync'), throwsStateError);
    await Future.wait([first, second]);
    expect(writes, 1);
  });
}
