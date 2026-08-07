#!/usr/bin/env python3
"""Subset + instance the Ubuntu superfamily into woff2 data URIs for the Toki sheet.

The Artifact CSP blocks font CDNs, so faces must be inlined. Three roles:
  console  Ubuntu Sans @ wdth 75  -- HUD chrome, headings, uppercase labels
  body     Ubuntu Sans @ wdth 100 -- prose in the Codex
  data     Ubuntu Sans Mono       -- numerals, dice, resource readouts

Writes fonts.css with @font-face blocks. Run from the repo root.
"""
import base64
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

SRC = Path("/usr/share/fonts/truetype/ubuntu")
OUT = Path("projects/toki_sheet/fonts.css")

# Latin-1-ish plus the typographic marks the export actually contains.
GLYPHS = (
    "".join(chr(c) for c in range(0x20, 0x7F))
    + " ©«»°±·×÷"
    + "‐‑–—‘’“”†‡•…′″"
    + "←↑→↓↻−≠≤≥▲▼◆●✓✗"
    + "ÀÁÂÃÄÅÇÈÉÊËÌÍÎÏÑÒÓÔÕÖÙÚÛÜÝàáâãäåçèéêëìíîïñòóôõöùúûüýÿŒœŠšŸŽž"
)

FACES = [
    ("console", "UbuntuSans[wdth,wght].ttf", {"wdth": 75, "wght": (300, 800)}),
    ("body",    "UbuntuSans[wdth,wght].ttf", {"wdth": 100, "wght": (300, 700)}),
    ("data",    "UbuntuSansMono[wght].ttf",  {"wght": (400, 700)}),
]


def build(family, filename, axes):
    font = TTFont(SRC / filename)
    instantiateVariableFont(font, axes, inplace=True, updateFontNames=False)

    # Ubuntu's variable fonts omit non-varying glyphs (.notdef, space, …) from gvar;
    # the subsetter assumes every retained glyph has an entry and dies on a KeyError.
    # Backfill empty deltas so the glyph set and gvar agree.
    if "gvar" in font:
        variations = font["gvar"].variations
        for name in font.getGlyphOrder():
            variations.setdefault(name, [])

    opts = subset.Options()
    opts.flavor = "woff2"
    opts.desubroutinize = False
    opts.layout_features = ["kern", "liga", "calt", "tnum", "ccmp", "locl", "mark", "mkmk"]
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    opts.recalc_bounds = True
    opts.drop_tables += ["DSIG"]

    subsetter = subset.Subsetter(options=opts)
    subsetter.populate(text=GLYPHS)
    subsetter.subset(font)

    tmp = Path(f"/tmp/{family}.woff2")
    font.save(tmp)
    data = tmp.read_bytes()
    tmp.unlink()

    lo, hi = axes["wght"]
    b64 = base64.b64encode(data).decode()
    print(f"  {family:<8} {len(data)/1024:6.1f} KB -> {len(b64)/1024:6.1f} KB base64")
    return (
        f"@font-face{{font-family:'Toki {family.title()}';"
        f"font-weight:{lo} {hi};font-style:normal;font-display:block;"
        f"src:url(data:font/woff2;base64,{b64}) format('woff2-variations');}}"
    )


def main():
    print("subsetting:")
    css = "\n".join(build(*f) for f in FACES)
    OUT.write_text(css + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
