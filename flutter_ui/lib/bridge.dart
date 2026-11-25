import 'dart:async';
import 'dart:convert';
import 'dart:io';

typedef Json = Map<String, dynamic>;
typedef HostCall =
    Future<dynamic> Function(String method, [List<dynamic> args]);

class PythonBridge {
  PythonBridge({Stream<String>? replies, Future<void> Function(String)? send})
    : _send = send ?? _write {
    (replies ?? stdin.transform(utf8.decoder).transform(const LineSplitter()))
        .listen(
          _receive,
          onDone: _disconnect,
          onError: (Object error) => _disconnect(),
        );
  }

  final Future<void> Function(String) _send;
  final _pending = <int, Completer<dynamic>>{};
  Future<void> _writes = Future<void>.value();
  var _id = 0;
  bool _closed = false;

  static Future<void> _write(String line) async {
    stdout.add(utf8.encode('$line\n'));
    await stdout.flush();
  }

  void _receive(String line) {
    if (_closed) return;
    try {
      final reply = jsonDecode(line);
      if (reply is! Json ||
          reply['id'] is! int ||
          (reply.containsKey('error')
              ? reply['error'] is! String
              : !reply.containsKey('result'))) {
        throw const FormatException('Invalid bridge reply');
      }
      final request = _pending.remove(reply['id']);
      if (reply.containsKey('error')) {
        request?.completeError(StateError(reply['error']));
      } else {
        request?.complete(reply['result']);
      }
    } on FormatException {
      _disconnect('本地后台返回了无法读取的结果。请重开助手。');
    }
  }

  void _disconnect([String message = '本地后台已关闭。请重开助手。']) {
    _closed = true;
    for (final c in _pending.values) {
      c.completeError(StateError(message));
    }
    _pending.clear();
  }

  Future<dynamic> call(String method, [List<dynamic> args = const []]) async {
    if (_closed) throw StateError('本地后台已关闭。');
    final id = ++_id;
    final line = jsonEncode({'id': id, 'method': method, 'args': args});
    final completer = Completer<dynamic>();
    _pending[id] = completer;
    // Polling and the stop action can write to the same pipe at the same time.
    _writes = _writes
        .then((_) async {
          if (!_closed) await _send(line);
        })
        .catchError((Object error) {
          _disconnect('无法连接本地后台。请重开助手。');
        });
    return completer.future;
  }
}
