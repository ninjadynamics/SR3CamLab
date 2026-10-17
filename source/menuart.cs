// SR3 Extras: the stage-select pictures of a track slot. SEGA Rally 3 looks up two textures by the
// slot's folder name, in frontend\arcade permanent resources_data.sbf:
//   BKGD_NAME_<slot>    1280 x 720, the blurred picture behind the stage-select screen
//   MENU_BANNER_<slot>  1024 x 128, the strip with the track's name
// A named texture is a small structure chunk {2, 0, texture id, -> name} plus the texture chunk.
// For an imported SEGA Rally Revo track, both are made from the track's own card picture
// (TRACKSLIDE_<TRACK>), which the arcade game still carries in frontend\frontend track cards_data.sbf.
// Compiled together with ps3conv.cs (it uses its Sbf reader and writer).
using System;
using System.Collections.Generic;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.IO;
using System.Runtime.InteropServices;

namespace SR3Extras
{
    public static class MenuArt
    {
        static uint U(byte[] d, int o) { return (uint)(d[o] | (d[o + 1] << 8) | (d[o + 2] << 16) | (d[o + 3] << 24)); }

        // name -> the texture chunk it points to
        public static Dictionary<string, Chunk> Named(Sbf s)
        {
            Dictionary<uint, Chunk> byId = new Dictionary<uint, Chunk>();
            foreach (Chunk c in s.Chunks) if (c.Kind == 4) byId[c.Id] = c;
            Dictionary<string, Chunk> r = new Dictionary<string, Chunk>(StringComparer.OrdinalIgnoreCase);
            foreach (Chunk c in s.Chunks)
            {
                if (c.Kind != 5 || c.Ref.Length != 1 || c.Size < 20 || U(s.D, c.Data) != 2 || U(s.D, c.Data + 12) != 0x10) continue;
                int e = c.Data + 16;
                while (e < c.Data + c.Size && s.D[e] != 0) e++;
                Chunk t;
                if (byId.TryGetValue(U(s.D, c.Data + 8), out t)) r[System.Text.Encoding.ASCII.GetString(s.D, c.Data + 16, e - c.Data - 16)] = t;
            }
            return r;
        }

        // ---- DXT1 / DXT5 ----
        static void Colours(byte[] d, int o, uint[] col, bool dxt1)
        {
            int c0 = d[o] | (d[o + 1] << 8), c1 = d[o + 2] | (d[o + 3] << 8);
            int[] r = new int[4], g = new int[4], b = new int[4];
            r[0] = (c0 >> 11) * 255 / 31; g[0] = ((c0 >> 5) & 63) * 255 / 63; b[0] = (c0 & 31) * 255 / 31;
            r[1] = (c1 >> 11) * 255 / 31; g[1] = ((c1 >> 5) & 63) * 255 / 63; b[1] = (c1 & 31) * 255 / 31;
            bool three = dxt1 && c0 <= c1;
            if (three) { r[2] = (r[0] + r[1]) / 2; g[2] = (g[0] + g[1]) / 2; b[2] = (b[0] + b[1]) / 2; r[3] = g[3] = b[3] = 0; }
            else
            {
                r[2] = (2 * r[0] + r[1]) / 3; g[2] = (2 * g[0] + g[1]) / 3; b[2] = (2 * b[0] + b[1]) / 3;
                r[3] = (r[0] + 2 * r[1]) / 3; g[3] = (g[0] + 2 * g[1]) / 3; b[3] = (b[0] + 2 * b[1]) / 3;
            }
            for (int k = 0; k < 4; k++) col[k] = (uint)((r[k] << 16) | (g[k] << 8) | b[k]) | ((three && k == 3) ? 0u : 0xFF000000u);
        }

        // the texture chunk's first mip level as a 32-bit picture
        public static Bitmap Decode(Sbf s, Chunk t)
        {
            int dds = t.Data + 48;                                          // past the 11 header words and "DDS "
            int h = (int)U(s.D, dds + 8), w = (int)U(s.D, dds + 12);
            string four = System.Text.Encoding.ASCII.GetString(s.D, dds + 80, 4);
            bool dxt1 = four == "DXT1";
            if (!dxt1 && four != "DXT5") throw new InvalidDataException("Texture format " + four + " is not supported.");
            int p = dds + 124, bw = (w + 3) / 4, bh = (h + 3) / 4;
            int[] px = new int[w * h]; uint[] col = new uint[4]; int[] al = new int[8];
            for (int by = 0; by < bh; by++)
                for (int bx = 0; bx < bw; bx++)
                {
                    long abits = 0;
                    if (!dxt1)
                    {
                        al[0] = s.D[p]; al[1] = s.D[p + 1];
                        if (al[0] > al[1]) for (int k = 1; k < 7; k++) al[k + 1] = ((7 - k) * al[0] + k * al[1]) / 7;
                        else { for (int k = 1; k < 5; k++) al[k + 1] = ((5 - k) * al[0] + k * al[1]) / 5; al[6] = 0; al[7] = 255; }
                        for (int k = 0; k < 6; k++) abits |= (long)s.D[p + 2 + k] << (8 * k);
                        p += 8;
                    }
                    Colours(s.D, p, col, dxt1);
                    uint idx = U(s.D, p + 4); p += 8;
                    for (int y = 0; y < 4; y++)
                        for (int x = 0; x < 4; x++)
                        {
                            int X = bx * 4 + x, Y = by * 4 + y;
                            if (X >= w || Y >= h) continue;
                            uint c = col[(idx >> (2 * (4 * y + x))) & 3];
                            if (!dxt1) c = (c & 0x00FFFFFF) | ((uint)al[(abits >> (3 * (4 * y + x))) & 7] << 24);
                            px[Y * w + X] = (int)c;
                        }
                }
            Bitmap bmp = new Bitmap(w, h, PixelFormat.Format32bppArgb);
            BitmapData bd = bmp.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
            Marshal.Copy(px, 0, bd.Scan0, px.Length); bmp.UnlockBits(bd);
            return bmp;
        }

        static int To565(int r, int g, int b) { return ((r * 31 + 127) / 255 << 11) | ((g * 63 + 127) / 255 << 5) | ((b * 31 + 127) / 255); }

        // DXT5 data of a picture (one mip level); width and height must be multiples of 4
        public static byte[] EncodeDxt5(Bitmap src)
        {
            int w = src.Width, h = src.Height;
            int[] px = new int[w * h];
            using (Bitmap b32 = src.Clone(new Rectangle(0, 0, w, h), PixelFormat.Format32bppArgb))
            {
                BitmapData bd = b32.LockBits(new Rectangle(0, 0, w, h), ImageLockMode.ReadOnly, PixelFormat.Format32bppArgb);
                Marshal.Copy(bd.Scan0, px, 0, px.Length); b32.UnlockBits(bd);
            }
            byte[] o = new byte[w / 4 * (h / 4) * 16]; int p = 0;
            int[] r = new int[16], g = new int[16], b = new int[16], a = new int[16];
            for (int by = 0; by < h; by += 4)
                for (int bx = 0; bx < w; bx += 4)
                {
                    int amin = 255, amax = 0, rmin = 255, gmin = 255, bmin = 255, rmax = 0, gmax = 0, bmax = 0;
                    for (int k = 0; k < 16; k++)
                    {
                        int c = px[(by + k / 4) * w + bx + k % 4];
                        a[k] = (c >> 24) & 255; r[k] = (c >> 16) & 255; g[k] = (c >> 8) & 255; b[k] = c & 255;
                        amin = Math.Min(amin, a[k]); amax = Math.Max(amax, a[k]);
                        rmin = Math.Min(rmin, r[k]); rmax = Math.Max(rmax, r[k]); gmin = Math.Min(gmin, g[k]); gmax = Math.Max(gmax, g[k]); bmin = Math.Min(bmin, b[k]); bmax = Math.Max(bmax, b[k]);
                    }
                    // alpha: two end points and six steps between them
                    o[p] = (byte)amax; o[p + 1] = (byte)amin; long abits = 0;
                    if (amax > amin)
                        for (int k = 0; k < 16; k++)
                        {
                            int step = ((amax - a[k]) * 7 + (amax - amin) / 2) / (amax - amin);        // 0 = max ... 7 = min
                            int code = step == 0 ? 0 : step == 7 ? 1 : step + 1;
                            abits |= (long)code << (3 * k);
                        }
                    for (int k = 0; k < 6; k++) o[p + 2 + k] = (byte)(abits >> (8 * k));
                    p += 8;
                    // colour: the corners of the block's colour box, pixels snapped to the four colours on the line between them
                    int c0 = To565(rmax, gmax, bmax), c1 = To565(rmin, gmin, bmin);
                    if (c0 < c1) { int t = c0; c0 = c1; c1 = t; }
                    uint idx = 0;
                    if (c0 != c1)
                    {
                        int dr = rmax - rmin, dg = gmax - gmin, db = bmax - bmin, len = dr * dr + dg * dg + db * db;
                        for (int k = 0; k < 16; k++)
                        {
                            int t = ((r[k] - rmin) * dr + (g[k] - gmin) * dg + (b[k] - bmin) * db) * 3;
                            int step = len == 0 ? 0 : (t + len / 2) / len;                              // 0 = min ... 3 = max
                            uint code = step >= 3 ? 0u : step == 2 ? 2u : step == 1 ? 3u : 1u;
                            idx |= code << (2 * k);
                        }
                    }
                    o[p] = (byte)c0; o[p + 1] = (byte)(c0 >> 8); o[p + 2] = (byte)c1; o[p + 3] = (byte)(c1 >> 8);
                    o[p + 4] = (byte)idx; o[p + 5] = (byte)(idx >> 8); o[p + 6] = (byte)(idx >> 16); o[p + 7] = (byte)(idx >> 24);
                    p += 8;
                }
            return o;
        }

        // ---- the two pictures of a slot, from a track's card ----
        // the card's picture without its transparent surround and frame
        static Rectangle Photo(Bitmap card)
        {
            int w = card.Width, h = card.Height, x0 = w, y0 = h, x1 = -1, y1 = -1;
            for (int y = 0; y < h; y += 2)
                for (int x = 0; x < w; x += 2)
                    if (card.GetPixel(x, y).A > 200) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
            if (x1 < 0) return new Rectangle(0, 0, w, h);
            Rectangle r = Rectangle.FromLTRB(x0, y0, x1 + 1, y1 + 1);
            r.Inflate(-r.Width / 40 - 2, -r.Height / 28 - 2);                // the white frame
            return r;
        }

        public static Bitmap MakeBackground(Bitmap card)
        {
            Rectangle ph = Photo(card);
            Bitmap small = new Bitmap(24, 14, PixelFormat.Format32bppArgb);                 // shrinking and stretching back is the blur
            using (Graphics g = Graphics.FromImage(small)) { g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.PixelOffsetMode = PixelOffsetMode.HighQuality; g.DrawImage(card, new Rectangle(0, 0, 24, 14), ph, GraphicsUnit.Pixel); }
            Bitmap bg = new Bitmap(1280, 720, PixelFormat.Format32bppArgb);
            using (Graphics g = Graphics.FromImage(bg))
            {
                g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.PixelOffsetMode = PixelOffsetMode.HighQuality;
                using (ImageAttributes ia = new ImageAttributes()) { ia.SetWrapMode(WrapMode.TileFlipXY); g.DrawImage(small, new Rectangle(0, 0, 1280, 720), 0, 0, 24, 14, GraphicsUnit.Pixel, ia); }
            }
            small.Dispose();
            return bg;
        }

        public static Bitmap MakeBanner(Bitmap card, string title)
        {
            Rectangle ph = Photo(card);
            Bitmap bn = new Bitmap(1024, 128, PixelFormat.Format32bppArgb);
            using (Graphics g = Graphics.FromImage(bn))
            {
                g.Clear(Color.Transparent);
                g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.PixelOffsetMode = PixelOffsetMode.HighQuality; g.SmoothingMode = SmoothingMode.AntiAlias;
                Rectangle body = new Rectangle(0, 16, 1024, 96);                                   // like the game's banners: a strip with a light line above and below
                int sh = ph.Width * body.Height / body.Width;                                      // a slice across the middle of the photo
                Rectangle slice = new Rectangle(ph.X, ph.Y + (ph.Height - sh) * 2 / 5, ph.Width, Math.Max(sh, 1));
                g.DrawImage(card, body, slice, GraphicsUnit.Pixel);
                using (LinearGradientBrush shade = new LinearGradientBrush(new Rectangle(0, 0, 520, 128), Color.FromArgb(215, 10, 20, 30), Color.FromArgb(0, 10, 20, 30), 0f)) g.FillRectangle(shade, new Rectangle(0, body.Y, 520, body.Height));
                using (Pen line = new Pen(Color.FromArgb(235, 235, 235), 4)) { g.DrawLine(line, 0, body.Y - 2, 1024, body.Y - 2); g.DrawLine(line, 0, body.Bottom + 2, 1024, body.Bottom + 2); }
                using (Font f = new Font("Segoe UI", 50, FontStyle.Bold, GraphicsUnit.Pixel))
                using (StringFormat sf = new StringFormat())
                {
                    sf.LineAlignment = StringAlignment.Center;
                    g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;
                    g.DrawString(title, f, Brushes.White, new RectangleF(22, body.Y, 700, body.Height), sf);
                }
            }
            return bn;
        }

        // ---- the stage card: in the arcade game it is a short video (frontend\PC\Videos\LANG_<language>_<TRO|CAN|ALP>.wmv) ----
        // The moving part: the card's photo, larger than the video so that it can zoom slowly.
        public static Bitmap MakeCardPhoto(Bitmap card)
        {
            Rectangle ph = Photo(card);
            int h = ph.Width * 9 / 16;                                                             // 16:9 out of the middle
            if (h > ph.Height) { int w = ph.Height * 16 / 9; ph = new Rectangle(ph.X + (ph.Width - w) / 2, ph.Y, w, ph.Height); }
            else ph = new Rectangle(ph.X, ph.Y + (ph.Height - h) / 2, ph.Width, h);
            Bitmap b = new Bitmap(1280, 720, PixelFormat.Format32bppArgb);
            using (Graphics g = Graphics.FromImage(b)) { g.InterpolationMode = InterpolationMode.HighQualityBicubic; g.PixelOffsetMode = PixelOffsetMode.HighQuality; g.DrawImage(card, new Rectangle(0, 0, 1280, 720), ph, GraphicsUnit.Pixel); }
            return b;
        }

        // The still part, drawn over the photo: the track's name and the slot's difficulty.
        public static Bitmap MakeCardOverlay(string title, string level)
        {
            Bitmap b = new Bitmap(640, 360, PixelFormat.Format32bppArgb);
            using (Graphics g = Graphics.FromImage(b))
            {
                g.Clear(Color.Transparent); g.SmoothingMode = SmoothingMode.AntiAlias;
                using (GraphicsPath path = new GraphicsPath())
                using (StringFormat sf = new StringFormat())
                using (FontFamily ff = new FontFamily("Arial"))
                {
                    sf.Alignment = StringAlignment.Center; sf.LineAlignment = StringAlignment.Center;
                    float size = 112;
                    using (Font probe = new Font(ff, size, FontStyle.Bold, GraphicsUnit.Pixel))
                    {
                        float w = g.MeasureString(title.ToUpper(), probe).Width;
                        if (w > 600) size = size * 600 / w;
                    }
                    path.AddString(title.ToUpper(), ff, (int)FontStyle.Bold, size, new RectangleF(0, 150, 640, 150), sf);
                    using (Pen edge = new Pen(Color.FromArgb(150, 60, 40, 0), 6)) { edge.LineJoin = LineJoin.Round; g.DrawPath(edge, path); }
                    using (Brush fill = new SolidBrush(Color.FromArgb(235, 255, 240, 0))) g.FillPath(fill, path);
                }
                if (!string.IsNullOrEmpty(level))
                {
                    Color c = level == "EASY" ? Color.FromArgb(60, 220, 60) : level == "HARD" ? Color.FromArgb(235, 60, 50) : Color.FromArgb(240, 160, 30);
                    using (Font f = new Font("Arial", 30, FontStyle.Bold, GraphicsUnit.Pixel))
                    using (Brush shadow = new SolidBrush(Color.FromArgb(150, 0, 0, 0)))
                    using (Brush br = new SolidBrush(c))
                    { g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAlias; g.DrawString(level, f, shadow, 20, 16); g.DrawString(level, f, br, 18, 14); }
                }
            }
            return b;
        }

        // ---- a second set of names ----
        // Copies the resource file and adds, for every named texture whose name starts with one of
        // the prefixes in 'rename' (old prefix -> new prefix), a second name. The new name shows the
        // picture given for it in 'pictures' (keyed by the NEW name), or else the same picture as the
        // old name. The game finds these when the switcher rewrites its name patterns.
        // The game crashed at start-up with this file grown from 10.5 to 16.7 MB (every new name
        // with a full-size picture of its own), so: when pictures are given, only the names that
        // have one are added, and a new picture may be smaller than the one it stands in for
        // (a blurred background does not need 1280 x 720).
        public static int AddNames(string srcFile, string dstFile, Dictionary<string, string> rename, Dictionary<string, Bitmap> pictures)
        {
            Sbf s = new Sbf(srcFile, false);
            Dictionary<string, Chunk> named = Named(s);
            HashSet<uint> ids = new HashSet<uint>();
            List<OutChunk> outp = new List<OutChunk>();
            foreach (Chunk c in s.Chunks)
            {
                ids.Add(c.Id);
                OutChunk oc = new OutChunk(); oc.Kind = c.Kind; oc.Id = c.Id; oc.Z = c.Z; oc.Fix = c.Fix; oc.Ref = c.Ref; oc.Data = s.Bytes(c);
                outp.Add(oc);
            }
            // the file's last structure is its index: {1, -> list, -> second list}, each list = record ids, then 0
            int ix = -1;
            for (int k = 0; k < outp.Count; k++)
                if (outp[k].Kind == 5 && outp[k].Fix.Length == 2 && outp[k].Fix[0] == 4 && outp[k].Fix[1] == 8 && outp[k].Data.Length >= 16 && U(outp[k].Data, 0) == 1) ix = k;
            if (ix < 0) throw new InvalidDataException("The game's menu file has no index this tool knows how to extend.");
            List<OutChunk> extra = new List<OutChunk>(); List<uint> newIds = new List<uint>();
            foreach (KeyValuePair<string, Chunk> kv in named)
            {
                string newName = null;
                foreach (KeyValuePair<string, string> r in rename)
                    if (kv.Key.StartsWith(r.Key, StringComparison.OrdinalIgnoreCase)) { newName = r.Value + kv.Key.Substring(r.Key.Length); break; }
                if (newName == null || named.ContainsKey(newName)) continue;
                Chunk t = kv.Value;
                byte[] d = s.Bytes(t);                                            // every name gets a texture of its own
                Bitmap pic;
                if (pictures != null)
                {
                    if (!pictures.TryGetValue(newName, out pic)) continue;
                    int dds = t.Data + 48, h = (int)U(s.D, dds + 8), w = (int)U(s.D, dds + 12);
                    if (48 + 124 + w * h != t.Size) throw new InvalidDataException(kv.Key + " is stored in a way this tool does not write (not a single DXT5 picture).");
                    if (pic.Width % 4 != 0 || pic.Height % 4 != 0 || pic.Width > w || pic.Height > h) throw new InvalidDataException(kv.Key + " is " + w + " x " + h + "; the new picture does not fit it.");
                    byte[] pix = EncodeDxt5(pic);
                    byte[] nd2 = new byte[48 + 124 + pix.Length];
                    Buffer.BlockCopy(d, 0, nd2, 0, 48 + 124);
                    Buffer.BlockCopy(pix, 0, nd2, 48 + 124, pix.Length);
                    Put(nd2, 8, (uint)pic.Width); Put(nd2, 12, (uint)pic.Height);                 // the texture's own header
                    Put(nd2, 48 + 8, (uint)pic.Height); Put(nd2, 48 + 12, (uint)pic.Width); Put(nd2, 48 + 16, (uint)pix.Length);   // the DDS header
                    d = nd2;
                }
                uint texId = FreeId(ids, newName + "/texture");
                OutChunk tc = new OutChunk(); tc.Kind = 4; tc.Id = texId; tc.Z = t.Z; tc.Fix = new int[0]; tc.Ref = new int[0]; tc.Data = d;
                extra.Add(tc);
                byte[] nm = System.Text.Encoding.ASCII.GetBytes(newName);
                byte[] rec = new byte[16 + (nm.Length + 4) / 4 * 4];
                rec[0] = 2; rec[12] = 0x10;
                rec[8] = (byte)texId; rec[9] = (byte)(texId >> 8); rec[10] = (byte)(texId >> 16); rec[11] = (byte)(texId >> 24);
                Buffer.BlockCopy(nm, 0, rec, 16, nm.Length);
                OutChunk nc = new OutChunk(); nc.Kind = 5; nc.Id = FreeId(ids, newName); nc.Z = 0; nc.Fix = new int[] { 12 }; nc.Ref = new int[] { 8 }; nc.Data = rec;
                extra.Add(nc); newIds.Add(nc.Id);
            }
            int added = newIds.Count;
            if (added > 0)
            {
                OutChunk index = outp[ix]; byte[] od = index.Data;
                int a = (int)U(od, 4), b = (int)U(od, 8), z = a;
                while (z + 4 <= od.Length && U(od, z) != 0) z += 4;                 // the end of the first list
                if (a < 12 || z >= od.Length || (b != 0 && b <= z)) throw new InvalidDataException("The game's menu file has an index this tool does not know how to extend.");
                byte[] nd = new byte[od.Length + 4 * added];
                Buffer.BlockCopy(od, 0, nd, 0, z);
                for (int k = 0; k < added; k++) { uint v = newIds[k]; nd[z + 4 * k] = (byte)v; nd[z + 4 * k + 1] = (byte)(v >> 8); nd[z + 4 * k + 2] = (byte)(v >> 16); nd[z + 4 * k + 3] = (byte)(v >> 24); }
                Buffer.BlockCopy(od, z, nd, z + 4 * added, od.Length - z);
                if (b != 0) { uint nb = (uint)(b + 4 * added); nd[8] = (byte)nb; nd[9] = (byte)(nb >> 8); nd[10] = (byte)(nb >> 16); nd[11] = (byte)(nb >> 24); }
                List<int> refs = new List<int>();
                foreach (int r in index.Ref) refs.Add(r < z ? r : r + 4 * added);
                for (int k = 0; k < added; k++) refs.Add(z + 4 * k);
                refs.Sort();
                OutChunk ni = new OutChunk(); ni.Kind = index.Kind; ni.Id = index.Id; ni.Z = index.Z; ni.Fix = index.Fix; ni.Ref = refs.ToArray(); ni.Data = nd;
                outp[ix] = ni;
                outp.InsertRange(ix, extra);                                      // the index stays behind what it lists
            }
            byte[] head = new byte[4];
            using (FileStream f = File.OpenRead(srcFile)) f.Read(head, 0, 4);
            bool packed = head[0] == 'S' && head[1] == 'B' && head[2] == 'Z' && head[3] == '1';
            File.WriteAllBytes(dstFile, Ps3Conv.BuildSbf(outp, packed));
            return added;
        }

        static void Put(byte[] b, int o, uint v) { b[o] = (byte)v; b[o + 1] = (byte)(v >> 8); b[o + 2] = (byte)(v >> 16); b[o + 3] = (byte)(v >> 24); }
        static uint FreeId(HashSet<uint> ids, string name)
        {
            uint h = 2166136261;
            foreach (char ch in name) { h ^= ch; h *= 16777619; }
            while (h == 0 || !ids.Add(h)) h++;
            return h;
        }

        // ---- writing ----
        // Copies the resource file, giving the named textures new pictures (same size as before).
        public static void Replace(string srcFile, string dstFile, Dictionary<string, Bitmap> pictures)
        {
            Sbf s = new Sbf(srcFile, false);
            Dictionary<string, Chunk> named = Named(s);
            Dictionary<uint, byte[]> newData = new Dictionary<uint, byte[]>();
            foreach (KeyValuePair<string, Bitmap> kv in pictures)
            {
                Chunk t;
                if (!named.TryGetValue(kv.Key, out t)) throw new InvalidDataException("The game's menu file has no picture called " + kv.Key + ".");
                int dds = t.Data + 48, h = (int)U(s.D, dds + 8), w = (int)U(s.D, dds + 12);
                if (kv.Value.Width != w || kv.Value.Height != h) throw new InvalidDataException(kv.Key + " is " + w + " x " + h + ", the new picture is not.");
                byte[] pix = EncodeDxt5(kv.Value);
                if (48 + 124 + pix.Length != t.Size) throw new InvalidDataException(kv.Key + " is stored in a way this tool does not write (not a single DXT5 picture).");
                byte[] d = s.Bytes(t);
                Buffer.BlockCopy(pix, 0, d, 48 + 124, pix.Length);
                newData[t.Id] = d;
            }
            List<OutChunk> outp = new List<OutChunk>();
            foreach (Chunk c in s.Chunks)
            {
                OutChunk oc = new OutChunk(); oc.Kind = c.Kind; oc.Id = c.Id; oc.Z = c.Z; oc.Fix = c.Fix; oc.Ref = c.Ref;
                byte[] nd;
                oc.Data = (c.Kind == 4 && newData.TryGetValue(c.Id, out nd)) ? nd : s.Bytes(c);
                outp.Add(oc);
            }
            byte[] head = new byte[4];
            using (FileStream f = File.OpenRead(srcFile)) f.Read(head, 0, 4);
            bool packed = head[0] == 'S' && head[1] == 'B' && head[2] == 'Z' && head[3] == '1';
            File.WriteAllBytes(dstFile, Ps3Conv.BuildSbf(outp, packed));
        }
    }
}
