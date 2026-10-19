"""One on-demand speech model; never free it during load, capture or flush."""
from contextlib import contextmanager
import threading
import time


class ModelHeadroom(Exception):
    pass


class LazyModel:
    def __init__(self, factory, idle_seconds=60, clock=time.monotonic):
        self.factory = factory
        self.idle_seconds = idle_seconds
        self.clock = clock
        self.model = None
        self.last_used = 0
        self.lock = threading.Lock()

    @property
    def loaded(self):
        return self.model is not None

    @contextmanager
    def use(self, admit):
        # A second caller must not wait and start a second utterance later.
        if not self.lock.acquire(blocking=False):
            raise RuntimeError('The speech model is already in use')
        try:
            if not admit(256 * 1024**2 if self.loaded else 1024**3):
                raise ModelHeadroom('Speech is waiting for desktop headroom')
            if self.model is None:
                self.model = self.factory()
            yield self.model
        finally:
            self.last_used = self.clock()
            self.lock.release()

    def trim(self, force=False):
        if not self.lock.acquire(blocking=False):
            return False
        try:
            if self.model is None or (not force and self.clock() - self.last_used < self.idle_seconds):
                return False
            self.model.close()
            self.model = None
            return True
        finally:
            self.lock.release()
