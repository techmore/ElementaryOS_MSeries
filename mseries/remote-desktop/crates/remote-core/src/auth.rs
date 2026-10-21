//! Invites (first pairing) and signed resume tokens (reconnect).
//!
//! * An **invite** is a 128-bit random, single-use, short-lived secret handed to
//!   the phone as a link/QR. Only its SHA-256 is stored, so lookup is by hash
//!   and there is no secret comparison to time.
//! * A **resume token** is `b64(claims).b64(HMAC-SHA256)` under a per-run key.
//!   It only re-attaches to the one live session it names, and dies with it.

use std::collections::HashMap;

use base64::engine::general_purpose::URL_SAFE_NO_PAD as B64;
use base64::Engine;
use hmac::{Hmac, Mac};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use subtle::ConstantTimeEq;

use crate::clock::Millis;

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum AuthError {
    #[error("invite unknown, used or expired")]
    InvalidInvite,
    #[error("too many pending invites")]
    TooManyInvites,
    #[error("too many failed attempts; try again later")]
    LockedOut,
    #[error("token malformed")]
    MalformedToken,
    #[error("token signature invalid")]
    BadSignature,
    #[error("token expired")]
    Expired,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Claims {
    pub sid: String,
    pub exp: Millis,
}

/// Per-run HMAC key. Never persisted: a host restart invalidates every token.
pub struct TokenKey([u8; 32]);

impl TokenKey {
    pub fn random() -> Self {
        Self(rand::random::<[u8; 32]>())
    }

    #[cfg(test)]
    pub fn fixed(b: u8) -> Self {
        Self([b; 32])
    }

    fn mac(&self, payload: &[u8]) -> HmacSha256 {
        let mut mac = HmacSha256::new_from_slice(&self.0).expect("HMAC accepts any key length");
        mac.update(payload);
        mac
    }

    pub fn issue(&self, claims: &Claims) -> String {
        let payload = serde_json::to_vec(claims).expect("claims serialise");
        let sig = self.mac(&payload).finalize().into_bytes();
        format!("{}.{}", B64.encode(&payload), B64.encode(sig))
    }

    pub fn verify(&self, token: &str, now: Millis) -> Result<Claims, AuthError> {
        let (p, s) = token.split_once('.').ok_or(AuthError::MalformedToken)?;
        let payload = B64.decode(p).map_err(|_| AuthError::MalformedToken)?;
        let sig = B64.decode(s).map_err(|_| AuthError::MalformedToken)?;
        // `verify_slice` is constant-time.
        self.mac(&payload)
            .verify_slice(&sig)
            .map_err(|_| AuthError::BadSignature)?;
        let claims: Claims = serde_json::from_slice(&payload).map_err(|_| AuthError::MalformedToken)?;
        if now >= claims.exp {
            return Err(AuthError::Expired);
        }
        Ok(claims)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InviteGrant {
    /// The owner may grant control for this invite (otherwise view-only only).
    pub allow_control: bool,
}

struct Invite {
    expires: Millis,
    allow_control: bool,
}

pub struct InviteStore {
    invites: HashMap<[u8; 32], Invite>,
    ttl_ms: Millis,
    max_pending: usize,
    failures: Vec<Millis>,
}

const FAIL_WINDOW_MS: Millis = 60_000;
const FAIL_LIMIT: usize = 8;

fn hash(token: &str) -> [u8; 32] {
    Sha256::digest(token.as_bytes()).into()
}

impl InviteStore {
    pub fn new(ttl_ms: Millis, max_pending: usize) -> Self {
        Self {
            invites: HashMap::new(),
            ttl_ms,
            max_pending,
            failures: Vec::new(),
        }
    }

    fn prune(&mut self, now: Millis) {
        self.invites.retain(|_, i| i.expires > now);
        self.failures.retain(|t| now.saturating_sub(*t) < FAIL_WINDOW_MS);
    }

    pub fn pending(&mut self, now: Millis) -> usize {
        self.prune(now);
        self.invites.len()
    }

    /// Returns the secret to embed in the link/QR.
    pub fn create(&mut self, now: Millis, allow_control: bool) -> Result<String, AuthError> {
        self.prune(now);
        if self.invites.len() >= self.max_pending {
            return Err(AuthError::TooManyInvites);
        }
        let token = B64.encode(rand::random::<[u8; 16]>());
        self.invites.insert(
            hash(&token),
            Invite {
                expires: now + self.ttl_ms,
                allow_control,
            },
        );
        Ok(token)
    }

    /// Single-use. Repeated failures lock redemption out for a minute so a
    /// guesser cannot enumerate the 128-bit space even in principle.
    pub fn redeem(&mut self, now: Millis, token: &str) -> Result<InviteGrant, AuthError> {
        self.prune(now);
        if self.failures.len() >= FAIL_LIMIT {
            return Err(AuthError::LockedOut);
        }
        let h = hash(token);
        // Equal-hash lookup; the explicit ct compare keeps this robust if the
        // map is ever replaced by a scan.
        let found = self.invites.keys().find(|k| bool::from(k.ct_eq(&h))).copied();
        match found.and_then(|k| self.invites.remove(&k)) {
            Some(inv) => Ok(InviteGrant {
                allow_control: inv.allow_control,
            }),
            None => {
                self.failures.push(now);
                Err(AuthError::InvalidInvite)
            }
        }
    }

    /// Revoke every outstanding invite (owner pressed "cancel").
    pub fn clear(&mut self) {
        self.invites.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn token_roundtrip_and_tamper() {
        let k = TokenKey::fixed(7);
        let t = k.issue(&Claims { sid: "s1".into(), exp: 1000 });
        assert_eq!(k.verify(&t, 10).unwrap().sid, "s1");
        assert_eq!(k.verify(&t, 1000), Err(AuthError::Expired));
        let other = TokenKey::fixed(8);
        assert_eq!(other.verify(&t, 10), Err(AuthError::BadSignature));
        let (p, s) = t.split_once('.').unwrap();
        let forged = format!("{}.{}", B64.encode(br#"{"sid":"s2","exp":99999}"#), s);
        assert_eq!(k.verify(&forged, 10), Err(AuthError::BadSignature));
        assert_eq!(k.verify(p, 10), Err(AuthError::MalformedToken));
        assert_eq!(k.verify("a.b", 10), Err(AuthError::MalformedToken));
    }

    #[test]
    fn invite_is_single_use_and_expires() {
        let mut s = InviteStore::new(1000, 4);
        let t = s.create(0, true).unwrap();
        assert!(s.redeem(10, &t).unwrap().allow_control);
        assert_eq!(s.redeem(11, &t), Err(AuthError::InvalidInvite));
        let t2 = s.create(0, false).unwrap();
        assert_eq!(s.redeem(1000, &t2), Err(AuthError::InvalidInvite));
    }

    #[test]
    fn pending_invites_are_capped() {
        let mut s = InviteStore::new(1000, 2);
        s.create(0, false).unwrap();
        s.create(0, false).unwrap();
        assert_eq!(s.create(0, false), Err(AuthError::TooManyInvites));
        assert_eq!(s.pending(2000), 0);
        assert!(s.create(2000, false).is_ok());
    }

    #[test]
    fn guessing_locks_out_even_the_right_invite() {
        let mut s = InviteStore::new(60_000, 4);
        let good = s.create(0, false).unwrap();
        for i in 0..FAIL_LIMIT {
            assert_eq!(s.redeem(i as u64, "wrong"), Err(AuthError::InvalidInvite));
        }
        assert_eq!(s.redeem(100, &good), Err(AuthError::LockedOut));
        // The window slides: after a minute the genuine invite (if unexpired) works.
        let mut s = InviteStore::new(600_000, 4);
        let good = s.create(0, false).unwrap();
        for i in 0..FAIL_LIMIT {
            let _ = s.redeem(i as u64, "wrong");
        }
        assert!(s.redeem(FAIL_WINDOW_MS + 100, &good).is_ok());
    }
}
