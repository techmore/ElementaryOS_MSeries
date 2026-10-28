//! Host daemon library: everything except `main`, so tests drive the real
//! controller and listener in-process.

pub mod backend;
pub mod client;
pub mod config;
pub mod controller;
#[cfg(feature = "dbus")]
pub mod dbus;
pub mod invite;
pub mod web;
