#!/usr/bin/python3
import unittest
from full_height_boot import prepare, without_managed, BEGIN

CMD = 'BOOT_IMAGE=/vmlinuz-test root=UUID=root cryptdevice=UUID=luks:root loglevel=7 appledrm.show_notch=0 rootflags=subvol=@elementary rw'
CFG = '''# Existing custom config
menuentry 'elementary safe' --id elementary-safe {
    search --fs-uuid --set=root BOOT-UUID
    linux /vmlinuz-test root=UUID=root cryptdevice=UUID=luks:root loglevel=7 appledrm.show_notch=0 rootflags=subvol=@elementary rw
    initrd /initrd-test
}
menuentry 'recovery' --id recovery {
    linux /vmlinuz-other root=UUID=root rootflags=subvol=@elementary rw
    initrd /initrd-other
}
# Existing one-shot trial fallback stays intact
if [ "${boot_once}" != "true" ]; then
    set default="elementary-safe"
fi
'''


class BootTests(unittest.TestCase):
    def test_same_kernel_initrd_and_encryption(self):
        result = prepare(CFG, CMD)
        added = result[result.index(BEGIN):]
        self.assertIn('linux /vmlinuz-test root=UUID=root cryptdevice=UUID=luks:root', added)
        self.assertIn('initrd /initrd-test', added)
        self.assertIn('appledrm.show_notch=1', added)
        self.assertNotIn('appledrm.show_notch=0', added)
        self.assertTrue(result.startswith(CFG.rstrip()))
        self.assertIn('"${boot_once}" != "true"', added)
        self.assertNotIn('next_entry=', result)

    def test_repeated_install_is_identical(self):
        first = prepare(CFG, CMD)
        self.assertEqual(first, prepare(first, CMD))

    def test_reinstall_from_full_height_boot(self):
        first = prepare(CFG, CMD)
        self.assertEqual(first, prepare(first, CMD.replace('show_notch=0', 'show_notch=1')))

    def test_remove_preserves_every_original_entry(self):
        self.assertEqual(without_managed(prepare(CFG, CMD)).rstrip(), CFG.rstrip())

    def test_no_guessing(self):
        for command in (CMD.replace('/vmlinuz-test', '/missing'), CMD.replace('BOOT_IMAGE=', 'UNKNOWN='),
                        CMD.replace('subvol=@elementary', 'subvol=@'), CMD.replace('loglevel=7', 'loglevel=3')):
            with self.subTest(command=command), self.assertRaises(ValueError):
                prepare(CFG, command)

    def test_duplicate_match_refused(self):
        with self.assertRaises(ValueError):
            prepare(CFG + CFG, CMD)

    def test_missing_initrd_refused(self):
        with self.assertRaises(ValueError):
            prepare(CFG.replace('    initrd /initrd-test\n', ''), CMD)

    def test_damaged_managed_block_refused(self):
        with self.assertRaises(ValueError):
            prepare(CFG + BEGIN, CMD)


if __name__ == '__main__':
    unittest.main()
