"""Bounded English grammar suggestions; raw streaming words stay separate."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Request:
    generation: int
    source: str


class LiveEnglishReview:
    def __init__(self, interval=3.0, settle=.8):
        self.interval, self.settle = interval, settle
        self.generation = 0
        self.source = ''
        self.options = None
        self.session = False
        self.capturing = False
        self.changed_at = 0
        self.last_start = -float('inf')
        self.inflight = None
        self.cached = None
        self.done = None
        self.failed = None

    def observe(self, source, enabled, previews, capturing, eligible, now):
        options = (enabled, previews)
        if options != self.options or not source.startswith(self.source):
            self.generation += 1
            self.cached = self.done = self.failed = None
            self.session = False
        if source != self.source:
            self.changed_at = now
            if enabled and capturing and eligible: self.session = True
            self.done = None
        self.source, self.options, self.capturing = source, options, capturing
        if not enabled or not source.strip() or len(source) > 4000: self.session = False

    def take(self, now):
        if not self.session or self.inflight is not None: return None
        identity = (self.generation, self.source)
        if self.done == identity or self.failed == identity: return None
        if self.cached and self.cached[0] == identity:
            if not self.capturing: self.done = identity
            return None
        if self.capturing and (not self.options[1] or now - self.last_start < self.interval): return None
        if not self.capturing and now - self.changed_at < self.settle: return None
        self.inflight = Request(self.generation, self.source)
        self.last_start = now
        return self.inflight

    def finish(self, request, proposal=None, error=None):
        if request != self.inflight: return None
        self.inflight = None
        if request.generation != self.generation or not self.session or not self.source.startswith(request.source): return None
        identity = (request.generation, request.source)
        if error:
            self.failed = identity
            return None
        self.cached = (identity, proposal)
        final = request.source == self.source and not self.capturing
        if final: self.done = identity
        return proposal, final

    @property
    def finalized(self):
        return self.done == (self.generation, self.source)
