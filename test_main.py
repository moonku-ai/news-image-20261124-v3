#!/usr/bin/env python3
"""Local tests for news-image-20261124 v3 (stdlib only)."""
import os, sys, hashlib, struct, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import main as M

FAIL = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + ((" — " + str(extra)) if extra else ""))
    if not cond:
        FAIL.append(name)


def test_atlas_loads():
    a = M.Atlas(os.path.join(HERE, "atlas.bin"))
    check("atlas loads 13 runs", len(a.runs) == 13, len(a.runs))
    for key in [("serifb", 54), ("serifb", 44), ("serif", 17), ("sansb", 12)]:
        check(f"run {key} has glyphs", key in a.runs and len(a.runs[key]) > 100)
    # spot-check: 'A' in serifb 54 has nonzero bitmap
    adv, xoff, yoff, w, h, bmp = a.runs[("serifb", 54)][ord("A")]
    check("glyph A bitmap nonempty", w > 10 and h > 10 and any(b > 0 for b in bmp))
    # special glyphs present and nonempty
    for ch in "—–●◐○€×→−":
        g = a.runs[("sans", 11)].get(ord(ch))
        check(f"glyph {ch!r} exists", g is not None and g[3] > 0)


def test_render():
    out = os.path.join(HERE, "entry-v3.png")
    size = M.render(M.Atlas(os.path.join(HERE, "atlas.bin")), out)
    check("png <= 1 MiB", size <= 1024 * 1024, size)
    d = open(out, "rb").read()
    check("png magic", d[:8] == b"\x89PNG\r\n\x1a\n")
    w, h = struct.unpack(">II", d[16:24])
    check("dims 1024x1024", (w, h) == (1024, 1024), (w, h))
    check("png > 20KB (content present)", size > 20000, size)


def test_determinism():
    tmp = tempfile.mkdtemp()
    o1, o2 = os.path.join(tmp, "a.png"), os.path.join(tmp, "b.png")
    M.render(M.Atlas(os.path.join(HERE, "atlas.bin")), o1)
    M.render(M.Atlas(os.path.join(HERE, "atlas.bin")), o2)
    h1 = hashlib.sha256(open(o1, "rb").read()).hexdigest()
    h2 = hashlib.sha256(open(o2, "rb").read()).hexdigest()
    check("deterministic sha256", h1 == h2, h1[:12])


def test_clean_dir():
    tmp = tempfile.mkdtemp()
    r = subprocess.run([sys.executable, os.path.join(HERE, "main.py"),
                        os.path.join(tmp, "out.png")],
                       cwd=tmp, capture_output=True, text=True)
    check("runs from clean dir", r.returncode == 0, r.stderr[-300:])
    check("clean-dir png exists",
          os.path.exists(os.path.join(tmp, "out.png")))
    leftovers = [f for f in os.listdir(tmp) if f != "out.png"]
    check("no extra files in clean dir", leftovers == [], leftovers)


def test_wrap_fit():
    a = M.Atlas(os.path.join(HERE, "atlas.bin"))
    # every layout string must fit its allotted width (no silent overflow)
    cases = [
        (("serifb", 50), "THE WORLD IN ONE DAY", 660),
        (("serifb", 44), "NATO SENDS ITS", 576),
        (("serifb", 44), "EYES TO POLAND", 576),
        (("sansb", 11), "NATO SENDS AWACS TO POLAND   •   SENEGAL CHAMPIONS AGAIN   •   SANOFI'S $41BN BET   •   14 NATIONS BACK ICJ RULING   •   NEPAL QUAKE M5.6", 976),
        (("sansb", 10), "AWACS E-3A — EYES OVER THE EASTERN FLANK (ILLUSTRATION)", 380),
    ]
    for key, s, w in cases:
        got = a.text_w(key, s)
        check(f"fit {s[:28]!r} <= {w}", got <= w, got)


if __name__ == "__main__":
    test_atlas_loads()
    test_render()
    test_determinism()
    test_clean_dir()
    test_wrap_fit()
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILURES: {FAIL}")
        sys.exit(1)
    print("ALL TESTS PASSED")
