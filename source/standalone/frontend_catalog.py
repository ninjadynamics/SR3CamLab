"""Build the in-game frontend catalog from installed track metadata, never assets.

Quick Race and the Classic source-game pages consume the same slot/directory
identities. Adding a UI card must not create an arbitrary gameplay track ID.
"""
import argparse
import json
from pathlib import Path
import re

SLOTS = {'Tropical4': 0, 'Canyon4': 1, 'Alpine4': 2,
         'Lakeside4': 3, 'Desert4': 4, 'Stadium4': 5}
GAMES = [('src', 'SEGA Rally Championship'), ('sr2', 'SEGA Rally 2'),
         ('daytona', 'Daytona USA'), ('daytona2', 'Daytona USA 2'), ('scud', 'Scud Race')]
GAME_PREVIEWS = {key: f'URL_GAME_{key.upper()}.wmv' for key, _ in GAMES}
GAME_IDS = {key for key, _ in GAMES} | {'sr3', 'revo'}
# What the menus show, by internal source id. Installers, tunes and switch.json
# keep the internal title: they find a track by it.
LABELS = {'src:mountain': 'SEGA Rally Championship - Mountain'}


def read(path, default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else default


def installed(folder, slot):
    names = {p.name.lower() for p in folder.iterdir() if p.is_file()} if folder.is_dir() else set()
    return (f'{slot.lower()}_master_gfx_xdata.sbf' in names and
            f'{slot.lower()}_master_xdata.sbf' in names)


def video(videos, suffix, classic=False):
    if not suffix or not re.fullmatch(r'[A-Za-z0-9]{1,8}', suffix):
        return ''
    if classic:
        name = f'classic_{suffix}.wmv'
        return name if (videos / name).is_file() else ''
    choices = sorted(p.name for p in videos.glob(f'LANG_*_{suffix}.wmv'))
    english = f'LANG_ENGLISH_{suffix}.wmv'
    return english if english in choices else choices[0] if choices else ''


def build_catalog(root):
    game = Path(root) / 'game/Rally'
    store = game / 'Main_release/tracks/_SR3Extras'
    videos = game / 'frontend/PC/Videos'
    state = read(store / 'state.json', {})
    switch = read(store / 'switch.json', {})
    origins = {}
    for slot, entries in state.get('alts', {}).items():
        for entry in entries:
            origins[(slot, str(entry.get('dir')))] = entry
    rows, keys = [], set()

    def add(slot, directory, title, source_game, preview='', ready=True, source_id=''):
        if slot not in SLOTS or not re.fullmatch(r'[s1-9]', directory):
            raise ValueError('Invalid installed track identity: ' + slot + '/' + directory)
        if source_game not in GAME_IDS:
            raise ValueError('Unknown source game: ' + source_game)
        key = slot + '/' + directory
        if key in keys:
            raise ValueError('Duplicate installed track identity: ' + key)
        keys.add(key)
        folder = game / 'Main_release' / ('tracks' if directory == 's' else 'track' + directory) / slot
        exists = installed(folder, slot)
        available = bool(ready and exists)
        rows.append(dict(key=key, source_id=source_id or key, title=LABELS.get(source_id, title), source_game=source_game,
                         slot=slot, native_id=SLOTS[slot], directory=directory, video=preview,
                         available=available, status='Ready' if available else 'Not installed' if not exists else 'WIP'))

    for slot, title, code in [('Tropical4', 'Tropical', 'TRO'), ('Canyon4', 'Canyon', 'CAN'),
                              ('Alpine4', 'Alpine', 'ALP')]:
        add(slot, 's', title, 'sr3', video(videos, code))

    for slot, group in switch.get('slots', {}).items():
        for item in group.get('tracks', []):
            directory = str(item.get('dir', ''))
            origin = origins.get((slot, directory), {})
            source_id = str(origin.get('id', ''))
            source_game = item.get('source_game') or origin.get('source_game') or source_id.partition(':')[0]
            # Current Classic installations predate origin metadata. These two
            # explicitly identified imports are the compatibility migration.
            title = str(item.get('title', ''))
            if not source_game and slot == 'Desert4' and title.lower().startswith('mountain'):
                source_game, source_id = 'src', 'src:mountain'
            if not source_game and slot == 'Desert4' and title.lower().startswith('daytona:'):
                source_game, source_id = 'daytona', 'daytona:three-seven-speedway'
            if not source_game:
                raise ValueError('Source game metadata needed for ' + slot + '/' + directory)
            # Owner explicitly deferred the current Daytona prototype. New
            # imports can declare readiness in their metadata when accepted.
            ready = item.get('ready', source_game != 'daytona')
            if type(ready) is not bool:
                raise ValueError('Track readiness must be boolean: ' + title)
            add(slot, directory, title, source_game,
                video(videos, str(item.get('video', '')), classic=slot == 'Desert4'),
                ready, source_id)
    if len(rows) > 128:
        raise ValueError('Frontend catalog exceeds 128 records; add pagination before extending it')
    games = []
    for key, title in GAMES:
        tracks = [row for row in rows if row['source_game'] == key]
        available = sum(row['available'] for row in tracks)
        dedicated = GAME_PREVIEWS[key]
        preview = dedicated if (videos / dedicated).is_file() else next((row['video'] for row in tracks if row['available'] and row['video']), '')
        games.append(dict(key=key, title=title, available=bool(available), video=preview,
                          status='Ready' if available else 'WIP' if tracks else 'Not installed'))
    return dict(version=1, video_capacity=64, games=games, tracks=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    catalog = build_catalog(args.workspace)
    out = args.out or args.workspace / 'config/frontend-tracks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')
    print(f"Catalog: {len(catalog['tracks'])} tracks, {sum(x['available'] for x in catalog['tracks'])} ready; {out}")


if __name__ == '__main__':
    main()
