"""patchzip.py - the course patches ship zipped (owner, 2026-10-16: "zip the patches and add an unzip step to the chain").

A course's numbered patch files (<game>.<course name>.patch.<n>.json, coursepatch.py) are kept in the repository as ONE zip beside the
course settings: <game>.<course name>.patches.zip (LZMA; Mountain's three, 15.3 MB of JSON, are 1.7 MB). The chain's first step
(stack.py, step 'unzip') unpacks them beside the zip, where the importer, derived_tiles and the patch generators look for them; the
unpacked files are not committed (.gitignore). Every process that asks common.courses_dir() for the folder does the same check (a few
milliseconds when nothing changed), so a run of import_classic.py outside the stack finds them too.
    python patchzip.py unpack [<courses folder> ...]     what the chain does (default: every game's courses folder)
    python patchzip.py pack [<courses folder> ...]       after a generator or Blender wrote a patch file: each course's files into its zip
A patch file that was changed here after it was unpacked (a new patch 3 from patch3_1995.py, an edit by hand) is never overwritten:
unpack keeps it and says so, and pack puts it into the zip. What was unpacked is remembered in <game>.<course name>.patches.unpacked.json
(the zip's sha1 and each file's). The zip is made the same way every time (members in number order, a fixed date, no system bits), so
packing unchanged files gives the same bytes."""
import os, sys, io, re, glob, json, hashlib, zipfile

NAME = re.compile(r'^[^/\\]+\.patch\.(\d+)\.json$')                   # <game>.<course name>.patch.<n>.json, no folders
def _sha(b): return hashlib.sha1(b).hexdigest()
def _stamp_path(zp): return zp[:-len('.zip')] + '.unpacked.json'
def _read_stamp(zp):
    try: return json.load(open(_stamp_path(zp), encoding='utf-8'))
    except (OSError, ValueError): return {}
def _write(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f: f.write(data)
    os.replace(tmp, path)
def _write_stamp(zp, st): _write(_stamp_path(zp), (json.dumps(st, indent=1, sort_keys=True) + '\n').encode('utf-8'))

def unpack(d, log=None):
    """every <prefix>.patches.zip in folder d unpacked beside it -> [(file name, what happened)] for the files written or kept"""
    done = []
    for zp in sorted(glob.glob(os.path.join(d, '*.patches.zip'))):
        zb = open(zp, 'rb').read(); zs = _sha(zb); st = _read_stamp(zp); prefix = os.path.basename(zp)[:-len('.patches.zip')]
        with zipfile.ZipFile(io.BytesIO(zb)) as z:
            names = z.namelist(); bad = [n for n in names if not (NAME.match(n) and n.startswith(prefix + '.patch.'))]
            if bad: raise ValueError('%s: members that are not this course\'s patch files: %s' % (zp, bad))
            if st.get('zip') == zs and all(os.path.exists(os.path.join(d, n)) for n in names): continue      # nothing changed since the last unpack
            was = st.get('files', {}); now = {}
            for n in names:
                data = z.read(n); h = _sha(data); p = os.path.join(d, n)
                if os.path.exists(p):
                    cur = _sha(open(p, 'rb').read())
                    if cur == h: now[n] = h; continue
                    if cur != was.get(n):                              # changed here since it was unpacked (or never unpacked): kept
                        now[n] = was.get(n); done.append((n, 'kept: changed here since it was unpacked (patchzip.py pack puts it into the zip)')); continue
                _write(p, data); now[n] = h; done.append((n, 'written'))
        _write_stamp(zp, dict(zip=zs, files=now))
    if log and done: log('patches (%s): %s' % (d, '; '.join('%s %s' % x for x in done)))
    return done

def pack(d, log=None):
    """each course's patch files in folder d into its <prefix>.patches.zip (the members the zip has and the folder lacks stay) -> [zip names written]"""
    groups = {}
    for p in glob.glob(os.path.join(d, '*.patch.*.json')):
        n = os.path.basename(p)
        if NAME.match(n): groups.setdefault(n[:n.index('.patch.')], {})[n] = open(p, 'rb').read()
    for zp in glob.glob(os.path.join(d, '*.patches.zip')):            # (members whose file is not here: kept as they are)
        pre = os.path.basename(zp)[:-len('.patches.zip')]
        with zipfile.ZipFile(zp) as z:
            for n in z.namelist():
                if NAME.match(n) and n not in groups.setdefault(pre, {}): groups[pre][n] = z.read(n)
    out = []
    for pre, files in sorted(groups.items()):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            for n in sorted(files, key=lambda n: int(NAME.match(n).group(1))):
                zi = zipfile.ZipInfo(n, date_time=(1980, 1, 1, 0, 0, 0)); zi.compress_type = zipfile.ZIP_LZMA; zi.create_system = 0; zi.external_attr = 0
                z.writestr(zi, files[n])
        zp = os.path.join(d, pre + '.patches.zip'); zb = buf.getvalue()
        if not os.path.exists(zp) or open(zp, 'rb').read() != zb: _write(zp, zb); out.append(os.path.basename(zp))
        _write_stamp(zp, dict(zip=_sha(zb), files={n: _sha(b) for n, b in files.items()}))
    if log: log('patches packed (%s): %s' % (d, ', '.join(out) if out else 'every zip already up to date'))
    return out

def folders():
    """every game's courses folder: tools/import/<game>/tracks/courses"""
    imp = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
    return sorted(p for p in glob.glob(os.path.join(imp, '*', 'tracks', 'courses')) if os.path.isdir(p))

if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('pack', 'unpack'): print(__doc__); sys.exit(2)
    for d in (sys.argv[2:] or folders()):
        if sys.argv[1] == 'pack': pack(d, print)
        else:
            r = unpack(d, print)
            if not r: print('patches (%s): up to date' % d)
