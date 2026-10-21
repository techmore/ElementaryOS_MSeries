//! Fixed-size latency histogram in microseconds.
//!
//! 84 buckets: 0–3 µs are exact, then every power of two is split into four
//! equal steps up to about 4.2 s. Recording is a few integer operations and no
//! allocation, so it can sit on the per-frame path. Percentiles are reported as
//! the upper edge of the bucket that holds them, so they are never below the
//! true value and at most 25% above it.

use std::time::Duration;

pub const BUCKETS: usize = 84;

#[derive(Clone, Debug)]
pub struct Histogram {
    counts: [u32; BUCKETS],
    count: u64,
    sum_us: u64,
    max_us: u64,
}

impl Default for Histogram {
    fn default() -> Self {
        Self {
            counts: [0; BUCKETS],
            count: 0,
            sum_us: 0,
            max_us: 0,
        }
    }
}

/// Bucket index for a value in microseconds.
pub fn bucket_index(us: u64) -> usize {
    if us < 4 {
        return us as usize;
    }
    let exponent = 63 - us.leading_zeros() as usize; // floor(log2), >= 2
    let step = ((us >> (exponent - 2)) & 3) as usize;
    (4 * (exponent - 1) + step).min(BUCKETS - 1)
}

/// Smallest value (µs) that lands in `index`.
pub fn bucket_lower(index: usize) -> u64 {
    if index < 4 {
        return index as u64;
    }
    let exponent = index / 4 + 1;
    let step = (index % 4) as u64;
    (4 + step) << (exponent - 2)
}

/// Largest value (µs) that lands in `index` (the last bucket is open-ended).
pub fn bucket_upper(index: usize) -> u64 {
    if index + 1 >= BUCKETS {
        return u64::MAX;
    }
    bucket_lower(index + 1) - 1
}

impl Histogram {
    pub fn record(&mut self, value: Duration) {
        self.record_us(u64::try_from(value.as_micros()).unwrap_or(u64::MAX));
    }

    pub fn record_us(&mut self, us: u64) {
        let index = bucket_index(us);
        self.counts[index] = self.counts[index].saturating_add(1);
        self.count += 1;
        self.sum_us = self.sum_us.saturating_add(us);
        self.max_us = self.max_us.max(us);
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn count(&self) -> u64 {
        self.count
    }

    pub fn max_us(&self) -> u64 {
        self.max_us
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn mean_us(&self) -> Option<u64> {
        (self.count > 0).then(|| self.sum_us / self.count)
    }

    /// Value at `quantile` (0.0–1.0), or `None` when nothing was recorded.
    /// Reported as the bucket's upper edge, capped at the observed maximum.
    pub fn percentile_us(&self, quantile: f64) -> Option<u64> {
        if self.count == 0 {
            return None;
        }
        let quantile = quantile.clamp(0.0, 1.0);
        // Rank of the sample we want, 1-based; ceil so p50 of 2 samples is the first.
        let rank = ((quantile * self.count as f64).ceil() as u64).max(1);
        let mut seen = 0_u64;
        for (index, count) in self.counts.iter().enumerate() {
            seen += u64::from(*count);
            if seen >= rank {
                return Some(bucket_upper(index).min(self.max_us));
            }
        }
        Some(self.max_us)
    }

    /// p50/p95/p99 in microseconds (0 when empty), for log fields.
    pub fn summary(&self) -> [u64; 3] {
        [0.50, 0.95, 0.99].map(|q| self.percentile_us(q).unwrap_or(0))
    }

    pub fn reset(&mut self) {
        *self = Self::default();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn buckets_are_contiguous_and_cover_the_range() {
        assert_eq!(bucket_lower(0), 0);
        for index in 0..BUCKETS - 1 {
            assert_eq!(
                bucket_upper(index) + 1,
                bucket_lower(index + 1),
                "gap at {index}"
            );
            assert_eq!(bucket_index(bucket_lower(index)), index);
            assert_eq!(bucket_index(bucket_upper(index)), index);
        }
        // About 4.2 s before the last bucket clamps.
        assert!(bucket_lower(BUCKETS - 1) > 3_000_000);
        assert_eq!(bucket_index(u64::MAX), BUCKETS - 1);
    }

    #[test]
    fn bucket_width_is_at_most_a_quarter() {
        for index in 4..BUCKETS - 1 {
            let lower = bucket_lower(index) as f64;
            let upper = bucket_upper(index) as f64;
            assert!(
                (upper - lower + 1.0) / lower <= 0.25 + f64::EPSILON,
                "{index}"
            );
        }
    }

    #[test]
    fn empty_histogram_has_no_percentiles() {
        let histogram = Histogram::default();
        assert_eq!(histogram.percentile_us(0.5), None);
        assert_eq!(histogram.mean_us(), None);
        assert_eq!(histogram.summary(), [0, 0, 0]);
    }

    #[test]
    fn single_value_is_exact_at_every_percentile() {
        let mut histogram = Histogram::default();
        histogram.record(Duration::from_micros(8_333));
        for quantile in [0.0, 0.5, 0.99, 1.0] {
            assert_eq!(histogram.percentile_us(quantile), Some(8_333));
        }
    }

    #[test]
    fn percentiles_of_uniform_samples_are_within_bucket_error() {
        let mut histogram = Histogram::default();
        for us in 1..=10_000 {
            histogram.record_us(us);
        }
        for (quantile, expected) in [(0.50, 5_000.0), (0.95, 9_500.0), (0.99, 9_900.0)] {
            let got = histogram.percentile_us(quantile).unwrap() as f64;
            assert!(got >= expected, "p{quantile}: {got} < {expected}");
            assert!(
                got <= expected * 1.25,
                "p{quantile}: {got} > {expected} + 25%"
            );
        }
        assert_eq!(histogram.count(), 10_000);
        assert_eq!(histogram.mean_us(), Some(5_000));
        assert_eq!(histogram.max_us(), 10_000);
    }

    #[test]
    fn tail_percentiles_see_a_few_slow_frames() {
        // 98 frames at ~8 ms and 2 at ~40 ms: p50 stays low, p99 shows the spike.
        let mut histogram = Histogram::default();
        for _ in 0..98 {
            histogram.record_us(8_000);
        }
        histogram.record_us(40_000);
        histogram.record_us(41_000);
        let [p50, p95, p99] = histogram.summary();
        assert!((8_000..=10_000).contains(&p50), "{p50}");
        assert!((8_000..=10_000).contains(&p95), "{p95}");
        assert!((40_000..=41_000).contains(&p99), "{p99}");
    }

    #[test]
    fn reset_clears_everything() {
        let mut histogram = Histogram::default();
        histogram.record_us(5);
        histogram.reset();
        assert_eq!(histogram.count(), 0);
        assert_eq!(histogram.percentile_us(0.5), None);
    }
}
