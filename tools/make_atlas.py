#!/usr/bin/env python3
"""Fresh TTF parser + glyph rasterizer (written from scratch for v3).

Reads Liberation Serif / DejaVu Sans from /usr/share/fonts, renders the
requested (font, size) combos into a simple binary atlas "FNT2":

  magic "FNT2" | u32 n_runs
  per run: u8 font_id | u16 size_px | u32 n_glyphs
  per glyph: u32 codepoint | i16 adv | i16 xoff | i16 yoff | u16 w | u16 h
             | u32 nbytes | bytes (grayscale 0..255, row-major)

Rasterization: quadratic outlines are flattened to line segments, then a
scanline fill with 4 sub-rows per pixel row and analytic horizontal
coverage (nonzero winding rule). No third-party code, stdlib only.
"""
import struct, sys, os, json, math

FONTS = {
    "serif":  "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "serifb": "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    "serifi": "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    "sans":   "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "sansb":  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
}

CHARS = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
         " .,;:!?-'\"()[]/%$#&@*+=<>_—–''""•●◐○€×→↑↓°…·−")

RUNS = [
    ("serifb", 54), ("serifb", 50), ("serifb", 44), ("serifb", 40), ("serifb", 23),
    ("serif", 17), ("serif", 15), ("serifi", 15),
    ("sansb", 12), ("sansb", 11), ("sansb", 10),
    ("sans", 12), ("sans", 11),
]


def u16(b, o): return struct.unpack_from(">H", b, o)[0]
def i16(b, o): return struct.unpack_from(">h", b, o)[0]
def u32(b, o): return struct.unpack_from(">I", b, o)[0]
def i32(b, o): return struct.unpack_from(">i", b, o)[0]


class TTF:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        d = self.data
        n = u16(d, 4)
        self.tables = {}
        for i in range(n):
            o = 12 + i * 16
            tag = d[o:o + 4].decode("latin1")
            self.tables[tag] = (u32(d, o + 8), u32(d, o + 12))
        head_off, _ = self.tables["head"]
        self.upem = u16(d, head_off + 18)
        self.loc_fmt = i16(d, head_off + 50)
        maxp_off, _ = self.tables["maxp"]
        self.nglyphs = u16(d, maxp_off + 4)
        hhea_off, _ = self.tables["hhea"]
        self.n_hmetrics = u16(d, hhea_off + 34)
        self._cmap = self._load_cmap()

    def _load_cmap(self):
        d = self.data
        off, _ = self.tables["cmap"]
        n = u16(d, off + 2)
        best4 = best12 = None
        for i in range(n):
            plat = u16(d, off + 4 + i * 8)
            enc = u16(d, off + 6 + i * 8)
            sub = off + u32(d, off + 8 + i * 8)
            fmt = u16(d, sub)
            if fmt == 12 and best12 is None:
                best12 = sub
            elif fmt == 4 and best4 is None:
                best4 = sub
        cmap = {}
        if best12 is not None:
            ng = u32(d, best12 + 12)
            for i in range(ng):
                o = best12 + 16 + i * 12
                s, e, g = u32(d, o), u32(d, o + 4), u32(d, o + 8)
                for c in range(s, e + 1):
                    cmap[c] = g + (c - s)
            return cmap
        # format 4
        seg = u16(d, best4 + 6) // 2
        end_base = best4 + 14
        start_base = end_base + 2 * seg + 2
        delta_base = start_base + 2 * seg
        range_base = delta_base + 2 * seg
        for i in range(seg):
            end = u16(d, end_base + 2 * i)
            start = u16(d, start_base + 2 * i)
            delta = i16(d, delta_base + 2 * i)
            ro = u16(d, range_base + 2 * i)
            for c in range(start, end + 1):
                if c == 0xFFFF:
                    continue
                if ro == 0:
                    g = (c + delta) % 65536
                else:
                    addr = range_base + 2 * i + ro + 2 * (c - start)
                    g = u16(d, addr)
                    if g:
                        g = (g + delta) % 65536
                cmap[c] = g
        return cmap

    def glyph_id(self, ch):
        return self._cmap.get(ord(ch), 0)

    def _glyph_offset(self, gid):
        d = self.data
        off, _ = self.tables["loca"]
        if self.loc_fmt == 0:
            return u16(d, off + 2 * gid) * 2, u16(d, off + 2 * gid + 2) * 2
        return u32(d, off + 4 * gid), u32(d, off + 4 * gid + 4)

    def advance(self, gid):
        d = self.data
        off, _ = self.tables["hmtx"]
        g = min(gid, self.n_hmetrics - 1)
        return u16(d, off + 4 * g)

    def outline(self, gid):
        """Return list of contours; each contour is a list of (x, y, oncurve)
        in font units (y up)."""
        d = self.data
        goff, gend = self._glyph_offset(gid)
        if gend <= goff:
            return []
        glyf_off, _ = self.tables["glyf"]
        base = glyf_off + goff
        ncont = i16(d, base)
        if ncont < 0:
            return self._composite(d, base)
        if ncont == 0:
            return []
        end_pts = [u16(d, base + 10 + 2 * i) for i in range(ncont)]
        ilen = u16(d, base + 10 + 2 * ncont)
        p = base + 12 + 2 * ncont + ilen
        npts = end_pts[-1] + 1
        flags = []
        while len(flags) < npts:
            f = d[p]; p += 1
            flags.append(f)
            if f & 0x08:
                rep = d[p]; p += 1
                flags.extend([f] * rep)
        xs = []
        x = 0
        for f in flags:
            if f & 0x02:
                v = d[p]; p += 1
                x += v if (f & 0x10) else -v
            elif f & 0x10:
                pass
            else:
                x += i16(d, p); p += 2
            xs.append(x)
        ys = []
        y = 0
        for f in flags:
            if f & 0x04:
                v = d[p]; p += 1
                y += v if (f & 0x20) else -v
            elif f & 0x20:
                pass
            else:
                y += i16(d, p); p += 2
            ys.append(y)
        contours = []
        start = 0
        for e in end_pts:
            contours.append([(xs[i], ys[i], bool(flags[i] & 0x01))
                             for i in range(start, e + 1)])
            start = e + 1
        return contours

    def _composite(self, d, base):
        glyf_off, _ = self.tables["glyf"]
        p = base + 10
        contours = []
        while True:
            flags = u16(d, p); gid = u16(d, p + 2); p += 4
            if flags & 0x0001:
                a1 = i16(d, p); a2 = i16(d, p + 2); p += 4
            else:
                a1 = d[p] if d[p] < 128 else d[p] - 256
                a2 = d[p + 1] if d[p + 1] < 128 else d[p + 1] - 256
                p += 2
            if flags & 0x0002:
                dx, dy = a1, a2
            else:
                dx = dy = 0
            sx = sy = 1.0; s01 = s10 = 0.0
            if flags & 0x0008:
                sx = sy = i16(d, p) / 16384.0; p += 2
            elif flags & 0x0080:
                sx = i16(d, p) / 16384.0; sy = i16(d, p + 2) / 16384.0; p += 4
            elif flags & 0x0100:
                sx = i16(d, p) / 16384.0; s01 = i16(d, p + 2) / 16384.0
                s10 = i16(d, p + 4) / 16384.0; sy = i16(d, p + 6) / 16384.0
                p += 8
            for cont in self.outline(gid):
                contours.append([(x * sx + y * s01 + dx, x * s10 + y * sy + dy, on)
                                 for (x, y, on) in cont])
            if not (flags & 0x0020):
                break
        return contours


def flatten(contour):
    """Contour of (x, y, on) -> list of (x, y) polygon points (floats)."""
    pts = contour
    n = len(pts)
    if n == 0:
        return []
    # find a starting on-curve point
    start = 0
    for i, p in enumerate(pts):
        if p[2]:
            start = i
            break
    else:
        # all off-curve: start at midpoint of last/first
        start = 0
    order = pts[start:] + pts[:start]
    # if first point is off-curve, prepend implicit on-curve midpoint
    if not order[0][2]:
        mx = (order[-1][0] + order[0][0]) / 2.0
        my = (order[-1][1] + order[0][1]) / 2.0
        order = [(mx, my, True)] + order
    out = [(order[0][0], order[0][1])]
    i = 1
    m = len(order)
    while i < m:
        x, y, on = order[i]
        if on:
            out.append((x, y)); i += 1
        else:
            # quadratic to next on-curve, or midpoint of next off-curve
            nx, ny, non = order[(i + 1) % m]
            if non:
                ex, ey = nx, ny
                nxt = i + 2
            else:
                ex, ey = (x + nx) / 2.0, (y + ny) / 2.0
                nxt = i + 1
            cx, cy = x, y
            px, py = out[-1]
            dist = math.hypot(cx - px, cy - py) + math.hypot(ex - cx, ey - cy)
            steps = max(2, int(dist / 24.0) + 1)
            for s in range(1, steps):
                t = s / steps
                u = 1 - t
                out.append((u * u * px + 2 * u * t * cx + t * t * ex,
                            u * u * py + 2 * u * t * cy + t * t * ey))
            out.append((ex, ey))
            i = nxt if nxt <= m else m
            if i == m and not non:
                break
    return out


def rasterize(polys, w, h, ss=4):
    """polys: list of point lists in pixel coords (y down). Returns bytes w*h."""
    cov = [0.0] * (w * h)
    edges = []
    for poly in polys:
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if y0 == y1:
                continue
            edges.append((x0, y0, x1, y1))
    for row in range(h):
        for s in range(ss):
            y = row + (s + 0.5) / ss
            xs = []
            for (x0, y0, x1, y1) in edges:
                if (y0 <= y < y1) or (y1 <= y < y0):
                    t = (y - y0) / (y1 - y0)
                    xs.append((x0 + t * (x1 - x0), 1 if y1 > y0 else -1))
            if not xs:
                continue
            xs.sort()
            winding = 0
            for k in range(len(xs) - 1):
                winding += xs[k][1]
                if winding == 0:
                    continue
                xa, xb = xs[k][0], xs[k + 1][0]
                if xb <= xa:
                    continue
                c0 = max(0, int(math.floor(xa)))
                c1 = min(w - 1, int(math.floor(xb - 1e-9)) if xb > 0 else -1)
                for cx in range(c0, c1 + 1):
                    ov = min(xb, cx + 1.0) - max(xa, float(cx))
                    if ov > 0:
                        cov[row * w + cx] += ov / ss
    return bytes(min(255, int(round(c * 255))) for c in cov)


def build(out_path):
    runs = []
    total = 0
    for fname, size in RUNS:
        ttf = TTF(FONTS[fname])
        scale = size / ttf.upem
        glyphs = []
        for ch in CHARS:
            gid = ttf.glyph_id(ch)
            adv = ttf.advance(gid) * scale
            contours = ttf.outline(gid)
            if not contours:
                glyphs.append((ord(ch), adv, 0, 0, 0, 0, b""))
                continue
            polys = []
            minx = miny = 1e9; maxx = maxy = -1e9
            for cont in contours:
                poly = [(x * scale, -y * scale) for (x, y) in flatten(cont)]
                if not poly:
                    continue
                polys.append(poly)
                for (x, y) in poly:
                    minx = min(minx, x); maxx = max(maxx, x)
                    miny = min(miny, y); maxy = max(maxy, y)
            if not polys:
                glyphs.append((ord(ch), adv, 0, 0, 0, 0, b""))
                continue
            x0 = int(math.floor(minx)); x1 = int(math.ceil(maxx))
            y0 = int(math.floor(miny)); y1 = int(math.ceil(maxy))
            w = max(1, x1 - x0); h = max(1, y1 - y0)
            shifted = [[(x - x0, y - y0) for (x, y) in poly] for poly in polys]
            bmp = rasterize(shifted, w, h)
            glyphs.append((ord(ch), adv, x0, y0, w, h, bmp))
            total += 1
        runs.append((fname, size, glyphs))
        print(f"{fname} {size}px: {len(glyphs)} glyphs", flush=True)
    with open(out_path, "wb") as f:
        f.write(b"FNT2")
        f.write(struct.pack(">I", len(runs)))
        for fname, size, glyphs in runs:
            fid = list(FONTS).index(fname)
            f.write(struct.pack(">BHI", fid, size, len(glyphs)))
            for (cp, adv, xoff, yoff, w, h, bmp) in glyphs:
                f.write(struct.pack(">IhhhHHI", cp, int(round(adv)), xoff, yoff, w, h, len(bmp)))
                f.write(bmp)
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes, {total} nonempty glyphs)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "atlas.bin")
