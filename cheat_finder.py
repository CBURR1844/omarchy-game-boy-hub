"""Public database lookup by local ROM hash; no ROM content is uploaded."""
import hashlib
import html
import json
from pathlib import Path
import re
import tempfile
import os
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile

SYSTEMS = {'GB': 'Nintendo - Game Boy', 'GBC': 'Nintendo - Game Boy Color', 'GBA': 'Nintendo - Game Boy Advance'}
RAW = 'https://raw.githubusercontent.com/libretro/libretro-database/'
TREE = 'https://api.github.com/repos/libretro/libretro-database/git/trees/master?recursive=1'

def atomic_write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.cheat-')
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(payload)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

def read_bounded(path):
    with path.open('rb') as stream:
        content = stream.read(4 * 1024 * 1024 + 1)
    if len(content) > 4 * 1024 * 1024:
        raise ValueError('Cheat file is larger than 4 MiB.')
    return content.decode('utf-8-sig')

def normalized(title):
    title = re.sub(r'\([^)]*\)|\[[^]]*\]', '', title)
    title = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', title.lower())

def regions(title):
    return set(re.findall(r'\b(USA|Europe|Japan|World|Australia|Germany|France|Spain|Italy|Korea|China)\b', title))

def revision(title):
    found = re.search(r'\((Rev [^)]*|v\d[^)]*)\)', title, re.I)
    return found.group(1).lower() if found else ''

def matching(title, candidate):
    if normalized(title) != normalized(candidate):
        return False
    a, b = regions(title), regions(candidate)
    return bool(a & b or 'World' in a | b) and revision(title) == revision(candidate)

def rom_hash(path, info):
    archive = None
    try:
        if info['member']:
            archive = zipfile.ZipFile(path)
            stream = archive.open(info['member'])
        elif path.suffix.lower() == '.7z':
            raise ValueError('Extract this 7z ROM into your library to identify it for cheats.')
        else:
            stream = path.open('rb')
        digest, size = hashlib.sha1(), 0
        with stream:
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
                if size > 64 * 1024 * 1024:
                    raise ValueError('ROM is larger than 64 MiB.')
                digest.update(chunk)
        return digest.hexdigest()
    finally:
        if archive:
            archive.close()

def identify(dat, digest):
    for block in re.findall(r'game\s*\(\s*\n(.*?)\n\)', dat, re.S):
        if re.search(r'\bsha1\s+' + re.escape(digest) + r'\b', block, re.I):
            return re.search(r'\bname\s+"([^"]+)"', block).group(1)
    return ''

def parse_codes(text, system, source_name=''):
    """Convert valid device codes to native mGBA sets; skip incomplete sets."""
    entries, skipped = [], 0
    if re.search(r'^\s*cheats\s*=', text, re.M):
        fields = {}
        for line in text.splitlines():
            found = re.match(r'\s*cheat(\d+)_(desc|code|handler)\s*=\s*(.*?)\s*$', line)
            if not found:
                continue
            index, key, value = found.groups()
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1].replace('\\"', '"').replace('\\\\', '\\')
            fields.setdefault(int(index), {})[key] = value
        if len(fields) > 20000:
            raise ValueError('Cheat list exceeds 20,000 entries.')
        for _, item in sorted(fields.items()):
            if item.get('handler', '0') != '0' or not item.get('code'):
                skipped += 1
                continue
            parts = [p.strip() for p in item['code'].split('+')]
            # Some databases split the two halves of GBA codes with '+'.
            if system == 'GBA' and parts and all(re.fullmatch(r'[0-9a-fA-F]{4,8}', p) for p in parts):
                if len(parts) % 2:
                    skipped += 1
                    continue
                parts = [' '.join(parts[i:i+2]) for i in range(0, len(parts), 2)]
            directive = []
            if system == 'GBA':
                if '(Action Replay)' in source_name or '(Pro Action Replay)' in source_name:
                    directive = ['PARv3']
                elif '(GameShark)' in source_name:
                    directive = ['GSAv1']
            entries.append({'name': html.unescape(item.get('desc', 'Unnamed code')), 'lines': parts, 'directives': directive})
    else:
        current, directives = None, []
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line == '!reset':
                directives = []
            elif line.startswith('!'):
                if line[1:] != 'disabled':
                    if line[1:] not in ('GSAv1', 'GSAv1 raw', 'PARv3', 'PARv3 raw'):
                        raise ValueError('Unsupported native cheat directive: ' + line)
                    directives.append(line[1:])
            elif line.startswith('#'):
                current = {'name': line.lstrip('# ').strip(), 'lines': [], 'directives': list(directives)}
                entries.append(current)
            elif current is not None:
                current['lines'].append(line)
            else:
                raise ValueError('This is not a supported mGBA or Libretro cheat file.')
    pattern = (r'(?:[0-9A-F]{8}\s+[0-9A-F]{4}(?:[0-9A-F]{4})?|[0-9A-F]{8}:[0-9A-F]{2,8})'
               if system == 'GBA' else r'(?:[0-9A-F]{8}|[0-9A-F]{3}-[0-9A-F]{3}(?:-[0-9A-F]{3})?)')
    valid = []
    for entry in entries:
        lines = [line.upper() for line in entry['lines']]
        if not lines or not all(re.fullmatch(pattern, line) for line in lines):
            skipped += 1
            continue
        entry['lines'] = lines
        entry['name'] = re.sub(r'[\x00-\x1f\x7f]', ' ', entry['name'])[:160]
        entry['id'] = str(len(valid))
        valid.append(entry)
    return valid, skipped

def native_text(entries):
    output = []
    for entry in entries:
        output.extend(['!reset', '!disabled'])
        output.extend('!' + d for d in entry['directives'])
        output.append('# ' + entry['name'])
        output.extend(entry['lines'])
    return '\n'.join(output) + '\n'

class Finder:
    def __init__(self, cache):
        self.cache = cache

    def fetch(self, url, limit=16 * 1024 * 1024):
        key = hashlib.sha256(url.encode()).hexdigest()
        cached = self.cache / 'downloads' / key
        if cached.exists():
            return cached.read_bytes()
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'GameBoyHub/1.1'})
            with urllib.request.urlopen(request, timeout=20) as response:
                content = response.read(limit + 1)
            if len(content) > limit:
                raise ValueError('The database response is too large.')
            atomic_write(cached, content)
            return content
        except (urllib.error.URLError, TimeoutError) as error:
            raise ValueError('Could not reach the cheat database. Check your connection and try again.') from error

    def database(self):
        tree = json.loads(self.fetch(TREE))
        if tree.get('truncated') or not re.fullmatch(r'[0-9a-f]{40}', tree.get('sha', '')):
            raise ValueError('The database returned an incomplete index.')
        return tree

    def cache_path(self, rom):
        return self.cache / 'matches' / (hashlib.sha256(str(rom).encode()).hexdigest() + '.json')

    def find(self, rom, info, save_dir, base, patched=False):
        result = {'rom': str(rom), 'title': info['title'], 'system': info['system'],
                  'identity': '', 'notice': '', 'candidates': [], 'entries': [], 'sourceId': ''}
        stems = {rom.stem, Path(info['member']).stem if info['member'] else rom.stem}
        for directory in {rom.parent, base / 'Cheats', save_dir}:
            for stem in sorted(stems):
                for suffix in ('.cheats', '.cht'):
                    file = directory / (stem + suffix)
                    if file.is_file():
                        result['candidates'].append({'id': 'local:' + str(file), 'name': file.name,
                            'source': str(file), 'kind': 'local', 'match': 'Local file · check game version'})
        if patched:
            result['notice'] = 'A ROM patch is attached. Base-game cheat matches are disabled; import codes made for this hack.'
        else:
            try:
                digest = rom_hash(rom, info)
                tree = self.database()
                systems = ['GBA'] if info['system'] == 'GBA' else ['GB', 'GBC']
                canonical, system = '', info['system']
                for candidate_system in systems:
                    dat_path = 'metadat/no-intro/' + SYSTEMS[candidate_system] + '.dat'
                    dat = self.fetch(RAW + tree['sha'] + '/' + urllib.parse.quote(dat_path), 4 * 1024 * 1024).decode('utf-8-sig')
                    canonical = identify(dat, digest)
                    if canonical:
                        system = candidate_system
                        break
                if canonical:
                    result.update(title=canonical, system=system, identity='ROM identified by SHA-1: ' + canonical)
                    prefix = 'cht/' + SYSTEMS[system] + '/'
                    for item in tree['tree']:
                        path = item['path']
                        name = Path(path).stem
                        if path.startswith(prefix) and path.endswith('.cht') and matching(canonical, name):
                            if any(x in name for x in ('Miyoo', 'Xploder')):
                                continue
                            result['candidates'].append({'id': path, 'name': name, 'kind': 'database',
                                'source': RAW + tree['sha'] + '/' + urllib.parse.quote(path),
                                'match': 'Title / region match · codes not verified'})
                    result['notice'] = 'Choose a list, preview its codes, then import the ones you want. Codes stay off until enabled in mGBA.'
                else:
                    result['notice'] = 'ROM checksum not recognized. No online cheats were matched; use a local cheat file for this version.'
            except ValueError as error:
                result['notice'] = str(error)
        result['candidates'].sort(key=lambda c: (c['kind'] != 'local', len(c['name'])))
        atomic_write(self.cache_path(rom), json.dumps(result).encode())
        return result

    def preview(self, rom, source_id):
        result = json.loads(self.cache_path(rom).read_text())
        candidate = next((c for c in result['candidates'] if c['id'] == source_id), None)
        if not candidate:
            raise ValueError('Run Find cheats again to refresh this list.')
        if candidate['kind'] == 'local':
            text = read_bounded(Path(candidate['source']))
        else:
            if not candidate['source'].startswith(RAW):
                raise ValueError('Unsupported database source.')
            text = self.fetch(candidate['source'], 4 * 1024 * 1024).decode('utf-8-sig')
        entries, skipped = parse_codes(text, result['system'], candidate['name'])
        result.update(entries=entries, sourceId=source_id, source=candidate['source'],
                      notice=f'{len(entries)} codes ready to preview; {skipped} unsupported or incomplete entries omitted. Imported codes start off.')
        atomic_write(self.cache_path(rom), json.dumps(result).encode())
        return result

    def export(self, rom, source_id, indices, directory):
        result = json.loads(self.cache_path(rom).read_text())
        if result['sourceId'] != source_id:
            raise ValueError('Preview this list again before importing.')
        chosen = set(indices)
        entries = [e for e in result['entries'] if e['id'] in chosen]
        if not entries or len(entries) != len(chosen) or len(entries) > 1000:
            raise ValueError('Select between 1 and 1,000 valid codes.')
        content = native_text(entries).encode()
        digest = hashlib.sha256(content).hexdigest()
        output = directory / (rom.stem + '-' + digest[:12] + '.cheats')
        atomic_write(output, content)
        atomic_write(output.with_suffix('.source.json'), json.dumps({'rom': str(rom), 'source': result['source'], 'codes': len(entries)}).encode())
        return {'file': str(output), 'sha256': digest, 'count': len(entries)}
