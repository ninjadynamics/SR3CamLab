"""Clone one SEGA Rally 3 car under a new folder name, as a staging folder laid out like the game folder, with an
ArcadeDatabase that lists the new car, a manifest and install / uninstall scripts. Nothing is written to the game.

    python car_clone.py <donor> <NewFolder> <staging root> [--id 10] [--name LANG_ID_BOWLER] [--sound ID_CAR_BOWLER]
                        [--nums-from Bowler] [--classic 0] [--bonus 0] [--tag hornet]
    e.g. python car_clone.py st205 Hornet <scratch>/hornet_test1

What it does (docs/kb, car files):
- the donor's files are copied under the new name; a name the exe does not know (0x5C6000: strnicmp against C4,
  Delta_HF, ST205, Enduro, RSFocus, 207, SubaruImpreza, SX4, Bowler, MitsubishiEvo) loads <name>gravelmodel_data and
  <name>gravel_data instead of <name>bespokemodel_data / <name>bespoke_data, so the donor's bespoke files are written
  under the gravel names;
- every chunk id that only the donor's files use, and the donor's texture-pack placeholder ids, get fresh ids (crc32 of
  "<tag>:<old id>", checked against every id of the ten cars), the same mapping in every file, so the donor and the
  clone can be in one race; ids several cars share (common shaders and textures) stay as SEGA has them;
- model chunks go through carmodel.read_model / serialize (the writer that rewrites SEGA's files byte for byte);
- the ArcadeDatabase gets one more record (arcadedb.add_car). It is built from the game's current file; the manifest
  keeps that file's SHA-256 so the install refuses a game whose ArcadeDatabase changed in between.
SEGA data: the staging folder holds SEGA's files; it never goes into the repository.
"""
import os, sys, json, struct, hashlib, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbfw, carmodel, arcadedb

from common import GAME
CARS = os.path.join(GAME, "Main_release", "cars")
TEN = ("207", "bowler", "c4", "delta_hf", "enduro", "mitsubishievo", "rsfocus", "st205", "subaruimpreza", "sx4")
KNOWN = ("C4", "Delta_HF", "ST205", "Enduro", "RSFocus", "207", "SubaruImpreza", "SX4", "Bowler", "MitsubishiEvo")


def car_files(car):
    """(kind, path) of one car's files, as the loader 0x5C5D30 asks for them"""
    c = car.lower()
    out = [("texturepack" + s, os.path.join(CARS, c + "texturepack%s_xdata.sbf" % s)) for s in ("dust", "mud", "snow")]
    out += [("chassismodel", os.path.join(CARS, c + "chassismodel_data.sbf")),
            ("bespokemodel", os.path.join(CARS, c + "bespokemodel_data.sbf")),
            ("bespoke", os.path.join(CARS, c + "bespoke_data.sbf")),
            ("mudmodel", os.path.join(CARS, c + "mudmodel_data.sbf")),
            ("snowmodel", os.path.join(CARS, c + "snowmodel_data.sbf")),
            ("bonnet", os.path.join(CARS, "bonnets", c + "_data.sbf"))]
    return out


def known_name(name):
    return any(name[:len(k)].lower() == k.lower() for k in KNOWN)


def target_name(kind, new):
    n = new.lower(); b = "bespoke" if known_name(new) else "gravel"
    return {"chassismodel": n + "chassismodel_data.sbf", "bespokemodel": n + b + "model_data.sbf", "bespoke": n + b + "_data.sbf",
            "mudmodel": n + "mudmodel_data.sbf", "snowmodel": n + "snowmodel_data.sbf", "bonnet": "bonnets/" + n + "_data.sbf",
            "texturepackdust": n + "texturepackdust_xdata.sbf", "texturepackmud": n + "texturepackmud_xdata.sbf",
            "texturepacksnow": n + "texturepacksnow_xdata.sbf"}[kind]


def sha(b): return hashlib.sha256(b).hexdigest().upper()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("donor"); ap.add_argument("new"); ap.add_argument("out")
    ap.add_argument("--id", type=int, default=10); ap.add_argument("--name", default="LANG_ID_BOWLER")
    ap.add_argument("--sound", default="ID_CAR_BOWLER"); ap.add_argument("--nums-from", default="Bowler")
    ap.add_argument("--classic", type=int, default=0); ap.add_argument("--bonus", type=int, default=0)
    ap.add_argument("--tag", default=None)
    a = ap.parse_args()
    tag = a.tag or a.new.lower()
    if known_name(a.new): print("note: '%s' starts with a name the exe knows: the bespoke file names are used" % a.new)

    # ids of every car's files, and which of them only the donor uses
    owner = {}; taken = set()
    for car in TEN:
        for kind, p in car_files(car):
            if not os.path.exists(p): continue
            f = sbfw.read_sbf(p)
            for c in f.chunks:
                owner.setdefault(c.id, set()).add(car); taken.add(c.id)
                for r in c.refs(): owner.setdefault(r, set()).add(car); taken.add(r)
            for ph in carmodel.placeholders(f): owner.setdefault(ph, set()).add(car); taken.add(ph)
    donor = a.donor.lower()
    files = []
    for kind, p in car_files(donor):
        if os.path.exists(p): files.append((kind, p, sbfw.read_sbf(p)))
        else: print("donor has no", os.path.basename(p))
    mine = set()
    for kind, p, f in files:
        mine.update(c.id for c in f.chunks); mine.update(carmodel.placeholders(f))
    specific = sorted(i for i in mine if owner.get(i) == {donor})
    mapping = {i: carmodel.fresh_id(tag, i, taken) for i in specific}
    print("donor ids %d, only the donor's %d -> fresh ids; shared with other cars %d (kept)" % (
        len(mine), len(specific), len(mine) - len(specific)))

    # raw words equal to a remapped id outside ref fields / placeholder slots would be links the remap misses
    loose = []
    for kind, p, f in files:
        for c in f.chunks:
            refs = set(c.ref)
            ph = set(8 + 8 * j + 4 for j in range(struct.unpack_from("<I", c.data, 4)[0])) if c.kind == 13 else set()
            for o in range(0, len(c.data) - 3, 4):
                if o in refs or o in ph: continue
                if struct.unpack_from("<I", c.data, o)[0] in mapping: loose.append((os.path.basename(p), c.kind, c.id, o))
    print("remapped ids found outside ref fields:", len(loose), loose[:5])

    manifest = dict(donor=a.donor, new=a.new, files=[], id_map={"%08x" % k: "%08x" % v for k, v in mapping.items()})
    for kind, p, f in files:
        # model chunks through the writer
        for i, c in enumerate(f.chunks):
            if c.kind == 1:
                m = carmodel.read_model(c)
                d, fx, rf = m.serialize()
                assert (d, fx, rf) == (c.data, c.fix, c.ref), "writer does not reproduce %s" % p
                f.chunks[i] = sbfw.Ch(1, c.id, d, fx, rf, c.z, c.gap)
        carmodel.remap(f, mapping)
        rel = "Main_release/cars/" + target_name(kind, a.new)
        dst = os.path.join(a.out, rel)
        b = carmodel.write_file(f, dst)
        g = sbfw.read_sbf(dst)
        assert [(c.kind, len(c.data)) for c in g.chunks] == [(c.kind, len(c.data)) for c in f.chunks]
        manifest["files"].append(dict(path=rel.replace("/", "\\"), source=os.path.basename(p), sha256=sha(b), size=len(b)))
        print("  %-44s <- %s (%d chunks)" % (rel, os.path.basename(p), len(g.chunks)))

    # cross-file refs after the remap must still resolve inside the clone's file set (or to ids SEGA shares)
    allnew = set()
    for e in manifest["files"]:
        g = sbfw.read_sbf(os.path.join(a.out, e["path"]))
        allnew.update(c.id for c in g.chunks); allnew.update(carmodel.placeholders(g))
    probs = []
    for e in manifest["files"]:
        probs += sbfw.validate(os.path.join(a.out, e["path"]), e["path"], extern_ids=allnew, quiet=True)
    print("validate problems:", len(probs), probs[:5])

    # ArcadeDatabase with the new record
    dbsrc = os.path.join(GAME, "ArcadeDatabase", "arcadedatabase_xdata.sbf")
    srcb = open(dbsrc, "rb").read()
    f = sbfw.read_sbf(dbsrc)
    cars = arcadedb.read_cars(f.byid()[arcadedb.CARS_ID])
    nums = [c for c in cars if c.folder.lower() == a.nums_from.lower()][0].nums
    car = arcadedb.Car(a.id, a.name, a.new, a.sound, a.classic, a.bonus, nums)
    arcadedb.add_car(f, car)
    dbb = arcadedb.write_db(f)
    rel = "ArcadeDatabase/arcadedatabase_xdata.sbf"
    os.makedirs(os.path.join(a.out, "ArcadeDatabase"), exist_ok=True)
    open(os.path.join(a.out, rel), "wb").write(dbb)
    back = arcadedb.read_cars(sbfw.read_sbf(os.path.join(a.out, rel)).byid()[arcadedb.CARS_ID])
    print("ArcadeDatabase: %d cars, last %r" % (len(back), back[-1]))
    manifest.update(db=dict(path=rel.replace("/", "\\"), source_sha256=sha(srcb), sha256=sha(dbb), size=len(dbb),
                            record=dict(id=a.id, name=a.name, folder=a.new, sound=a.sound, classic=a.classic, bonus=a.bonus, nums=nums)))
    json.dump(manifest, open(os.path.join(a.out, "manifest.json"), "w"), indent=1)
    here = os.path.dirname(os.path.abspath(__file__))
    for s, d in (("car_install.ps1", "install.ps1"), ("car_uninstall.ps1", "uninstall.ps1")):
        open(os.path.join(a.out, d), "wb").write(open(os.path.join(here, s), "rb").read())
    print("wrote", os.path.join(a.out, "manifest.json"), "+ install.ps1, uninstall.ps1")


if __name__ == "__main__":
    main()
