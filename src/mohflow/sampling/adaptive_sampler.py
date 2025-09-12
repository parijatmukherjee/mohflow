"""
Intelligent log sampling and rate limiting for high-volume services.

This module provides:
- Adaptive sampling that adjusts based on load
- Rate limiting with burst support
- Statistical sampling with consistent rates
- Per-level and per-component sampling
- Memory-efficient implementation with sliding windows
"""

import time
import threading
import random
import hashlib
from typing import Dict, Optional, Any
from dataclasses import dataclass, field
from collections import deque
from enum import Enum


class SamplingStrategy(Enum):
    """Available sampling strategies."""

    RANDOM = "random"
    DETERMINISTIC = "deterministic"
    ADAPTIVE = "adaptive"
    RATE_LIMITED = "rate_limited"
    BURST_ALLOWED = "burst_allowed"


@dataclass
class SamplingConfig:
    """Configuration for log sampling."""

    # Basic sampling
    sample_rate: float = 1.0  # 1.0 = 100% sampling, 0.1 = 10% sampling
    strategy: SamplingStrategy = SamplingStrategy.RANDOM

    # Rate limiting
    max_logs_per_second: Optional[int] = None
    burst_limit: Optional[int] = None
    burst_window_seconds: int = 60

    # Adaptive sampling
    enable_adaptive: bool = False
    adaptive_target_rate: int = 1000  # Target logs per second
    adaptive_window_seconds: int = 60
    min_sample_rate: float = 0.001  # Never sample less than 0.1%
    max_sample_rate: float = 1.0

    # Per-level sampling
    level_sample_rates: Optional[Dict[str, float]] = None

    # Per-component sampling
    component_sample_rates: Optional[Dict[str, float]] = None

    # Memory management
    window_size_seconds: int = 300  # 5 minutes
    cleanup_interval_seconds: int = 60


@dataclass
class SamplingResult:
    """Result of sampling decision."""

    should_log: bool
    sample_rate_used: float
    strategy_used: SamplingStrategy
    reason: str
    stats: Dict[str, Any] = field(default_factory=dict)


class SlidingWindowCounter:
    """Memory-efficient sliding window counter."""

    def __init__(self, window_seconds: int = 60, bucket_count: int = 60):
        """
        Initialize sliding window counter.

        Args:
            window_seconds: Total window size in seconds
            bucket_count: Number of buckets (granularity)
        """
        self.window_seconds = window_seconds
        self.bucket_seconds = window_seconds / bucket_count
        self.buckets = deque(maxlen=bucket_count)
        self.bucket_timestamps = deque(maxlen=bucket_count)
        self._lock = threading.Lock()

        # Initialize empty buckets
        current_time = time.time()
        for i in range(bucket_count):
            self.buckets.append(0)
            self.bucket_timestamps.append(
                current_time - (bucket_count - i) * self.bucket_seconds
            )

    def increment(self, count: int = 1) -> None:
        """Increment counter for current time."""
        with self._lock:
            current_time = time.time()
            self._cleanup_old_buckets(current_time)

            # Add to current bucket
            if self.bucket_timestamps:
                last_bucket_time = self.bucket_timestamps[-1]
                if current_time - last_bucket_time < self.bucket_seconds:
                    # Same bucket
                    self.buckets[-1] += count
                else:
                    # New bucket needed
                    self.buckets.append(count)
                    self.bucket_timestamps.append(current_time)
            else:
                # First bucket
                self.buckets.append(count)
                self.bucket_timestamps.append(current_time)

    def get_count(self, window_seconds: Optional[int] = None) -> int:
        """Get count for specified window (or full window if None)."""
        with self._lock:
            current_time = time.time()
            self._cleanup_old_buckets(current_time)

            if window_seconds is None:
                window_seconds = self.window_seconds

            cutoff_time = current_time - window_seconds
            total = 0

            for i, timestamp in enumerate(self.bucket_timestamps):
                if timestamp >= cutoff_time:
                    total += self.buckets[i]

            return total

    def get_rate(self, window_seconds: Optional[int] = None) -> float:
        """Get rate (count per second) for specified window."""
        if window_seconds is None:
            window_seconds = self.window_seconds

        count = self.get_count(window_seconds)
        return count / window_seconds if window_seconds > 0 else 0.0

    def _cleanup_old_buckets(self, current_time: float) -> None:
        """Remove buckets older than window."""
        cutoff_time = current_time - self.window_seconds

        while (
            self.bucket_timestamps and self.bucket_timestamps[0] < cutoff_time
        ):
            self.buckets.popleft()
            self.bucket_timestamps.popleft()


class AdaptiveSampler:
    """
    Intelligent adaptive log sampler with rate limiting.

    Features:
    - Multiple sampling strategies
    - Adaptive sampling based on load
    - Rate limiting with burst support
    - Per-level and per-component rates
    - Memory-efficient sliding windows
    - Thread-safe implementation
    """

    def __init__(self, config: SamplingConfig):
        """Initialize adaptive sampler."""
        self.config = config
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

        # Counters for different metrics
        self.total_logs = SlidingWindowCounter(
            window_seconds=config.window_size_seconds
        )
        self.sampled_logs = SlidingWindowCounter(
            window_seconds=config.window_size_seconds
        )

        # Rate limiting counters
        if config.max_logs_per_second or config.burst_limit:
            self.rate_limit_counter = SlidingWindowCounter(
                window_seconds=60  # Rate limiting window
            )
        else:
            self.rate_limit_counter = None

        if config.burst_limit:
            self.burst_counter = SlidingWindowCounter(
                window_seconds=config.burst_window_seconds
            )
        else:
            self.burst_counter = None

        # Per-level counters
        self.level_counters: Dict[str, SlidingWindowCounter] = {}

        # Per-component counters
        self.component_counters: Dict[str, SlidingWindowCounter] = {}

        # Adaptive sampling state
        self._current_sample_rate = config.sample_rate
        self._last_adaptive_update = time.time()

        # Random seed for deterministic sampling
        self._random = random.Random()

    def should_sample(
        self,
        level: str = "INFO",
        component: Optional[str] = None,
        message: Optional[str] = None,
        **kwargs: Any,
    ) -> SamplingResult:
        """
        Determine if log should be sampled.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            component: Component/module name for component-specific sampling
            message: Log message (used for deterministic sampling)
            **kwargs: Additional context

        Returns:
            SamplingResult with decision and metadata
        """
        with self._lock:
            # Periodic cleanup
            self._maybe_cleanup()

            # Increment total logs counter
            self.total_logs.increment()

            # Update per-level counter
            if level not in self.level_counters:
                self.level_counters[level] = SlidingWindowCounter(
                    window_seconds=self.config.window_size_seconds
                )
            self.level_counters[level].increment()

            # Update per-component counter
            if component:
                if component not in self.component_counters:
                    self.component_counters[component] = SlidingWindowCounter(
                        window_seconds=self.config.window_size_seconds
                    )
                self.component_counters[component].increment()

            # Check rate limiting first
            rate_limit_result = self._check_rate_limits()
            if not rate_limit_result.should_log:
                return rate_limit_result

            # Determine sampling rate to use
            sample_rate = self._get_effective_sample_rate(level, component)

            # Make sampling decision
            should_log = self._make_sampling_decision(
                sample_rate, level, message, **kwargs
            )

            # Update adaptive sampling if enabled
            if self.config.enable_adaptive:
                self._update_adaptive_sampling()

            # Record sampling result
            if should_log:
                self.sampled_logs.increment()

            return SamplingResult(
                should_log=should_log,
                sample_rate_used=sample_rate,
                strategy_used=self.config.strategy,
                reason=(
                    f"Sampling at {sample_rate:.3f} rate using "
                    f"{self.config.strategy.value} strategy"
                ),
                stats={
                    "total_rate": self.total_logs.get_rate(60),
                    "sampled_rate": self.sampled_logs.get_rate(60),
                    "effective_sample_rate": sample_rate,
                },
            )

    def _check_rate_limits(self) -> SamplingResult:
        """Check if rate limits allow logging."""
        # current_time = time.time()

        # Check burst limit
        if (
            self.config.burst_limit
            and self.burst_counter
            and self.burst_counter.get_count() >= self.config.burst_limit
        ):
            return SamplingResult(
                should_log=False,
                sample_rate_used=0.0,
                strategy_used=SamplingStrategy.BURST_ALLOWED,
                reason=(
                    f"Burst limit exceeded ({self.config.burst_limit} logs "
                    f"in {self.config.burst_window_seconds}s)"
                ),
            )

        # Check rate limit
        if (
            self.config.max_logs_per_second
            and self.rate_limit_counter
            and self.rate_limit_counter.get_rate(1)
            >= self.config.max_logs_per_second
        ):
            return SamplingResult(
                should_log=False,
                sample_rate_used=0.0,
                strategy_used=SamplingStrategy.RATE_LIMITED,
                reason=(
                    f"Rate limit exceeded "
                    f"({self.config.max_logs_per_second} logs/sec)"
                ),
            )

        # Rate limits passed
        if self.rate_limit_counter:
            self.rate_limit_counter.increment()
        if self.burst_counter:
            self.burst_counter.increment()

        return SamplingResult(
            should_log=True,
            sample_rate_used=1.0,
            strategy_used=SamplingStrategy.RATE_LIMITED,
            reason="Rate limits passed",
        )

    def _get_effective_sample_rate(
        self, level: str, component: Optional[str]
    ) -> float:
        """Get the effective sample rate considering all factors."""
        base_rate = self._current_sample_rate

        # Check level-specific sampling
        if (
            self.config.level_sample_rates
            and level in self.config.level_sample_rates
        ):
            level_rate = self.config.level_sample_rates[level]
            base_rate = min(base_rate, level_rate)

        # Check component-specific sampling
        if (
            component
            and self.config.component_sample_rates
            and component in self.config.component_sample_rates
        ):
            component_rate = self.config.component_sample_rates[component]
            base_rate = min(base_rate, component_rate)

        return base_rate

    def _make_sampling_decision(
        self,
        sample_rate: float,
        level: str,
        message: Optional[str],
        **kwargs: Any,
    ) -> bool:
        """Make the actual sampling decision based on strategy."""
        if sample_rate >= 1.0:
            return True
        if sample_rate <= 0.0:
            return False

        if self.config.strategy == SamplingStrategy.RANDOM:
            return self._random.random() < sample_rate

        elif self.config.strategy == SamplingStrategy.DETERMINISTIC:
            # Use hash of message/context for deterministic sampling
            hash_input = (
                f"{level}:{message or ''}:{kwargs.get('component', '')}"
            )
            hash_value = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
            return (hash_value % 10000) < (sample_rate * 10000)

        elif self.config.strategy == SamplingStrategy.ADAPTIVE:
            # Adaptive uses random but adjusts rate based on load
            return self._random.random() < sample_rate

        else:
            # Default to random
            return self._random.random() < sample_rate

    def _update_adaptive_sampling(self) -> None:
        """Update adaptive sampling rate based on current load."""
        current_time = time.time()

        # Update adaptive sampling every window
        if (
            current_time - self._last_adaptive_update
            >= self.config.adaptive_window_seconds
        ):

            current_rate = self.total_logs.get_rate(
                self.config.adaptive_window_seconds
            )
            target_rate = self.config.adaptive_target_rate

            if current_rate > target_rate:
                # Too much load, decrease sampling
                adjustment_factor = target_rate / current_rate
                new_rate = self._current_sample_rate * adjustment_factor
            elif current_rate < target_rate * 0.8:
                # Low load, can increase sampling
                adjustment_factor = min(1.2, target_rate / current_rate)
                new_rate = self._current_sample_rate * adjustment_factor
            else:
                # Rate is acceptable
                new_rate = self._current_sample_rate

            # Apply bounds
            self._current_sample_rate = max(
                self.config.min_sample_rate,
                min(self.config.max_sample_rate, new_rate),
            )

            self._last_adaptive_update = current_time

    def _maybe_cleanup(self) -> None:
        """Periodic cleanup of old data."""
        current_time = time.time()
        if (
            current_time - self._last_cleanup
            >= self.config.cleanup_interval_seconds
        ):

            # Cleanup is handled automatically by SlidingWindowCounter
            # but we can do additional cleanup here if needed
            self._last_cleanup = current_time

    def get_stats(self) -> Dict[str, Any]:
        """Get sampling statistics."""
        stats = {
            "current_sample_rate": self._current_sample_rate,
            "strategy": self.config.strategy.value,
            "total_logs_rate": self.total_logs.get_rate(60),
            "sampled_logs_rate": self.sampled_logs.get_rate(60),
            "total_logs_count": self.total_logs.get_count(),
            "sampled_logs_count": self.sampled_logs.get_count(),
            "level_stats": {},
            "component_stats": {},
        }

        # Add per-level stats
        for level, counter in self.level_counters.items():
            stats["level_stats"][level] = {
                "rate": counter.get_rate(60),
                "count": counter.get_count(),
            }

        # Add per-component stats
        for component, counter in self.component_counters.items():
            stats["component_stats"][component] = {
                "rate": counter.get_rate(60),
                "count": counter.get_count(),
            }

        # Add rate limiting stats
        if self.rate_limit_counter:
            stats["rate_limit_current"] = self.rate_limit_counter.get_rate(1)
            stats["rate_limit_max"] = self.config.max_logs_per_second

        if self.burst_counter:
            stats["burst_current"] = self.burst_counter.get_count()
            stats["burst_limit"] = self.config.burst_limit

        return stats

    def reset(self) -> None:
        """Reset all counters and state."""
        with self._lock:
            self.total_logs = SlidingWindowCounter(
                window_seconds=self.config.window_size_seconds
            )
            self.sampled_logs = SlidingWindowCounter(
                window_seconds=self.config.window_size_seconds
            )
            self.level_counters.clear()
            self.component_counters.clear()
            self._current_sample_rate = self.config.sample_rate
            self._last_adaptive_update = time.time()


# Factory functions for common configurations
def create_high_volume_sampler(
    sample_rate: float = 0.1,
    max_logs_per_second: int = 1000,
    burst_limit: int = 2000,
) -> AdaptiveSampler:
    """Create sampler optimized for high-volume services."""
    config = SamplingConfig(
        sample_rate=sample_rate,
        strategy=SamplingStrategy.ADAPTIVE,
        max_logs_per_second=max_logs_per_second,
        burst_limit=burst_limit,
        enable_adaptive=True,
        adaptive_target_rate=max_logs_per_second,
        level_sample_rates={
            "DEBUG": 0.01,  # 1% of debug logs
            "INFO": 0.1,  # 10% of info logs
            "WARNING": 0.5,  # 50% of warning logs
            "ERROR": 1.0,  # 100% of error logs
            "CRITICAL": 1.0,  # 100% of critical logs
        },
    )
    return AdaptiveSampler(config)


def create_development_sampler() -> AdaptiveSampler:
    """Create sampler for development environments (no sampling)."""
    config = SamplingConfig(sample_rate=1.0, strategy=SamplingStrategy.RANDOM)
    return AdaptiveSampler(config)


def create_production_sampler(
    sample_rate: float = 0.2, max_logs_per_second: int = 500
) -> AdaptiveSampler:
    """Create sampler for production environments."""
    config = SamplingConfig(
        sample_rate=sample_rate,
        strategy=SamplingStrategy.DETERMINISTIC,
        max_logs_per_second=max_logs_per_second,
        burst_limit=max_logs_per_second * 2,
        level_sample_rates={
            "DEBUG": 0.01,
            "INFO": 0.2,
            "WARNING": 0.8,
            "ERROR": 1.0,
            "CRITICAL": 1.0,
        },
    )
    return AdaptiveSampler(config)
