#!/usr/bin/python3
"""Local ROM library, mGBA launcher and on-demand public cheat lookup."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
import cheat_finder

HOME = Path.home()
BASE = HOME / 'Games' / 'Game Boy'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config')) / 'game-boy-hub' / 'library.json'
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'game-boy-hub'
ROM_EXT = {'.gba': 'GBA', '.gb': 'GB', '.gbc': 'GBC'}
PATCH_EXT = {'.ips', '.ups', '.bps'}

def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

@contextmanager
def config_lock():
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with (CONFIG.parent / 'library.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield

def load_config():
    if CONFIG.exists():
        config = json.loads(CONFIG.read_text())
        if not isinstance(config, dict):
            raise ValueError('Library settings must be a JSON object.')
    else:
        config = {}
    defaults = {'folders': [str(BASE / 'ROMs')], 'favorites': [], 'recent': [],
                'patches': {}, 'cheatImports': {}, 'speed': 4, 'rewind': True, 'fullscreen': False}
    return defaults | config

def game_info(path):
    suffix = path.suffix.lower()
    if suffix in ROM_EXT:
        return {'system': ROM_EXT[suffix], 'title': path.stem, 'member': ''}
    if suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            games = [i for i in archive.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in ROM_EXT]
            if not games:
                return None
            if len(games) != 1:
                raise ValueError(f'{path.name}: contains {len(games)} ROMs. Extract them into a library folder to choose each game.')
            member = games[0]
            if member.file_size > 64 * 1024 * 1024:
                raise ValueError(f'{path.name}: ROM is larger than 64 MiB.')
            return {'system': ROM_EXT[Path(member.filename).suffix.lower()],
                    'title': Path(member.filename).stem, 'member': member.filename}
    if suffix == '.7z':
        # mGBA supports 7z directly; extraction/selection remains in mGBA.
        return {'system': 'Archive', 'title': path.stem, 'member': ''}
    return None

def scan(config):
    games, warnings, seen = [], [], set()
    recent = {p: i for i, p in enumerate(config['recent'])}
    for folder in config['folders']:
        directory = Path(folder).expanduser()
        if not directory.is_dir():
            warnings.append(f'Folder unavailable: {directory}')
            continue
        def walk_error(error):
            warnings.append(str(error))
        for current, dirs, files in os.walk(directory, followlinks=False, onerror=walk_error):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            for name in sorted(files):
                path = Path(current) / name
                if path.suffix.lower() not in {*ROM_EXT, '.zip', '.7z'}:
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                try:
                    info = game_info(path)
                    if info:
                        games.append(info | {'path': key, 'favorite': key in config['favorites'],
                                             'recent': recent.get(key, -1), 'patch': config['patches'].get(key, '')})
                except (OSError, ValueError, zipfile.BadZipFile) as error:
                    warnings.append(str(error))
    games.sort(key=lambda g: g['title'].casefold())
    return {'games': games, 'warnings': warnings, 'settings': config,
            'installed': bool(shutil.which('mgba-qt')), 'base': str(BASE)}

def game_directory(path, patch=''):
    identity = str(path.resolve()) + ('\n' + str(Path(patch).resolve()) if patch else '')
    tag = hashlib.sha256(identity.encode()).hexdigest()[:12]
    label = re.sub(r'[^\w .-]', '', path.stem)[:65].strip() or 'Game'
    if patch:
        label += ' - ' + re.sub(r'[^\w .-]', '', Path(patch).stem)[:40]
    return BASE / 'Saves' / f'{label}-{tag}'

def launch_command(path, config):
    emulator = shutil.which('mgba-qt')
    if not emulator:
        raise ValueError('mGBA is not installed. Install the mgba-qt package first.')
    command = [emulator, '-4']
    options = {'fastForwardRatio': config['speed'], 'fastForwardHeldRatio': config['speed'],
               'rewindEnable': int(config['rewind']), 'rewindBufferCapacity': 600,
               'rewindBufferInterval': 1, 'lockAspectRatio': 1, 'interframeBlending': 0,
               'resampleVideo': 0, 'suspendScreensaver': 1,
               'cheatAutoload': 1, 'cheatAutosave': 1}
    if config['fullscreen']:
        command.append('-f')
    if path:
        path = path.expanduser().resolve()
        if not path.is_file() or not game_info(path):
            raise ValueError('Choose an existing GB, GBC, GBA, ZIP or 7z ROM.')
        patch = config['patches'].get(str(path), '')
        if patch and (not Path(patch).is_file() or Path(patch).suffix.lower() not in PATCH_EXT):
            raise ValueError('The selected patch is missing or unsupported. Clear it or choose another.')
        save_dir = game_directory(path, patch)
        save_dir.mkdir(parents=True, exist_ok=True)
        # Copy existing battery saves and cheats once, never replace either.
        if not patch:
            info = game_info(path)
            stems = {path.stem, Path(info['member']).stem if info['member'] else path.stem}
            for stem in stems:
                for extension in ('.sav', '.cht', '.cheats'):
                    source = path.parent / (stem + extension)
                    target = save_dir / ((path.stem + extension) if extension == '.cheats' else source.name)
                    if source.is_file() and not target.exists():
                        shutil.copy2(source, target)
        apply_cheat_import(path, patch, save_dir, config)
        for key in ('savegamePath', 'savestatePath', 'cheatsPath'):
            options[key] = str(save_dir)
        screenshots = BASE / 'Screenshots'
        screenshots.mkdir(parents=True, exist_ok=True)
        options['screenshotPath'] = str(screenshots)
        atomic_json(save_dir / 'game.json', {'rom': str(path), 'patch': patch})
        if patch:
            command.extend(['-p', patch])
    for key, value in options.items():
        command.extend(['-C', f'{key}={value}'])
    if path:
        command.append(str(path))
    return command

def apply_cheat_import(path, patch, save_dir, config):
    record = config.get('cheatImports', {}).get(str(path) + '\n' + patch)
    if not record:
        return
    marker = save_dir / 'cheat-import.json'
    if marker.exists() and json.loads(marker.read_text()).get('sha256') == record['sha256']:
        return  # Preserve edits and enabled states saved by mGBA after first import.
    source = Path(record['file'])
    content = source.read_bytes()
    if hashlib.sha256(content).hexdigest() != record['sha256']:
        raise ValueError('The staged cheat file changed. Find and import the codes again.')
    target = save_dir / (path.stem + '.cheats')
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + '.backup-' + str(time.time_ns())))
    cheat_finder.atomic_write(target, content)
    atomic_json(marker, record)

def launch(path, config):
    command = launch_command(path, config)
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'emulator.log').open('ab') as log:
        process = subprocess.Popen(command, cwd=BASE, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=log, start_new_session=True)
    time.sleep(0.7)
    if process.poll() is not None:
        raise ValueError(f'mGBA exited during startup. See {STATE / "emulator.log"}.')
    if path:
        key = str(path.expanduser().resolve())
        with config_lock():
            fresh = load_config()
            fresh['recent'] = [key] + [p for p in fresh['recent'] if p != key][:29]
            atomic_json(CONFIG, fresh)
    return {'ok': True, 'pid': process.pid}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['scan', 'launch', 'favorite', 'setting', 'add-folder', 'remove-folder', 'patch', 'folder',
                                         'cheats-find', 'cheats-preview', 'cheats-import'])
    parser.add_argument('values', nargs='*')
    args = parser.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / 'ROMs').mkdir(exist_ok=True)
    values = args.values
    if args.action.startswith('cheats-'):
        config = load_config()
        rom = Path(values[0]).expanduser().resolve()
        info = game_info(rom)
        if not rom.is_file() or not info:
            raise ValueError('Select a ROM first.')
        patch = config['patches'].get(str(rom), '')
        finder = cheat_finder.Finder(STATE / 'cheat-cache')
        if args.action == 'cheats-find':
            found = finder.find(rom, info, game_directory(rom, patch), BASE, bool(patch))
            result = {'cheatResult': found}
        elif args.action == 'cheats-preview':
            result = {'cheatResult': finder.preview(rom, values[1])}
        else:
            exported = finder.export(rom, values[1], values[2].split(','), BASE / 'Cheats' / 'Imported')
            with config_lock():
                fresh = load_config()
                fresh['cheatImports'][str(rom) + '\n' + patch] = exported
                atomic_json(CONFIG, fresh)
            result = {'cheatMessage': f'{exported["count"]} codes imported, all off. They load on your next launch from the Hub. '
                      f'For a running game: Tools → Cheats → Load this file: {exported["file"]}'}
    elif args.action == 'scan':
        result = scan(load_config())
    elif args.action == 'launch':
        result = launch(Path(values[0]) if values else None, load_config())
    elif args.action == 'folder':
        allowed = {'roms': BASE / 'ROMs', 'saves': BASE / 'Saves', 'screenshots': BASE / 'Screenshots'}
        target = allowed[values[0]]
        target.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(['xdg-open', str(target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        result = {'ok': True}
    else:
        with config_lock():
            config = load_config()
            if args.action == 'favorite':
                key = str(Path(values[0]).expanduser().resolve())
                if key in config['favorites']:
                    config['favorites'].remove(key)
                else:
                    config['favorites'].append(key)
            elif args.action == 'setting':
                key, value = values
                if key == 'speed' and value in ('2', '4', '8', '-1'):
                    config[key] = int(value)
                elif key in ('rewind', 'fullscreen') and value in ('true', 'false'):
                    config[key] = value == 'true'
                else:
                    raise ValueError('Unsupported setting or value.')
            elif args.action in ('add-folder', 'remove-folder'):
                folder = str(Path(values[0]).expanduser().resolve())
                if args.action == 'add-folder':
                    if not Path(folder).is_dir():
                        raise ValueError('That folder does not exist.')
                    if folder not in config['folders']:
                        config['folders'].append(folder)
                else:
                    config['folders'] = [p for p in config['folders'] if p != folder]
            elif args.action == 'patch':
                key = str(Path(values[0]).expanduser().resolve())
                if len(values) > 1 and values[1]:
                    patch = Path(values[1]).expanduser().resolve()
                    if not patch.is_file() or patch.suffix.lower() not in PATCH_EXT:
                        raise ValueError('Choose an IPS, UPS or BPS patch.')
                    config['patches'][key] = str(patch)
                else:
                    config['patches'].pop(key, None)
            atomic_json(CONFIG, config)
        result = scan(config)
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, IndexError, zipfile.BadZipFile) as error:
        print(json.dumps({'error': str(error)}))
        sys.exit(1)
