//! Monitor identity from a raw EDID, and detection of stale duplicate connectors.
//!
//! The native backend used to publish every monitor as `Apple:<connector>:Unknown`,
//! so the display-profile watcher (which matches `vendor:product:serial`) could
//! never recognise an attached monitor. This module parses the identity fields
//! the same way Mutter writes them to `monitors.xml`: the PNP vendor id, the
//! model-name descriptor (or the hex product code) and the serial-number
//! descriptor (or the hex numeric serial).
//!
//! It also decides which of several connectors carrying the same physical
//! monitor is the live one. After a Thunderbolt dock moves to another Type-C
//! PHY, the Apple DCP driver can leave the old DisplayPort connector reported
//! as connected with the old EDID while the new connector carries the same
//! monitor. Mapping both leaves a phantom output between the real screens.
//! Pure functions only, so it is unit tested without a display.

use std::collections::HashMap;
use std::hash::Hash;

const HEADER: [u8; 8] = [0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00];
const DESCRIPTOR_OFFSETS: [usize; 4] = [54, 72, 90, 108];
const TAG_SERIAL: u8 = 0xff;
const TAG_NAME: u8 = 0xfc;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EdidIdentity {
    /// Three-letter PNP manufacturer id, for example `AOC`.
    pub vendor: String,
    /// Model-name descriptor, else `0x` plus the 16-bit product code.
    pub product: String,
    /// Serial-number descriptor, else `0x` plus the 32-bit numeric serial.
    pub serial: String,
    /// True when the serial tells two units of the same model apart.
    /// Some panels and TVs report 0 or 0x01010101 for every unit.
    pub has_unique_serial: bool,
}

fn descriptor_text(block: &[u8]) -> String {
    block[5..18]
        .iter()
        .take_while(|byte| **byte != 0x0a)
        .filter(|byte| (0x20..0x7f).contains(*byte))
        .map(|byte| *byte as char)
        .collect::<String>()
        .trim()
        .to_owned()
}

/// Parse the identity fields of an EDID base block. Returns `None` when the
/// data is shorter than one block, lacks the EDID header, or has an invalid
/// manufacturer id. The checksum is not enforced: identity is advisory.
pub fn parse(edid: &[u8]) -> Option<EdidIdentity> {
    if edid.len() < 128 || edid[..8] != HEADER {
        return None;
    }
    let manufacturer = u16::from_be_bytes([edid[8], edid[9]]);
    let mut vendor = String::with_capacity(3);
    for shift in [10u16, 5, 0] {
        let letter = ((manufacturer >> shift) & 0x1f) as u8;
        if !(1..=26).contains(&letter) {
            return None;
        }
        vendor.push((b'A' + letter - 1) as char);
    }
    let product_code = u16::from_le_bytes([edid[10], edid[11]]);
    let numeric_serial = u32::from_le_bytes([edid[12], edid[13], edid[14], edid[15]]);

    let mut name = String::new();
    let mut serial_text = String::new();
    for offset in DESCRIPTOR_OFFSETS {
        let block = &edid[offset..offset + 18];
        if block[..3] != [0, 0, 0] {
            continue;
        }
        match block[3] {
            TAG_NAME if name.is_empty() => name = descriptor_text(block),
            TAG_SERIAL if serial_text.is_empty() => serial_text = descriptor_text(block),
            _ => {}
        }
    }

    let has_unique_serial =
        !serial_text.is_empty() || !matches!(numeric_serial, 0 | 0x0101_0101 | 0xffff_ffff);
    Some(EdidIdentity {
        vendor,
        product: if name.is_empty() {
            format!("0x{product_code:04x}")
        } else {
            name
        },
        serial: if serial_text.is_empty() {
            format!("0x{numeric_serial:08x}")
        } else {
            serial_text
        },
        has_unique_serial,
    })
}

#[derive(Clone, Debug)]
pub struct Candidate<K> {
    pub key: K,
    pub edid: Vec<u8>,
    /// Kernel property-blob id of the connector's EDID. Blob ids only grow, and
    /// the driver publishes a fresh blob when it re-reads the EDID on a
    /// (re)connect, so the larger id is the more recently connected connector.
    pub blob_id: u32,
    pub interface_id: u32,
}

/// Connectors that are stale copies of another connector's monitor.
///
/// Two connectors are the same monitor only when their EDIDs are byte
/// identical and carry a unit-unique serial; identical models with distinct
/// serials differ in the EDID bytes and are never merged. For each group the
/// connector with the newest EDID blob is kept; ties keep the lowest
/// interface id so the choice is stable. Everything else is returned.
pub fn stale_duplicates<K: Copy + Eq + Hash>(candidates: &[Candidate<K>]) -> Vec<K> {
    let mut groups: HashMap<&[u8], Vec<&Candidate<K>>> = HashMap::new();
    for candidate in candidates {
        if parse(&candidate.edid).is_some_and(|identity| identity.has_unique_serial) {
            groups
                .entry(candidate.edid.as_slice())
                .or_default()
                .push(candidate);
        }
    }
    let mut stale = Vec::new();
    for group in groups.into_values().filter(|group| group.len() > 1) {
        let keep = group
            .iter()
            .max_by_key(|candidate| (candidate.blob_id, std::cmp::Reverse(candidate.interface_id)))
            .expect("group has at least two candidates");
        stale.extend(
            group
                .iter()
                .filter(|candidate| candidate.key != keep.key)
                .map(|candidate| candidate.key),
        );
    }
    stale
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Base block of the AOC 24E2QA read from the dock on 2026-10-21.
    const AOC: &str = "00ffffffffffff0005e30224d34d00003223010380351e782a0ca5a5554ea0260e5054bfef00d1c0b30095008180814081c001010101023a801871382d40582c45000f282100001e000000ff00524a4c52434841303139393233000000fc003234453251410a202020202020000000fd00304b1e5512000a20202020202001a8";

    fn bytes(hex: &str) -> Vec<u8> {
        (0..hex.len())
            .step_by(2)
            .map(|i| u8::from_str_radix(&hex[i..i + 2], 16).unwrap())
            .collect()
    }

    fn blank(manufacturer: [u8; 2], product: u16, serial: u32) -> Vec<u8> {
        let mut edid = vec![0u8; 128];
        edid[..8].copy_from_slice(&HEADER);
        edid[8..10].copy_from_slice(&manufacturer);
        edid[10..12].copy_from_slice(&product.to_le_bytes());
        edid[12..16].copy_from_slice(&serial.to_le_bytes());
        edid
    }

    fn put_descriptor(edid: &mut [u8], slot: usize, tag: u8, text: &str) {
        let at = DESCRIPTOR_OFFSETS[slot];
        edid[at..at + 18].fill(0);
        edid[at + 3] = tag;
        let mut field = [0x20u8; 13];
        field[..text.len()].copy_from_slice(text.as_bytes());
        // A 13-character text fills the field and has no terminator.
        if text.len() < field.len() {
            field[text.len()] = 0x0a;
        }
        edid[at + 5..at + 18].copy_from_slice(&field);
    }

    #[test]
    fn parses_the_aoc_monitor_from_the_dock() {
        let identity = parse(&bytes(AOC)).expect("valid EDID");
        assert_eq!(identity.vendor, "AOC");
        assert_eq!(identity.product, "24E2QA");
        assert_eq!(identity.serial, "RJLRCHA019923");
        assert!(identity.has_unique_serial);
    }

    #[test]
    fn falls_back_to_hex_codes_without_descriptors() {
        // "INS" = 9,14,19 -> 0b0_01001_01110_10011 = 0x25d3.
        let edid = blank([0x25, 0xd3], 0x1234, 0x0101_0101);
        let identity = parse(&edid).expect("valid EDID");
        assert_eq!(identity.vendor, "INS");
        assert_eq!(identity.product, "0x1234");
        assert_eq!(identity.serial, "0x01010101");
        assert!(!identity.has_unique_serial);
    }

    #[test]
    fn descriptor_name_and_serial_override_the_codes() {
        let mut edid = blank([0x25, 0xd3], 0x1234, 0);
        put_descriptor(&mut edid, 0, TAG_NAME, "NS65DF710NA21");
        put_descriptor(&mut edid, 1, TAG_SERIAL, "ABC123");
        let identity = parse(&edid).expect("valid EDID");
        assert_eq!(identity.product, "NS65DF710NA21");
        assert_eq!(identity.serial, "ABC123");
        assert!(identity.has_unique_serial);
    }

    #[test]
    fn rejects_short_or_headerless_data_and_bad_vendor() {
        assert_eq!(parse(&[]), None);
        assert_eq!(parse(&bytes(AOC)[..100]), None);
        let mut no_header = bytes(AOC);
        no_header[0] = 0x01;
        assert_eq!(parse(&no_header), None);
        // Manufacturer letter 0 is not a valid PNP letter.
        assert_eq!(parse(&blank([0x00, 0x00], 1, 1)), None);
    }

    fn candidate(key: u32, edid: &[u8], blob_id: u32, interface_id: u32) -> Candidate<u32> {
        Candidate {
            key,
            edid: edid.to_vec(),
            blob_id,
            interface_id,
        }
    }

    #[test]
    fn newest_blob_wins_and_the_older_connector_is_stale() {
        // The incident: DP-2 (blob 88) is the leftover, DP-1 (blob 94) is live.
        let edid = bytes(AOC);
        let stale = stale_duplicates(&[candidate(77, &edid, 88, 2), candidate(74, &edid, 94, 1)]);
        assert_eq!(stale, vec![77]);
    }

    #[test]
    fn the_choice_follows_the_dock_back_to_the_first_connector() {
        let edid = bytes(AOC);
        let stale = stale_duplicates(&[candidate(77, &edid, 120, 2), candidate(74, &edid, 94, 1)]);
        assert_eq!(stale, vec![74]);
    }

    #[test]
    fn equal_blobs_keep_the_lowest_interface_id() {
        let edid = bytes(AOC);
        let stale = stale_duplicates(&[candidate(77, &edid, 90, 2), candidate(74, &edid, 90, 1)]);
        assert_eq!(stale, vec![77]);
    }

    #[test]
    fn different_units_of_one_model_are_never_merged() {
        let mut other = bytes(AOC);
        put_descriptor(&mut other, 1, TAG_SERIAL, "RJLRCHA000001");
        let first = bytes(AOC);
        assert!(
            stale_duplicates(&[candidate(1, &first, 10, 1), candidate(2, &other, 20, 2)])
                .is_empty()
        );
    }

    #[test]
    fn identical_monitors_without_a_unique_serial_are_left_alone() {
        let edid = blank([0x25, 0xd3], 0x1234, 0x0101_0101);
        assert!(
            stale_duplicates(&[candidate(1, &edid, 10, 1), candidate(2, &edid, 20, 2)]).is_empty()
        );
    }

    #[test]
    fn three_copies_leave_exactly_one() {
        let edid = bytes(AOC);
        let mut stale = stale_duplicates(&[
            candidate(1, &edid, 10, 1),
            candidate(2, &edid, 30, 2),
            candidate(3, &edid, 20, 3),
        ]);
        stale.sort_unstable();
        assert_eq!(stale, vec![1, 3]);
    }
}
