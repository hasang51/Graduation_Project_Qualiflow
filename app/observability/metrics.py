from __future__ import annotations

from collections import defaultdict
from threading import Lock

_lock = Lock()
_request_counts: dict[tuple[str, str, int], int] = defaultdict(int)
_request_latency_ms: dict[tuple[str, str], list[float]] = defaultdict(list)
_job_counts: dict[str, int] = defaultdict(int)
_worker_success = 0
_worker_failure = 0


def record_request(*, method: str, path: str, status_code: int, duration_ms: float) -> None:
    with _lock:
        _request_counts[(method, path, status_code)] += 1
        _request_latency_ms[(method, path)].append(duration_ms)


def record_job_status(status: str) -> None:
    with _lock:
        _job_counts[status] += 1


def record_worker_success() -> None:
    global _worker_success
    with _lock:
        _worker_success += 1


def record_worker_failure() -> None:
    global _worker_failure
    with _lock:
        _worker_failure += 1


def render_prometheus_metrics() -> str:
    lines: list[str] = []
    with _lock:
        lines.append("# HELP qualiflow_http_requests_total Total HTTP requests")
        lines.append("# TYPE qualiflow_http_requests_total counter")
        for (method, path, status), count in sorted(_request_counts.items()):
            lines.append(
                f'qualiflow_http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}'
            )

        lines.append("# HELP qualiflow_http_request_duration_ms HTTP request latency samples")
        lines.append("# TYPE qualiflow_http_request_duration_ms summary")
        for (method, path), samples in sorted(_request_latency_ms.items()):
            if not samples:
                continue
            total = sum(samples)
            lines.append(
                f'qualiflow_http_request_duration_ms_sum{{method="{method}",path="{path}"}} {total:.4f}'
            )
            lines.append(
                f'qualiflow_http_request_duration_ms_count{{method="{method}",path="{path}"}} {len(samples)}'
            )

        lines.append("# HELP qualiflow_jobs_total Jobs observed by status")
        lines.append("# TYPE qualiflow_jobs_total counter")
        for status, count in sorted(_job_counts.items()):
            lines.append(f'qualiflow_jobs_total{{status="{status}"}} {count}')

        lines.append("# HELP qualiflow_worker_success_total Successful worker runs")
        lines.append("# TYPE qualiflow_worker_success_total counter")
        lines.append(f"qualiflow_worker_success_total {_worker_success}")

        lines.append("# HELP qualiflow_worker_failure_total Failed worker runs")
        lines.append("# TYPE qualiflow_worker_failure_total counter")
        lines.append(f"qualiflow_worker_failure_total {_worker_failure}")

    return "\n".join(lines) + "\n"
