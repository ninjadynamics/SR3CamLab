"""Import an SR3 TeknoParrot XInput profile into the shared scalar YAML schema.

No dependency on PyYAML or TeknoParrot at runtime. Refuses unsupported active
features/bindings rather than silently claiming an equivalent configuration.
"""
import argparse
import configparser
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

BUTTONS = {1: 'dpad_up', 2: 'dpad_down', 4: 'dpad_left', 8: 'dpad_right',
           16: 'start', 32: 'back', 64: 'left_stick', 128: 'right_stick',
           256: 'left_shoulder', 512: 'right_shoulder', 4096: 'south',
           8192: 'east', 16384: 'west', 32768: 'north'}
AXES = {'IsLeftThumbX': 'left_x', 'IsLeftThumbY': 'left_y',
        'IsRightThumbX': 'right_x', 'IsRightThumbY': 'right_y',
        'IsLeftTrigger': 'left_trigger', 'IsRightTrigger': 'right_trigger'}

def binding(x, analog=False):
    if x is None:
        raise ValueError('Missing XInput mapping')
    if x.findtext('IsButton') == 'true':
        if analog:
            raise ValueError('Button-based analog input is not imported')
        code = int(x.findtext('ButtonCode', '0'))
        if code not in BUTTONS:
            raise ValueError(f'Unsupported XInput button mask {code}')
        return BUTTONS[code]
    axes = [name for flag, name in AXES.items() if x.findtext(flag) == 'true']
    if len(axes) != 1:
        raise ValueError('Expected one XInput axis')
    axis = axes[0]
    if analog or 'trigger' in axis:
        return axis
    minus = x.findtext('IsAxisMinus') == 'true'
    if axis.endswith('_y'):
        minus = not minus  # XInput Y+ points up; SDL Y- points up.
    return axis + ('_minus' if minus else '_plus')

def convert(profile, game_ini, game_path):
    root = ET.parse(profile).getroot()
    if root.findtext('ProfileName') != 'SR3':
        raise ValueError('Select the SR3 user profile')
    fields = {(f.findtext('CategoryName'), f.findtext('FieldName')): f.findtext('FieldValue', '')
              for f in root.findall('./ConfigValues/FieldInformation')}
    get = lambda name, default: fields.get(('General', name), default)
    if get('Input API', '') != 'XInput':
        raise ValueError('This importer supports XInput profiles; DirectInput GUID bindings require manual mapping')
    for key in [('General', 'Use Keyboard/Button For Axis'), ('General', 'Enable Outputs'),
                ('FFB Blaster', 'Enable'), ('Score', 'Enable Submission'), ('Score', 'Enable GUI'),
                ('Score', 'Enable Capture'), ('Score', 'Enable YouTube Upload')]:
        if fields.get(key, '0').lower() in ('1', 'true'):
            raise ValueError(f'Active feature is not supported by this runtime: {key}')
    ini = configparser.ConfigParser(inline_comment_prefixes=(';',))
    if game_ini:
        with Path(game_ini).open(encoding='utf-8-sig') as f:
            ini.read_file(f)
    number = lambda section, name, default: ini.getint(section, name, fallback=default)
    result = {'version': 1, 'launch': {'game_path': str(game_path).replace('\\', '/')},
              'display': {'width': int(get('ResolutionWidth', '1280')), 'height': int(get('ResolutionHeight', '720')),
                          'windowed': get('Windowed', '1') == '1', 'hud_adjust': get('InRace 2D Adjust', '0') == '1',
                          'vsync': bool(number('Graphics', 'VSync', 1)), 'refresh_rate': number('Graphics', 'RefreshRate', 60)},
              'game': {'freeplay': get('FreePlay', '1') == '1', 'language': get('Language', 'English'),
                       'music': number('Audio', 'MusicVolume', 80), 'sfx': number('Audio', 'SFXVolume', 70),
                       'voice': number('Audio', 'VoiceVolume', 80), 'attract_music': bool(number('Audio', 'AttractMusic', 1))},
              'input': {'controller': 0, 'deadzone': 0, 'threshold': 15000, 'background': False,
                        'steering': 'left_x', 'invert': False, 'gas': 'right_trigger', 'brake': 'left_trigger',
                        'start': 'none', 'view': 'none', 'handbrake': 'none', 'up': 'none', 'down': 'none', 'coin': 'none',
                        'dpad': False, 'curve': 'teknoparrot'}, 'runtime': {'cores': 4}}
    digital = {'Coin1': 'coin', 'P1ButtonStart': 'start', 'P1Button1': 'up',
               'P1Button2': 'down', 'P1Button3': 'view', 'P1Button4': 'handbrake'}
    analog = {'Analog0': 'steering', 'Analog2': 'gas', 'Analog4': 'brake'}
    indices = set()
    for item in root.findall('./JoystickButtons/JoystickButtons'):
        x = item.find('XInputButton')
        if x is None:
            continue
        mapping = item.findtext('InputMapping')
        if mapping not in digital and mapping not in analog:
            continue
        key = (digital | analog)[mapping]
        value = binding(x, mapping in analog)
        if key in ('gas', 'brake') and 'trigger' not in value:
            raise ValueError('Pedals mapped to stick axes require manual configuration')
        if key == 'steering' and 'trigger' in value:
            raise ValueError('Steering must use a stick axis')
        result['input'][key] = value
        # Wheel input ignores IsAxisMinus in TP. Y axes need a sign conversion.
        if key == 'steering':
            result['input']['invert'] = value.endswith('_y')
        indices.add(int(x.findtext('XInputIndex', '0')))
    if len(indices) != 1:
        raise ValueError('Expected all bindings on one controller')
    result['input']['controller'] = indices.pop()
    return result, fields

def yaml(data):
    def scalar(value):
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, int):
            return str(value)
        return "'" + value.replace("'", "''") + "'"
    lines = ['# Imported from your TeknoParrot SR3 profile. Edit with settings.exe.',
             '# Controls use SDL positions: south = Cross/A; Y minus = up.',
             '# XInput slot and SDL enumeration may differ with multiple controllers.']
    for section, value in data.items():
        if isinstance(value, dict):
            lines.append(section + ':')
            lines.extend(f'  {key}: {scalar(v)}' for key, v in value.items())
        else:
            lines.append(f'{section}: {scalar(value)}')
    return '\n'.join(lines) + '\n'

def render_import(data, existing=''):
    """Keep the suite's scalar patches section outside the TP import's scope."""
    lines = existing.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines)
              if re.match(r'^patches\s*:\s*(?:#.*)?$', line.rstrip('\r\n'))]
    if len(starts) > 1:
        raise ValueError('Duplicate patches sections; existing settings were not changed.')
    if starts:
        start = starts[0]
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].strip() and not lines[i][0].isspace()
                    and not lines[i].startswith('#')), len(lines))
        section = ''.join(lines[start:end]).rstrip() + '\n'
    else:
        suite = Path(__file__).resolve().parent.parent.as_posix().replace("'", "''")
        section = f"patches:\n  mod_folder: '{suite}'\n  watchdog: on\n"
    return yaml(data) + '\n' + section


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('profile', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--game-ini', type=Path)
    p.add_argument('--game-path', default='Rally.exe')
    args = p.parse_args()
    data, fields = convert(args.profile, args.game_ini, args.game_path)
    rendered = render_import(data, args.output.read_text(encoding='utf-8-sig')
                             if args.output.exists() else '')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        shutil.copy2(args.output, args.output.with_suffix('.yaml.before-import'))
    temp = args.output.with_suffix('.yaml.tmp')
    temp.write_text(rendered, encoding='utf-8')
    temp.replace(args.output)
    # Preserve the full source profile, including inactive TP-only options, for audit/re-import.
    shutil.copy2(args.profile, args.output.parent / 'teknoparrot-import.xml')
    report = {'source': str(args.profile.resolve()), 'settings': data,
              'original_options': {f'{a}/{b}': v for (a, b), v in fields.items()},
              'notes': ['TP online scores, uploads, FFB Blaster and outputs were disabled.',
                        'Keyboard axis sensitivities were inactive; native keyboard fallback remains available.',
                        'Game graphics/quality options not overridden here remain in the private game config.ini.',
                        'Controller index 0 selects the first SDL gamepad; multiple-device ordering can differ from XInput.']}
    args.output.with_name('settings-import.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Imported {args.output}')

if __name__ == '__main__':
    main()
