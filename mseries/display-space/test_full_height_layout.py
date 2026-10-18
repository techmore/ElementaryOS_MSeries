import copy
import unittest
import xml.etree.ElementTree as ET
from repair_full_height_layout import repair_monitors, repair_profiles


class SavedLayouts(unittest.TestCase):
    def test_profiles_preserve_vrr_and_external_mode(self):
        data = {'profiles': {'desk': {'match': ['tv'], 'layout': [
            {'scale': 2, 'x': 0, 'monitors': [{'key': 'builtin', 'mode': '3024x1890@120.000+vrr'}]},
            {'scale': 1, 'x': 1512, 'monitors': [{'key': 'tv', 'mode': '1920x1080@60.000'}]}]}}}
        old = copy.deepcopy(data)
        fixed = repair_profiles(data)
        self.assertEqual(fixed['profiles']['desk']['layout'][0]['monitors'][0]['mode'], '3024x1964@120.000+vrr')
        self.assertEqual(old['profiles']['desk']['layout'][1], fixed['profiles']['desk']['layout'][1])
        self.assertEqual(fixed, repair_profiles(copy.deepcopy(fixed)))

    def test_xml_repairs_only_stale_builtin_and_unsupported_scale(self):
        root = ET.fromstring('''<monitors><configuration><logicalmonitor><scale>1.5</scale><monitor>
        <monitorspec><connector>eDP-1</connector></monitorspec><mode><width>3024</width><height>1890</height>
        <rate>120</rate><ratemode>variable</ratemode></mode></monitor></logicalmonitor><logicalmonitor><scale>1</scale>
        <monitor><monitorspec><connector>DP-2</connector></monitorspec><mode><width>3024</width>
        <height>1890</height></mode></monitor></logicalmonitor></configuration></monitors>''')
        before = ET.tostring(root.findall('.//logicalmonitor')[1])
        repair_monitors(root)
        self.assertEqual(root.findtext('.//logicalmonitor/scale'), '2')
        self.assertEqual(root.findtext('.//mode/height'), '1964')
        self.assertEqual(root.findtext('.//mode/ratemode'), 'variable')
        self.assertEqual(before, ET.tostring(root.findall('.//logicalmonitor')[1]))
        once = ET.tostring(root)
        repair_monitors(root)
        self.assertEqual(once, ET.tostring(root))


if __name__ == '__main__':
    unittest.main()
