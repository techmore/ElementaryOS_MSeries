//! X11 keysym mapping for the keys a phone keyboard or toolbar can send.
//! Mirrors the vetted table in the earlier Python input adapter.

use crate::protocol::Modifier;

const NAMED: &[(&str, u32)] = &[
    ("Enter", 0xff0d),
    ("Backspace", 0xff08),
    ("Tab", 0xff09),
    ("Escape", 0xff1b),
    ("Delete", 0xffff),
    ("ArrowLeft", 0xff51),
    ("ArrowUp", 0xff52),
    ("ArrowRight", 0xff53),
    ("ArrowDown", 0xff54),
    ("Home", 0xff50),
    ("End", 0xff57),
    ("PageUp", 0xff55),
    ("PageDown", 0xff56),
];

/// Characters that may be typed: printable, plus newline and tab.
pub fn typeable(c: char) -> bool {
    c == '\n' || c == '\t' || (!c.is_control() && (c as u32) >= 32)
}

fn char_keysym(c: char) -> u32 {
    match c {
        '\n' => 0xff0d,
        '\t' => 0xff09,
        c if (c as u32) <= 0xff => c as u32,
        c => 0x0100_0000 | c as u32,
    }
}

/// Keysym for a key name (`Enter`, ...) or a single typeable character.
pub fn keysym(key: &str) -> Option<u32> {
    if let Some((_, sym)) = NAMED.iter().find(|(n, _)| *n == key) {
        return Some(*sym);
    }
    let mut chars = key.chars();
    match (chars.next(), chars.next()) {
        (Some(c), None) if typeable(c) => Some(char_keysym(c)),
        _ => None,
    }
}

/// Keysyms for each character of `text`.
pub fn text_keysyms(text: &str) -> Vec<u32> {
    text.chars()
        .filter(|c| typeable(*c))
        .map(char_keysym)
        .collect()
}

pub fn modifier_keysym(m: Modifier) -> u32 {
    match m {
        Modifier::Ctrl => 0xffe3,
        Modifier::Alt => 0xffe9,
        Modifier::Shift => 0xffe1,
        Modifier::Meta => 0xffeb,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_names_and_characters() {
        assert_eq!(keysym("Enter"), Some(0xff0d));
        assert_eq!(keysym("a"), Some(0x61));
        assert_eq!(keysym("é"), Some(0xe9));
        assert_eq!(keysym("€"), Some(0x0100_20ac));
        assert_eq!(keysym("ab"), None);
        assert_eq!(keysym("\u{7}"), None);
    }
}
