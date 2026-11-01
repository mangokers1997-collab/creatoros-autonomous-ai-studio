"""Resource-aware admission control for local production workloads.

Uses only the Python standard library. Linux /proc metrics are preferred;
unsupported metrics are reported as unknown rather than fabricated.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _memory_available_mb() -> float | None:
    try:
        with open("/proc/meminfo", "r", encoding="ascii") as handle:
            values = {}
            for line in handle:
                key, _, rest = line.partition(":")
                if key in {"MemAvailable", "MemFree"}:
                    values[key] = int(rest.strip().split()[0])
            kb = values.get("MemAvailable", values.get("MemFree"))
            return round(kb / 1024, 1) if kb is not None else None
    except (OSError, ValueError, IndexError):
        pass
    try:
        import psutil  # optional dependency
        return round(psutil.virtual_memory().available / (1024 * 1024), 1)
    except (ImportError, OSError, AttributeError):
        return None


def _cpu_load_per_core() -> float | None:
    try:
        loads = os.getloadavg()
        cores = os.cpu_count() or 1
        return round(float(loads[0]) / cores, 3)
    except (AttributeError, OSError, TypeError, ValueError):
        try:
            import psutil
            return round(psutil.cpu_percent(interval=0.15) / 100, 3)
        except (ImportError, OSError, AttributeError):
            return None


def resource_snapshot() -> dict:
    media_root = Path(os.getenv("CREATOROS_MEDIA_DIR", "media"))
    try:
        media_root.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(media_root)
        disk_free_mb = round(disk.free / (1024 * 1024), 1)
        disk_total_mb = round(disk.total / (1024 * 1024), 1)
    except OSError:
        disk_free_mb = None
        disk_total_mb = None
    memory = _memory_available_mb()
    cpu = _cpu_load_per_core()
    mode = os.getenv("CREATOROS_RESOURCE_MODE", "balanced").lower()
    if mode not in {"conservative", "balanced", "performance"}:
        mode = "balanced"
    profiles = {
        "conservative": {"memory_mb": 2048, "disk_mb": 4096, "cpu_load_per_core": 0.60},
        "balanced": {"memory_mb": 1024, "disk_mb": 2048, "cpu_load_per_core": 0.85},
        "performance": {"memory_mb": 512, "disk_mb": 1024, "cpu_load_per_core": 1.25},
    }
    thresholds = profiles[mode]
    overrides = {
        "memory_mb": "CREATOROS_MIN_FREE_MEMORY_MB",
        "disk_mb": "CREATOROS_MIN_FREE_DISK_MB",
        "cpu_load_per_core": "CREATOROS_MAX_CPU_LOAD_PER_CORE",
    }
    for key, env_name in overrides.items():
        raw = os.getenv(env_name)
        if raw:
            try:
                thresholds[key] = max(0.1, float(raw))
            except ValueError:
                pass
    checks = {
        "memory": {"value": memory, "minimum": thresholds["memory_mb"],
                   "passed": memory is None or memory >= thresholds["memory_mb"]},
        "disk": {"value": disk_free_mb, "minimum": thresholds["disk_mb"],
                 "passed": disk_free_mb is None or disk_free_mb >= thresholds["disk_mb"]},
        "cpu": {"value": cpu, "maximum": thresholds["cpu_load_per_core"],
                "passed": cpu is None or cpu <= thresholds["cpu_load_per_core"]},
    }
    blocked = [name for name, check in checks.items() if not check["passed"]]
    # Unknown readings are surfaced, but do not permanently deadlock unsupported hosts.
    unknown = [name for name, check in checks.items() if check["value"] is None]
    enabled = os.getenv("CREATOROS_RESOURCE_GUARD_ENABLED", "true").lower() in {"1", "true", "yes"}
    return {
        "enabled": enabled,
        "mode": mode,
        "can_start_job": not enabled or not blocked,
        "status": "blocked" if enabled and blocked else ("monitoring_limited" if unknown else "ready"),
        "cpu_load_per_core": cpu,
        "cpu_cores": os.cpu_count() or 1,
        "available_memory_mb": memory,
        "free_disk_mb": disk_free_mb,
        "disk_total_mb": disk_total_mb,
        "thresholds": thresholds,
        "checks": checks,
        "blocked_reasons": blocked if enabled else [],
        "unknown_metrics": unknown,
        "policy": "Admission control only; running jobs are not forcibly interrupted.",
    }
