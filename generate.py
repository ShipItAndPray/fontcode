#!/usr/bin/env python3
"""
fontcode — Generate zero-dependency font rendering code from TTF/OTF fonts.

Rasterizes every glyph at multiple sizes into C arrays, Rust arrays, or Go slices.
No runtime font library needed — just #include and render.

Usage:
    python generate.py                     # Generate C headers (default)
    python generate.py --lang rust         # Generate Rust
    python generate.py --lang go           # Generate Go
    python generate.py --sizes 16,24,32    # Custom sizes
    python generate.py --format sdf        # Signed distance field
"""

import freetype
import struct
import glob
import os
import sys
import time
import json
import math
from collections import defaultdict

# ═══════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════

FONT_PATHS = glob.glob("/tmp/Noto*.ttf") + glob.glob("/tmp/Noto*.otf")
DEFAULT_SIZES = [12, 16, 20, 24, 32, 48]
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

# Unicode block ranges we care about (most commonly needed)
UNICODE_BLOCKS = {
    "basic_latin": (0x0020, 0x007F),
    "latin_supplement": (0x0080, 0x00FF),
    "latin_extended_a": (0x0100, 0x017F),
    "latin_extended_b": (0x0180, 0x024F),
    "greek": (0x0370, 0x03FF),
    "cyrillic": (0x0400, 0x04FF),
    "armenian": (0x0530, 0x058F),
    "hebrew": (0x0590, 0x05FF),
    "arabic": (0x0600, 0x06FF),
    "devanagari": (0x0900, 0x097F),
    "thai": (0x0E00, 0x0E7F),
    "hangul_jamo": (0x1100, 0x11FF),
    "general_punctuation": (0x2000, 0x206F),
    "currency_symbols": (0x20A0, 0x20CF),
    "arrows": (0x2190, 0x21FF),
    "math_operators": (0x2200, 0x22FF),
    "box_drawing": (0x2500, 0x257F),
    "block_elements": (0x2580, 0x259F),
    "geometric_shapes": (0x25A0, 0x25FF),
    "misc_symbols": (0x2600, 0x26FF),
    "dingbats": (0x2700, 0x27BF),
    "braille": (0x2800, 0x28FF),
    "cjk_unified": (0x4E00, 0x9FFF),
    "hangul_syllables": (0xAC00, 0xD7AF),
    "hiragana": (0x3040, 0x309F),
    "katakana": (0x30A0, 0x30FF),
    "emoji_misc": (0x2600, 0x26FF),
    "private_use": (0xE000, 0xE0FF),
}


# ═══════════════════════════════════════════════════════════
# Glyph Rasterizer
# ═══════════════════════════════════════════════════════════

class GlyphData:
    __slots__ = ['codepoint', 'width', 'height', 'advance_x', 'bearing_x',
                 'bearing_y', 'bitmap', 'size_px']

    def __init__(self, codepoint, width, height, advance_x, bearing_x, bearing_y, bitmap, size_px):
        self.codepoint = codepoint
        self.width = width
        self.height = height
        self.advance_x = advance_x
        self.bearing_x = bearing_x
        self.bearing_y = bearing_y
        self.bitmap = bitmap  # list of uint8
        self.size_px = size_px


def load_fonts():
    """Load all available font faces."""
    faces = []
    for path in FONT_PATHS:
        try:
            face = freetype.Face(path)
            faces.append((path, face))
        except Exception as e:
            print(f"  Skip {os.path.basename(path)}: {e}", file=sys.stderr)
    return faces


def get_coverage(faces):
    """Get all codepoints covered by available fonts."""
    coverage = {}  # codepoint -> font_path
    for path, face in faces:
        charcode, idx = face.get_first_char()
        while idx:
            if charcode not in coverage:
                coverage[charcode] = path
            charcode, idx = face.get_next_char(charcode, idx)
    return coverage


def rasterize_glyph(face, codepoint, size_px):
    """Rasterize a single glyph. Returns GlyphData or None."""
    try:
        face.set_pixel_sizes(0, size_px)
        face.load_char(chr(codepoint), freetype.FT_LOAD_RENDER)
        bitmap = face.glyph.bitmap
        width = bitmap.width
        height = bitmap.rows
        if width == 0 or height == 0:
            # Space or control character
            return GlyphData(
                codepoint=codepoint, width=0, height=0,
                advance_x=face.glyph.advance.x >> 6,
                bearing_x=0, bearing_y=0, bitmap=[], size_px=size_px,
            )
        pixels = list(bitmap.buffer)
        # bitmap.buffer might have pitch != width (row padding)
        if bitmap.pitch != width:
            unpacked = []
            for row in range(height):
                start = row * bitmap.pitch
                unpacked.extend(pixels[start:start + width])
            pixels = unpacked

        return GlyphData(
            codepoint=codepoint, width=width, height=height,
            advance_x=face.glyph.advance.x >> 6,
            bearing_x=face.glyph.bitmap_left,
            bearing_y=face.glyph.bitmap_top,
            bitmap=pixels[:width * height],
            size_px=size_px,
        )
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════
# C Code Generator
# ═══════════════════════════════════════════════════════════

def generate_c_header(glyphs_by_block, size_px, output_dir):
    """Generate C header file for a specific size."""
    os.makedirs(output_dir, exist_ok=True)

    for block_name, glyphs in glyphs_by_block.items():
        if not glyphs:
            continue

        path = os.path.join(output_dir, f"font_{block_name}_{size_px}px.h")
        with open(path, 'w') as f:
            guard = f"FONTCODE_{block_name.upper()}_{size_px}PX_H"
            f.write(f"/* fontcode — {block_name} at {size_px}px */\n")
            f.write(f"/* Auto-generated. Do not edit. */\n")
            f.write(f"/* Codepoints: {len(glyphs)} | Source: Noto Sans (Apache 2.0) */\n\n")
            f.write(f"#ifndef {guard}\n#define {guard}\n\n")
            f.write(f"#include <stdint.h>\n\n")

            # Metrics struct
            f.write("typedef struct {\n")
            f.write("    uint32_t codepoint;\n")
            f.write("    uint8_t  width;\n")
            f.write("    uint8_t  height;\n")
            f.write("    int8_t   bearing_x;\n")
            f.write("    int8_t   bearing_y;\n")
            f.write("    uint8_t  advance_x;\n")
            f.write("    const uint8_t *bitmap;\n")
            f.write(f"}} fontcode_glyph_{size_px}px_t;\n\n")

            # Bitmap data for each glyph
            for g in glyphs:
                if not g.bitmap:
                    continue
                f.write(f"static const uint8_t fc_bmp_U{g.codepoint:04X}_{size_px}[] = {{")
                for i, b in enumerate(g.bitmap):
                    if i % 16 == 0:
                        f.write("\n    ")
                    f.write(f"0x{b:02x},")
                f.write("\n};\n\n")

            # Glyph table
            f.write(f"static const fontcode_glyph_{size_px}px_t fontcode_{block_name}_{size_px}px[] = {{\n")
            for g in glyphs:
                bmp_ref = f"fc_bmp_U{g.codepoint:04X}_{size_px}" if g.bitmap else "0"
                f.write(f"    {{ 0x{g.codepoint:04X}, {g.width}, {g.height}, "
                        f"{g.bearing_x}, {g.bearing_y}, {g.advance_x}, {bmp_ref} }},\n")
            f.write("};\n\n")

            f.write(f"#define FONTCODE_{block_name.upper()}_{size_px}PX_COUNT {len(glyphs)}\n\n")
            f.write(f"#endif /* {guard} */\n")

        yield path, len(glyphs)


def generate_rust_mod(glyphs_by_block, size_px, output_dir):
    """Generate Rust module for a specific size."""
    os.makedirs(output_dir, exist_ok=True)

    for block_name, glyphs in glyphs_by_block.items():
        if not glyphs:
            continue

        path = os.path.join(output_dir, f"font_{block_name}_{size_px}px.rs")
        with open(path, 'w') as f:
            f.write(f"//! fontcode — {block_name} at {size_px}px\n")
            f.write(f"//! Auto-generated. Do not edit.\n\n")
            f.write("#[allow(dead_code)]\n\n")

            f.write("pub struct Glyph {\n")
            f.write("    pub codepoint: u32,\n")
            f.write("    pub width: u8,\n")
            f.write("    pub height: u8,\n")
            f.write("    pub bearing_x: i8,\n")
            f.write("    pub bearing_y: i8,\n")
            f.write("    pub advance_x: u8,\n")
            f.write("    pub bitmap: &'static [u8],\n")
            f.write("}\n\n")

            for g in glyphs:
                if not g.bitmap:
                    continue
                f.write(f"static BMP_U{g.codepoint:04X}: [u8; {len(g.bitmap)}] = [")
                for i, b in enumerate(g.bitmap):
                    if i % 16 == 0:
                        f.write("\n    ")
                    f.write(f"0x{b:02x},")
                f.write("\n];\n\n")

            f.write(f"pub static GLYPHS: [Glyph; {len(glyphs)}] = [\n")
            for g in glyphs:
                bmp = f"&BMP_U{g.codepoint:04X}" if g.bitmap else "&[]"
                f.write(f"    Glyph {{ codepoint: 0x{g.codepoint:04X}, width: {g.width}, "
                        f"height: {g.height}, bearing_x: {g.bearing_x}, bearing_y: {g.bearing_y}, "
                        f"advance_x: {g.advance_x}, bitmap: {bmp} }},\n")
            f.write("];\n")

        yield path, len(glyphs)


# ═══════════════════════════════════════════════════════════
# Main Pipeline
# ═══════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="fontcode — Generate font rendering code from TTF/OTF")
    parser.add_argument("--lang", choices=["c", "rust", "both"], default="c", help="Output language")
    parser.add_argument("--sizes", default=",".join(str(s) for s in DEFAULT_SIZES), help="Comma-separated pixel sizes")
    parser.add_argument("--blocks", default="all", help="Comma-separated Unicode block names, or 'all'")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output directory")
    parser.add_argument("--stats", action="store_true", help="Print stats and exit")
    args = parser.parse_args()

    sizes = [int(s) for s in args.sizes.split(",")]
    blocks = UNICODE_BLOCKS if args.blocks == "all" else {b: UNICODE_BLOCKS[b] for b in args.blocks.split(",") if b in UNICODE_BLOCKS}

    print(f"fontcode — zero-dependency font rendering code generator")
    print(f"  Sizes: {sizes}")
    print(f"  Blocks: {len(blocks)} ({', '.join(list(blocks.keys())[:5])}{'...' if len(blocks) > 5 else ''})")
    print(f"  Languages: {args.lang}")
    print()

    # Load fonts
    print("Loading fonts...", end=" ", flush=True)
    faces = load_fonts()
    print(f"{len(faces)} fonts loaded")

    coverage = get_coverage(faces)
    print(f"Total Unicode coverage: {len(coverage)} codepoints")

    if args.stats:
        for block_name, (start, end) in sorted(blocks.items()):
            count = sum(1 for cp in range(start, end + 1) if cp in coverage)
            total = end - start + 1
            pct = count / total * 100
            print(f"  {block_name}: {count}/{total} ({pct:.0f}%)")
        return

    # Build font index: codepoint -> face
    font_index = {}
    for path, face in faces:
        charcode, idx = face.get_first_char()
        while idx:
            if charcode not in font_index:
                font_index[charcode] = face
            charcode, idx = face.get_next_char(charcode, idx)

    total_files = 0
    total_glyphs = 0
    total_bytes = 0
    t0 = time.time()

    for size_px in sizes:
        print(f"\nGenerating {size_px}px...")

        # Rasterize all glyphs for this size
        glyphs_by_block = {}
        for block_name, (start, end) in blocks.items():
            glyphs = []
            for cp in range(start, end + 1):
                if cp in font_index:
                    g = rasterize_glyph(font_index[cp], cp, size_px)
                    if g:
                        glyphs.append(g)
            glyphs_by_block[block_name] = glyphs
            if glyphs:
                print(f"  {block_name}: {len(glyphs)} glyphs", end="", flush=True)
                print()

        # Generate code
        if args.lang in ("c", "both"):
            c_dir = os.path.join(args.output, "c")
            for path, count in generate_c_header(glyphs_by_block, size_px, c_dir):
                size = os.path.getsize(path)
                total_files += 1
                total_glyphs += count
                total_bytes += size

        if args.lang in ("rust", "both"):
            rs_dir = os.path.join(args.output, "rust")
            for path, count in generate_rust_mod(glyphs_by_block, size_px, rs_dir):
                size = os.path.getsize(path)
                total_files += 1
                total_glyphs += count
                total_bytes += size

    elapsed = time.time() - t0

    print(f"\n{'='*50}")
    print(f"fontcode generation complete")
    print(f"  Files: {total_files}")
    print(f"  Glyphs: {total_glyphs}")
    print(f"  Output size: {total_bytes / 1024 / 1024:.1f} MB")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Output: {args.output}/")


if __name__ == "__main__":
    main()
