import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from import_settings import binding, convert, yaml

class ImportTests(unittest.TestCase):
    def axis(self, name, minus=False):
        return ET.fromstring(f'<XInputButton><{name}>true</{name}><IsAxisMinus>{str(minus).lower()}</IsAxisMinus></XInputButton>')

    def test_y_direction_converts_xinput_to_sdl(self):
        self.assertEqual(binding(self.axis('IsRightThumbY')), 'right_y_minus')
        self.assertEqual(binding(self.axis('IsRightThumbY', True)), 'right_y_plus')
        self.assertEqual(binding(self.axis('IsRightThumbX', True)), 'right_x_minus')
        self.assertEqual(binding(self.axis('IsLeftThumbX', True), True), 'left_x')

    def test_buttons_and_triggers(self):
        self.assertEqual(binding(ET.fromstring('<XInputButton><IsButton>true</IsButton><ButtonCode>4096</ButtonCode></XInputButton>')), 'south')
        self.assertEqual(binding(self.axis('IsRightTrigger')), 'right_trigger')
        with self.assertRaises(ValueError):
            binding(ET.fromstring('<XInputButton><IsButton>true</IsButton><ButtonCode>48</ButtonCode></XInputButton>'))

    def test_import_requires_supported_active_features(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'profile.xml'
            p.write_text('<GameProfile><ProfileName>SR3</ProfileName><ConfigValues><FieldInformation><CategoryName>General</CategoryName><FieldName>Input API</FieldName><FieldValue>DirectInput</FieldValue></FieldInformation></ConfigValues></GameProfile>')
            with self.assertRaisesRegex(ValueError, 'XInput'):
                convert(p, None, 'Rally.exe')

    def test_yaml_quotes_paths(self):
        self.assertIn("game_path: 'C:/Bruno''s games/Rally.exe'", yaml({'launch': {'game_path': "C:/Bruno's games/Rally.exe"}}))

if __name__ == '__main__':
    unittest.main()
