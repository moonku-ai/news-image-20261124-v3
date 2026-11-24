#!/usr/bin/env python3
"""news-image-20261124 v3 — "THE SKY OVER POLAND".
Pure Python stdlib. Renders one 1024x1024 PNG from atlas.bin.
Deterministic: no time, no randomness, no network.
Usage: python3 main.py [out.png]
"""
import struct, sys, os, math, zlib, hashlib

W, H = 1024, 1024
PAPER = (251, 246, 236)
INK = (26, 26, 26)
NAVY = (15, 34, 64)
NAVY2 = (22, 48, 90)
RED = (193, 18, 31)
STEEL = (46, 94, 140)
GOLD = (201, 162, 39)
MUTED = (90, 90, 82)
HAIR = (201, 191, 169)
PANEL = (241, 234, 216)
GREEN = (27, 120, 62)

# ---------------------------------------------------------------- atlas
class Atlas:
    def __init__(self, path):
        d = open(path, "rb").read()
        assert d[:4] == b"FNT2", "bad atlas magic"
        p = 4
        nruns = struct.unpack_from(">I", d, p)[0]; p += 4
        self.runs = {}
        self.font_ids = ["serif", "serifb", "serifi", "sans", "sansb"]
        for _ in range(nruns):
            fid, size, n = struct.unpack_from(">BHI", d, p); p += 7
            glyphs = {}
            for _ in range(n):
                cp, adv, xoff, yoff, w, h, nb = struct.unpack_from(">IhhhHHI", d, p)
                p += 18
                bmp = d[p:p + nb]; p += nb
                glyphs[cp] = (adv, xoff, yoff, w, h, bmp)
            self.runs[(self.font_ids[fid], size)] = glyphs

    def text_w(self, key, s):
        g = self.runs[key]
        return sum(g.get(ord(c), (0, 0, 0, 0, 0, b""))[0] for c in s)

    def draw(self, cv, key, x, y_base, s, color):
        """Draw text at baseline y_base. Returns width drawn."""
        g = self.runs[key]
        px = x
        for c in s:
            gl = g.get(ord(c))
            if gl is None:
                continue
            adv, xoff, yoff, w, h, bmp = gl
            if w and h:
                cv.blit(px + xoff, y_base + yoff, w, h, bmp, color)
            px += adv
        return px - x

# ---------------------------------------------------------------- canvas
class Canvas:
    def __init__(self, w, h, bg):
        self.w, self.h = w, h
        self.px = bytearray(bg * (w * h))

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(c)

    def blit(self, x, y, w, h, bmp, color):
        for r in range(h):
            yy = y + r
            if yy < 0 or yy >= self.h:
                continue
            row = r * w
            for cx in range(w):
                a = bmp[row + cx]
                if a == 0:
                    continue
                xx = x + cx
                if xx < 0 or xx >= self.w:
                    continue
                i = (yy * self.w + xx) * 3
                if a == 255:
                    self.px[i:i + 3] = bytes(color)
                else:
                    self.px[i] = (self.px[i] * (255 - a) + color[0] * a) // 255
                    self.px[i + 1] = (self.px[i + 1] * (255 - a) + color[1] * a) // 255
                    self.px[i + 2] = (self.px[i + 2] * (255 - a) + color[2] * a) // 255

    def rect(self, x, y, w, h, c):
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(self.w, x + w); y1 = min(self.h, y + h)
        for yy in range(y0, y1):
            i = (yy * self.w + x0) * 3
            self.px[i:(yy * self.w + x1) * 3] = bytes(c) * (x1 - x0)

    def hline(self, x, y, w, c, th=1):
        self.rect(x, y, w, th, c)

    def vline(self, x, y, h, c, th=1):
        self.rect(x, y, th, h, c)

    def poly(self, pts, c):
        """Scanline fill, nonzero winding."""
        if len(pts) < 3:
            return
        edges = []
        n = len(pts)
        for i in range(n):
            x0, y0 = pts[i]; x1, y1 = pts[(i + 1) % n]
            if y0 != y1:
                edges.append((x0, y0, x1, y1))
        ymin = max(0, int(math.floor(min(p[1] for p in pts))))
        ymax = min(self.h - 1, int(math.ceil(max(p[1] for p in pts))))
        for y in range(ymin, ymax + 1):
            yc = y + 0.5
            xs = []
            for (x0, y0, x1, y1) in edges:
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    t = (yc - y0) / (y1 - y0)
                    xs.append((x0 + t * (x1 - x0), 1 if y1 > y0 else -1))
            xs.sort()
            wind = 0
            for k in range(len(xs) - 1):
                wind += xs[k][1]
                if wind == 0:
                    continue
                xa, xb = xs[k][0], xs[k + 1][0]
                x0 = max(0, int(math.ceil(xa))); x1 = min(self.w, int(math.floor(xb)))
                if x1 > x0:
                    self.rect(x0, y, x1 - x0, 1, c)

    def circle(self, cx, cy, r, c):
        for y in range(int(cy - r), int(cy + r) + 1):
            dy = y - cy
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.rect(int(cx - dx), y, 2 * dx + 1, 1, c)

    def ring(self, cx, cy, r, c, th=1):
        for y in range(int(cy - r - th), int(cy + r + th) + 1):
            dy = y - cy
            for x in range(int(cx - r - th), int(cx + r + th) + 1):
                dx = x - cx
                d = math.sqrt(dx * dx + dy * dy)
                if abs(d - r) <= th / 2.0:
                    self.set(x, y, c)

    def line(self, x0, y0, x1, y1, c, th=1):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L == 0:
            self.circle(x0, y0, th // 2 + 1, c)
            return
        nx, ny = -dy / L * th / 2.0, dx / L * th / 2.0
        self.poly([(x0 + nx, y0 + ny), (x1 + nx, y1 + ny),
                   (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)], c)

    def dashed(self, x0, y0, x1, y1, c, th=1, dash=7, gap=5):
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L == 0:
            return
        ux, uy = dx / L, dy / L
        d = 0.0
        while d < L:
            e = min(d + dash, L)
            self.line(int(x0 + ux * d), int(y0 + uy * d),
                      int(x0 + ux * e), int(y0 + uy * e), c, th)
            d = e + gap

    def png(self, path):
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride:(y + 1) * stride]
        comp = zlib.compress(bytes(raw), 9)

        def chunk(tag, data):
            out = struct.pack(">I", len(data)) + tag + data
            out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
            return out
        ihdr = struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            f.write(chunk(b"IHDR", ihdr))
            f.write(chunk(b"IDAT", comp))
            f.write(chunk(b"IEND", b""))
        return os.path.getsize(path)

# ---------------------------------------------------------------- text utils
def wrap(atlas, key, text, width):
    words = text.split(" ")
    lines, cur = [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if atlas.text_w(key, trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines

# ---------------------------------------------------------------- map data
# Simplified continent outlines (lon, lat), hand-drawn for this page.
N_AMERICA = [(-168,66),(-160,58),(-150,60),(-140,60),(-132,56),(-126,49),
             (-124,41),(-120,34),(-112,29),(-108,24),(-104,20),(-97,16),
             (-93,15),(-87,13),(-83,9),(-79,9),(-77,7),(-80,8),(-81,13),
             (-85,16),(-88,18),(-90,21),(-87,21),(-85,29),(-81,26),(-80,32),
             (-76,35),(-74,39),(-70,42),(-66,45),(-60,47),(-56,50),(-60,55),
             (-65,58),(-70,58),(-78,62),(-85,66),(-92,66),(-100,69),
             (-110,68),(-125,70),(-140,70),(-155,71),(-165,68)]
S_AMERICA = [(-77,7),(-79,4),(-80,-2),(-81,-5),(-78,-10),(-74,-16),(-71,-19),
             (-70,-23),(-71,-30),(-72,-37),(-74,-44),(-73,-50),(-69,-54),
             (-66,-55),(-65,-48),(-63,-41),(-58,-35),(-52,-33),(-48,-28),
             (-42,-23),(-39,-17),(-35,-9),(-35,-6),(-38,-4),(-43,-2),(-49,0),
             (-51,4),(-56,6),(-60,8),(-64,10),(-68,11),(-72,12),(-76,10),(-79,9)]
AFRICA = [(-6,35),(-9,32),(-13,28),(-16,23),(-17,16),(-15,12),(-12,8),
          (-8,5),(-4,5),(1,6),(6,4),(9,4),(9,0),(12,-4),(13,-9),(12,-15),
          (13,-20),(15,-26),(17,-31),(19,-35),(25,-34),(31,-29),(35,-24),
          (36,-19),(39,-15),(40,-10),(41,-5),(44,-1),(48,2),(51,5),(51,10),
          (48,11),(44,11),(41,14),(39,18),(37,21),(35,26),(33,30),(28,31),
          (22,33),(15,33),(11,34),(10,37),(6,37),(0,36),(-5,35)]
EUROPE = [(-9,37),(-9,43),(-2,44),(-1,46),(-4,48),(-1,49),(2,51),(5,53),
          (8,55),(8,57),(10,59),(6,60),(6,62),(12,64),(18,69),(25,71),
          (30,70),(32,68),(38,67),(44,66),(50,66),(56,68),(62,68),(66,69),
          (62,64),(58,58),(54,54),(50,51),(46,47),(42,44),(38,41),(36,36),
          (32,36),(28,37),(24,36),(21,39),(19,42),(15,44),(12,44),(8,44),
          (4,43),(0,40),(-2,37),(-6,36)]
ASIA = [(36,36),(40,39),(44,42),(48,45),(51,48),(54,52),(57,56),(60,61),
        (63,66),(67,69),(72,72),(78,73),(85,74),(92,75),(99,76),(105,77),
        (111,74),(117,73),(123,72),(129,71),(135,71),(141,72),(147,71),
        (153,70),(159,69),(165,67),(171,66),(177,65),(178,63),(172,60),
        (166,60),(162,60),(158,57),(156,51),(152,58),(146,59),(142,55),
        (140,50),(136,44),(132,43),(128,39),(126,40),(123,39),(121,36),
        (119,33),(115,29),(111,24),(109,20),(106,15),(104,9),(101,7),
        (99,10),(97,15),(94,17),(92,21),(89,22),(86,20),(83,18),(80,14),
        (77,8),(75,11),(73,17),(70,21),(67,24),(63,25),(60,25),(57,22),
        (54,17),(50,15),(46,13),(43,12),(41,17),(39,21),(37,25),(35,29),
        (37,32),(40,36)]
AUSTRALIA = [(113,-22),(114,-30),(115,-34),(118,-35),(124,-33),(129,-32),
             (132,-32),(135,-35),(138,-35),(140,-38),(145,-38),(150,-37),
             (153,-32),(153,-27),(150,-23),(146,-19),(142,-15),(142,-11),
             (137,-12),(135,-15),(132,-12),(130,-13),(126,-14),(122,-17),
             (118,-20),(114,-22)]
UK = [(-5,50),(-3,53),(-5,56),(-3,58),(-1,57),(0,53),(1,51),(-3,50)]
JAPAN = [(130,31),(133,34),(137,35),(140,38),(142,42),(144,44),(141,45),
         (140,40),(137,37),(133,35),(130,33)]
INDONESIA = [(95,5),(100,0),(104,-3),(108,-6),(112,-7),(116,-8),(120,-9),
             (125,-9),(130,-3),(135,-4),(140,-8),(138,-2),(132,0),(128,1),
             (124,1),(120,0),(116,0),(112,-1),(108,-2),(104,-1),(100,2),(96,4)]

PINS = [  # (number, lon, lat, display dx, display dy) — offsets unclutter Europe/Asia
    (1, 19, 52, 0, -14), (2, 35, 47.8, 17, 3), (3, 84, 28, -11, -9),
    (4, 96, 21, 12, 7), (5, -17, 14.7, 0, 0),
    (6, 6.6, 46.5, -17, 9), (7, -73.6, 4.1, 0, 0), (8, 20, 32.1, 2, 14),
    (9, -99, 19.4, 0, 0),
]

# ---------------------------------------------------------------- illustrations
def draw_radar(cv, x, y, w, h):
    cv.rect(x, y, w, h, NAVY)
    cx, cy = x + w // 2, y + h // 2 - 8
    for r, col in ((112, (58, 92, 140)), (78, (58, 92, 140)), (44, (58, 92, 140))):
        cv.ring(cx, cy, r, col, 1)
    cv.line(cx - 118, cy, cx + 118, cy, (58, 92, 140), 1)
    cv.line(cx, cy - 118, cx, cy + 118, (58, 92, 140), 1)
    # sweep wedge (gold, translucent feel via lighter navy + gold edge)
    ang0, ang1 = -2.35, -1.15
    wedge = [(cx, cy)]
    for i in range(13):
        a = ang0 + (ang1 - ang0) * i / 12.0
        wedge.append((cx + 112 * math.cos(a), cy + 112 * math.sin(a)))
    cv.poly(wedge, (38, 74, 118))
    cv.line(cx, cy, int(cx + 112 * math.cos(ang1)), int(cy + 112 * math.sin(ang1)),
            GOLD, 2)
    # blips
    for (bx, by) in ((cx - 52, cy - 66), (cx + 60, cy - 40), (cx - 78, cy + 30),
                     (cx + 30, cy + 74), (cx + 88, cy + 12)):
        cv.circle(bx, by, 4, RED)
        cv.ring(bx, by, 8, RED, 1)
    # dashed intruder path from the east
    cv.dashed(x + w - 12, y + 52, cx + 52, cy - 18, (251, 246, 236), 2)
    cv.circle(cx + 52, cy - 18, 5, (251, 246, 236))
    # AWACS silhouette (top view) at centre
    cv.poly([(cx - 8, cy - 34), (cx + 8, cy - 34), (cx + 6, cy + 30),
             (cx - 6, cy + 30)], (251, 246, 236))
    cv.poly([(cx - 52, cy - 6), (cx - 6, cy - 12), (cx - 6, cy + 2),
             (cx - 52, cy + 8)], (251, 246, 236))
    cv.poly([(cx + 52, cy - 6), (cx + 6, cy - 12), (cx + 6, cy + 2),
             (cx + 52, cy + 8)], (251, 246, 236))
    cv.poly([(cx - 26, cy + 22), (cx - 4, cy + 16), (cx - 4, cy + 26),
             (cx - 26, cy + 30)], (251, 246, 236))
    cv.poly([(cx + 26, cy + 22), (cx + 4, cy + 16), (cx + 4, cy + 26),
             (cx + 26, cy + 30)], (251, 246, 236))
    cv.circle(cx, cy - 2, 10, (251, 246, 236))
    cv.circle(cx, cy - 2, 6, NAVY)
    cv.circle(cx, cy, 3, RED)


def draw_trophy(cv, x, y, w, h):
    cv.rect(x, y, w, h, PANEL)
    cx = x + w // 2
    top = y + 14
    # cup
    cv.poly([(cx - 34, top), (cx + 34, top), (cx + 28, top + 34),
             (cx + 12, top + 44), (cx - 12, top + 44), (cx - 28, top + 34)], GOLD)
    cv.rect(cx - 40, top + 6, 8, 22, GOLD)
    cv.rect(cx + 32, top + 6, 8, 22, GOLD)
    cv.rect(cx - 4, top + 44, 8, 16, GOLD)
    cv.rect(cx - 20, top + 60, 40, 7, GOLD)
    cv.rect(cx - 26, top + 67, 52, 6, GOLD)
    # star on cup
    cv.circle(cx, top + 22, 7, (251, 246, 236))
    # confetti ticks
    for (dx, dy, ln) in ((-58, -2, 8), (52, 4, 8), (-48, 34, 6), (46, 40, 6)):
        cv.line(cx + dx, y + 30 + dy, cx + dx + ln, y + 30 + dy + 4, RED, 2)


def draw_pill(cv, x, y, w, h):
    cv.rect(x, y, w, h, PANEL)
    cx, cy = x + w // 2, y + h // 2 + 4
    # clean horizontal capsule: red left half, white right half
    cv.rect(cx - 58, cy - 15, 116, 30, RED)
    cv.rect(cx, cy - 15, 58, 30, (251, 246, 236))
    cv.circle(cx - 58, cy, 15, RED)
    cv.circle(cx + 58, cy, 15, (251, 246, 236))
    cv.line(cx, cy - 15, cx, cy + 15, (200, 200, 190), 1)
    # small tablets below
    cv.circle(cx - 66, cy + 34, 10, STEEL)
    cv.circle(cx - 42, cy + 38, 8, GOLD)
    cv.circle(cx + 64, cy + 34, 9, STEEL)


def draw_scales(cv, x, y, w, h):
    cv.rect(x, y, w, h, PANEL)
    cx = x + w // 2
    top = y + 12
    cv.rect(cx - 2, top, 4, 62, INK)
    cv.line(cx - 52, top + 8, cx + 52, top + 8, INK, 3)
    cv.circle(cx, top + 8, 5, GOLD)
    for sgn in (-1, 1):
        px = cx + sgn * 52
        cv.line(px, top + 8, px - 16, top + 40, INK, 2)
        cv.line(px, top + 8, px + 16, top + 40, INK, 2)
        cv.poly([(px - 20, top + 40), (px + 20, top + 40), (px, top + 56)], STEEL)
    cv.rect(cx - 26, top + 74, 52, 6, INK)
    cv.rect(cx - 32, top + 80, 64, 5, INK)


def draw_seismo(cv, x, y, w, h):
    cv.rect(x, y, w, h, PANEL)
    for gx in range(x + 14, x + w, 18):
        cv.vline(gx, y + 8, h - 16, (220, 212, 192), 1)
    for gy in range(y + 12, y + h, 16):
        cv.hline(x + 8, gy, w - 16, (220, 212, 192), 1)
    mid = y + h // 2
    pts = []
    import random as _r
    _r.seed(24)
    px = x + 10
    py = mid
    pts.append((px, py))
    while px < x + w - 10:
        step = _r.randint(6, 14)
        px += step
        amp = _r.choice([4, 6, 8, 30, 42, 12, 5])
        py = mid + _r.choice([-1, 1]) * amp if _r.random() < 0.55 else mid + _r.randint(-4, 4)
        pts.append((px, py))
    for i in range(len(pts) - 1):
        cv.line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], RED, 2)
    cv.circle(x + w - 14, mid, 4, INK)


# ---------------------------------------------------------------- layout
def render(atlas, out):
    cv = Canvas(W, H, PAPER)
    A = atlas.draw

    # ---- masthead (inverted navy band)
    cv.rect(0, 0, W, 108, NAVY)
    A(cv, ("serifb", 50), 24, 66, "THE WORLD IN ONE DAY", (251, 246, 236))
    A(cv, ("sansb", 12), 700, 50, "TUESDAY 24 NOVEMBER 2026", GOLD)
    A(cv, ("sans", 11), 700, 72, "$100 MAKE.FUN BOUNTY ENTRY", (180, 195, 215))
    cv.rect(0, 104, W, 4, GOLD)

    # ---- red ticker strip
    cv.rect(0, 108, W, 24, RED)
    A(cv, ("sansb", 11), 24, 125, "NATO SENDS AWACS TO POLAND   •   SENEGAL CHAMPIONS AGAIN   •   SANOFI'S $41BN BET   •   14 NATIONS BACK ICJ RULING   •   NEPAL QUAKE M5.6", (255, 255, 255))

    # ---- HERO
    A(cv, ("sansb", 12), 24, 158, "NATO  ·  EUROPE", RED)
    A(cv, ("serifb", 44), 24, 202, "NATO SENDS ITS", INK)
    A(cv, ("serifb", 44), 24, 250, "EYES TO POLAND", INK)
    deck = ("After a Russian drone slipped into Polish airspace, and three "
            "cruise missiles landed days earlier, NATO is sending an AWACS "
            "jet to watch the eastern sky.")
    yy = 282
    for ln in wrap(atlas, ("serif", 17), deck, 576):
        A(cv, ("serif", 17), 24, yy, ln, INK)
        yy += 23
    # three fact boxes
    facts = [("3", "Kh-101 missiles found in Poland on 20 Nov"),
             ("9 min", "Russian drone inside Polish airspace, Mon night"),
             ("14", "AWACS jets in NATO's airborne fleet")]
    fx = 24
    for num, lab in facts:
        cv.rect(fx, 360, 184, 64, PANEL)
        A(cv, ("serifb", 23), fx + 10, 386, num, RED)
        ly = 404
        for ln in wrap(atlas, ("sans", 11), lab, 164):
            A(cv, ("sans", 11), fx + 10, ly, ln, INK)
            ly += 14
        fx += 196
    # radar panel
    draw_radar(cv, 620, 140, 380, 284)
    A(cv, ("sansb", 10), 632, 412, "AWACS E-3A: EYES OVER THE EASTERN FLANK (ILLUSTRATION)", GOLD)

    cv.hline(24, 434, 976, INK, 2)

    # ---- four illustrated leads
    leads = [
        ("SPORT", "SENEGAL CHAMPIONS AGAIN",
         "CAS restores the 1-0 AFCON final win over Morocco. Unanimous; the trophy returns to Dakar.",
         draw_trophy),
        ("BUSINESS", "SANOFI'S $41BN BET",
         "Sanofi will buy US biotech Insmed for $175 a share, the biggest pharma deal of 2026.",
         draw_pill),
        ("JUSTICE", "14 NATIONS BACK ICJ RULING",
         "The UK, Spain, Canada, Australia and ten more affirm the genocide finding on Myanmar.",
         draw_scales),
        ("EARTH", "NEPAL SHAKEN: M5.6",
         "A 5.6-magnitude quake strikes Koshi province near the China border; no major damage yet.",
         draw_seismo),
    ]
    lx = 24
    for kicker, head, body, ill in leads:
        ill(cv, lx, 446, 232, 94)
        A(cv, ("sansb", 11), lx, 556, kicker, RED)
        hy = 580
        for ln in wrap(atlas, ("serifb", 23), head, 232):
            A(cv, ("serifb", 23), lx, hy, ln, INK)
            hy += 26
        by = 634
        for ln in wrap(atlas, ("serif", 15), body, 232):
            A(cv, ("serif", 15), lx, by, ln, INK)
            by += 18
        if lx < 756:
            cv.vline(lx + 244, 446, 236, HAIR, 1)
        lx += 248

    cv.hline(24, 694, 976, INK, 2)

    # ---- markets strip (data only, not the hero)
    A(cv, ("sansb", 11), 24, 712, "MARKETS — TUESDAY CLOSE", RED)
    markets = [("NASDAQ", "+6.51%"), ("S&P 500", "+4.73%"), ("NIKKEI", "+3.91%"),
               ("SEOUL", "+6.00%"), ("BRENT", "$86.70  −2.99%"),
               ("GOLD", "$3,620.40  −0.85%")]
    mx = 24
    for name, val in markets:
        wname = A(cv, ("sans", 12), mx, 738, name + "  ", MUTED)
        col = GREEN if val.startswith("+") else RED
        A(cv, ("sansb", 12), mx + wname, 738, val, col)
        mx += 164

    # ---- section headers
    cv.hline(24, 750, 976, INK, 1)
    A(cv, ("sansb", 12), 24, 768, "THE DAY IN BRIEF", INK)
    A(cv, ("sansb", 12), 520, 768, "THE WORLD ON THE MAP", INK)

    # ---- briefs (left)
    briefs = [
        ("Zaporizhzhia: ", "Russian overnight strikes kill 2 and wound 40, including four children."),
        ("Colombia: ", "Car bomb hits the governor's office in Villavicencio."),
        ("Malaysia: ", "Thousands of migrants to be returned to Myanmar; 1,500 by ship in December."),
        ("Bangladesh: ", "Ex-PM Hasina plans to return from exile on 16 December."),
        ("Hormuz: ", "Three tankers catch fire after hitting mines; Iran warns on a US blockade."),
        ("Space: ", "BepiColombo enters orbit around Mercury; COP31 ends with no final deal."),
    ]
    by = 784
    for lead, rest in briefs:
        txt = lead + rest
        lines = wrap(atlas, ("sans", 12), txt, 472)
        ly = by
        for ln in lines[:2]:
            # bold the lead-in on the first line
            if ln == lines[0]:
                wlead = A(cv, ("sansb", 12), 24, ly, lead, INK)
                A(cv, ("sans", 12), 24 + wlead, ly, ln[len(lead):], INK)
            else:
                A(cv, ("sans", 12), 24, ly, ln, INK)
            ly += 15
        by += 30

    # ---- map (right)
    mapx, mapy, mapw, maph = 520, 786, 480, 128
    cv.rect(mapx, mapy, mapw, maph, (232, 240, 246))
    def proj(lon, lat):
        return (mapx + (lon + 180.0) / 360.0 * mapw,
                mapy + (78.0 - lat) / 136.0 * maph)
    for cont in (N_AMERICA, S_AMERICA, AFRICA, EUROPE, ASIA, AUSTRALIA,
                 UK, JAPAN, INDONESIA):
        cv.poly([proj(lon, lat) for (lon, lat) in cont], STEEL)
    for num, lon, lat, dx, dy in PINS:
        px, py = proj(lon, lat)
        cx, cy = int(px) + dx, int(py) + dy
        if dx or dy:
            cv.line(int(px), int(py), cx, cy, RED, 1)
            cv.circle(int(px), int(py), 2, RED)
        cv.circle(cx, cy, 8, RED)
        cv.ring(cx, cy, 8, (255, 255, 255), 1)
        A(cv, ("sansb", 10), cx - 3, cy + 4, str(num), (255, 255, 255))
    A(cv, ("sans", 11), 520, 930,
      "1 Poland  ·  2 Ukraine  ·  3 Nepal  ·  4 Myanmar  ·  5 Senegal", INK)
    A(cv, ("sans", 11), 520, 946,
      "6 Switzerland  ·  7 Colombia  ·  8 Libya  ·  9 Mexico", INK)

    # ---- footer
    cv.hline(24, 960, 976, INK, 2)
    A(cv, ("sans", 11), 24, 978,
      "● Confirmed today    ◐ Reported Monday    ○ Scheduled today", INK)
    A(cv, ("sans", 11), 24, 996,
      "Sources: Reuters, AP, NATO, CAS, Sanofi, ICJ, EMSC. Illustrations are drawn from the facts.",
      MUTED)
    A(cv, ("sans", 11), 24, 1014,
      "THE WORLD IN ONE DAY, Tuesday 24 November 2026. All stories verified against reporting dated 24 Nov 2026.",
      MUTED)

    size = cv.png(out)
    return size


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "entry-v3.png"
    atlas = Atlas(os.path.join(os.path.dirname(os.path.abspath(__file__)), "atlas.bin"))
    size = render(atlas, out)
    h = hashlib.sha256(open(out, "rb").read()).hexdigest()
    print(f"{out}: {size} bytes, sha256 {h}")


if __name__ == "__main__":
    main()
