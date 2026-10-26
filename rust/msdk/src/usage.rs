//! Candidate usage-monitor data semantics. This module does not collect data,
//! authenticate providers, render a status control, or install a shell host.
//! Callers must use opaque identifiers and keep credentials out of these fields.

/// Stable keys distinguish a provider aggregate from a particular account at
/// a particular source. A remote server is not the same source as a local client.
#[derive(Clone, PartialEq, Eq, Hash)]
pub struct Scope {
    pub provider: String,
    pub source: Source,
    pub account: Option<String>,
}

impl std::fmt::Debug for Scope {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Scope")
            .field("source", &self.source)
            .field("has_account", &self.account.is_some())
            .finish_non_exhaustive()
    }
}

#[derive(Clone, PartialEq, Eq, Hash)]
pub enum Source {
    LocalClient,
    ProviderApi,
    Server(String),
}
impl std::fmt::Debug for Source {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(match self {
            Self::LocalClient => "LocalClient",
            Self::ProviderApi => "ProviderApi",
            Self::Server(_) => "Server(..)",
        })
    }
}

/// A missing value is not an observed zero. A failure may retain a stale value.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum State {
    Loading,
    Empty,
    Unknown,
    Fresh,
    Stale,
    Unavailable,
    Failed,
    Unsupported,
    Expired,
}

/// Percentages use basis points (0 through 10,000) to avoid rounding and
/// ambiguity between used and remaining. Conversion requires explicit units.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QuotaUnit {
    Used,
    Remaining,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Quota {
    basis_points: u16,
    unit: QuotaUnit,
    /// Source observation and optional reset in Unix seconds, never receipt time.
    observed_at: i64,
    reset_at: Option<i64>,
}

impl Quota {
    pub fn new(basis_points: u16, unit: QuotaUnit, observed_at: i64, reset_at: Option<i64>) -> Option<Self> {
        (basis_points <= 10_000).then_some(Self { basis_points, unit, observed_at, reset_at })
    }

    pub fn used_basis_points(self) -> u16 {
        match self.unit {
            QuotaUnit::Used => self.basis_points,
            QuotaUnit::Remaining => 10_000 - self.basis_points,
        }
    }

    pub fn remaining_basis_points(self) -> u16 {
        10_000 - self.used_basis_points()
    }

    pub fn observed_at(self) -> i64 {
        self.observed_at
    }

    /// An expired reset is not current capacity, even when the last read was
    /// successful. The caller must obtain a fresh source observation.
    pub fn state_at(self, source_state: State, now: i64) -> State {
        if source_state == State::Fresh && self.reset_at.is_some_and(|reset| reset <= now) {
            State::Expired
        } else {
            source_state
        }
    }
}

/// Source-defined token counts. Cached input and reasoning are subsets of input
/// and output respectively; neither is added again to the total.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Tokens {
    pub input: Option<u64>,
    pub output: Option<u64>,
    pub cached_input: Option<u64>,
    pub reasoning: Option<u64>,
}
impl Tokens {
    /// Return no total if either component is unknown or the sum overflows.
    pub fn total(self) -> Option<u64> {
        self.input?.checked_add(self.output?)
    }

    /// Reject contradictions where a declared subset exceeds its known parent.
    pub fn subsets_valid(self) -> bool {
        !matches!((self.cached_input, self.input), (Some(child), Some(parent)) if child > parent)
            && !matches!((self.reasoning, self.output), (Some(child), Some(parent)) if child > parent)
    }
}

/// Coverage describes whether a collector has observed the full scope it
/// promises. Partial is not interchangeable with a complete empty result.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Coverage {
    Complete,
    Partial,
    Unknown,
}

/// One provider aggregate or account at one source. Window identifiers are
/// stable within this observation and are not interpreted as account IDs.
#[derive(Clone)]
pub struct Observation {
    pub scope: Scope,
    pub state: State,
    pub observed_at: Option<i64>,
    pub windows: Vec<Window>,
    pub tokens: Option<Tokens>,
}

#[derive(Clone)]
pub struct Window {
    pub key: String,
    pub quota: Option<Quota>,
}

/// Versioned in-memory boundary, not a wire format or collector protocol.
/// Consumers can distinguish an empty complete collection from incomplete
/// coverage without deduplicating or summing overlapping sources implicitly.
pub struct Snapshot {
    pub coverage: Coverage,
    pub observations: Vec<Observation>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapshotError {
    EmptyIdentity,
    DuplicateScope,
    DuplicateWindow,
    FreshWithoutTimestamp,
    InvalidTokenSubset,
}

impl Snapshot {
    pub const VERSION: u32 = 1;

    /// Validate structural facts only. This does not prove provider coverage,
    /// authorize an account, or deduplicate overlapping upstream measurements.
    pub fn validate(&self) -> Result<(), SnapshotError> {
        let mut scopes = std::collections::HashSet::new();
        for observation in &self.observations {
            let scope = &observation.scope;
            if scope.provider.trim().is_empty()
                || scope.account.as_ref().is_some_and(|key| key.trim().is_empty())
                || matches!(&scope.source, Source::Server(key) if key.trim().is_empty())
            {
                return Err(SnapshotError::EmptyIdentity);
            }
            if !scopes.insert(scope) {
                return Err(SnapshotError::DuplicateScope);
            }
            if observation.state == State::Fresh && observation.observed_at.is_none() {
                return Err(SnapshotError::FreshWithoutTimestamp);
            }
            if observation.tokens.is_some_and(|tokens| !tokens.subsets_valid()) {
                return Err(SnapshotError::InvalidTokenSubset);
            }
            let mut windows = std::collections::HashSet::new();
            for window in &observation.windows {
                if window.key.trim().is_empty() {
                    return Err(SnapshotError::EmptyIdentity);
                }
                if !windows.insert(&window.key) {
                    return Err(SnapshotError::DuplicateWindow);
                }
            }
        }
        Ok(())
    }
}
