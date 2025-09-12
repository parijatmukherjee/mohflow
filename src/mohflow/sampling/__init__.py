"""
MohFlow Log Sampling and Rate Limiting

This package provides intelligent log sampling capabilities for high-volume services:

- Adaptive sampling that adjusts based on load
- Rate limiting with burst support
- Multiple sampling strategies (random, deterministic, adaptive)
- Per-level and per-component sampling rates
- Memory-efficient sliding window counters
- Thread-safe implementation

Example usage:

    from mohflow.sampling import (
        AdaptiveSampler, SamplingConfig, SamplingStrategy,
        create_high_volume_sampler, create_production_sampler
    )

    # High-volume service with adaptive sampling
    sampler = create_high_volume_sampler(
        sample_rate=0.1,  # 10% base rate
        max_logs_per_second=1000,
        burst_limit=2000
    )

    # Check if log should be sampled
    result = sampler.should_sample(
        level="INFO",
        component="api",
        message="User login"
    )

    if result.should_log:
        logger.info("User login", **extra_context)
"""

from .adaptive_sampler import (
    AdaptiveSampler,
    SamplingConfig,
    SamplingResult,
    SamplingStrategy,
    SlidingWindowCounter,
    create_high_volume_sampler,
    create_development_sampler,
    create_production_sampler,
)

__all__ = [
    "AdaptiveSampler",
    "SamplingConfig",
    "SamplingResult",
    "SamplingStrategy",
    "SlidingWindowCounter",
    "create_high_volume_sampler",
    "create_development_sampler",
    "create_production_sampler",
]
