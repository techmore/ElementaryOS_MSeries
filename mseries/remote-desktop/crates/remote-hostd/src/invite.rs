//! Invite links and the QR the owner scans with the phone.

use std::net::IpAddr;

use qrcode::{Color, QrCode};
use serde::Serialize;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct Link {
    pub label: String,
    pub url: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct InviteInfo {
    pub links: Vec<Link>,
    /// QR of the first link, as rows of '0'/'1' (the GTK UI draws it with Cairo).
    pub qr: Vec<String>,
    pub expires_ms: u64,
    pub control_offered: bool,
}

fn label_for(ip: IpAddr) -> &'static str {
    match ip {
        IpAddr::V4(v4) => {
            let o = v4.octets();
            if o[0] == 100 && (64..=127).contains(&o[1]) {
                "Tailnet"
            } else if v4.is_private() {
                "Local network"
            } else {
                "Network"
            }
        }
        IpAddr::V6(_) => "Network",
    }
}

/// `base` addresses to offer. Tailnet first (encrypted by WireGuard), then LAN.
pub fn candidate_hosts(advertise: &[String]) -> Vec<(String, String)> {
    if !advertise.is_empty() {
        return advertise.iter().map(|h| ("Configured".to_string(), h.clone())).collect();
    }
    let mut out: Vec<(u8, String, String)> = Vec::new();
    for iface in if_addrs::get_if_addrs().unwrap_or_default() {
        let ip = iface.ip();
        if ip.is_loopback() || !ip.is_ipv4() {
            continue;
        }
        let label = label_for(ip);
        let rank = if label == "Tailnet" { 0 } else { 1 };
        out.push((rank, label.to_string(), ip.to_string()));
    }
    out.sort();
    out.into_iter().map(|(_, l, h)| (l, h)).collect()
}

pub fn build_links(hosts: &[(String, String)], port: u16, token: &str) -> Vec<Link> {
    hosts
        .iter()
        .map(|(label, host)| Link {
            label: label.clone(),
            // The secret rides in the fragment: it is never sent in an HTTP request line or logged.
            url: format!("http://{host}:{port}/#i={token}"),
        })
        .collect()
}

pub fn qr_rows(text: &str) -> Vec<String> {
    let Ok(code) = QrCode::new(text.as_bytes()) else {
        return Vec::new();
    };
    let w = code.width();
    code.to_colors()
        .chunks(w)
        .map(|row| row.iter().map(|c| if *c == Color::Dark { '1' } else { '0' }).collect())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn secret_is_in_the_fragment() {
        let links = build_links(&[("Tailnet".into(), "100.64.0.9".into())], 8484, "tok");
        assert_eq!(links[0].url, "http://100.64.0.9:8484/#i=tok");
    }

    #[test]
    fn qr_is_square_and_binary() {
        let rows = qr_rows("http://100.64.0.9:8484/#i=abcdefghijklmnopqrstuv");
        assert!(rows.len() >= 21);
        assert!(rows.iter().all(|r| r.len() == rows.len() && r.chars().all(|c| c == '0' || c == '1')));
    }

    #[test]
    fn tailnet_ranges_are_labelled() {
        assert_eq!(label_for("100.100.1.1".parse().unwrap()), "Tailnet");
        assert_eq!(label_for("192.168.1.2".parse().unwrap()), "Local network");
        assert_eq!(label_for("100.200.1.1".parse().unwrap()), "Network");
    }
}
