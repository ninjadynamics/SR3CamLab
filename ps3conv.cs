// SR3 Extras: converts SEGA Rally Revo track files from the PlayStation 3 layout (big-endian,
// textures in separate .vbf files) to the PC layout SEGA Rally 3 reads. Compiled at run time by
// extras.ps1 (Add-Type), so it sticks to C# 5.
//
// A track file (.sbf) is a list of chunks: kind, id, size, type tag, pointer offsets, resource
// reference offsets, data. What each kind needs:
//   1 mesh       rebuilt: half-float positions and packed normals become floats, strips with
//                restart indices become joined strips
//   2 material   drop the PS3's 0xC8 bytes of run-time space, 32-bit swap, strings as they are
//   4 texture    header swapped, DDS pixel data as it is (it lives in the .vbf files)
//   5, 11        pointer-linked structures: per-word rules from ps3model.txt
//   7            raw files: unchanged
//   12           typed objects: per-type rules from ps3model.txt
// The game expects structure data at a file offset that is a multiple of 16 (textures: 16n + 4).
using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace SR3Extras
{
    public class Chunk
    {
        public uint Kind, Id, Z;
        public int Size, Data;
        public int[] Fix, Ref;
    }

    public class OutChunk
    {
        public uint Kind, Id, Z;
        public int[] Fix, Ref;
        public byte[] Data;
    }

    public class Sbf
    {
        public byte[] D;
        public bool BE;
        public List<Chunk> Chunks = new List<Chunk>();

        public static byte[] Raw(string path)
        {
            byte[] b = File.ReadAllBytes(path);
            if (b.Length < 10 || b[0] != 'S' || b[1] != 'B' || b[2] != 'Z' || b[3] != '1') return b;
            using (MemoryStream src = new MemoryStream(b, 10, b.Length - 10))       // past "SBZ1", the size and the zlib header
            using (DeflateStream z = new DeflateStream(src, CompressionMode.Decompress))
            using (MemoryStream dst = new MemoryStream())
            {
                z.CopyTo(dst);
                return dst.ToArray();
            }
        }

        public uint U(int o)
        {
            if (BE) return ((uint)D[o] << 24) | ((uint)D[o + 1] << 16) | ((uint)D[o + 2] << 8) | D[o + 3];
            return ((uint)D[o + 3] << 24) | ((uint)D[o + 2] << 16) | ((uint)D[o + 1] << 8) | D[o];
        }

        public Sbf(string path, bool be)
        {
            D = Raw(path); BE = be;
            if (D.Length < 24) return;
            int count = (int)U(20);
            for (int i = 0; i < count; i++)
            {
                int off = (int)U(24 + 8 * i + 4);
                Chunk c = new Chunk();
                c.Kind = U(off); c.Id = U(off + 4); c.Size = (int)U(off + 8); c.Z = U(off + 12);
                int nfix = (int)U(off + 16), p = off + 20;
                c.Fix = new int[nfix];
                for (int k = 0; k < nfix; k++) c.Fix[k] = (int)U(p + 4 * k);
                p += 4 * nfix;
                int nref = (int)U(p); p += 4;
                c.Ref = new int[nref];
                for (int k = 0; k < nref; k++) c.Ref[k] = (int)U(p + 4 * k);
                c.Data = p + 4 * nref;
                Chunks.Add(c);
            }
        }

        public byte[] Bytes(Chunk c)
        {
            byte[] r = new byte[c.Size];
            Buffer.BlockCopy(D, c.Data, r, 0, c.Size);
            return r;
        }
    }

    public class Layout
    {
        public char Kind;                   // u = one op for every word, r = header + records, f = fixed size, w = weak
        public byte Op;
        public byte[] Hdr, Per, Ops;
    }

    public class Model
    {
        public Dictionary<string, Layout> Roles = new Dictionary<string, Layout>();
        public Dictionary<string, Layout> Sigs = new Dictionary<string, Layout>();
        public HashSet<string> Strings = new HashSet<string>();
        public Dictionary<string, List<KeyValuePair<int, Layout>>> Kids = new Dictionary<string, List<KeyValuePair<int, Layout>>>();
        public Dictionary<string, byte[]> Typed = new Dictionary<string, byte[]>();
        public HashSet<string> Classes = new HashSet<string>();             // every chunk class that has a role

        static byte[] Ops(string s)
        {
            if (s == "-") return new byte[0];
            byte[] r = new byte[s.Length];
            for (int i = 0; i < s.Length; i++) r[i] = (byte)(s[i] - '0');
            return r;
        }

        static Layout Lay(string s)
        {
            string[] p = s.Split(' ');
            Layout e = new Layout(); e.Kind = p[0][0];
            if (e.Kind == 'u' || e.Kind == 'w') e.Op = (byte)int.Parse(p[1]);
            else if (e.Kind == 'r') { e.Hdr = Ops(p[1]); e.Per = Ops(p[2]); }
            else e.Ops = Ops(p[1]);
            return e;
        }

        public static Model Load(string path)
        {
            Model m = new Model(); bool ok = false;
            foreach (string line in File.ReadAllLines(path))
            {
                if (line.Length == 0 || line[0] == '#') continue;
                if (line.StartsWith("SR3PS3MODEL")) { ok = true; continue; }
                string[] f = line.Split('|');
                if (f[0] == "role")
                {
                    Layout e = Lay(f[3]); m.Roles[f[1] + "|" + f[2]] = e; m.Classes.Add(f[1]);
                    int cut = f[2].LastIndexOf(',');
                    if (cut > 0)
                    {
                        string key = f[1] + "|" + f[2].Substring(0, cut); int last;
                        if (int.TryParse(f[2].Substring(cut + 1), out last))
                        {
                            if (!m.Kids.ContainsKey(key)) m.Kids[key] = new List<KeyValuePair<int, Layout>>();
                            m.Kids[key].Add(new KeyValuePair<int, Layout>(last, e));
                        }
                    }
                }
                else if (f[0] == "sig") m.Sigs[f[1] + "|" + f[2] + "|" + f[3]] = Lay(f[4]);
                else if (f[0] == "str") m.Strings.Add(f[1] + "|" + f[2]);
                else if (f[0] == "typ") m.Typed[f[1] + ":" + f[2]] = Ops(f[3]);
            }
            if (!ok) throw new InvalidDataException("Not a converter model file: " + path);
            return m;
        }
    }

    public class ConvertReport
    {
        public int Chunks, Textures, FailedMeshes, Files;
        public long Words, Guessed;
        public bool Grass;
        public List<string> Notes = new List<string>();
    }

    public static class Ps3Conv
    {
        // ---- small helpers ----
        static uint BE32(byte[] d, int o) { return ((uint)d[o] << 24) | ((uint)d[o + 1] << 16) | ((uint)d[o + 2] << 8) | d[o + 3]; }
        static void LE32(byte[] d, int o, uint v) { d[o] = (byte)v; d[o + 1] = (byte)(v >> 8); d[o + 2] = (byte)(v >> 16); d[o + 3] = (byte)(v >> 24); }

        static byte[] Swap32(byte[] d, int off, int len)
        {
            byte[] r = new byte[len]; int n = len / 4 * 4;
            for (int i = 0; i < n; i += 4) { r[i] = d[off + i + 3]; r[i + 1] = d[off + i + 2]; r[i + 2] = d[off + i + 1]; r[i + 3] = d[off + i]; }
            for (int i = n; i < len; i++) r[i] = d[off + i];
            return r;
        }

        static readonly bool[] NameChar = MakeSet("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-. /:()[]#+,&'\\");
        static readonly bool[] Alpha = MakeSet("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz");
        static bool[] MakeSet(string s) { bool[] r = new bool[256]; foreach (char c in s) r[c] = true; return r; }

        // bytes that belong to zero-terminated name-like strings (4+ characters, 3+ letters, starting on a word boundary)
        static bool[] TextMask(byte[] d)
        {
            int n = d.Length; bool[] m = new bool[n]; int i = 0;
            while (i < n)
            {
                int j = i, letters = 0;
                while (j < n && NameChar[d[j]]) { if (Alpha[d[j]]) letters++; j++; }
                int st = (i + 3) & ~3;
                if (j - st >= 4 && letters >= 3 && (j == n || d[j] == 0))
                    for (int k = st; k < Math.Min(j + 1, n); k++) m[k] = true;
                i = Math.Max(j, i) + 1;
            }
            return m;
        }

        // generic structure data: 32-bit swap, except words that are part of a string
        static byte[] ConvStruct(byte[] d, ICollection<int> fix, ICollection<int> refs)
        {
            byte[] r = Swap32(d, 0, d.Length); bool[] m = TextMask(d);
            HashSet<int> keep = new HashSet<int>();
            if (fix != null) foreach (int o in fix) keep.Add(o);
            if (refs != null) foreach (int o in refs) keep.Add(o);
            for (int o = 0; o + 3 < d.Length; o += 4)
                if (!keep.Contains(o) && (m[o] || m[o + 1] || m[o + 2] || m[o + 3])) { r[o] = d[o]; r[o + 1] = d[o + 1]; r[o + 2] = d[o + 2]; r[o + 3] = d[o + 3]; }
            return r;
        }

        // ---- structures (kinds 5 and 11) ----
        static readonly int[][] Perm = { new[] { 3, 2, 1, 0 }, new[] { 1, 0, 3, 2 }, new[] { 0, 1, 2, 3 }, new[] { 1, 0, 2, 3 }, new[] { 0, 1, 3, 2 }, new[] { 2, 1, 0, 3 } };
        const byte RawOp = 2;
        const int MaxP = 1024, MaxDepth = 7, SigMax = 4096;

        static byte[] ApplyOps(byte[] d, byte[] ops)
        {
            byte[] r = (byte[])d.Clone();
            for (int w = 0; w < ops.Length; w++)
            {
                int[] p = Perm[ops[w]]; int o = w * 4;
                r[o] = d[o + p[0]]; r[o + 1] = d[o + p[1]]; r[o + 2] = d[o + p[2]]; r[o + 3] = d[o + p[3]];
            }
            return r;
        }

        // a block that is one zero-terminated printable string of 3+ characters (what follows the terminator is padding)
        static bool IsString(byte[] d, int a, int b)
        {
            int z = -1;
            for (int i = a; i < b; i++) if (d[i] == 0) { z = i - a; break; }
            if (z < 3 || z < (b - a) - 7) return false;
            for (int i = a; i < a + z; i++) if (d[i] < 0x20 || d[i] > 0x7e) return false;
            return true;
        }

        // (H, P) in words: after H words the pointer positions repeat every P words; no repetition: (n, 1)
        static void PtrLayout(bool[] flags, bool[] zero, int a, int n, out int H, out int P)
        {
            H = n; P = 1;
            int first = -1, count = 0;
            for (int i = 0; i < n; i++) if (flags[a + i]) { if (first < 0) first = i; count++; }
            if (count < 2) return;
            int maxP = Math.Min((n - first) / 2, MaxP);
            bool[] col = new bool[Math.Max(maxP, 1)];
            for (int p = 1; p <= maxP; p++)
            {
                for (int pass = 0; pass < 2; pass++)
                {
                    int h;
                    if (first % p != 0) h = pass == 0 ? first - first % p : first;
                    else { if (pass == 1) break; h = first; }
                    int m = (n - h) / p;
                    if (m < (p <= 2 ? 8 : 2)) continue;
                    bool tail = false;
                    for (int i = h + m * p; i < n; i++) if (flags[a + i]) { tail = true; break; }
                    if (tail) continue;
                    for (int j = 0; j < p; j++) col[j] = false;
                    for (int i = 0; i < m * p; i++) if (flags[a + h + i]) col[i % p] = true;
                    bool ok = true; long set = 0, total = 0;
                    for (int i = 0; i < m * p && ok; i++)
                    {
                        if (!col[i % p]) continue;
                        total++;
                        if (flags[a + h + i]) set++;
                        else if (!zero[a + h + i]) ok = false;
                    }
                    if (ok && total > 0 && (double)set / total > (m < 16 ? 0.5 : 0.02)) { H = h; P = p; return; }
                }
            }
        }

        static byte[] LayoutOps(Layout e, int n)
        {
            byte[] o = new byte[n];
            if (e.Kind == 'u') { for (int i = 0; i < n; i++) o[i] = e.Op; return o; }
            if (e.Kind == 'r')
            {
                int p = e.Per.Length;
                for (int i = 0; i < n; i++) o[i] = e.Per[i % p];
                for (int i = 0; i < Math.Min(e.Hdr.Length, n); i++) o[i] = e.Hdr[i];
                return o;
            }
            if (e.Kind == 'f' && e.Ops.Length == n) return (byte[])e.Ops.Clone();
            return null;
        }

        static int LowerBound(int[] a, int v) { int lo = 0, hi = a.Length; while (lo < hi) { int mid = (lo + hi) / 2; if (a[mid] < v) lo = mid + 1; else hi = mid; } return lo; }
        static int UpperBound(int[] a, int v) { int lo = 0, hi = a.Length; while (lo < hi) { int mid = (lo + hi) / 2; if (a[mid] <= v) lo = mid + 1; else hi = mid; } return lo; }

        public static string ChunkClass(string suffix, Chunk c, byte[] d)
        {
            int[] f = (int[])c.Fix.Clone(); Array.Sort(f);
            StringBuilder sb = new StringBuilder();
            sb.Append(suffix).Append(';').Append(c.Kind).Append(';');
            if (f.Length == 0) sb.Append('-');
            for (int i = 0; i < Math.Min(3, f.Length); i++) { if (i > 0) sb.Append(','); sb.Append(f[i]); }
            uint w0 = d.Length >= 4 ? BE32(d, 0) : 0;
            sb.Append(';').Append(Math.Min(w0, 64u));
            return sb.ToString();
        }

        // The scenery tree (kind 11) is one structure, but its class holds the first three pointer offsets,
        // and a tree whose second or third node has no content gets a class the model has never seen
        // (arctic1, arctic6: 12,44,140 instead of 12,44,76). Such a tree takes the model's tree class.
        public static string TreeClass(Model M, string cls)
        {
            if (M.Classes.Contains(cls)) return cls;
            string[] p = cls.Split(';'); string found = null;
            foreach (string k in M.Classes)
            {
                string[] q = k.Split(';');
                if (q.Length != 4 || p.Length != 4 || q[1] != "11" || q[0] != p[0] || q[3] != p[3]) continue;
                if (found != null) return cls;                              // more than one candidate: leave it
                found = k;
            }
            return found ?? cls;
        }

        static byte[] ConvStructure(Model M, string cls, byte[] d, int[] fixIn, int[] refs, ConvertReport rep)
        {
            int n = d.Length / 4 * 4, nw = n / 4;
            if (nw == 0) return (byte[])d.Clone();
            List<int> fl = new List<int>();
            foreach (int x in fixIn) if (x + 4 <= n && x % 4 == 0) fl.Add(x);
            fl.Sort();
            int[] fix = fl.ToArray();
            bool[] isfix = new bool[nw + 1], zero = new bool[nw];
            for (int w = 0; w < nw; w++) zero[w] = d[w * 4] == 0 && d[w * 4 + 1] == 0 && d[w * 4 + 2] == 0 && d[w * 4 + 3] == 0;
            SortedSet<int> bs = new SortedSet<int>(); bs.Add(0); bs.Add(n);
            long[] vals = new long[fix.Length]; bool[] okv = new bool[fix.Length];
            for (int k = 0; k < fix.Length; k++)
            {
                isfix[fix[k] / 4] = true; vals[k] = BE32(d, fix[k]);
                okv[k] = vals[k] < n && vals[k] % 4 == 0;
                if (okv[k]) bs.Add((int)vals[k]);
            }
            int[] bounds = new int[bs.Count]; bs.CopyTo(bounds);
            int nb = bounds.Length - 1;
            List<long>[] kids = new List<long>[nb];                         // (rel << 32) | child, so that sorting orders by rel, then child
            for (int k = 0; k < fix.Length; k++)
            {
                if (!okv[k]) continue;
                int p = UpperBound(bounds, fix[k]) - 1, c = LowerBound(bounds, (int)vals[k]);
                if (c < nb && p < nb)
                {
                    if (kids[p] == null) kids[p] = new List<long>();
                    kids[p].Add(((long)(fix[k] - bounds[p]) << 32) | (uint)c);
                }
            }
            // roles: how each block is reached from the first one
            string[] role = new string[nb]; int[] depth = new int[nb]; int[] last = new int[nb];
            role[0] = "R"; depth[0] = 1;
            Queue<int> q = new Queue<int>(); q.Enqueue(0);
            while (q.Count > 0)
            {
                int p = q.Dequeue();
                if (kids[p] == null) continue;
                int a = bounds[p] / 4, b = bounds[p + 1] / 4, H, P;
                PtrLayout(isfix, zero, a, b - a, out H, out P); H *= 4; P *= 4;
                if (p == 0 && H == 0 && P > 4) H = P;                      // a chunk starts with a header
                kids[p].Sort();
                foreach (long kc in kids[p])
                {
                    int rel = (int)(kc >> 32), c = (int)(kc & 0xFFFFFFFF);
                    if (role[c] != null) continue;
                    int key = rel < H ? rel : H + (rel - H) % P;
                    if (depth[p] < MaxDepth && role[p][0] == 'R') { role[c] = role[p] + "," + key; depth[c] = depth[p] + 1; last[c] = key; }
                    else { role[c] = "deep"; depth[c] = 1; }
                    q.Enqueue(c);
                }
            }
            byte[] ops = new byte[nw]; bool[] tm = null; long guessed = 0;
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < nb; i++)
            {
                int a = bounds[i] / 4, b = bounds[i + 1] / 4, len = b - a;
                string r = role[i] ?? "orphan";
                Layout e; M.Roles.TryGetValue(cls + "|" + r, out e);
                bool isstr = IsString(d, a * 4, b * 4);
                byte[] o = null;
                if (isstr && (len >= 2 || M.Strings.Contains(cls + "|" + r) || e == null)) { for (int w = a; w < b; w++) ops[w] = RawOp; continue; }
                if (e != null && e.Kind != 'w') o = LayoutOps(e, len);
                if (o == null && len * 4 <= SigMax)
                {
                    sb.Length = 0; bool any = false;
                    for (int w = a; w < b; w++) if (isfix[w]) { if (any) sb.Append(','); sb.Append(w - a); any = true; }
                    Layout e2;
                    if (any && M.Sigs.TryGetValue(cls + "|" + len + "|" + sb, out e2)) o = LayoutOps(e2, len);
                }
                if (o == null && isstr) { for (int w = a; w < b; w++) ops[w] = RawOp; continue; }
                if (o == null && e == null && depth[i] > 1 && r[0] == 'R')
                {
                    List<KeyValuePair<int, Layout>> sib; int cut = r.LastIndexOf(',');
                    if (M.Kids.TryGetValue(cls + "|" + r.Substring(0, cut), out sib))
                    {
                        int bd = int.MaxValue, bk = int.MaxValue;
                        foreach (KeyValuePair<int, Layout> s in sib)
                        {
                            if (s.Value.Kind == 'w') continue;
                            int dist = Math.Abs(s.Key - last[i]);
                            if (dist > bd || (dist == bd && s.Key >= bk)) continue;
                            byte[] t = LayoutOps(s.Value, len);
                            if (t != null) { o = t; bd = dist; bk = s.Key; }
                        }
                    }
                }
                if (o == null && len >= 8 && len * 4 <= SigMax && !(e != null && e.Kind == 'w'))
                {
                    Layout e4;
                    if (M.Sigs.TryGetValue(cls + "|" + len + "|*", out e4) && e4.Kind != 'u') o = LayoutOps(e4, len);
                }
                if (o == null && e != null && e.Kind == 'w') { for (int w = a; w < b; w++) ops[w] = e.Op; continue; }
                if (o == null)
                {
                    if (tm == null) tm = TextMask(d);
                    for (int w = a; w < b; w++) ops[w] = (tm[w * 4] || tm[w * 4 + 1] || tm[w * 4 + 2] || tm[w * 4 + 3]) ? RawOp : (byte)0;
                    guessed += len; continue;
                }
                Buffer.BlockCopy(o, 0, ops, a, len);
            }
            for (int w = 0; w < nw; w++) if (isfix[w]) ops[w] = 0;
            foreach (int x in refs) if (x % 4 == 0 && x / 4 < nw) ops[x / 4] = 0;
            if (rep != null) { rep.Words += nw; rep.Guessed += guessed; }
            return ApplyOps(d, ops);
        }

        static byte[] ConvTyped(Model M, byte[] d, uint z)
        {
            byte[] ops;
            if (M.Typed.TryGetValue(z.ToString("x8") + ":" + d.Length, out ops)) return ApplyOps(d, ops);
            return ConvStruct(d, null, null);
        }

        // ---- textures (kind 4): 11 words, word 1 = self-relative pointer to the DDS header + pixels ----
        static byte[] ConvTexture(Sbf v, Chunk c)
        {
            int p = c.Data + 4 + (int)v.U(c.Data + 4), n = c.Size - 48;
            if (n < 124 || p < 0 || p + n > v.D.Length) throw new InvalidDataException("texture " + c.Id.ToString("x8") + ": data runs past the end of the file");
            byte[] r = new byte[c.Size];
            for (int k = 0; k < 11; k++) LE32(r, 4 * k, k == 1 ? 0 : v.U(c.Data + 4 * k));
            r[44] = (byte)'D'; r[45] = (byte)'D'; r[46] = (byte)'S'; r[47] = (byte)' ';
            Buffer.BlockCopy(Swap32(v.D, p, 124), 0, r, 48, 124);
            Buffer.BlockCopy(v.D, p + 124, r, 48 + 124, n - 124);
            return r;
        }

        // ---- materials (kind 2): the PS3 has 0xC8 bytes of run-time space after the first word ----
        const int MatPad = 0xC8;
        static OutChunk ConvMaterial(Chunk c, byte[] d)
        {
            byte[] body = new byte[d.Length - MatPad];
            Buffer.BlockCopy(d, 0, body, 0, 4); Buffer.BlockCopy(d, 4 + MatPad, body, 4, d.Length - 4 - MatPad);
            int[] nfix = new int[c.Fix.Length], nref = new int[c.Ref.Length];
            for (int k = 0; k < nfix.Length; k++) nfix[k] = c.Fix[k] < 4 ? c.Fix[k] : c.Fix[k] - MatPad;
            for (int k = 0; k < nref.Length; k++) nref[k] = c.Ref[k] < 4 ? c.Ref[k] : c.Ref[k] - MatPad;
            byte[] r = ConvStruct(body, nfix, nref);
            for (int k = 0; k < nfix.Length; k++)
            {
                uint v = BE32(d, c.Fix[k]);
                LE32(r, nfix[k], v < 4 ? v : v - MatPad);
            }
            OutChunk oc = new OutChunk(); oc.Kind = c.Kind; oc.Id = c.Id; oc.Z = c.Z; oc.Fix = nfix; oc.Ref = nref; oc.Data = r;
            return oc;
        }

        // ---- meshes (kind 1) ----
        const int Ps3Lod = 0x108, PcLod = 0x48;

        static float HalfToFloat(int h)
        {
            int s = (h >> 15) & 1, e = (h >> 10) & 31, m = h & 1023;
            double v;
            if (e == 0) v = m * Math.Pow(2, -24);
            else if (e == 31) v = m == 0 ? double.PositiveInfinity : double.NaN;
            else v = (1024 + m) * Math.Pow(2, e - 25);
            return (float)(s == 1 ? -v : v);
        }

        static void PutFloat(byte[] d, int o, float f) { byte[] b = BitConverter.GetBytes(f); d[o] = b[0]; d[o + 1] = b[1]; d[o + 2] = b[2]; d[o + 3] = b[3]; }

        static float Snorm(long w, int bits)
        {
            long x = w & ((1L << bits) - 1);
            if (x >= (1L << (bits - 1))) x -= 1L << bits;
            return (float)(x / (double)((1L << (bits - 1)) - 1));
        }

        static byte[] ConvVertices(byte[] d, int off, int nv, uint fmt, int stride, out int nstride)
        {
            int ns = 16;
            if ((fmt & 2) != 0) ns += 12;
            if ((fmt & 4) != 0) ns += 12;
            uint[] small = { 0x10, 0x20, 0x40, 0x80, 0x100 };
            foreach (uint bit in small) if ((fmt & bit) != 0) ns += 4;
            int ps = (fmt & 0x1000) != 0 ? 8 : 16;
            if ((fmt & 2) != 0) ps += 4;
            if ((fmt & 4) != 0) ps += 4;
            foreach (uint bit in small) if ((fmt & bit) != 0) ps += 4;
            if (ps != stride) throw new InvalidDataException("vertex format " + fmt.ToString("x") + ": elements add up to " + ps + ", stride is " + stride);
            if (off < 0 || (long)off + (long)nv * stride > d.Length) throw new InvalidDataException("vertex data runs past the end of the mesh");
            byte[] r = new byte[nv * ns];
            for (int v = 0; v < nv; v++)
            {
                int s = off + v * stride, t = v * ns;
                if ((fmt & 0x1000) != 0)
                {
                    for (int k = 0; k < 4; k++) PutFloat(r, t + 4 * k, HalfToFloat((d[s + 2 * k] << 8) | d[s + 2 * k + 1]));
                    s += 8;
                }
                else
                {
                    for (int k = 0; k < 16; k += 4) { r[t + k] = d[s + k + 3]; r[t + k + 1] = d[s + k + 2]; r[t + k + 2] = d[s + k + 1]; r[t + k + 3] = d[s + k]; }
                    s += 16;
                }
                t += 16;
                for (int e = 0; e < 2; e++)
                {
                    if ((fmt & (e == 0 ? 2u : 4u)) == 0) continue;
                    long w = BE32(d, s);                                   // normal / tangent: 11, 11 and 10 bits
                    PutFloat(r, t, Snorm(w, 11)); PutFloat(r, t + 4, Snorm(w >> 11, 11)); PutFloat(r, t + 8, Snorm(w >> 22, 10));
                    s += 4; t += 12;
                }
                foreach (uint bit in small)
                {
                    if ((fmt & bit) == 0) continue;
                    if (bit == 0x10 || bit == 0x20) { r[t] = d[s + 2]; r[t + 1] = d[s + 1]; r[t + 2] = d[s]; r[t + 3] = d[s + 3]; }   // colours: red and blue trade places
                    else { r[t] = d[s + 1]; r[t + 1] = d[s]; r[t + 2] = d[s + 3]; r[t + 3] = d[s + 2]; }                            // two 16-bit values
                    s += 4; t += 4;
                }
            }
            nstride = ns;
            return r;
        }

        // 16-bit indices with 0xFFFF restarts -> one strip joined by repeated indices
        static void ConvStrip(byte[] d, int off, int count, List<int> dst)
        {
            int start = dst.Count;
            for (int i = 0; i < count; i++)
            {
                int x = (d[off + 2 * i] << 8) | d[off + 2 * i + 1];
                if (x == 0xFFFF)
                {
                    if (dst.Count > start && i + 1 < count)
                    {
                        int nxt = (d[off + 2 * i + 2] << 8) | d[off + 2 * i + 3];
                        if (nxt != 0xFFFF)
                        {
                            dst.Add(dst[dst.Count - 1]); dst.Add(nxt);
                            if (((dst.Count - start) & 1) != 0) dst.Add(nxt);
                        }
                    }
                }
                else dst.Add(x);
            }
        }

        class Seg { public int A, B, N; public byte[] Data; }

        static OutChunk ConvMesh(Chunk c, byte[] d)
        {
            int pre = Ps3Lod - 0x3c;
            if (d.Length < Ps3Lod) throw new InvalidDataException("unexpected mesh header");
            uint first = BE32(d, pre + 32);
            int nl = (int)(first / Ps3Lod);
            if (first % Ps3Lod != 0 || nl <= 0 || nl > 64 || nl * Ps3Lod > d.Length) throw new InvalidDataException("unexpected mesh header");
            List<Seg> segs = new List<Seg>(); uint[][] hdrs = new uint[nl][];
            for (int i = 0; i < nl; i++)
            {
                int h = i * Ps3Lod;
                uint stride = BE32(d, h), w1 = BE32(d, h + 4), fmt = BE32(d, h + 8);
                uint[] t = new uint[15];
                for (int k = 0; k < 15; k++) t[k] = BE32(d, h + pre + 4 * k);
                int nv = (int)t[2], ni = (int)t[4], ng = (int)t[5], pA = (int)t[8], pB = (int)t[9], pC = (int)t[10];
                if ((fmt & 0x4000) != 0) throw new InvalidDataException("vertex format " + fmt.ToString("x") + " not handled");
                int nstride;
                byte[] vb = ConvVertices(d, pB, nv, fmt, (int)stride, out nstride);
                if (pC < 0 || (long)pC + 2L * ni > d.Length || pA < 0 || (long)pA + 20L * ng > d.Length) throw new InvalidDataException("mesh data runs past the end");
                uint[][] groups = new uint[ng][]; long total = 0;
                for (int k = 0; k < ng; k++)
                {
                    groups[k] = new uint[5];
                    for (int j = 0; j < 5; j++) groups[k][j] = BE32(d, pA + 20 * k + 4 * j);
                    total += groups[k][3] & 0xFFFF;
                }
                List<int> ix = new List<int>();
                if (ng > 0 && total == ni)
                {
                    foreach (uint[] g in groups)
                    {
                        int cnt = (int)(g[3] & 0xFFFF), before = ix.Count;
                        ConvStrip(d, pC + 2 * (int)g[2], cnt, ix);
                        g[2] = (uint)before; g[3] = (g[3] & 0xFFFF0000) | (uint)(ix.Count - before);
                    }
                }
                else ConvStrip(d, pC, ni, ix);
                byte[] ib = new byte[(ix.Count * 2 + 3) / 4 * 4];
                for (int k = 0; k < ix.Count; k++) { ib[2 * k] = (byte)ix[k]; ib[2 * k + 1] = (byte)(ix[k] >> 8); }
                int oldEnd = pC + 2 * ni + ((4 - (2 * ni) % 4) % 4);
                uint[] hdr = new uint[18];
                hdr[0] = (uint)nstride; hdr[1] = w1; hdr[2] = fmt & ~0x1000u;
                for (int k = 0; k < 15; k++) hdr[3 + k] = t[k];
                hdr[7] = (uint)ix.Count;
                hdrs[i] = hdr;
                byte[] gb = new byte[20 * ng];
                for (int k = 0; k < ng; k++) for (int j = 0; j < 5; j++) LE32(gb, 20 * k + 4 * j, groups[k][j]);
                Seg s1 = new Seg(); s1.A = pA; s1.B = pB; s1.Data = gb; segs.Add(s1);
                Seg s2 = new Seg(); s2.A = pB; s2.B = pC; s2.Data = vb; segs.Add(s2);
                Seg s3 = new Seg(); s3.A = pC; s3.B = oldEnd; s3.Data = ib; segs.Add(s3);
            }
            segs.Sort(delegate (Seg x, Seg y) { return x.A != y.A ? x.A.CompareTo(y.A) : x.B.CompareTo(y.B); });
            List<Seg> full = new List<Seg>(); int pos = nl * Ps3Lod;
            foreach (Seg s in segs)
            {
                if (s.A < pos) throw new InvalidDataException("overlapping mesh blocks");
                if (s.A > pos) { Seg g = new Seg(); g.A = pos; g.B = s.A; full.Add(g); }
                full.Add(s); pos = s.B;
            }
            if (pos < d.Length) { Seg g = new Seg(); g.A = pos; g.B = d.Length; full.Add(g); }
            int newpos = nl * PcLod;
            foreach (Seg s in full) { s.N = newpos; newpos += s.Data == null ? s.B - s.A : s.Data.Length; }
            int[] olds = new int[full.Count + 1]; olds[0] = 0;
            for (int k = 0; k < full.Count; k++) olds[k + 1] = full[k].A;
            Func<long, int> remap = delegate (long o)
            {
                if (o < nl * Ps3Lod)
                {
                    int i = (int)(o / Ps3Lod), r = (int)(o % Ps3Lod);
                    return i * PcLod + (r < 12 ? r : r >= 0xCC ? r - 0xC0 : 12);
                }
                int j = UpperBound(olds, (int)Math.Min(o, int.MaxValue)) - 1;
                if (j == 0) return full.Count > 0 ? full[0].N : (int)o;
                Seg s = full[j - 1];
                if (o >= s.B && j < full.Count) return full[j].N;
                return (int)(s.N + (o - s.A));
            };
            HashSet<int> fixset = new HashSet<int>(c.Fix);
            byte[] res = new byte[newpos];
            for (int i = 0; i < nl; i++)
            {
                uint[] hdr = hdrs[i]; int h = i * Ps3Lod;
                for (int k = 11; k <= 13; k++) if (fixset.Contains(h + pre + 4 * (k - 3))) hdr[k] = (uint)remap(hdr[k]);
                for (int k = 0; k < 18; k++) LE32(res, i * PcLod + 4 * k, hdr[k]);
            }
            foreach (Seg s in full)
            {
                byte[] nb = s.Data;
                if (nb == null)
                {
                    byte[] part = new byte[s.B - s.A]; Buffer.BlockCopy(d, s.A, part, 0, part.Length);
                    List<int> f2 = new List<int>(), r2 = new List<int>();
                    foreach (int o in c.Fix) if (o >= s.A && o < s.B) f2.Add(o - s.A);
                    foreach (int o in c.Ref) if (o >= s.A && o < s.B) r2.Add(o - s.A);
                    nb = ConvStruct(part, f2, r2);
                    foreach (int o in f2) LE32(nb, o, (uint)remap(BE32(d, s.A + o)));
                }
                Buffer.BlockCopy(nb, 0, res, s.N, nb.Length);
            }
            OutChunk oc = new OutChunk(); oc.Kind = c.Kind; oc.Id = c.Id; oc.Z = c.Z; oc.Data = res;
            oc.Fix = new int[c.Fix.Length]; oc.Ref = new int[c.Ref.Length];
            for (int k = 0; k < c.Fix.Length; k++) oc.Fix[k] = remap(c.Fix[k]);
            Array.Sort(oc.Fix);
            for (int k = 0; k < c.Ref.Length; k++) oc.Ref[k] = remap(c.Ref[k]);
            return oc;
        }

        // ---- the container ----
        static int AlignOf(uint kind)
        {
            switch (kind) { case 5: case 6: case 11: case 13: return 0; case 4: return 4; case 7: return 8; default: return -1; }
        }

        static uint Adler32(byte[] d)
        {
            uint a = 1, b = 0; int i = 0;
            while (i < d.Length)
            {
                int end = Math.Min(i + 3800, d.Length);
                for (; i < end; i++) { a += d[i]; b += a; }
                a %= 65521; b %= 65521;
            }
            return (b << 16) | a;
        }

        public static byte[] BuildSbf(List<OutChunk> chunks) { return BuildSbf(chunks, true); }

        public static byte[] BuildSbf(List<OutChunk> chunks, bool compress)
        {
            int n = chunks.Count; long pos = 24 + 8L * n;
            pos = Math.Max(0x1000, (pos + 0xFFF) & ~0xFFFL);
            MemoryStream body = new MemoryStream(); BinaryWriter w = new BinaryWriter(body);
            long[] offs = new long[n];
            for (int i = 0; i < n; i++)
            {
                OutChunk c = chunks[i];
                long here = pos + body.Length; int hdr = 24 + 4 * c.Fix.Length + 4 * c.Ref.Length, want = AlignOf(c.Kind);
                int pad = want < 0 ? (int)((4 - here % 4) % 4) : (int)(((want - (here + hdr)) % 16 + 16) % 16);
                for (int k = 0; k < pad; k++) w.Write((byte)0);
                offs[i] = pos + body.Length;
                w.Write(c.Kind); w.Write(c.Id); w.Write((uint)c.Data.Length); w.Write(c.Z); w.Write((uint)c.Fix.Length);
                foreach (int x in c.Fix) w.Write((uint)x);
                w.Write((uint)c.Ref.Length);
                foreach (int x in c.Ref) w.Write((uint)x);
                w.Write(c.Data);
            }
            w.Flush();
            byte[] raw = new byte[pos + body.Length + 2048];
            LE32(raw, 0, 4); LE32(raw, 20, (uint)n);
            for (int i = 0; i < n; i++) { LE32(raw, 24 + 8 * i, chunks[i].Id); LE32(raw, 28 + 8 * i, (uint)offs[i]); }
            body.Position = 0; body.Read(raw, (int)pos, (int)body.Length);
            if (!compress) return raw;
            MemoryStream outp = new MemoryStream();
            outp.Write(new byte[] { (byte)'S', (byte)'B', (byte)'Z', (byte)'1' }, 0, 4);
            byte[] len = new byte[4]; LE32(len, 0, (uint)raw.Length); outp.Write(len, 0, 4);
            outp.WriteByte(0x78); outp.WriteByte(0x9C);
            using (DeflateStream z = new DeflateStream(outp, CompressionLevel.Optimal, true)) z.Write(raw, 0, raw.Length);
            uint ad = Adler32(raw);
            outp.Write(new byte[] { (byte)(ad >> 24), (byte)(ad >> 16), (byte)(ad >> 8), (byte)ad }, 0, 4);
            return outp.ToArray();
        }

        // ---- a whole file ----
        public static readonly string[] Used = { "game_objects_gfx_data", "gameobj_gfx_dis_data", "pobj_master_gfx_xdata", "pobj_plac_gfx_xdata", "master_gfx_xdata", "master_xdata" };

        public static List<OutChunk> ConvertSbf(Model M, string sbfPath, string suffix, ConvertReport rep)
        {
            Sbf s = new Sbf(sbfPath, true);
            string stem = sbfPath.Substring(0, sbfPath.Length - 4);
            Dictionary<uint, KeyValuePair<Sbf, Chunk>> tex = new Dictionary<uint, KeyValuePair<Sbf, Chunk>>();
            List<uint> order = new List<uint>();
            foreach (string ext in new[] { ".vbf", ".1.vbf", ".2.vbf" })
            {
                string vp = stem + ext;
                if (!File.Exists(vp) || new FileInfo(vp).Length < 64) continue;
                Sbf v = new Sbf(vp, true);
                foreach (Chunk c in v.Chunks) { if (!tex.ContainsKey(c.Id)) order.Add(c.Id); tex[c.Id] = new KeyValuePair<Sbf, Chunk>(v, c); }
            }
            List<OutChunk> outp = new List<OutChunk>(); HashSet<uint> done = new HashSet<uint>();
            Action<uint> emit = delegate (uint id)
            {
                KeyValuePair<Sbf, Chunk> t;
                if (!tex.TryGetValue(id, out t) || !done.Add(id)) return;
                OutChunk oc = new OutChunk(); oc.Kind = 4; oc.Id = t.Value.Id; oc.Z = t.Value.Z; oc.Fix = new int[0]; oc.Ref = new int[0];
                oc.Data = ConvTexture(t.Key, t.Value); outp.Add(oc); rep.Textures++;
            };
            foreach (Chunk c in s.Chunks)
            {
                byte[] d = s.Bytes(c);
                foreach (int o in c.Ref) if (o + 4 <= d.Length) emit(BE32(d, o));
                OutChunk oc = new OutChunk(); oc.Kind = c.Kind; oc.Id = c.Id; oc.Z = c.Z; oc.Fix = c.Fix; oc.Ref = c.Ref;
                if (c.Kind == 1)
                {
                    try { oc = ConvMesh(c, d); }
                    catch (InvalidDataException) { rep.FailedMeshes++; continue; }
                }
                else if (c.Kind == 2) oc = ConvMaterial(c, d);
                else if (c.Kind == 7) oc.Data = d;
                else if (c.Kind == 6) oc.Data = Swap32(d, 0, d.Length);
                else if (c.Kind == 12) oc.Data = ConvTyped(M, d, c.Z);
                else if (c.Kind == 11) oc.Data = ConvStructure(M, TreeClass(M, ChunkClass(suffix, c, d)), d, c.Fix, c.Ref, rep);
                else if (c.Kind == 5) oc.Data = ConvStructure(M, ChunkClass(suffix, c, d), d, c.Fix, c.Ref, rep);
                else oc.Data = ConvStruct(d, c.Fix, c.Ref);
                outp.Add(oc); rep.Chunks++;
            }
            foreach (uint id in order) emit(id);
            return outp;
        }

        // ---- the grass cache (proc_cached.bin) ----
        public static byte[] ConvProc(byte[] p)
        {
            if (p.Length < 64) throw new InvalidDataException("not a grass cache");
            uint[] h = new uint[16];
            for (int k = 0; k < 16; k++) h[k] = BE32(p, 4 * k);
            long[] offs = new long[9];
            for (int k = 0; k < 8; k++) offs[k] = h[4 + k];
            offs[8] = p.Length;
            if (h[0] != 2 || offs[0] != 0x40) throw new InvalidDataException("not a grass cache this converter knows");
            for (int k = 0; k < 8; k++) if (offs[k] > offs[k + 1] || (k < 7 && (offs[k + 1] - offs[k]) % 4 != 0)) throw new InvalidDataException("not a grass cache this converter knows");
            byte[] r = (byte[])p.Clone();
            for (int k = 0; k < 16; k++) LE32(r, 4 * k, h[k]);
            for (long o = offs[0]; o + 8 <= offs[1]; o += 8)                // u32, u16, u16
            {
                r[o] = p[o + 3]; r[o + 1] = p[o + 2]; r[o + 2] = p[o + 1]; r[o + 3] = p[o];
                r[o + 4] = p[o + 5]; r[o + 5] = p[o + 4]; r[o + 6] = p[o + 7]; r[o + 7] = p[o + 6];
            }
            for (long o = offs[1]; o + 96 <= offs[2]; o += 96)              // 96-byte records, two 16-bit values at 0x54
                for (int k = 0; k < 96; k += 4)
                {
                    if (k == 0x54) { r[o + k] = p[o + k + 1]; r[o + k + 1] = p[o + k]; r[o + k + 2] = p[o + k + 3]; r[o + k + 3] = p[o + k + 2]; }
                    else { r[o + k] = p[o + k + 3]; r[o + k + 1] = p[o + k + 2]; r[o + k + 2] = p[o + k + 1]; r[o + k + 3] = p[o + k]; }
                }
            for (long o = offs[2]; o + 4 <= offs[3]; o += 4) { r[o] = p[o + 3]; r[o + 1] = p[o + 2]; r[o + 2] = p[o + 1]; r[o + 3] = p[o]; }
            for (long o = offs[3]; o + 4 <= offs[4]; o += 4)                // bit fields 8, 5, 8, 10, 1 -> 8, 5, 10, 8, 1
            {
                uint v = BE32(p, (int)o);
                LE32(r, (int)o, (v >> 24) | (((v >> 19) & 31) << 8) | (((v >> 1) & 1023) << 13) | (((v >> 11) & 255) << 23) | ((v & 1) << 31));
            }
            for (long o = offs[4]; o + 4 <= offs[7]; o += 4) { r[o] = p[o + 3]; r[o + 1] = p[o + 2]; r[o + 2] = p[o + 1]; r[o + 3] = p[o]; }
            long i = offs[7], n = p.Length;                                 // u16 count, then per cell: u16 id, byte pairs, ff 00
            if (n - i >= 2) { r[i] = p[i + 1]; r[i + 1] = p[i]; i += 2; }
            while (i + 1 < n)
            {
                r[i] = p[i + 1]; r[i + 1] = p[i];
                if (p[i] == 0xff && p[i + 1] == 0xff) { i += 2; continue; }
                i += 2;
                while (i + 1 < n && !(p[i] == 0xff && p[i + 1] == 0x00)) i += 2;
                i += 2;
            }
            return r;
        }

        // ---- a whole track ----
        // src = the PS3 track folder; files are written to dst as <route>_... and <env>_...
        public static ConvertReport ConvertTrack(Model M, string src, string dst, string srcRoute, string srcEnv, string route, string env)
        {
            return ConvertTrack(M, src, dst, srcRoute, srcEnv, route, env, true);
        }

        public static ConvertReport ConvertTrack(Model M, string src, string dst, string srcRoute, string srcEnv, string route, string env, bool compress)
        {
            ConvertReport rep = new ConvertReport();
            Directory.CreateDirectory(dst);
            foreach (string suffix in Used)
            {
                bool isEnv = suffix.StartsWith("master");
                string p = Path.Combine(src, (isEnv ? srcEnv : srcRoute) + "_" + suffix + ".sbf");
                if (!File.Exists(p)) { rep.Notes.Add("The PS3 track has no " + suffix + " file."); continue; }
                List<OutChunk> chunks = ConvertSbf(M, p, suffix, rep);
                File.WriteAllBytes(Path.Combine(dst, (isEnv ? env : route) + "_" + suffix + ".sbf"), BuildSbf(chunks, compress));
                rep.Files++;
            }
            string grass = Path.Combine(src, srcRoute + "_proc_cached.bin");
            if (File.Exists(grass))
            {
                try { File.WriteAllBytes(Path.Combine(dst, route + "_proc_cached.bin"), ConvProc(File.ReadAllBytes(grass))); rep.Grass = true; rep.Files++; }
                catch (InvalidDataException e) { rep.Notes.Add("Grass was left out: " + e.Message); }
            }
            if (rep.FailedMeshes > 0) rep.Notes.Add(rep.FailedMeshes + " object(s) could not be converted and were left out.");
            if (rep.Words > 0 && rep.Guessed * 200 > rep.Words) rep.Notes.Add("About " + (rep.Guessed * 100 / rep.Words) + "% of this track's structure data is of a kind the converter has not seen; it may misbehave.");
            return rep;
        }
    }
}
