"""Setup regression tests: fresh layout, idempotency, and safe upgrades; no game launch."""
import importlib.util,json,shutil,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('workspace_setup',Path(__file__).with_name('setup.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SetupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='URL setup ');self.root=Path(self.tmp.name)
  src=self.root/'source';(src/'standalone').mkdir(parents=True);(src/'tools/workspace/templates').mkdir(parents=True)
  for name in ['profiles.yaml','defaults.yaml','handling.example.json']:shutil.copy2(m.ROOT/'source'/name,src/name)
  shutil.copy2(m.ROOT/'source/standalone/settings.yaml',src/'standalone/settings.yaml')
  for name in ['PLAY.bat','CAMLAB-PLAY.bat','CAMLAB-patch.ps1']:shutil.copy2(m.ROOT/'source/tools/workspace/templates'/name,src/'tools/workspace/templates'/name)
 def tearDown(self):self.tmp.cleanup()
 def test_initialize_preserves_edits_and_disables_unverified_candidate(self):
  cfg=m.initialize(self.root,Path('python.exe'))
  self.assertEqual(cfg['candidate'],'');self.assertTrue(all((self.root/d).is_dir() for d in m.DIRS))
  profiles=self.root/'apps/camlab/profiles.yaml';profiles.write_text('my edited camera')
  handling=self.root/'config/handling.json';handling.write_text('{"custom":true}')
  text=(self.root/'settings.yaml').read_text().replace('width: 1280','width: 3840');(self.root/'settings.yaml').write_text(text)
  m.initialize(self.root,Path('python.exe'))
  self.assertEqual(profiles.read_text(),'my edited camera');self.assertEqual(handling.read_text(),'{"custom":true}')
  self.assertIn('width: 3840',(self.root/'settings.yaml').read_text())
  self.assertIn('watchdog: off',(self.root/'settings.yaml').read_text())
 def test_install_backs_up_binary_and_preserves_content(self):
  m.initialize(self.root,Path('python.exe'));build=self.root/'scratchpad/build/native';mods=self.root/'scratchpad/build/mods'
  build.mkdir(parents=True);mods.mkdir(parents=True)
  game=self.root/'game/Rally';game.mkdir();(game/'Rally.exe').write_bytes(b'owner game');(game/'track.sbf').write_bytes(b'owner track')
  (self.root/'settings.exe').write_bytes(b'old settings')
  for name in ['launch.exe','settings.exe','watchdog.exe','dinput8.dll','SDL-LICENSE.txt','raylib-LICENSE.txt']:(build/name).write_bytes(b'new '+name.encode())
  (mods/'sr3mods.dll').write_bytes(b'new mods')
  m.install(self.root,build,mods)
  self.assertEqual((game/'track.sbf').read_bytes(),b'owner track')
  self.assertEqual((game/'Rally.exe').read_bytes(),b'owner game')
  self.assertEqual(next((self.root/'work').glob('setup-*/settings.exe')).read_bytes(),b'old settings')
  baseline=json.loads((self.root/'config/accepted-baseline.json').read_text())
  self.assertEqual(baseline['files']['sr3mods.dll'],m.digest(game/'sr3mods.dll'))
 def test_copy_refuses_existing_game(self):
  (self.root/'game/Rally').mkdir(parents=True)
  with self.assertRaisesRegex(ValueError,'already exists'):m.copy_game(self.root,self.root/'original',self.root/'build')
 def test_scalar_retains_other_settings(self):
  original='display:\n  width: 3840\npatches:\n  watchdog: on\n  custom: 7\n'
  result=m.scalar(original,'patches','watchdog','off')
  self.assertIn('custom: 7',result);self.assertIn('width: 3840',result);self.assertEqual(result.count('watchdog:'),1)
if __name__=='__main__':unittest.main()
