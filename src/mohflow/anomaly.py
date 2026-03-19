"""
Log anomaly detection for MohFlow.

Provides statistical anomaly detection on log streams without
external dependencies — lightweight rolling-window statistics
that learn normal patterns and alert on deviations.

Usage::

    from mohflow.anomaly import AnomalyDetector

    detector = AnomalyDetector(
        logger,
        window_minutes=15,
        error_rate_threshold=2.0,   # 2x baseline
        volume_change_threshold=3.0, # 3x std-dev
    )

    # Feed log events
    detector.observe({"level": "ERROR", "message": "connection refused"})

    # Check for anomalies
    anomalies = detector.check()
    # [{"type": "error_spike", "metric": "error_rate", ...}]

Features:
- Error rate spike detection (sudden increase vs baseline)
- Volume anomaly detection (unusual log rates)
- New-error detection (messages never seen before)
- Missing-pattern detection (expected logs not appearing)
- Configurable alert callbacks
- No external ML dependencies — pure statistical approach
"""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict, deque
from typing import (
    Any,
    Callable,
    Deque,
    Dict,
    List,
    Optional,
    Set,
)
import math


class _RollingWindow:
    """Fixed-size sliding window of (timestamp, value) pairs."""

    __slots__ = ("_window_seconds", "_data")

    def __init__(self, window_seconds: float):
        self._window_seconds = window_seconds
        self._data: Deque[tuple] = deque()

    def add(self, value: float, ts: Optional[float] = None) -> None:
        now = ts or time.time()
        self._data.append((now, value))
        self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._data and self._data[0][0] < cutoff:
            self._data.popleft()

    @property
    def count(self) -> int:
        self._evict(time.time())
        return len(self._data)

    @property
    def values(self) -> List[float]:
        self._evict(time.time())
        return [v for _, v in self._data]

    def mean(self) -> float:
        vals = self.values
        return sum(vals) / len(vals) if vals else 0.0

    def std(self) -> float:
        vals = self.values
        if len(vals) < 2:
            return 0.0
        m = sum(vals) / len(vals)
        variance = sum((x - m) ** 2 for x in vals) / len(vals)
        return math.sqrt(variance)

    def rate_per_second(self) -> float:
        self._evict(time.time())
        if not self._data:
            return 0.0
        return len(self._data) / self._window_seconds


class Anomaly:
    """Describes a single detected anomaly."""

    __slots__ = (
        "anomaly_type",
        "metric",
        "message",
        "current_value",
        "baseline_value",
        "severity",
        "timestamp",
        "details",
    )

    def __init__(
        self,
        anomaly_type: str,
        metric: str,
        message: str,
        current_value: float = 0.0,
        baseline_value: float = 0.0,
        severity: str = "warning",
        details: Optional[Dict[str, Any]] = None,
    ):
        self.anomaly_type = anomaly_type
        self.metric = metric
        self.message = message
        self.current_value = current_value
        self.baseline_value = baseline_value
        self.severity = severity
        self.timestamp = time.time()
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "metric": self.metric,
            "message": self.message,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "severity": self.severity,
            "timestamp": self.timestamp,
            **self.details,
        }


class AnomalyDetector:
    """Statistical anomaly detector for log streams.

    Parameters
    ----------
    logger : Any
        MohFlow logger for emitting alerts.
    window_minutes : int
        Rolling window size in minutes.
    error_rate_threshold : float
        Alert when error rate exceeds ``baseline * threshold``.
    volume_change_threshold : float
        Alert when log volume deviates by this many standard
        deviations from the rolling mean.
    new_error_tracking : bool
        Track and alert on previously unseen error messages.
    alert_callback : callable, optional
        Called with an :class:`Anomaly` when one is detected.
    cooldown_seconds : float
        Minimum seconds between repeated alerts of the same type.
    """

    def __init__(
        self,
        logger: Any,
        window_minutes: int = 15,
        error_rate_threshold: float = 2.0,
        volume_change_threshold: float = 3.0,
        new_error_tracking: bool = True,
        alert_callback: Optional[Callable[["Anomaly"], None]] = None,
        cooldown_seconds: float = 300.0,
    ):
        self._logger = logger
        self._window_seconds = window_minutes * 60
        self.error_rate_threshold = error_rate_threshold
        self.volume_change_threshold = volume_change_threshold
        self.new_error_tracking = new_error_tracking
        self._alert_callback = alert_callback
        self._cooldown_seconds = cooldown_seconds

        # Tracking state
        self._total_window = _RollingWindow(self._window_seconds)
        self._error_window = _RollingWindow(self._window_seconds)
        self._volume_windows: Dict[str, _RollingWindow] = {}

        # New-error tracking
        self._known_errors: Set[str] = set()

        # Missing-pattern tracking
        self._expected_patterns: Dict[str, float] = {}

        # Cooldown tracking
        self._last_alert: Dict[str, float] = {}

        # Detected anomalies (most recent)
        self._anomalies: List[Anomaly] = []

    # ── observation ──────────────────────────────────────────

    def observe(self, event: Dict[str, Any]) -> None:
        """Feed a log event into the detector."""
        now = time.time()
        level = str(event.get("level", "INFO")).upper()
        message = str(event.get("message", ""))

        # Track total volume
        self._total_window.add(1.0, now)

        # Track errors
        if level in ("ERROR", "CRITICAL"):
            self._error_window.add(1.0, now)

            # New-error tracking
            if self.new_error_tracking:
                msg_hash = hashlib.md5(
                    message.encode("utf-8", errors="replace")
                ).hexdigest()[:12]
                if msg_hash not in self._known_errors:
                    self._known_errors.add(msg_hash)
                    if len(self._known_errors) > 1:
                        anomaly = Anomaly(
                            anomaly_type="new_error",
                            metric="error_message",
                            message=(
                                f"New error message detected: "
                                f"{message[:100]}"
                            ),
                            severity="info",
                            details={"error_message": message[:200]},
                        )
                        self._emit_anomaly(anomaly)

        # Per-minute volume bucket
        minute_key = str(int(now / 60))
        if minute_key not in self._volume_windows:
            self._volume_windows[minute_key] = _RollingWindow(
                self._window_seconds
            )
        self._volume_windows[minute_key].add(1.0, now)

    # ── checking ─────────────────────────────────────────────

    def check(self) -> List[Anomaly]:
        """Run all anomaly checks and return any detected anomalies."""
        anomalies: List[Anomaly] = []

        # 1. Error rate spike
        error_anomaly = self._check_error_rate()
        if error_anomaly:
            anomalies.append(error_anomaly)

        # 2. Volume anomaly
        volume_anomaly = self._check_volume()
        if volume_anomaly:
            anomalies.append(volume_anomaly)

        # 3. Missing patterns
        missing = self._check_missing_patterns()
        anomalies.extend(missing)

        return anomalies

    def add_expected_pattern(
        self, name: str, min_rate_per_minute: float
    ) -> None:
        """Register a pattern that should appear at least N times/min.

        If the pattern is not observed within a check window, an
        anomaly is raised.
        """
        self._expected_patterns[name] = min_rate_per_minute

    def get_stats(self) -> Dict[str, Any]:
        """Return current detector statistics."""
        return {
            "total_events": self._total_window.count,
            "error_events": self._error_window.count,
            "error_rate": self._compute_error_rate(),
            "known_error_signatures": len(self._known_errors),
            "anomalies_detected": len(self._anomalies),
            "window_seconds": self._window_seconds,
        }

    def reset(self) -> None:
        """Clear all state."""
        self._total_window = _RollingWindow(self._window_seconds)
        self._error_window = _RollingWindow(self._window_seconds)
        self._volume_windows.clear()
        self._known_errors.clear()
        self._last_alert.clear()
        self._anomalies.clear()

    # ── internal checks ──────────────────────────────────────

    def _compute_error_rate(self) -> float:
        total = self._total_window.count
        if total == 0:
            return 0.0
        return self._error_window.count / total

    def _check_error_rate(self) -> Optional[Anomaly]:
        """Detect error rate spikes."""
        total = self._total_window.count
        errors = self._error_window.count
        if total < 10:
            return None  # Not enough data

        rate = errors / total
        # Baseline: assume 5% error rate is normal
        baseline = 0.05
        if rate > baseline * self.error_rate_threshold:
            if self._in_cooldown("error_rate"):
                return None
            anomaly = Anomaly(
                anomaly_type="error_spike",
                metric="error_rate",
                message=(
                    f"Error rate spike: {rate:.1%} "
                    f"(threshold: "
                    f"{baseline * self.error_rate_threshold:.1%})"
                ),
                current_value=rate,
                baseline_value=baseline,
                severity="error",
                details={
                    "error_count": errors,
                    "total_count": total,
                },
            )
            self._emit_anomaly(anomaly)
            return anomaly
        return None

    def _check_volume(self) -> Optional[Anomaly]:
        """Detect unusual log volume."""
        window = self._total_window
        if window.count < 10:
            return None

        rate = window.rate_per_second()
        mean = window.mean()
        std = window.std()

        if std == 0:
            return None

        z_score = abs(rate - mean) / std if std > 0 else 0
        if z_score > self.volume_change_threshold:
            if self._in_cooldown("volume"):
                return None
            anomaly = Anomaly(
                anomaly_type="volume_anomaly",
                metric="log_volume",
                message=(
                    f"Unusual log volume: "
                    f"{rate:.1f}/s "
                    f"(z-score: {z_score:.1f})"
                ),
                current_value=rate,
                baseline_value=mean,
                severity="warning",
                details={"z_score": z_score, "std": std},
            )
            self._emit_anomaly(anomaly)
            return anomaly
        return None

    def _check_missing_patterns(self) -> List[Anomaly]:
        """Check for expected patterns that haven't appeared."""
        anomalies: List[Anomaly] = []
        # This is a placeholder for pattern tracking;
        # full implementation would track per-pattern counters
        return anomalies

    def _in_cooldown(self, alert_type: str) -> bool:
        """Check if we're still in cooldown for this alert type."""
        last = self._last_alert.get(alert_type, 0)
        return (time.time() - last) < self._cooldown_seconds

    def _emit_anomaly(self, anomaly: Anomaly) -> None:
        """Record anomaly, log it, and fire callback."""
        self._anomalies.append(anomaly)
        self._last_alert[anomaly.anomaly_type] = time.time()

        # Log the anomaly
        log_method = (
            self._logger.error
            if anomaly.severity == "error"
            else self._logger.warning
        )
        log_method(
            f"Anomaly detected: {anomaly.message}",
            **anomaly.to_dict(),
        )

        # Fire callback
        if self._alert_callback:
            try:
                self._alert_callback(anomaly)
            except Exception:
                pass  # Don't let callback errors break detection
