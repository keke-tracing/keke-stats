"""Optional process stats for keke traces."""

import os
import sys
import time
from threading import Event, Thread
from types import TracebackType
from typing import Any, Iterable, Optional, Protocol, Type

import keke

try:
    from ._version import __version__
except ImportError:  # pragma: no cover
    __version__ = "dev"

_resource: Any
try:
    import resource as _resource
except ImportError:  # pragma: no cover
    _resource = None

try:
    import psutil as _psutil
except ImportError:  # pragma: no cover
    _psutil = None

AVAILABLE_STATS = ("cpu", "fd", "rss")
DEFAULT_STATS = ("cpu", "fd", "rss")


class Collector(Protocol):
    def sample(self) -> None:  # pragma: no cover
        pass


class CpuCollector:
    def __init__(self) -> None:
        self.prev_ts: Optional[float] = None
        self.prev_process_time: Optional[float] = None

    def sample(self) -> None:
        ts = time.time()
        process_time = time.process_time()
        if self.prev_ts is not None:
            assert self.prev_process_time is not None
            elapsed = ts - self.prev_ts
            if elapsed > 0:
                keke.kcount(
                    "proc_cpu_pct",
                    int(100 * (process_time - self.prev_process_time) / elapsed),
                )

        self.prev_ts = ts
        self.prev_process_time = process_time


class FdCollector:
    def sample(self) -> None:
        keke.kcount("num_fds", get_fd_count())


class RssCollector:
    def sample(self) -> None:
        keke.kcount("proc_rss_mib", get_rss_mib())
        keke.kcount("proc_peak_rss_mib", get_peak_rss_mib())


COLLECTORS: dict[str, type[Collector]] = {
    "cpu": CpuCollector,
    "fd": FdCollector,
    "rss": RssCollector,
}


class Stats:
    def __init__(self, which: Iterable[str] = DEFAULT_STATS, period: float = 0.5):
        self.which = tuple(which)
        self.period = period
        self.collectors = [_get_collector(stat) for stat in self.which]
        self._stop = Event()
        self._thread: Optional[Thread] = None

    def start(self) -> "Stats":
        if self._thread is not None:
            return self
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True, name="keke-stats")
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.period * 2, 0.1))
            self._thread = None

    def _run(self) -> None:
        try:
            while True:  # pragma: no branch
                for collector in self.collectors:
                    collector.sample()
                if self._stop.wait(self.period):
                    return
        except StopIteration:
            pass  # for testing

    def __enter__(self) -> "Stats":
        return self.start()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.stop()


def collect(which: Iterable[str] = DEFAULT_STATS, period: float = 0.5) -> Stats:
    return Stats(which, period)


def start(which: Iterable[str] = DEFAULT_STATS, period: float = 0.5) -> Stats:
    return Stats(which, period).start()


def _get_collector(stat: str) -> Collector:
    try:
        return COLLECTORS[stat]()
    except KeyError:
        raise ValueError(f"unknown keke stat: {stat!r}") from None


def _require_psutil() -> Any:
    if _psutil is None:  # pragma: no cover
        raise RuntimeError("psutil is required for this stat on this platform")
    return _psutil


def get_fd_count() -> int:
    if sys.platform == "win32":
        psutil = _require_psutil()
        return psutil.Process().num_handles()  # type: ignore[attr-defined, no-any-return]
    elif sys.platform == "darwin":
        return len(os.listdir("/dev/fd"))
    elif sys.platform == "linux":
        return len(os.listdir("/proc/self/fd"))
    else:  # pragma: no cover
        return 0


def get_rss_mib() -> int:
    if sys.platform == "win32":
        psutil = _require_psutil()
        return int(psutil.Process().memory_info().rss / 1048576)  # type: ignore[attr-defined]
    elif sys.platform == "linux":
        with open("/proc/self/statm") as f:
            resident_pages = int(f.read().split()[1])
        return int(resident_pages * os.sysconf("SC_PAGE_SIZE") / 1048576)
    elif sys.platform == "darwin":
        psutil = _require_psutil()
        return int(psutil.Process().memory_info().rss / 1048576)  # type: ignore[attr-defined]
    else:  # pragma: no cover
        return 0


def get_peak_rss_mib() -> int:
    if sys.platform == "win32":
        psutil = _require_psutil()
        return int(psutil.Process().memory_info().peak_wset / 1048576)  # type: ignore[attr-defined]
    elif _resource is None:  # pragma: no cover
        return 0

    peak_rss = _resource.getrusage(_resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return int(peak_rss / 1048576)
    return int(peak_rss / 1024)


__all__ = [
    "AVAILABLE_STATS",
    "DEFAULT_STATS",
    "Collector",
    "CpuCollector",
    "FdCollector",
    "RssCollector",
    "Stats",
    "collect",
    "get_fd_count",
    "get_peak_rss_mib",
    "get_rss_mib",
    "start",
    "__version__",
]
