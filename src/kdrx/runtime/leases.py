"""Lease renewal and cooperative cancellation across process boundaries."""

from __future__ import annotations

import threading

from kdrx.runtime.store import StateConflict


class LeaseKeeper:
    def __init__(
        self, store, lease: dict, *, seconds: float = 300, interval: float | None = None
    ):
        self.store, self.lease, self.seconds = store, lease, seconds
        self.interval = interval if interval is not None else min(1.0, seconds / 3)
        if self.interval <= 0 or self.interval >= seconds:
            raise ValueError(
                "heartbeat interval must be positive and shorter than the lease"
            )
        self.cancelled = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._renew, name=f"lease-{lease['attempt_id']}", daemon=True
        )

    def start(self):
        self._thread.start()
        return self

    def _renew(self):
        while not self._stop.wait(self.interval):
            try:
                self.store.heartbeat(self.lease, self.seconds)
            except Exception:
                # Storage uncertainty cannot authorize continued provider work.
                self.cancelled.set()
                return

    def check(self):
        if self.cancelled.is_set():
            raise StateConflict("task lease revoked or renewal failed")

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=35)
