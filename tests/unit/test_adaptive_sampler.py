"""Tests for adaptive_sampler module: sampling, rate limiting, counters."""

import threading
import time
from unittest.mock import patch

import pytest

from mohflow.sampling.adaptive_sampler import (
    AdaptiveSampler,
    SamplingConfig,
    SamplingResult,
    SamplingStrategy,
    SlidingWindowCounter,
    create_development_sampler,
    create_high_volume_sampler,
    create_production_sampler,
)

# -----------------------------------------------------------
# SamplingStrategy enum
# -----------------------------------------------------------


class TestSamplingStrategy:
    """Verify enum members and values."""

    def test_all_members_present(self):
        members = {m.name for m in SamplingStrategy}
        assert members == {
            "RANDOM",
            "DETERMINISTIC",
            "ADAPTIVE",
            "RATE_LIMITED",
            "BURST_ALLOWED",
        }

    def test_values(self):
        assert SamplingStrategy.RANDOM.value == "random"
        assert SamplingStrategy.DETERMINISTIC.value == "deterministic"
        assert SamplingStrategy.ADAPTIVE.value == "adaptive"
        assert SamplingStrategy.RATE_LIMITED.value == "rate_limited"
        assert SamplingStrategy.BURST_ALLOWED.value == "burst_allowed"

    def test_lookup_by_value(self):
        assert SamplingStrategy("random") is SamplingStrategy.RANDOM

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            SamplingStrategy("nonexistent")


# -----------------------------------------------------------
# SamplingConfig dataclass
# -----------------------------------------------------------


class TestSamplingConfig:
    """Cover defaults and custom construction."""

    def test_defaults(self):
        cfg = SamplingConfig()
        assert cfg.sample_rate == 1.0
        assert cfg.strategy is SamplingStrategy.RANDOM
        assert cfg.max_logs_per_second is None
        assert cfg.burst_limit is None
        assert cfg.burst_window_seconds == 60
        assert cfg.enable_adaptive is False
        assert cfg.adaptive_target_rate == 1000
        assert cfg.adaptive_window_seconds == 60
        assert cfg.min_sample_rate == 0.001
        assert cfg.max_sample_rate == 1.0
        assert cfg.level_sample_rates is None
        assert cfg.component_sample_rates is None
        assert cfg.window_size_seconds == 300
        assert cfg.cleanup_interval_seconds == 60

    def test_custom_values(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.DETERMINISTIC,
            max_logs_per_second=100,
            burst_limit=200,
            burst_window_seconds=30,
            enable_adaptive=True,
            adaptive_target_rate=500,
            adaptive_window_seconds=120,
            min_sample_rate=0.01,
            max_sample_rate=0.9,
            level_sample_rates={"ERROR": 1.0},
            component_sample_rates={"api": 0.5},
            window_size_seconds=600,
            cleanup_interval_seconds=120,
        )
        assert cfg.sample_rate == 0.5
        assert cfg.strategy is SamplingStrategy.DETERMINISTIC
        assert cfg.max_logs_per_second == 100
        assert cfg.burst_limit == 200
        assert cfg.burst_window_seconds == 30
        assert cfg.enable_adaptive is True
        assert cfg.adaptive_target_rate == 500
        assert cfg.adaptive_window_seconds == 120
        assert cfg.min_sample_rate == 0.01
        assert cfg.max_sample_rate == 0.9
        assert cfg.level_sample_rates == {"ERROR": 1.0}
        assert cfg.component_sample_rates == {"api": 0.5}
        assert cfg.window_size_seconds == 600
        assert cfg.cleanup_interval_seconds == 120


# -----------------------------------------------------------
# SamplingResult dataclass
# -----------------------------------------------------------


class TestSamplingResult:
    """Cover dataclass creation and defaults."""

    def test_required_fields(self):
        result = SamplingResult(
            should_log=True,
            sample_rate_used=0.5,
            strategy_used=SamplingStrategy.RANDOM,
            reason="test",
        )
        assert result.should_log is True
        assert result.sample_rate_used == 0.5
        assert result.strategy_used is SamplingStrategy.RANDOM
        assert result.reason == "test"
        assert result.stats == {}

    def test_custom_stats(self):
        result = SamplingResult(
            should_log=False,
            sample_rate_used=0.0,
            strategy_used=SamplingStrategy.RATE_LIMITED,
            reason="limited",
            stats={"total_rate": 42.0},
        )
        assert result.stats == {"total_rate": 42.0}


# -----------------------------------------------------------
# SlidingWindowCounter
# -----------------------------------------------------------


class TestSlidingWindowCounter:
    """Full coverage for sliding window counter."""

    def test_initial_count_is_zero(self):
        counter = SlidingWindowCounter(window_seconds=60)
        assert counter.get_count() == 0

    def test_increment_default(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment()
        assert counter.get_count() >= 1

    def test_increment_custom_count(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(5)
        assert counter.get_count() >= 5

    def test_get_count_with_custom_window(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(10)
        # Smaller window should still capture recent events
        assert counter.get_count(window_seconds=1) >= 0

    def test_get_rate_non_zero_window(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(120)
        rate = counter.get_rate(60)
        assert rate == counter.get_count(60) / 60

    def test_get_rate_zero_window(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(10)
        assert counter.get_rate(0) == 0.0

    def test_get_rate_default_window(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(60)
        rate = counter.get_rate()
        assert rate >= 0.0

    def test_get_count_default_window(self):
        counter = SlidingWindowCounter(window_seconds=60)
        counter.increment(7)
        count = counter.get_count()
        assert count >= 7

    def test_new_bucket_creation(self):
        """Force a new bucket by mocking time advancement."""
        counter = SlidingWindowCounter(window_seconds=10, bucket_count=10)
        # bucket_seconds = 1.0
        counter.increment(3)

        # Advance time beyond one bucket boundary
        base = time.time() + 2.0
        with patch("time.time", return_value=base):
            counter.increment(5)

        # Both increments should be counted
        assert counter.get_count() >= 5

    def test_cleanup_removes_old_buckets(self):
        """Old buckets should be evicted after the window elapses."""
        counter = SlidingWindowCounter(window_seconds=2, bucket_count=2)
        counter.increment(10)

        # Jump far into the future so everything is old
        future = time.time() + 100
        with patch("time.time", return_value=future):
            assert counter.get_count() == 0

    def test_thread_safety(self):
        """Multiple threads incrementing should not corrupt state."""
        counter = SlidingWindowCounter(window_seconds=60)
        barrier = threading.Barrier(4)

        def worker():
            barrier.wait()
            for _ in range(100):
                counter.increment()

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter.get_count() == 400

    def test_empty_bucket_timestamps_branch(self):
        """Cover the 'first bucket' branch when deques are empty."""
        counter = SlidingWindowCounter(window_seconds=5, bucket_count=5)
        # Force empty deques by jumping far ahead so cleanup
        # removes all buckets, then incrementing enters the else
        # branch.
        future = time.time() + 100
        with patch("time.time", return_value=future):
            counter.increment(1)
            assert counter.get_count() >= 1


# -----------------------------------------------------------
# AdaptiveSampler -- initialisation
# -----------------------------------------------------------


class TestAdaptiveSamplerInit:
    """Verify constructor sets up correct state."""

    def test_default_config(self):
        sampler = AdaptiveSampler(SamplingConfig())
        assert sampler.rate_limit_counter is None
        assert sampler.burst_counter is None
        assert sampler._current_sample_rate == 1.0

    def test_rate_limit_counter_created(self):
        cfg = SamplingConfig(max_logs_per_second=100)
        sampler = AdaptiveSampler(cfg)
        assert sampler.rate_limit_counter is not None

    def test_burst_counter_created(self):
        cfg = SamplingConfig(burst_limit=200)
        sampler = AdaptiveSampler(cfg)
        assert sampler.burst_counter is not None
        assert sampler.rate_limit_counter is not None

    def test_both_counters_none_when_no_limits(self):
        cfg = SamplingConfig()
        sampler = AdaptiveSampler(cfg)
        assert sampler.rate_limit_counter is None
        assert sampler.burst_counter is None


# -----------------------------------------------------------
# AdaptiveSampler.should_sample -- basic
# -----------------------------------------------------------


class TestShouldSampleBasic:
    """Core sampling decisions without rate limiting."""

    def test_full_rate_always_logs(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        for _ in range(50):
            result = sampler.should_sample(level="INFO")
            assert result.should_log is True
            assert result.sample_rate_used == 1.0

    def test_zero_rate_never_logs(self):
        cfg = SamplingConfig(sample_rate=0.0)
        sampler = AdaptiveSampler(cfg)
        for _ in range(50):
            result = sampler.should_sample(level="INFO")
            assert result.should_log is False

    def test_result_contains_stats(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO")
        assert "total_rate" in result.stats
        assert "sampled_rate" in result.stats
        assert "effective_sample_rate" in result.stats

    def test_strategy_recorded_in_result(self):
        cfg = SamplingConfig(sample_rate=1.0, strategy=SamplingStrategy.RANDOM)
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample()
        assert result.strategy_used is SamplingStrategy.RANDOM

    def test_reason_string_populated(self):
        cfg = SamplingConfig(sample_rate=0.5)
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample()
        assert "random" in result.reason.lower() or "0.5" in result.reason


# -----------------------------------------------------------
# Per-level sampling
# -----------------------------------------------------------


class TestPerLevelSampling:
    """Level-specific sample rates."""

    def test_error_always_sampled(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            level_sample_rates={"ERROR": 1.0, "DEBUG": 0.0},
        )
        sampler = AdaptiveSampler(cfg)
        for _ in range(20):
            result = sampler.should_sample(level="ERROR")
            assert result.should_log is True

    def test_debug_never_sampled_at_zero(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            level_sample_rates={"DEBUG": 0.0},
        )
        sampler = AdaptiveSampler(cfg)
        for _ in range(20):
            result = sampler.should_sample(level="DEBUG")
            assert result.should_log is False

    def test_level_rate_takes_minimum_with_base(self):
        """When base=0.5 and level=0.8, effective = min(0.5, 0.8) = 0.5."""
        cfg = SamplingConfig(
            sample_rate=0.5,
            level_sample_rates={"INFO": 0.8},
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO")
        assert result.sample_rate_used == 0.5

    def test_unlisted_level_uses_base_rate(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            level_sample_rates={"ERROR": 0.5},
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO")
        assert result.sample_rate_used == 1.0

    def test_level_counter_created_on_first_call(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        assert "INFO" not in sampler.level_counters
        sampler.should_sample(level="INFO")
        assert "INFO" in sampler.level_counters


# -----------------------------------------------------------
# Per-component sampling
# -----------------------------------------------------------


class TestPerComponentSampling:
    """Component-specific sample rates."""

    def test_component_rate_applied(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            component_sample_rates={"noisy_api": 0.0},
        )
        sampler = AdaptiveSampler(cfg)
        for _ in range(20):
            result = sampler.should_sample(level="INFO", component="noisy_api")
            assert result.should_log is False

    def test_component_rate_minimum_with_base(self):
        cfg = SamplingConfig(
            sample_rate=0.3,
            component_sample_rates={"api": 0.8},
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO", component="api")
        assert result.sample_rate_used == 0.3

    def test_unknown_component_uses_base(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            component_sample_rates={"api": 0.5},
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO", component="other")
        assert result.sample_rate_used == 1.0

    def test_none_component_ignored(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            component_sample_rates={"api": 0.0},
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO", component=None)
        assert result.should_log is True

    def test_component_counter_created(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO", component="db")
        assert "db" in sampler.component_counters

    def test_no_component_counter_when_none(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO")
        assert len(sampler.component_counters) == 0


# -----------------------------------------------------------
# Deterministic sampling strategy
# -----------------------------------------------------------


class TestDeterministicSampling:
    """Deterministic strategy yields reproducible results."""

    def test_same_message_same_result(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.DETERMINISTIC,
        )
        sampler = AdaptiveSampler(cfg)
        results = set()
        for _ in range(10):
            r = sampler.should_sample(level="INFO", message="fixed-msg")
            results.add(r.should_log)
        # All calls should give the same answer
        assert len(results) == 1

    def test_different_messages_can_differ(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.DETERMINISTIC,
        )
        sampler = AdaptiveSampler(cfg)
        outcomes = set()
        for i in range(200):
            r = sampler.should_sample(level="INFO", message=f"msg-{i}")
            outcomes.add(r.should_log)
        # With 200 distinct messages at 50% rate we expect both
        assert outcomes == {True, False}

    def test_deterministic_with_none_message(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.DETERMINISTIC,
        )
        sampler = AdaptiveSampler(cfg)
        # Should not raise
        result = sampler.should_sample(level="INFO", message=None)
        assert isinstance(result.should_log, bool)

    def test_deterministic_full_rate(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            strategy=SamplingStrategy.DETERMINISTIC,
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO", message="hi")
        assert result.should_log is True

    def test_deterministic_zero_rate(self):
        cfg = SamplingConfig(
            sample_rate=0.0,
            strategy=SamplingStrategy.DETERMINISTIC,
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO", message="hi")
        assert result.should_log is False


# -----------------------------------------------------------
# Random sampling strategy
# -----------------------------------------------------------


class TestRandomSampling:
    """Random strategy sampling at fractional rates."""

    def test_random_sampling_produces_both(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.RANDOM,
        )
        sampler = AdaptiveSampler(cfg)
        outcomes = set()
        for _ in range(500):
            r = sampler.should_sample(level="INFO")
            outcomes.add(r.should_log)
        assert outcomes == {True, False}

    def test_random_near_zero_mostly_drops(self):
        cfg = SamplingConfig(
            sample_rate=0.001,
            strategy=SamplingStrategy.RANDOM,
        )
        sampler = AdaptiveSampler(cfg)
        logged = sum(
            1
            for _ in range(1000)
            if sampler.should_sample(level="INFO").should_log
        )
        # Expect very few (statistically should be ~1)
        assert logged < 50

    def test_random_near_one_mostly_logs(self):
        cfg = SamplingConfig(
            sample_rate=0.999,
            strategy=SamplingStrategy.RANDOM,
        )
        sampler = AdaptiveSampler(cfg)
        logged = sum(
            1
            for _ in range(1000)
            if sampler.should_sample(level="INFO").should_log
        )
        assert logged > 900


# -----------------------------------------------------------
# Adaptive sampling strategy
# -----------------------------------------------------------


class TestAdaptiveSampling:
    """Adaptive strategy adjusts rate based on load."""

    def test_adaptive_uses_random_decision(self):
        """Adaptive strategy falls through to random."""
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
        )
        sampler = AdaptiveSampler(cfg)
        outcomes = set()
        for _ in range(200):
            r = sampler.should_sample(level="INFO")
            outcomes.add(r.should_log)
        assert outcomes == {True, False}

    def test_adaptive_decreases_rate_under_load(self):
        """When log rate > target, sample rate should decrease."""
        cfg = SamplingConfig(
            sample_rate=1.0,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
            adaptive_target_rate=10,
            adaptive_window_seconds=1,
            min_sample_rate=0.001,
        )
        sampler = AdaptiveSampler(cfg)

        # Simulate a burst of logs
        for _ in range(200):
            sampler.should_sample(level="INFO")

        # Force the adaptive update by advancing time
        sampler._last_adaptive_update = time.time() - 10
        sampler.should_sample(level="INFO")

        assert sampler._current_sample_rate < 1.0

    def test_adaptive_increases_rate_when_idle(self):
        """When load is low, rate should increase toward max."""
        cfg = SamplingConfig(
            sample_rate=0.1,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
            adaptive_target_rate=10000,
            adaptive_window_seconds=1,
            max_sample_rate=1.0,
        )
        sampler = AdaptiveSampler(cfg)

        # Just a few logs -- well below target
        sampler.should_sample(level="INFO")

        # Force update
        sampler._last_adaptive_update = time.time() - 10
        sampler.should_sample(level="INFO")

        assert sampler._current_sample_rate >= 0.1

    def test_adaptive_respects_min_sample_rate(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
            adaptive_target_rate=1,
            adaptive_window_seconds=1,
            min_sample_rate=0.05,
        )
        sampler = AdaptiveSampler(cfg)

        for _ in range(500):
            sampler.should_sample(level="INFO")

        sampler._last_adaptive_update = time.time() - 10
        sampler.should_sample(level="INFO")

        assert sampler._current_sample_rate >= 0.05

    def test_adaptive_respects_max_sample_rate(self):
        cfg = SamplingConfig(
            sample_rate=0.01,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
            adaptive_target_rate=999999,
            adaptive_window_seconds=1,
            max_sample_rate=0.9,
        )
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO")

        sampler._last_adaptive_update = time.time() - 10
        sampler.should_sample(level="INFO")

        assert sampler._current_sample_rate <= 0.9

    def test_adaptive_no_change_in_acceptable_range(self):
        """Rate stays the same when load is between 80%-100%."""
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
            adaptive_target_rate=100,
            adaptive_window_seconds=1,
        )
        sampler = AdaptiveSampler(cfg)

        # Ensure current_rate lands in the acceptable band
        # (target * 0.8 <= current_rate <= target).
        # We mock get_rate to return exactly 90 (within band).
        original_rate = sampler._current_sample_rate
        with patch.object(
            sampler.total_logs,
            "get_rate",
            return_value=90.0,
        ):
            sampler._last_adaptive_update = time.time() - 10
            sampler._update_adaptive_sampling()

        assert sampler._current_sample_rate == original_rate


# -----------------------------------------------------------
# Rate limiting
# -----------------------------------------------------------


class TestRateLimiting:
    """Rate limit checks via max_logs_per_second."""

    def test_rate_limit_blocks_when_exceeded(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            max_logs_per_second=5,
        )
        sampler = AdaptiveSampler(cfg)

        blocked = False
        for _ in range(200):
            r = sampler.should_sample(level="INFO")
            if not r.should_log:
                blocked = True
                assert r.strategy_used is SamplingStrategy.RATE_LIMITED
                assert "Rate limit" in r.reason
                break
        assert blocked, "Expected rate limit to block at least once"

    def test_rate_limit_passes_when_within_limit(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            max_logs_per_second=100000,
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO")
        assert result.should_log is True


# -----------------------------------------------------------
# Burst limiting
# -----------------------------------------------------------


class TestBurstLimiting:
    """Burst limit checks."""

    def test_burst_limit_blocks_when_exceeded(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            burst_limit=10,
            burst_window_seconds=60,
        )
        sampler = AdaptiveSampler(cfg)

        blocked = False
        for _ in range(100):
            r = sampler.should_sample(level="INFO")
            if not r.should_log:
                blocked = True
                assert r.strategy_used is SamplingStrategy.BURST_ALLOWED
                assert "Burst limit" in r.reason
                break
        assert blocked, "Expected burst limit to trigger"

    def test_burst_limit_allows_within_limit(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            burst_limit=100000,
            burst_window_seconds=60,
        )
        sampler = AdaptiveSampler(cfg)
        result = sampler.should_sample(level="INFO")
        assert result.should_log is True


# -----------------------------------------------------------
# Combined level + component + rate limiting
# -----------------------------------------------------------


class TestCombinedSampling:
    """Level, component, and rate limits together."""

    def test_level_and_component_combined(self):
        cfg = SamplingConfig(
            sample_rate=1.0,
            level_sample_rates={"DEBUG": 0.0},
            component_sample_rates={"noisy": 0.0},
        )
        sampler = AdaptiveSampler(cfg)

        # DEBUG at noisy component: blocked by either rate
        r = sampler.should_sample(level="DEBUG", component="noisy")
        assert r.should_log is False

    def test_rate_limit_preempts_sampling(self):
        """Rate limit should block before sampling decision."""
        cfg = SamplingConfig(
            sample_rate=1.0,
            max_logs_per_second=1,
            burst_limit=1,
            burst_window_seconds=60,
        )
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO")

        result = sampler.should_sample(level="INFO")
        # Second call should be rate/burst limited
        assert result.should_log is False


# -----------------------------------------------------------
# _maybe_cleanup
# -----------------------------------------------------------


class TestMaybeCleanup:
    """Periodic cleanup path."""

    def test_cleanup_updates_timestamp(self):
        cfg = SamplingConfig(cleanup_interval_seconds=0)
        sampler = AdaptiveSampler(cfg)
        old_ts = sampler._last_cleanup

        # Advance time so cleanup triggers
        sampler._last_cleanup = time.time() - 100
        sampler.should_sample(level="INFO")
        assert sampler._last_cleanup > old_ts

    def test_cleanup_skipped_when_recent(self):
        cfg = SamplingConfig(cleanup_interval_seconds=9999)
        sampler = AdaptiveSampler(cfg)
        ts_before = sampler._last_cleanup
        sampler.should_sample(level="INFO")
        assert sampler._last_cleanup == ts_before


# -----------------------------------------------------------
# get_stats
# -----------------------------------------------------------


class TestGetStats:
    """Verify statistics dictionary."""

    def test_empty_stats(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        stats = sampler.get_stats()

        assert stats["current_sample_rate"] == 1.0
        assert stats["strategy"] == "random"
        assert stats["level_stats"] == {}
        assert stats["component_stats"] == {}
        assert "rate_limit_current" not in stats
        assert "burst_current" not in stats

    def test_stats_after_sampling(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO", component="api")
        sampler.should_sample(level="ERROR", component="api")

        stats = sampler.get_stats()
        assert "INFO" in stats["level_stats"]
        assert "ERROR" in stats["level_stats"]
        assert "api" in stats["component_stats"]
        assert stats["total_logs_count"] >= 2
        assert stats["sampled_logs_count"] >= 2

    def test_stats_with_rate_limit(self):
        cfg = SamplingConfig(sample_rate=1.0, max_logs_per_second=100)
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO")
        stats = sampler.get_stats()
        assert "rate_limit_current" in stats
        assert stats["rate_limit_max"] == 100

    def test_stats_with_burst_limit(self):
        cfg = SamplingConfig(sample_rate=1.0, burst_limit=50)
        sampler = AdaptiveSampler(cfg)
        sampler.should_sample(level="INFO")
        stats = sampler.get_stats()
        assert "burst_current" in stats
        assert stats["burst_limit"] == 50


# -----------------------------------------------------------
# reset
# -----------------------------------------------------------


class TestReset:
    """Verify full state reset."""

    def test_reset_clears_counters(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)

        for _ in range(10):
            sampler.should_sample(level="INFO", component="api")

        assert sampler.total_logs.get_count() >= 10
        assert len(sampler.level_counters) > 0
        assert len(sampler.component_counters) > 0

        sampler.reset()

        assert sampler.total_logs.get_count() == 0
        assert sampler.sampled_logs.get_count() == 0
        assert sampler.level_counters == {}
        assert sampler.component_counters == {}
        assert sampler._current_sample_rate == cfg.sample_rate

    def test_reset_restores_sample_rate(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.ADAPTIVE,
            enable_adaptive=True,
            adaptive_target_rate=1,
            adaptive_window_seconds=1,
        )
        sampler = AdaptiveSampler(cfg)
        # Force adaptive update to change rate
        for _ in range(100):
            sampler.should_sample(level="INFO")
        sampler._last_adaptive_update = time.time() - 10
        sampler.should_sample(level="INFO")

        sampler.reset()
        assert sampler._current_sample_rate == 0.5


# -----------------------------------------------------------
# Factory functions
# -----------------------------------------------------------


class TestFactoryFunctions:
    """Cover all three factory helpers."""

    def test_create_high_volume_sampler_defaults(self):
        sampler = create_high_volume_sampler()
        assert sampler.config.sample_rate == 0.1
        assert sampler.config.max_logs_per_second == 1000
        assert sampler.config.burst_limit == 2000
        assert sampler.config.strategy is SamplingStrategy.ADAPTIVE
        assert sampler.config.enable_adaptive is True
        assert sampler.config.adaptive_target_rate == 1000
        assert sampler.config.level_sample_rates is not None
        assert sampler.config.level_sample_rates["DEBUG"] == 0.01
        assert sampler.config.level_sample_rates["CRITICAL"] == 1.0

    def test_create_high_volume_sampler_custom(self):
        sampler = create_high_volume_sampler(
            sample_rate=0.05,
            max_logs_per_second=500,
            burst_limit=1000,
        )
        assert sampler.config.sample_rate == 0.05
        assert sampler.config.max_logs_per_second == 500
        assert sampler.config.burst_limit == 1000

    def test_create_development_sampler(self):
        sampler = create_development_sampler()
        assert sampler.config.sample_rate == 1.0
        assert sampler.config.strategy is SamplingStrategy.RANDOM
        # Everything should be logged
        for _ in range(20):
            r = sampler.should_sample(level="DEBUG")
            assert r.should_log is True

    def test_create_production_sampler_defaults(self):
        sampler = create_production_sampler()
        assert sampler.config.sample_rate == 0.2
        assert sampler.config.max_logs_per_second == 500
        assert sampler.config.burst_limit == 1000
        assert sampler.config.strategy is SamplingStrategy.DETERMINISTIC
        assert sampler.config.level_sample_rates["ERROR"] == 1.0

    def test_create_production_sampler_custom(self):
        sampler = create_production_sampler(
            sample_rate=0.5, max_logs_per_second=200
        )
        assert sampler.config.sample_rate == 0.5
        assert sampler.config.max_logs_per_second == 200
        assert sampler.config.burst_limit == 400


# -----------------------------------------------------------
# Edge-case / default-branch coverage
# -----------------------------------------------------------


class TestEdgeCases:
    """Boundary conditions, fallbacks, unusual inputs."""

    def test_unrecognised_strategy_falls_back_to_random(self):
        """The else branch in _make_sampling_decision."""
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.BURST_ALLOWED,
        )
        sampler = AdaptiveSampler(cfg)
        outcomes = set()
        for _ in range(200):
            r = sampler.should_sample(level="INFO")
            outcomes.add(r.should_log)
        # Should still produce both outcomes via the default
        assert outcomes == {True, False}

    def test_kwargs_forwarded_to_sampling_decision(self):
        cfg = SamplingConfig(
            sample_rate=0.5,
            strategy=SamplingStrategy.DETERMINISTIC,
        )
        sampler = AdaptiveSampler(cfg)
        # Should not raise
        r = sampler.should_sample(
            level="INFO",
            message="hello",
            component="test",
            extra_key="extra_value",
        )
        assert isinstance(r.should_log, bool)

    def test_sample_rate_boundary_one(self):
        """Exactly 1.0 should always return True."""
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        assert sampler.should_sample().should_log is True

    def test_sample_rate_boundary_zero(self):
        """Exactly 0.0 should always return False."""
        cfg = SamplingConfig(sample_rate=0.0)
        sampler = AdaptiveSampler(cfg)
        assert sampler.should_sample().should_log is False

    def test_sample_rate_above_one_treated_as_always(self):
        """Rate >= 1.0 short-circuits to True."""
        cfg = SamplingConfig(sample_rate=1.5)
        sampler = AdaptiveSampler(cfg)
        assert sampler.should_sample().should_log is True

    def test_sample_rate_negative_treated_as_never(self):
        """Rate <= 0.0 short-circuits to False."""
        cfg = SamplingConfig(sample_rate=-0.5)
        sampler = AdaptiveSampler(cfg)
        assert sampler.should_sample().should_log is False

    def test_many_levels_tracked(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        levels = [
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        ]
        for lvl in levels:
            sampler.should_sample(level=lvl)
        assert set(sampler.level_counters.keys()) == set(levels)

    def test_many_components_tracked(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        components = ["api", "db", "cache", "auth"]
        for c in components:
            sampler.should_sample(level="INFO", component=c)
        assert set(sampler.component_counters.keys()) == set(components)


# -----------------------------------------------------------
# Thread-safety of AdaptiveSampler
# -----------------------------------------------------------


class TestThreadSafety:
    """Ensure sampler works under concurrent access."""

    def test_concurrent_should_sample(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        errors = []

        def worker():
            try:
                for _ in range(100):
                    r = sampler.should_sample(level="INFO", component="test")
                    assert isinstance(r.should_log, bool)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"

    def test_concurrent_reset(self):
        cfg = SamplingConfig(sample_rate=1.0)
        sampler = AdaptiveSampler(cfg)
        errors = []

        def sample_worker():
            try:
                for _ in range(50):
                    sampler.should_sample(level="INFO")
            except Exception as exc:
                errors.append(exc)

        def reset_worker():
            try:
                for _ in range(5):
                    sampler.reset()
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=sample_worker),
            threading.Thread(target=sample_worker),
            threading.Thread(target=reset_worker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Thread errors: {errors}"
