from pathlib import Path
import tempfile,json,sys,contextlib,io
r=Path(r'F:\Jogos\Ultimate Race Lab')
sys.path.insert(0,str(r/'source/standalone'))
from pom_native_config import load,material_settings,verify
source=(r/'config/mountain-pom-depth.yaml').read_text()
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);(root/'config').mkdir()
    yaml=root/'config/mountain-pom-depth.yaml';yaml.write_text(source)
    receipt={'material_settings':material_settings(load(yaml)),'files':{}}
    (root/'config/pom-native-install.json').write_text(json.dumps(receipt))
    for text,accepted in [
        (source,True),
        (source.replace('global_depth_initial: 0.6','global_depth_initial: 0.3'),True),
        (source.replace('live_tuner: true','live_tuner: false'),True),
        (source.replace('tex_s1_x0000_y0512_128x128: 3','tex_s1_x0000_y0512_128x128: 4'),False),
        (source.replace('excluded_variants: tex_s1_x0000_y0000_256x256_c1A6','excluded_variants: different_variant'),False),
        (source.replace('global_depth_initial: 0.6','global_depth_initial: nan'),False),
        (source.replace('global_depth_initial: 0.6','global_depth_initial: 0.35'),False),
        (source.replace('fps_overlay: false','fps_overlay: true'),False),
    ]:
        yaml.write_text(text)
        try:
            with contextlib.redirect_stdout(io.StringIO()):verify(root)
        except (AssertionError,ValueError):
            assert not accepted
        else:assert accepted
print('PASS YAML receipt: global/live changes allowed; stale family/exclusion values and invalid controls rejected.')
