import 'dart:async';
import 'dart:convert';
import 'dart:io';

typedef Json = Map<String, dynamic>;
typedef HostCall =
    Future<dynamic> Function(String method, [List<dynamic> args]);

class PythonBridge {
  final _pending = <int, Completer<dynamic>>{};
  var _id = 0;
  bool _closed = false;

  PythonBridge() {
    stdin
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(
          (line) {
            final reply = jsonDecode(line) as Json;
            final c = _pending.remove(reply['id']);
            if (reply.containsKey('error')) {
              c?.completeError(StateError(reply['error']));
            } else {
              c?.complete(reply['result']);
            }
          },
          onDone: _disconnect,
          onError: (Object error) => _disconnect(),
        );
  }

  void _disconnect() {
    _closed = true;
    for (final c in _pending.values) {
      c.completeError(StateError('本地后台已关闭。'));
    }
    _pending.clear();
  }

  Future<dynamic> call(String method, [List<dynamic> args = const []]) async {
    if (_closed) throw StateError('本地后台已关闭。');
    final id = ++_id;
    final completer = Completer<dynamic>();
    _pending[id] = completer;
    stdout.add(
      utf8.encode(
        '${jsonEncode({'id': id, 'method': method, 'args': args})}\n',
      ),
    );
    await stdout.flush();
    return completer.future;
  }
}
