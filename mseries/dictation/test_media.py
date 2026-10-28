#!/usr/bin/env python3
"""Save/restore logic of dictation_media against a fake busctl/pw-dump/wpctl (no PipeWire or D-Bus needed)."""
import json, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dictation_media import MediaQuiet, RESUME_WINDOW, parse_streams, stream_key

ME = 4242  # our daemon: its children are the pw-play chimes


class FakeSystem:
    def __init__(self):
        self.players = {}   # bus name -> PlaybackStatus
        self.nodes = {}     # id -> dict(serial, props, muted, state)
        self.setting = 'true'
        self.calls = []

    def add_stream(self, node_id, app, pid, muted=False, state='running', **extra):
        props = {'media.class': 'Stream/Output/Audio', 'object.serial': 1000 + node_id,
                 'application.name': app, 'application.process.id': pid, **extra}
        self.nodes[node_id] = {'props': props, 'muted': muted, 'state': state}

    def dump(self):
        return json.dumps([{'id': i, 'type': 'PipeWire:Interface:Node',
                            'info': {'state': n['state'], 'props': n['props'],
                                     'params': {'Props': [{'mute': n['muted'], 'volume': 1.0}]}}}
                           for i, n in self.nodes.items()])

    def run(self, cmd, timeout=2):
        self.calls.append(cmd)
        if cmd[:2] == ['busctl', '--user'] and 'list' in cmd:
            return ''.join(f'{n} 100 app user :1.{i} user@1000.service - -\n' for i, n in enumerate(self.players))
        if 'get-property' in cmd:
            name = cmd[cmd.index('get-property') + 1]
            return f's "{self.players[name]}"\n' if name in self.players else None
        if 'call' in cmd:
            name, method = cmd[cmd.index('call') + 1], cmd[-1]
            if name not in self.players:
                return None
            self.players[name] = {'Pause': 'Paused', 'Play': 'Playing'}[method]
            return ''
        if cmd == ['pw-dump']:
            return self.dump()
        if cmd[:2] == ['wpctl', 'set-mute']:
            node = self.nodes.get(int(cmd[2]))
            if node is None:
                return None
            node['muted'] = cmd[3] == '1'
            return ''
        if cmd[:2] == ['wpctl', 'settings']:
            if len(cmd) == 4:
                self.setting = cmd[3]
                return ''
            return f'Value: {self.setting}\n'
        raise AssertionError(cmd)


class MediaQuietTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'media.json'
        self.sys = FakeSystem()
        self.now = 1000.0
        self.media = self.make()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self):
        return MediaQuiet(run=self.sys.run, path=self.path, sleep=lambda s: None,
                          clock=lambda: self.now, is_own=lambda pid: pid in (ME, 5555))

    def test_pauses_and_mutes_only_what_was_playing_then_restores_it(self):
        s = self.sys
        s.players = {'org.mpris.MediaPlayer2.spotify': 'Playing', 'org.mpris.MediaPlayer2.vlc': 'Paused'}
        s.add_stream(10, 'Brave', 300)                    # audible: mute
        s.add_stream(11, 'Firefox', 301, muted=True)      # owner already muted: leave
        s.add_stream(12, 'mpv', 302, state='idle')        # silent: leave
        s.add_stream(13, 'pw-play', 5555, **{'media.role': 'Notification'})  # our chime: leave

        did = self.media.quiet()
        self.assertEqual(did, {'paused': ['org.mpris.MediaPlayer2.spotify'], 'muted': [10]})
        self.assertEqual(s.players['org.mpris.MediaPlayer2.spotify'], 'Paused')
        self.assertEqual({i: n['muted'] for i, n in s.nodes.items()}, {10: True, 11: True, 12: False, 13: False})
        self.assertEqual(s.setting, 'false', 'WirePlumber must not remember our temporary mute')
        self.assertTrue(self.path.exists())

        done = self.media.restore()
        self.assertEqual(done, {'unmuted': [10], 'resumed': ['org.mpris.MediaPlayer2.spotify']})
        self.assertEqual(s.players, {'org.mpris.MediaPlayer2.spotify': 'Playing', 'org.mpris.MediaPlayer2.vlc': 'Paused'})
        self.assertEqual({i: n['muted'] for i, n in s.nodes.items()}, {10: False, 11: True, 12: False, 13: False})
        self.assertEqual(s.setting, 'true')
        self.assertFalse(self.path.exists())

    def test_restore_is_idempotent_and_cheap_without_state(self):
        self.assertEqual(self.media.restore(), {'unmuted': [], 'resumed': []})
        self.assertEqual(self.sys.calls, [], 'no state file: no subprocesses at all')

    def test_nothing_playing_touches_nothing(self):
        self.sys.add_stream(10, 'Brave', 300, state='idle')
        self.assertEqual(self.media.quiet(), {'paused': [], 'muted': []})
        self.assertEqual(self.sys.setting, 'true')
        self.media.restore()
        self.assertFalse(self.path.exists())

    def test_crash_recovery_from_state_file(self):
        s = self.sys
        s.players = {'org.mpris.MediaPlayer2.spotify': 'Playing'}
        s.add_stream(10, 'Brave', 300)
        self.media.quiet()
        # the daemon dies here; systemd starts a new one a few seconds later
        self.now += 5
        done = self.make().restore()
        self.assertEqual(done, {'unmuted': [10], 'resumed': ['org.mpris.MediaPlayer2.spotify']})
        self.assertEqual(s.setting, 'true')

    def test_stale_crash_unmutes_but_does_not_restart_music(self):
        s = self.sys
        s.players = {'org.mpris.MediaPlayer2.spotify': 'Playing'}
        s.add_stream(10, 'Brave', 300)
        self.media.quiet()
        self.now += RESUME_WINDOW + 1
        self.assertEqual(self.make().restore(), {'unmuted': [10], 'resumed': []})
        self.assertEqual(s.players['org.mpris.MediaPlayer2.spotify'], 'Paused')

    def test_user_choices_during_dictation_win(self):
        s = self.sys
        s.players = {'org.mpris.MediaPlayer2.spotify': 'Playing'}
        s.add_stream(10, 'Brave', 300)
        self.media.quiet()
        s.players['org.mpris.MediaPlayer2.spotify'] = 'Stopped'  # the owner stopped it meanwhile
        del s.nodes[10]                                           # the stream went away
        s.add_stream(10, 'Other', 301, muted=True)                # id reused by an unrelated muted stream
        s.nodes[10]['props']['object.serial'] = 2000
        self.assertEqual(self.media.restore(), {'unmuted': [], 'resumed': []})
        self.assertTrue(s.nodes[10]['muted'], 'a different stream with a reused id is not ours to unmute')

    def test_state_written_before_acting(self):
        s = self.sys
        s.players = {'org.mpris.MediaPlayer2.spotify': 'Playing'}
        s.add_stream(10, 'Brave', 300)
        real = s.run
        seen = []
        def spy(cmd, timeout=2):
            if 'Pause' in cmd or cmd[:2] == ['wpctl', 'set-mute']:
                seen.append(json.loads(self.path.read_text()))
            return real(cmd, timeout)
        self.media.run = spy
        self.media.quiet()
        self.assertIn('org.mpris.MediaPlayer2.spotify', seen[0]['paused'])
        self.assertEqual([m['serial'] for m in seen[-1]['muted']], [1010])
        self.assertEqual(seen[-1]['setting'], 'true')


class ParseTest(unittest.TestCase):
    def test_skips_capture_filter_chain_and_appless_nodes(self):
        dump = json.dumps([
            {'id': 1, 'type': 'PipeWire:Interface:Node', 'info': {'state': 'running', 'props': {
                'media.class': 'Stream/Input/Audio', 'application.process.id': 9}}},
            {'id': 2, 'type': 'PipeWire:Interface:Node', 'info': {'state': 'running', 'props': {
                'media.class': 'Stream/Output/Audio', 'node.link-group': 'filter-chain-1-20', 'application.process.id': 9}}},
            {'id': 3, 'type': 'PipeWire:Interface:Node', 'info': {'state': 'running', 'props': {
                'media.class': 'Stream/Output/Audio', 'node.name': 'effect_output.j314-convolver'}}},
            {'id': 4, 'type': 'PipeWire:Interface:Node', 'info': {'state': 'running', 'props': {
                'media.class': 'Stream/Output/Audio', 'application.process.id': '77', 'object.serial': 44,
                'application.name': 'Brave', 'media.role': 'Music'}}},
            {'id': 5, 'type': 'PipeWire:Interface:Node', 'info': {'state': 'running', 'props': {
                'media.class': 'Stream/Output/Audio', 'node.passive': True, 'client.id': 90}}},
            # a native client (pw-play): the pid lives on the client object
            {'id': 90, 'type': 'PipeWire:Interface:Client', 'info': {'props': {'application.process.id': 88}}},
            {'id': 6, 'type': 'PipeWire:Interface:Node', 'info': {'state': 'idle', 'props': {
                'media.class': 'Stream/Output/Audio', 'client.id': 90, 'object.serial': 45,
                'application.name': 'pw-play', 'node.name': 'pw-play'}, 'params': {'Props': [{'mute': True}]}}},
        ])
        self.assertEqual(parse_streams(dump), [
            {'id': 4, 'serial': 44, 'key': 'Output/Audio:media.role:Music', 'pid': 77, 'muted': False, 'running': True},
            {'id': 6, 'serial': 45, 'key': 'Output/Audio:application.name:pw-play', 'pid': 88, 'muted': True, 'running': False}])
        self.assertEqual(parse_streams('not json'), [])
        self.assertEqual(parse_streams(None), [])

    def test_key_matches_wireplumber_order(self):
        self.assertEqual(stream_key({'media.class': 'Stream/Output/Audio', 'application.name': 'Brave',
                                     'application.id': 'mpv'}), 'Output/Audio:application.id:mpv')


if __name__ == '__main__':
    unittest.main()
