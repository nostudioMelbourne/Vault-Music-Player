"""Coalesce bursts of UI events without waiting for the burst to end."""


class ThrottledCallback:
    """Run at most one queued callback per interval, using its latest state."""

    def __init__(self, scheduler, callback, interval_ms=16):
        self.scheduler = scheduler
        self.callback = callback
        self.interval_ms = interval_ms
        self.pending_job = None

    def request(self, *_args):
        if self.pending_job is None:
            self.pending_job = self.scheduler.after(self.interval_ms, self.run)

    def run(self):
        self.pending_job = None
        self.callback()
