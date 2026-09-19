import time
from typing import cast
from unittest.mock import call, Mock, patch

import pytest

import keke_stats
from keke_stats import (
    Collector,
    CpuCollector,
    FdCollector,
    get_fd_count,
    get_peak_rss_mib,
    get_rss_mib,
    RssCollector,
    start,
    Stats,
)


def test_cpu_collector() -> None:
    with patch("keke_stats.time.process_time", side_effect=[1, 2, 2]), patch(
        "keke_stats.time.time", side_effect=[0, 0.5, 1.0]
    ), patch("keke_stats.keke.kcount") as kc:
        collector = CpuCollector()
        collector.sample()
        collector.sample()
        collector.sample()

        kc.assert_has_calls(
            [
                call("proc_cpu_pct", 200),
                call("proc_cpu_pct", 0),
            ],
        )


def test_get_fd() -> None:
    assert get_fd_count() >= 3


def test_fd_collector() -> None:
    with patch("keke_stats.get_fd_count", side_effect=[3, 4, 5]), patch(
        "keke_stats.keke.kcount"
    ) as kc:
        collector = FdCollector()
        collector.sample()
        collector.sample()
        collector.sample()

        kc.assert_has_calls(
            [
                call("num_fds", 3),
                call("num_fds", 4),
                call("num_fds", 5),
            ],
        )


def test_get_rss_mib() -> None:
    assert get_rss_mib() > 0


def test_get_peak_rss_mib() -> None:
    assert get_peak_rss_mib() > 0


def test_rss_collector() -> None:
    with patch("keke_stats.get_rss_mib", side_effect=[11, 12, 13]), patch(
        "keke_stats.get_peak_rss_mib", side_effect=[21, 22, 23]
    ), patch("keke_stats.keke.kcount") as kc:
        collector = RssCollector()
        collector.sample()
        collector.sample()
        collector.sample()

        kc.assert_has_calls(
            [
                call("proc_rss_mib", 11),
                call("proc_peak_rss_mib", 21),
                call("proc_rss_mib", 12),
                call("proc_peak_rss_mib", 22),
                call("proc_rss_mib", 13),
                call("proc_peak_rss_mib", 23),
            ],
        )


def test_start_and_stop() -> None:
    real_sleep = time.sleep
    with patch("keke_stats.get_fd_count", side_effect=[3, 4, 5]), patch(
        "keke_stats.keke.kcount"
    ) as kc:
        stats = start(["fd"], period=0)
        thread = stats._thread
        assert thread is not None
        assert thread.name == "keke-stats"

        while len(kc.mock_calls) < 3:
            real_sleep(0.01)
        stats.stop()

        kc.assert_has_calls(
            [
                call("num_fds", 3),
                call("num_fds", 4),
                call("num_fds", 5),
            ],
        )
        assert stats._thread is None


def test_context_manager_stops() -> None:
    stats = Stats([])
    with stats as entered:
        assert entered is stats
    assert stats._thread is None


def test_stop_before_start() -> None:
    stats = Stats([])
    stats.stop()
    assert stats._thread is None


def test_run_stops_on_event() -> None:
    stats = Stats(["fd"], period=0)
    with patch("keke_stats.get_fd_count", return_value=3), patch(
        "keke_stats.keke.kcount"
    ) as kc:
        stats._stop.set()
        stats._run()
        kc.assert_called_once_with("num_fds", 3)


def test_run_stops_on_stop_iteration() -> None:
    stats = Stats([])
    collector = Mock()
    collector.sample.side_effect = StopIteration
    stats.collectors = [cast(Collector, collector)]
    stats._run()
    collector.sample.assert_called_once_with()


def test_collect() -> None:
    stats = keke_stats.collect(["fd"], period=1.25)
    assert stats.which == ("fd",)
    assert stats.period == 1.25
    assert isinstance(stats.collectors[0], FdCollector)


def test_unknown_stat() -> None:
    with pytest.raises(ValueError, match="unknown keke stat"):
        keke_stats.start(["wat"])


def test_fd_platforms() -> None:
    with patch("keke_stats.sys.platform", "darwin"), patch(
        "keke_stats.os.listdir", return_value=["0", "1"]
    ):
        assert get_fd_count() == 2

    with patch("keke_stats._psutil") as psutil, patch(
        "keke_stats.sys.platform", "win32"
    ):
        psutil.Process.return_value.num_handles.return_value = 7
        assert get_fd_count() == 7


def test_rss_platforms() -> None:
    with patch("keke_stats._psutil") as psutil:
        mem = psutil.Process.return_value.memory_info.return_value
        mem.rss = 22 * 1048576
        mem.peak_wset = 33 * 1048576

        with patch("keke_stats.sys.platform", "darwin"):
            assert get_rss_mib() == 22

        with patch("keke_stats.sys.platform", "win32"):
            assert get_rss_mib() == 22
            assert get_peak_rss_mib() == 33

    with patch("keke_stats.sys.platform", "darwin"), patch(
        "keke_stats._resource.getrusage"
    ) as getrusage:
        getrusage.return_value.ru_maxrss = 44 * 1048576
        assert get_peak_rss_mib() == 44
