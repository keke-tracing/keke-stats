# keke-stats

Collect process stats for [`keke`](https://github.com/keke-tracing/keke) traces.

`keke-stats` records low-frequency process metrics as keke counter events, so they show up alongside trace spans in Perfetto or Chrome Tracing.

## Installation

```bash
pip install keke-stats
```

`keke-stats` depends on `keke`. It uses `psutil` where the standard library or platform files do not expose the needed process data directly: RSS on macOS and Windows, and handle counts on Windows.

## Usage

The preferred API is a context manager. It starts a background stats thread on entry and stops it on exit:

```python
import keke
import keke_stats

with open("trace.json", "w") as f:
    with keke.TraceOutput(file=f):
        with keke_stats.collect(period=0.5):
            do_work()
```

You can also choose specific collectors and keep the `Stats` object:

```python
with keke_stats.collect(["cpu", "rss"], period=1.0) as stats:
    do_work()
```

For fire-and-forget usage, start collectors explicitly and stop them when done:

```python
stats = keke_stats.start(["cpu", "fd", "rss"], period=0.5)
try:
    do_work()
finally:
    stats.stop()
```

## Collectors

Available collectors:

| Collector | Events | Description |
| --- | --- | --- |
| `cpu` | `proc_cpu_pct` | Process CPU percentage over the sample period. |
| `fd` | `num_fds` | Number of open file descriptors, or handles on Windows. |
| `rss` | `proc_rss_mib`, `proc_peak_rss_mib` | Current RSS and peak RSS in MiB. |

By default, all collectors are enabled:

```python
keke_stats.DEFAULT_STATS == ("cpu", "fd", "rss")
```

## Notes

Stats are sampled from a single background thread per `Stats` instance. Collectors should be cheap process-local reads. If a collector becomes expensive, make it optional or move it to a dedicated collector implementation.

Peak RSS is the process-lifetime peak, not the peak since tracing started. This is intentional: it remains useful even if stats collection starts after the process has already been running.

## Low-level helpers

The individual helper functions are public for callers that want to record their own counters:

```python
keke_stats.get_fd_count()
keke_stats.get_rss_mib()
keke_stats.get_peak_rss_mib()
```

## Version compatibility

This library supports Python 3.10+.

## License

`keke-stats` is copyright [Tim Hatch](https://timhatch.com/), and licensed under the MIT license. See the `LICENSE` file for details.
