// SR3 Extras: post-pass over a converted (PC layout) SEGA Rally Revo track, so that the arcade engine
// shows what Revo showed. Compiled at run time together with ps3conv.cs (Add-Type), so it sticks to C# 5.
// It uses Sbf, OutChunk and Ps3Conv.BuildSbf from ps3conv.cs.
//
// Steps (each can be switched on or off):
//   shaders   materials whose shader the arcade game does not have (i_pl.fx, i_pl_psm.fx) are rebuilt as
//             copies of a genuine Uber material of the same track (same chunk id, the i_pl textures put in
//             the Uber diffuse / normal / specular / light slots)
//   birds     hide the Thrush flocks (moved 10 km below the ground). Off by default: the arcade engine
//             treats them exactly as on its own Tropical track
//   emitters  write 2000.0 at +0x10C of Revo particle emitters (the arcade's value). Off by default: the
//             meaning of that field is not proven
// Files that no step changes are copied byte for byte.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

namespace SR3Extras
{
    public class RevoFixReport
    {
        public SortedDictionary<string, int> Counts = new SortedDictionary<string, int>(StringComparer.Ordinal);
        public List<string> Log = new List<string>();
        public void Add(string what) { int n; Counts.TryGetValue(what, out n); Counts[what] = n + 1; }
    }

    public static class RevoFix
    {
        static readonly string[] Used = { "game_objects_gfx_data", "gameobj_gfx_dis_data", "pobj_master_gfx_xdata", "pobj_plac_gfx_xdata", "master_gfx_xdata", "master_xdata" };
        // every effect of the arcade shader libraries (system\shaderlib3_data.sbf + the Uber library and its alias)
        static readonly HashSet<string> ArcadeFx = new HashSet<string>(("3wayblend.fx frontend.fx frontend_logo.fx grannycpuskinning_tex.fx grannygpuskinning_tex.fx graphicsdebug.fx " +
            "grass.fx horizon.fx hud.fx impostor.fx particlesystem.fx posteffects.fx shadows_cast.fx smallinstances.fx sr_car_chrome.fx " +
            "sr_car_discs.fx sr_car_exterior.fx sr_car_exterior2.fx sr_car_glass.fx sr_car_glow.fx sr_car_interior.fx sr_car_lights.fx " +
            "sr_car_moving.fx sr_car_mudassets.fx sr_car_mudmesh.fx sr_car_mudmesh2.fx sr_car_shadow.fx sr_car_spokes.fx sr_car_wheels.fx " +
            "textsheeneffect.fx track.fx trackmultiblend.fx water.fx ubershadergame.fx ubershadermax.fx").Split(' '));
        static readonly string[] BadFlags = { "ABLEND", "ABLENDAdd", "SCROLL", "TWOS", "REFL", "DISCR", "GLITTER" };
        static readonly string[] Slots = { "gTextureDiffuse", "gTextureNormal", "gTextureSpecular", "gTextureLight" };
        const uint EmitterRevo = 0x5a1bb4a6;

        class RChunk
        {
            public uint Kind, Id, Z;
            public List<int> Fix, Ref;
            public byte[] Data;
        }

        class RFile
        {
            public string Suffix, Name;
            public List<RChunk> Chunks = new List<RChunk>();
            public bool Dirty;
        }

        static uint U(byte[] d, int o) { return (uint)(d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)); }
        static void Put(byte[] d, int o, uint v) { d[o] = (byte)v; d[o + 1] = (byte)(v >> 8); d[o + 2] = (byte)(v >> 16); d[o + 3] = (byte)(v >> 24); }

        static string CStr(byte[] d, long o)
        {
            if (o < 0 || o >= d.Length) return "";
            int e = (int)o;
            while (e < d.Length && d[e] != 0) e++;
            StringBuilder sb = new StringBuilder(e - (int)o);
            for (int i = (int)o; i < e; i++) sb.Append((char)d[i]);
            return sb.ToString();
        }

        // kind 3: the effect's file name (pointer at +0x18)
        static string StubName(RChunk c)
        {
            if (c.Data.Length < 0x1c || !c.Fix.Contains(0x18)) return "";
            return CStr(c.Data, U(c.Data, 0x18)).ToLowerInvariant();
        }

        // kind 2: +0 reference to the shader stub, +8 u16 count, then count x {value, name pointer, 0, 0};
        // value = pointer to numbers | texture reference | nothing
        class Mat
        {
            public RChunk C;
            public bool Ok;
            public List<string> Names = new List<string>();
            public List<char> Kinds = new List<char>();                     // t = texture, d = data, n = nothing
            public List<int> Offs = new List<int>();
            Dictionary<string, int> by = new Dictionary<string, int>(StringComparer.Ordinal);

            public Mat(RChunk c)
            {
                C = c; byte[] d = c.Data;
                HashSet<int> fx = new HashSet<int>(c.Fix), rf = new HashSet<int>(c.Ref);
                int n = d[8] | (d[9] << 8);
                for (int k = 0; k < n; k++)
                {
                    int o = 0xC + 16 * k;
                    if (o + 8 > d.Length || !fx.Contains(o + 4)) { Ok = false; return; }
                    string name = CStr(d, U(d, o + 4));
                    char kind = rf.Contains(o) ? 't' : fx.Contains(o) ? 'd' : 'n';
                    if (!by.ContainsKey(name)) by[name] = Names.Count;
                    Names.Add(name); Kinds.Add(kind); Offs.Add(o);
                }
                Ok = n > 0;
            }

            public int Find(string name, char kind)
            {
                int i;
                if (by.TryGetValue(name, out i) && Kinds[i] == kind) return Offs[i];
                return -1;
            }

            public uint Tex(string name) { int o = Find(name, 't'); return o < 0 ? 0 : U(C.Data, o); }

            public uint Flag(string name)
            {
                int o = Find("gbUber" + name, 'd');
                if (o < 0) return 0;
                long p = U(C.Data, o);
                return p + 4 <= C.Data.Length ? U(C.Data, (int)p) : 0;
            }
        }

        // kind 4 texture: 44-byte header, then a DDS file. True if the top mip level has any pixel that is not opaque.
        static bool HasAlpha(RChunk tex)
        {
            byte[] d = tex.Data;
            if (d.Length < 172 || d[44] != 'D' || d[45] != 'D' || d[46] != 'S' || d[47] != ' ') return false;
            long h = U(d, 44 + 12), w = U(d, 44 + 16);
            if (d[128] != 'D' || d[129] != 'X' || d[130] != 'T') return false;
            if (d[131] == '3' || d[131] == '2') return true;
            if (d[131] != '5' && d[131] != '4') return false;
            long n = Math.Max(1, w / 4) * Math.Max(1, h / 4);
            for (long k = 0; k < n; k++)
            {
                long o = 172 + 16 * k;
                if (o + 2 > d.Length) break;
                if (d[o] < 255 || d[o + 1] < 255) return true;
            }
            return false;
        }

        // kind 1: (vertex format, material id) of every group of every detail level
        static void MeshGroups(RChunk c, Dictionary<uint, HashSet<uint>> use)
        {
            byte[] d = c.Data;
            if (d.Length < 0x48) return;
            long nl = U(d, 0x2c) / 0x48;
            if (nl < 1 || nl * 0x48 > d.Length) nl = 1;
            for (int i = 0; i < nl; i++)
            {
                uint fmt = U(d, i * 0x48 + 8); long ng = U(d, i * 0x48 + 0x20), pa = U(d, i * 0x48 + 0x2c);
                for (long g = 0; g < ng; g++)
                {
                    long o = pa + 20 * g;
                    if (o + 20 > d.Length) break;
                    uint m = U(d, (int)o + 16); HashSet<uint> s;
                    if (!use.TryGetValue(m, out s)) { s = new HashSet<uint>(); use[m] = s; }
                    s.Add(fmt);
                }
            }
        }

        class UberMat { public int File, Index; public Mat M; public HashSet<uint> Formats; }

        static bool All(HashSet<uint> fmts, uint bit) { foreach (uint f in fmts) if ((f & bit) == 0) return false; return true; }

        static void FixShaders(List<RFile> files, RevoFixReport rep)
        {
            List<UberMat> ubers = new List<UberMat>();
            List<Dictionary<uint, HashSet<uint>>> uses = new List<Dictionary<uint, HashSet<uint>>>();
            for (int fi = 0; fi < files.Count; fi++)
            {
                List<RChunk> chunks = files[fi].Chunks;
                Dictionary<uint, string> stubs = new Dictionary<uint, string>();
                Dictionary<uint, HashSet<uint>> use = new Dictionary<uint, HashSet<uint>>();
                foreach (RChunk c in chunks) { if (c.Kind == 3) stubs[c.Id] = StubName(c); if (c.Kind == 1) MeshGroups(c, use); }
                uses.Add(use);
                for (int ci = 0; ci < chunks.Count; ci++)
                {
                    RChunk c = chunks[ci]; string sn;
                    if (c.Kind != 2 || c.Data.Length < 12 || !stubs.TryGetValue(U(c.Data, 0), out sn) || (sn != "ubershadermax.fx" && sn != "ubershadergame.fx")) continue;
                    Mat m = new Mat(c);
                    if (!m.Ok) continue;
                    UberMat u = new UberMat(); u.File = fi; u.Index = ci; u.M = m;
                    if (!use.TryGetValue(c.Id, out u.Formats)) u.Formats = new HashSet<uint>();
                    ubers.Add(u);
                }
            }
            for (int fi = 0; fi < files.Count; fi++)
            {
                RFile file = files[fi]; List<RChunk> chunks = file.Chunks;
                Dictionary<uint, string> stubs = new Dictionary<uint, string>();
                Dictionary<uint, RChunk> byid = new Dictionary<uint, RChunk>();
                foreach (RChunk c in chunks) { if (c.Kind == 3) stubs[c.Id] = StubName(c); byid[c.Id] = c; }
                Dictionary<uint, HashSet<uint>> use = uses[fi];
                int ci = 0;
                while (ci < chunks.Count)
                {
                    RChunk c = chunks[ci]; ci++;
                    if (c.Kind != 2 || c.Data.Length < 12) continue;
                    string name;
                    if (!stubs.TryGetValue(U(c.Data, 0), out name) || name.Length == 0 || ArcadeFx.Contains(name)) continue;
                    if (name != "i_pl.fx" && name != "i_pl_psm.fx")
                    {
                        rep.Add("materials with another unknown shader (left alone)");
                        rep.Log.Add(file.Suffix + ": material " + c.Id.ToString("x8") + " uses " + name + ", not handled");
                        continue;
                    }
                    Mat src = new Mat(c); HashSet<uint> fmts;
                    if (!src.Ok || !use.TryGetValue(c.Id, out fmts) || fmts.Count == 0) { rep.Add("materials with a missing shader that no mesh uses (left alone)"); continue; }
                    uint[] t = new uint[4];
                    for (int k = 0; k < 4; k++) t[k] = src.Tex("gTexture" + k);
                    if (name == "i_pl.fx") { t[2] = 0; t[3] = 0; }          // its gTexture2 is a noise pattern, not a specular map
                    for (int k = 0; k < 4; k++) { RChunk tc; if (!(byid.TryGetValue(t[k], out tc) && tc.Kind == 4)) t[k] = 0; }
                    if (t[0] == 0) { rep.Add("materials with a missing shader and no diffuse texture (left alone)"); continue; }
                    bool alpha = HasAlpha(byid[t[0]]);
                    bool tang = All(fmts, 4), col = All(fmts, 0x10), uv2 = All(fmts, 0x80);
                    UberMat best = null; int bestScore = 0;
                    foreach (UberMat um in ubers)
                    {
                        Mat u = um.M; bool bad = false;
                        foreach (string b in BadFlags) if (u.Flag(b) != 0) { bad = true; break; }
                        if (bad || u.Flag("DIFFM") != 1) continue;
                        bool nrm = u.Flag("NORM") != 0, spc = u.Flag("SPECM") != 0, lmp = u.Flag("LMAP") != 0;
                        if ((nrm && !(t[1] != 0 && tang)) || (spc && t[2] == 0) || (lmp && !(t[3] != 0 && uv2)) || (u.Flag("VCOL") != 0 && !col)) continue;
                        if (u.Find("gTextureDiffuse", 't') < 0) continue;
                        bool other = false;                                 // a texture we could not supply
                        for (int k = 0; k < u.Names.Count && !other; k++)
                            if (u.Kinds[k] == 't' && Array.IndexOf(Slots, u.Names[k]) < 0 && U(u.C.Data, u.Offs[k]) != 0) other = true;
                        if (other) continue;
                        bool shares = false;
                        foreach (uint f in um.Formats) if (fmts.Contains(f)) { shares = true; break; }
                        int score = ((u.Flag("ATEST") != 0) != alpha ? 100 : 0) + (t[3] != 0 && uv2 && !lmp ? 8 : 0) + (t[1] != 0 && tang && !nrm ? 4 : 0)
                                  + (t[2] != 0 && !spc ? 2 : 0) + (alpha && u.Flag("DSIDE") == 0 ? 1 : 0) + (shares ? 0 : 16) + (um.File != fi ? 32 : 0);
                        if (best == null || score < bestScore) { best = um; bestScore = score; }       // ubers are in (file, chunk) order
                    }
                    if (best == null) { rep.Add("materials with a missing shader and no usable Uber material in the track (left alone)"); continue; }
                    Mat don = best.M; byte[] d = (byte[])don.C.Data.Clone();
                    bool[] on = { true, don.Flag("NORM") != 0, don.Flag("SPECM") != 0, don.Flag("LMAP") != 0 };
                    for (int k = 0; k < 4; k++)
                    {
                        int o = don.Find(Slots[k], 't');
                        if (o >= 0) Put(d, o, on[k] ? t[k] : 0);
                    }
                    string[] pn = { "gfBumpScale", "gfSpecularPower", "gf3SpecCol" }; int[] ps = { 4, 4, 12 };
                    for (int k = 0; k < 3; k++)
                    {
                        int a = src.Find(pn[k], 'd'), b = don.Find(pn[k], 'd');
                        if (a < 0 || b < 0) continue;
                        long so = U(src.C.Data, a), dof = U(d, b);
                        if (so + ps[k] <= src.C.Data.Length && dof + ps[k] <= d.Length) Buffer.BlockCopy(src.C.Data, (int)so, d, (int)dof, ps[k]);
                    }
                    uint sid = U(d, 0);
                    if (!byid.ContainsKey(sid))                              // the Uber stub is not in this file: bring it along
                    {
                        RChunk st = null;
                        foreach (RChunk x in files[best.File].Chunks) if (x.Id == sid) { st = x; break; }
                        if (st == null) throw new InvalidDataException("Uber material " + don.C.Id.ToString("x8") + " has no shader stub");
                        RChunk n = new RChunk(); n.Kind = st.Kind; n.Id = st.Id; n.Z = st.Z; n.Fix = new List<int>(st.Fix); n.Ref = new List<int>(st.Ref); n.Data = (byte[])st.Data.Clone();
                        chunks.Insert(ci - 1, n); byid[sid] = n; stubs[sid] = StubName(n); ci++;
                        rep.Add("Uber shader stubs added");
                    }
                    c.Data = d; c.Fix = new List<int>(don.C.Fix); c.Ref = new List<int>(don.C.Ref); file.Dirty = true;
                    rep.Add("materials rebuilt as Uber (" + name + ")");
                    if (bestScore % 16 != 0 || bestScore >= 100) rep.Add("... of which with an approximate donor");
                    List<uint> fl = new List<uint>(fmts); fl.Sort(); StringBuilder fs = new StringBuilder();
                    foreach (uint f in fl) { if (fs.Length > 0) fs.Append(','); fs.Append(f.ToString("x")); }
                    rep.Log.Add(file.Suffix + ": material " + c.Id.ToString("x8") + " (" + name + ", formats " + fs + ", " + (alpha ? "alpha" : "opaque") + ") rebuilt from Uber material "
                        + don.C.Id.ToString("x8") + " of " + files[best.File].Suffix + ", score " + bestScore);
                    // check: reads back like its donor, every reference resolves
                    Mat chk = new Mat(c);
                    if (!chk.Ok || chk.Names.Count != don.Names.Count) throw new InvalidDataException("material " + c.Id.ToString("x8") + ": rebuilt material does not read back");
                    foreach (int o in c.Ref)
                    {
                        uint v = U(c.Data, o);
                        if (v != 0 && !byid.ContainsKey(v)) throw new InvalidDataException("material " + c.Id.ToString("x8") + ": reference " + v.ToString("x8") + " not in the file");
                    }
                }
            }
        }

        // kind 5 game object list: records {class name, type name, flags, id, 4x4 matrix, parameter list}
        static void FixBirds(List<RFile> files, RevoFixReport rep)
        {
            foreach (RFile file in files)
            {
                if (file.Suffix != "game_objects_gfx_data") continue;
                foreach (RChunk c in file.Chunks)
                {
                    if (c.Kind != 5) continue;
                    byte[] d = c.Data; HashSet<int> fx = new HashSet<int>(c.Fix);
                    List<int> order = new List<int>(fx); order.Sort();
                    foreach (int o in order)
                    {
                        if (!fx.Contains(o + 4) || !fx.Contains(o + 0x50) || fx.Contains(o + 8) || o + 0x54 > d.Length || U(d, o + 0x4c) != 0x3f800000) continue;
                        long p = U(d, o + 4);
                        if (p >= d.Length || CStr(d, p) != "Thrush") continue;
                        float y = BitConverter.ToSingle(d, o + 0x44);
                        if (y > -5000.0f)
                        {
                            byte[] b = BitConverter.GetBytes((float)((double)y - 10000.0));
                            Buffer.BlockCopy(b, 0, d, o + 0x44, 4); file.Dirty = true; rep.Add("Thrush flocks hidden");
                        }
                    }
                }
            }
        }

        static void FixEmitters(List<RFile> files, RevoFixReport rep)
        {
            foreach (RFile file in files)
                foreach (RChunk c in file.Chunks)
                    if (c.Kind == 12 && c.Z == EmitterRevo && c.Data.Length == 452 && U(c.Data, 0x10c) == 0)
                    {
                        Buffer.BlockCopy(BitConverter.GetBytes(2000.0f), 0, c.Data, 0x10c, 4); file.Dirty = true;
                        rep.Add("particle emitters given the arcade distance value");
                    }
        }

        public static RevoFixReport FixTrack(string src, string dst, bool shaders, bool birds, bool emitters)
        {
            return FixTrack(src, dst, shaders, birds, emitters, true);
        }

        // src = a converted track folder; the fixed track is written to dst (another folder)
        public static RevoFixReport FixTrack(string src, string dst, bool shaders, bool birds, bool emitters, bool compress)
        {
            RevoFixReport rep = new RevoFixReport();
            Directory.CreateDirectory(dst);
            Dictionary<string, string> names = new Dictionary<string, string>();
            foreach (string path in Directory.GetFiles(src))
            {
                string f = Path.GetFileName(path), low = f.ToLowerInvariant(), suf = null;
                foreach (string s in Used) if (low.EndsWith("_" + s + ".sbf", StringComparison.Ordinal)) { suf = s; break; }
                if (suf != null) names[suf] = f;
                else File.Copy(path, Path.Combine(dst, f), true);
            }
            List<RFile> files = new List<RFile>();
            foreach (string suf in Used)
            {
                string f;
                if (!names.TryGetValue(suf, out f)) continue;
                RFile rf = new RFile(); rf.Suffix = suf; rf.Name = f;
                Sbf s = new Sbf(Path.Combine(src, f), false);
                foreach (Chunk c in s.Chunks)
                {
                    RChunk r = new RChunk(); r.Kind = c.Kind; r.Id = c.Id; r.Z = c.Z; r.Fix = new List<int>(c.Fix); r.Ref = new List<int>(c.Ref); r.Data = s.Bytes(c);
                    rf.Chunks.Add(r);
                }
                files.Add(rf);
            }
            if (shaders) FixShaders(files, rep);
            if (birds) FixBirds(files, rep);
            if (emitters) FixEmitters(files, rep);
            foreach (RFile rf in files)
            {
                string p = Path.Combine(dst, rf.Name);
                if (!rf.Dirty) { File.Copy(Path.Combine(src, rf.Name), p, true); continue; }
                List<OutChunk> outp = new List<OutChunk>();
                foreach (RChunk r in rf.Chunks)
                {
                    OutChunk oc = new OutChunk(); oc.Kind = r.Kind; oc.Id = r.Id; oc.Z = r.Z; oc.Fix = r.Fix.ToArray(); oc.Ref = r.Ref.ToArray(); oc.Data = r.Data;
                    outp.Add(oc);
                }
                File.WriteAllBytes(p, Ps3Conv.BuildSbf(outp, compress));
                rep.Add("files rewritten");
            }
            return rep;
        }
    }
}
