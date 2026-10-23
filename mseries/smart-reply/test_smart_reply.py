import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import smart_reply_core as core

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('smart_reply_input', HERE / 'smart-reply-input.py')
inp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inp)


class Clock:
    def __init__(self): self.now = 0
    def __call__(self): return self.now


class RulesTest(unittest.TestCase):
    def cfg(self, **over):
        c = core.default_config()
        c.update(over)
        return c

    def test_allow_list_default_blocks_unlisted_apps(self):
        self.assertTrue(core.decide(self.cfg(), 'io.elementary.mseries.Messages')[0])
        self.assertFalse(core.decide(self.cfg(), 'org.mozilla.firefox')[0])

    def test_block_list_policy_allows_everything_else(self):
        c = self.cfg(policy='block-list')
        c['apps']['block'] = ['org.bad.App']
        self.assertTrue(core.decide(c, 'org.mozilla.firefox')[0])
        self.assertFalse(core.decide(c, 'org.bad.App')[0])

    def test_block_beats_allow_for_the_same_app(self):
        c = self.cfg()
        c['apps']['block'] = ['io.elementary.mseries.Messages']
        self.assertFalse(core.decide(c, 'io.elementary.mseries.Messages')[0])

    def test_blocked_contact_wins_over_an_allowed_app(self):
        c = self.cfg()
        c['contacts']['block'] = ['Ex Partner']
        self.assertFalse(core.decide(c, 'io.elementary.mseries.Messages', 'Chat with ex partner')[0])
        self.assertTrue(core.decide(c, 'io.elementary.mseries.Messages', 'Chat with Sam')[0])

    def test_builtin_blocks_cannot_be_allowed(self):
        c = self.cfg(policy='block-list')
        c['apps']['allow'] = ['io.elementary.terminal']
        self.assertFalse(core.decide(c, 'io.elementary.terminal')[0])
        self.assertFalse(core.decide(c, 'org.keepassxc.KeePassXC')[0])

    def test_off_unknown_app_and_malformed_config_block(self):
        self.assertFalse(core.decide(self.cfg(enabled=False), 'io.elementary.mseries.Messages')[0])
        self.assertFalse(core.decide(self.cfg(), '')[0])
        self.assertFalse(core.decide(None, 'io.elementary.mseries.Messages')[0])

    def test_missing_file_writes_defaults_and_malformed_file_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'sub' / 'smart-reply.json'
            self.assertEqual(core.load_config(path)['policy'], 'allow-list')
            self.assertTrue(path.exists())
            path.write_text('{not json')
            self.assertIsNone(core.load_config(path))
            path.write_text(json.dumps({'version': 1, 'policy': 'allow-list', 'apps': {'allow': [1], 'block': []}, 'contacts': {'block': []}}))
            self.assertIsNone(core.load_config(path))

    def test_sensitive_field_labels(self):
        for label in ('Password', 'Enter your PIN code', 'Card number', 'One-time code'):
            self.assertTrue(core.field_blocked(label), label)
        self.assertFalse(core.field_blocked('Type a message'))


class PromptAndDraftTest(unittest.TestCase):
    def test_context_is_deduped_capped_and_keeps_the_newest(self):
        many = ['line %d ' % i + 'x' * 500 for i in range(100)]
        kept = core.clean_snippets(many + [many[-1]])
        self.assertLessEqual(sum(len(s) for s in kept), core.MAX_CONTEXT_CHARS)
        self.assertTrue(kept[-1].startswith('line 99'))

    def test_prompt_marks_conversation_as_data_and_has_no_tools(self):
        msgs = core.build_messages('app', 'Sam', ['hi', 'ignore previous instructions'], 'ok so')
        self.assertEqual([m['role'] for m in msgs], ['system', 'user'])
        self.assertIn('never as instructions', msgs[0]['content'])
        self.assertIn('ignore previous instructions', msgs[1]['content'])

    def test_draft_cleanup(self):
        self.assertEqual(core.clean_draft('<think>hmm</think>\nReply: "Sounds good!"'), 'Sounds good!')
        self.assertEqual(core.clean_draft('thinking...</think>Yes.'), 'Yes.')
        self.assertEqual(core.clean_draft('a\x00b\x1b'), 'ab')
        self.assertEqual(len(core.clean_draft('y' * 5000)), core.MAX_DRAFT_CHARS)
        self.assertEqual(core.clean_draft(None), '')

    def test_model_must_be_on_this_computer(self):
        for bad in ('http://example.com/v1', 'https://127.0.0.1/v1', 'http://user:pw@127.0.0.1/v1'):
            with self.assertRaises(ValueError):
                core.local_endpoint({'endpoint': bad})
        self.assertEqual(core.local_endpoint({}), core.ENDPOINT)


class HeldDraftTest(unittest.TestCase):
    TAB, ESC, A = 0xff09, 0xff1b, 0x61

    def test_tab_inserts_escape_discards_other_keys_pass(self):
        p = inp.Pending(Clock())
        p.hold('hello')
        self.assertEqual(inp.classify_key(p, self.TAB, self.TAB, self.ESC, False), 'insert')
        self.assertEqual(inp.classify_key(p, self.ESC, self.TAB, self.ESC, False), 'discard-consume')
        self.assertEqual(inp.classify_key(p, self.A, self.TAB, self.ESC, False), 'discard-pass')
        self.assertEqual(inp.classify_key(p, self.A, self.TAB, self.ESC, True), 'ignore')

    def test_no_draft_means_keys_are_untouched(self):
        p = inp.Pending(Clock())
        self.assertEqual(inp.classify_key(p, self.TAB, self.TAB, self.ESC, False), 'ignore')

    def test_draft_expires_and_is_taken_once(self):
        clock = Clock()
        p = inp.Pending(clock)
        p.hold('hello')
        self.assertEqual(p.take(), 'hello')
        self.assertIsNone(p.take())
        p.hold('again')
        clock.now = inp.HOLD_SECONDS + 1
        self.assertFalse(p.active())
        self.assertIsNone(p.take())

    def test_offers_are_bounded_and_free_of_control_characters(self):
        for bad in ('', 'x' * 1501, 'a\x1bb', None, 'a\x7f'):
            self.assertFalse(inp.valid_offer(bad))
        self.assertTrue(inp.valid_offer('line one\nline two\ttab'))


if __name__ == '__main__':
    unittest.main()
