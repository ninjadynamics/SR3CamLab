import json
from pathlib import Path
import tempfile
import unittest
from frontend_catalog import build_catalog


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game/Rally'
        self.store = self.game / 'Main_release/tracks/_SR3Extras'
        self.store.mkdir(parents=True)

    def install(self, slot, directory):
        folder = self.game / 'Main_release' / ('tracks' if directory == 's' else 'track' + directory) / slot
        folder.mkdir(parents=True)
        for suffix in ['_master_gfx_xdata.sbf', '_master_xdata.sbf']:
            (folder / (slot.lower() + suffix)).touch()

    def write(self, name, value):
        (self.store / name).write_text(json.dumps(value))

    def test_shared_catalog_and_readiness(self):
        self.install('Tropical4', 's')
        self.install('Tropical4', '1')
        self.install('Desert4', '1')
        self.install('Desert4', '5')
        self.write('state.json', {'alts': {'Tropical4': [{'id': 'revo:tropical2', 'dir': '1'}]}})
        self.write('switch.json', {'slots': {
            'Tropical4': {'tracks': [{'title': 'Tropical 2', 'dir': '1'}]},
            'Desert4': {'tracks': [{'title': 'Mountain R4', 'dir': '1'},
                                  {'title': 'Daytona: Three Seven Speedway', 'dir': '5'}]}}})
        result = build_catalog(self.root)
        by_key = {t['key']: t for t in result['tracks']}
        self.assertEqual(by_key['Tropical4/1']['source_game'], 'revo')
        self.assertEqual(by_key['Desert4/1']['native_id'], by_key['Desert4/5']['native_id'])
        self.assertTrue(by_key['Desert4/1']['available'])
        self.assertEqual(by_key['Desert4/5']['status'], 'WIP')
        self.assertEqual(by_key['Desert4/1']['title'], 'SEGA Rally Championship - Mountain')
        self.assertEqual(by_key['Desert4/1']['source_id'], 'src:mountain')
        self.assertEqual(by_key['Desert4/5']['title'], 'Daytona: Three Seven Speedway')
        self.assertFalse(by_key['Canyon4/s']['available'])
        self.assertEqual([g['key'] for g in result['games'] if g['available']], ['src'])
        self.assertEqual(result['video_capacity'], 64)

    def test_explicit_future_game_origin(self):
        self.install('Lakeside4', '2')
        self.write('switch.json', {'slots': {'Lakeside4': {'tracks': [
            {'title': 'Future SR2 import', 'dir': '2', 'source_game': 'sr2', 'ready': True}]}}})
        result = build_catalog(self.root)
        self.assertTrue(result['games'][1]['available'])

    def test_reject_unsafe_or_ambiguous_identity(self):
        for item in [{'title': 'Unknown', 'dir': '1'},
                     {'title': 'Mountain', 'dir': '../1'},
                     {'title': 'Mountain', 'dir': '1', 'ready': 'yes'}]:
            self.write('switch.json', {'slots': {'Desert4': {'tracks': [item]}}})
            with self.assertRaises(ValueError):
                build_catalog(self.root)


if __name__ == '__main__':
    unittest.main()
