//! Host daemon library: everything except `main`, so tests drive the real
//! controller and listener in-process.

pub mod backend;
pub mod config;
pub mod controller;
pub mod invite;
pub mod web;
