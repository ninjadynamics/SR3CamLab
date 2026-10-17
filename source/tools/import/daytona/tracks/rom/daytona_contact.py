"""Contact sheet of a course's exported texture tiles (most used first).
    python daytona_contact.py beginner [max tiles]      -> <COURSES>/<course>/textures_contact.png"""
import os, sys, json
from collections import Counter
from PIL import Image, ImageDraw
from daytona_paths import COURSES


def contact(course, maxn=400, cell=132):
    folder = os.path.join(COURSES, course)
    use = Counter()
    for line in open(os.path.join(folder, "daytona_%s.obj" % course)):
        if line.startswith("usemtl "): cur = line.split()[1]
        elif line.startswith("f "): use[cur] += 1
    names = [n for n, _ in use.most_common() if n.startswith("tex_")][:maxn]
    cols = 12
    rows = (len(names) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 12)), (40, 40, 60))
    dr = ImageDraw.Draw(sheet)
    for i, n in enumerate(names):
        im = Image.open(os.path.join(folder, "textures", n + ".png")).convert("RGBA")
        bg = Image.new("RGBA", im.size, (200, 60, 200, 255))            # magenta shows through the cut-out parts
        im = Image.alpha_composite(bg, im).convert("RGB")
        k = min((cell - 4) / im.width, (cell - 4) / im.height)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.NEAREST if k > 1 else Image.BILINEAR)
        x = (i % cols) * cell + 2; y = (i // cols) * (cell + 12) + 2
        sheet.paste(im, (x, y))
        p = n.split("_")
        dr.text((x, y + cell - 4), "%s %s %s n%d" % (p[1], p[2][1:], p[3][1:], use[n]), fill=(255, 255, 255))
    out = os.path.join(folder, "textures_contact.png")
    sheet.save(out)
    print(out, sheet.size, "%d of %d textured materials" % (len(names), sum(1 for n in use if n.startswith("tex_"))))


if __name__ == "__main__":
    contact(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 400)
