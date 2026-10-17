#!/usr/bin/env python3
"""Executable model of the DP-IN tunnel refcount in DPIN-ROUTER-HOOK-DESIGN.md.

This models the *design*, not kernel code: start/stop only queue work, the
queued work runs later outside the CM lock, hardware toggles on 0->1 / 1->0.
It exists to pin the semantics (overlap, discovery, cancel, failed ACK) so the
real implementation can be reviewed against them. No hardware is touched.
"""
import unittest


class DpinProvider:
    def __init__(self, ack_ok=True):
        self.count = 0
        self.hw_active = False
        self.queue = []          # pending work items, run "outside tb->lock"
        self.ack_ok = ack_ok
        self.hw_log = []

    # called from the CM hook: must only queue
    def tunnel_start(self, tunnel):
        self.queue.append(("start", tunnel))

    def tunnel_stop(self, tunnel):
        # cancel a not-yet-run start for the same tunnel first
        for item in self.queue:
            if item == ("start", tunnel):
                self.queue.remove(item)
                return
        self.queue.append(("stop", tunnel))

    def run_work(self):
        while self.queue:
            op, _ = self.queue.pop(0)
            if op == "start":
                if self.count == 0:
                    if not self._hw(True):
                        return False      # count untouched on failure
                    self.hw_active = True
                self.count += 1
            else:
                if self.count == 0:
                    continue              # stop without start: no underflow
                self.count -= 1
                if self.count == 0:
                    self._hw(False)
                    self.hw_active = False
        return True

    def _hw(self, on):
        self.hw_log.append(on)
        return self.ack_ok if on else True


class RefcountModel(unittest.TestCase):
    def test_single_tunnel(self):
        p = DpinProvider()
        p.tunnel_start("t1"); p.run_work()
        self.assertTrue(p.hw_active)
        p.tunnel_stop("t1"); p.run_work()
        self.assertFalse(p.hw_active)
        self.assertEqual(p.hw_log, [True, False])

    def test_replacement_overlap_does_not_glitch_hardware(self):
        p = DpinProvider()
        p.tunnel_start("old"); p.run_work()
        p.tunnel_start("new"); p.run_work()      # new created before old torn down
        p.tunnel_stop("old"); p.run_work()
        self.assertTrue(p.hw_active)
        self.assertEqual(p.count, 1)
        self.assertEqual(p.hw_log, [True])       # never toggled off/on

    def test_stop_before_work_ran_cancels_start(self):
        p = DpinProvider()
        p.tunnel_start("t1")
        p.tunnel_stop("t1")                      # torn down inside the ACK window
        p.run_work()
        self.assertEqual(p.hw_log, [])
        self.assertEqual(p.count, 0)

    def test_stop_without_start_does_not_underflow(self):
        p = DpinProvider()
        p.tunnel_stop("never-started"); p.run_work()
        self.assertEqual(p.count, 0)
        self.assertFalse(p.hw_active)

    def test_failed_ack_leaves_state_consistent_and_retryable(self):
        p = DpinProvider(ack_ok=False)
        p.tunnel_start("t1")
        self.assertFalse(p.run_work())
        self.assertEqual((p.count, p.hw_active), (0, False))
        p.ack_ok = True
        p.tunnel_start("t1"); p.run_work()
        self.assertEqual((p.count, p.hw_active), (1, True))

    def test_discovered_tunnel_needs_explicit_start(self):
        # Boot-time discovery does not call tb_dp_activate(); the design
        # requires the discovery path to call tunnel_start too.
        p = DpinProvider()
        p.tunnel_start("discovered"); p.run_work()
        p.tunnel_stop("discovered"); p.run_work()
        self.assertEqual(p.hw_log, [True, False])


if __name__ == "__main__":
    unittest.main()
