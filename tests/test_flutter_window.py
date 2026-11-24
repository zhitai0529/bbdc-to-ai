from io import StringIO
import json
import unittest
from unittest.mock import Mock

from src.flutter_window import serve


class FlutterWindowTests(unittest.TestCase):
    def test_private_pipe_round_trips_errors_and_closes_when_window_exits(self):
        api = Mock()
        api.initialize.return_value = {'data': {'prompt': '第一行\n第二行'}}
        api.start.side_effect = ValueError('无可用实例')
        requests = StringIO('\n'.join([
            'engine diagnostic',
            json.dumps({'id': 1, 'method': 'initialize'}),
            json.dumps({'id': 2, 'method': 'start', 'args': ['sync']}),
            json.dumps({'id': 3, 'method': '_close'}),
        ]))
        replies = StringIO()
        serve(api, requests, replies)
        output = list(map(json.loads, replies.getvalue().splitlines()))
        self.assertEqual(output[0]['result']['data']['prompt'], '第一行\n第二行')
        self.assertEqual(output[1]['error'], '无可用实例')
        self.assertIn('error', output[2])
        api.start.assert_called_once_with('sync')
        api._close.assert_called_once_with()

    def test_closed_reply_pipe_stops_owned_task(self):
        api = Mock()
        api.poll.return_value = {'status': 'running'}
        replies = Mock()
        replies.flush.side_effect = BrokenPipeError()
        serve(api, StringIO('{"id": 1, "method": "poll"}\n'), replies)
        api._close.assert_called_once_with()
