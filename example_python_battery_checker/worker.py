"""Background thread that owns the DMM session.

The GUI sends commands; the worker sends back events on a queue:
  ("status", text) ("live", volts) ("result", stamp, Measurement, Assessment)
  ("error", text) ("busy", bool)
"""
import queue
import threading
import time

from .dmm import Dmm, DmmError

from .analysis import Thresholds, assess
from .measure import TestSettings, quick_read, run_test


class DmmWorker(threading.Thread):
    def __init__(self, resource: str, events: queue.Queue, poll_s: float = 0.4):
        super().__init__(daemon=True)
        self.resource = resource
        self.events = events
        self.poll_s = poll_s
        self.commands: queue.Queue = queue.Queue()
        self.monitoring = False
        self._dmm: Dmm | None = None

    # Commands (called from the GUI thread)
    def test(self, settings: TestSettings, thresholds: Thresholds):
        self.commands.put(("test", settings, thresholds))

    def set_monitoring(self, on: bool):
        self.commands.put(("monitor", on))

    def set_resource(self, resource: str):
        self.commands.put(("resource", resource))

    def quit(self):
        self.commands.put(("quit",))

    # Thread body
    def _ensure_dmm(self) -> Dmm:
        if self._dmm is None:
            self.events.put(("status", f"Opening DMM {self.resource}…"))
            self._dmm = Dmm(self.resource)
            self.events.put(("status", f"DMM {self.resource} ready"))
        return self._dmm

    def _close_dmm(self):
        if self._dmm:
            try:
                self._dmm.close()
            finally:
                self._dmm = None

    def _fail(self, e: Exception):
        self._close_dmm()  # reopen cleanly on the next command
        self.events.put(("error", str(e)))

    def run(self):
        try:
            while True:
                try:
                    cmd = self.commands.get(timeout=self.poll_s if self.monitoring else None)
                except queue.Empty:
                    cmd = None
                if cmd:
                    kind = cmd[0]
                    if kind == "quit":
                        break
                    if kind == "monitor":
                        self.monitoring = cmd[1]
                    elif kind == "resource":
                        self._close_dmm()
                        self.resource = cmd[1]
                    elif kind == "test":
                        self._run_test(cmd[1], cmd[2])
                    continue
                if self.monitoring:
                    try:
                        self.events.put(("live", quick_read(self._ensure_dmm())))
                    except (DmmError, OSError) as e:
                        self.monitoring = False
                        self._fail(e)
        finally:
            self._close_dmm()

    def _run_test(self, settings: TestSettings, thresholds: Thresholds):
        self.events.put(("busy", True))
        try:
            m = run_test(self._ensure_dmm(), settings,
                         progress=lambda msg: self.events.put(("status", msg)))
            self.events.put(("result", time.strftime("%Y-%m-%d %H:%M:%S"), m, assess(m, thresholds)))
            self.events.put(("status", "Test complete"))
        except (DmmError, OSError) as e:
            self._fail(e)
        finally:
            self.events.put(("busy", False))
