# fontcode

Zero-dependency font rendering. Every Unicode glyph as a C array. No FreeType. No .ttf files. Just `#include` and render.

```c
#include "fontcode.h"
#include "font_basic_latin_24px.h"

int main() {
    uint8_t framebuffer[800 * 200];
    memset(framebuffer, 0, sizeof(framebuffer));

    fontcode_init();
    fontcode_add_block(fontcode_basic_latin_24px, FONTCODE_BASIC_LATIN_24PX_COUNT);
    fontcode_render_string(framebuffer, 800, 200, 10, 40, "Hello, World!", 0xFF);
    fontcode_save_pgm("hello.pgm", framebuffer, 800, 200);
}
```

That's it. No library to link. No font file to ship. Compiles anywhere C compiles.

## Why

- **Embedded systems** — Microcontrollers with 32KB RAM can render text. No filesystem needed.
- **WASM** — Ship a 50KB font module instead of a 500KB .ttf + FreeType WASM build.
- **Game engines** — Compile-time font baking. Zero runtime overhead for text rendering.
- **Bare metal** — OS kernel, bootloader, UEFI app? Just `#include`.
- **CI/CD** — Generate images with text in a Docker container. No font packages to install.

## Numbers

| Metric | Value |
|--------|-------|
| Unicode codepoints | **47,122** |
| Glyphs rendered | **272,608** (across all sizes) |
| Sizes | 16px, 24px, 32px, 48px |
| Scripts | Latin, Greek, Cyrillic, CJK (21K), Hangul (11K), Hiragana, Katakana, math, symbols |
| Output languages | **C** headers + **Rust** modules |
| Total generated code | **1.24 GB** |
| Source font | Noto Sans (Apache 2.0) |
| Dependencies | **Zero** |

## What's included

```
fontcode/
├── generate.py              # Generator — run to regenerate from any TTF/OTF
├── output/
│   ├── c/
│   │   ├── fontcode.h       # Renderer: lookup, render, measure, UTF-8 decode
│   │   ├── font_basic_latin_16px.h
│   │   ├── font_basic_latin_24px.h
│   │   ├── font_cjk_unified_32px.h    # 21K Chinese/Japanese glyphs, 103MB
│   │   ├── font_hangul_syllables_48px.h # 11K Korean glyphs, 99MB
│   │   └── ... (84 files, 648MB)
│   └── rust/
│       ├── font_basic_latin_16px.rs
│       └── ... (84 files, 652MB)
└── samples/                 # Git-friendly samples (small blocks only)
```

## API (C)

```c
// Initialize
fontcode_init();

// Register font blocks (include as many as you need)
fontcode_add_block(fontcode_basic_latin_24px, FONTCODE_BASIC_LATIN_24PX_COUNT);
fontcode_add_block(fontcode_cyrillic_24px, FONTCODE_CYRILLIC_24PX_COUNT);
fontcode_add_block(fontcode_cjk_unified_24px, FONTCODE_CJK_UNIFIED_24PX_COUNT);

// Look up a glyph
const fontcode_glyph_t *g = fontcode_find_glyph(0x4E16); // 世
// g->width, g->height, g->bitmap, g->advance_x, g->bearing_x, g->bearing_y

// Render to 8-bit grayscale framebuffer
uint8_t fb[WIDTH * HEIGHT];
fontcode_render_glyph(fb, WIDTH, HEIGHT, x, y, g, 0xFF);

// Render UTF-8 string (handles multi-byte, newlines)
fontcode_render_string(fb, WIDTH, HEIGHT, 10, 30, "Hello 世界 مرحبا", 0xFF);

// Measure without rendering
int width = fontcode_measure_string("Hello");

// Save as PGM image (for testing)
fontcode_save_pgm("output.pgm", fb, WIDTH, HEIGHT);
```

## Features

- **Binary search lookup** — O(log n) glyph lookup across registered blocks
- **Alpha blending** — Anti-aliased glyph rendering with configurable intensity
- **UTF-8 decoding** — Full 4-byte UTF-8 support built in
- **String rendering** — Line breaks, cursor advance, missing glyph fallback
- **Measurement** — Calculate string width before rendering
- **PGM export** — Write framebuffer to image for debugging
- **Block system** — Only include the Unicode blocks you need. Latin-only app? 53KB. Full CJK? 220MB. Your choice.

## Generate from any font

```bash
# Install deps
pip install freetype-py

# Download Noto Sans (or use any TTF/OTF)
# Place .ttf files in /tmp/

# Generate
python generate.py --lang c --sizes 16,24,32     # C only
python generate.py --lang rust --sizes 24         # Rust only
python generate.py --lang both --sizes 16,24,32,48  # Everything
python generate.py --stats                         # Show coverage
```

## Unicode coverage

| Block | Codepoints | Coverage |
|-------|-----------|----------|
| Basic Latin (ASCII) | 95 | 99% |
| Latin Extended A+B | 336 | 100% |
| Greek | 121 | 84% |
| Cyrillic | 256 | 100% |
| CJK Unified | 20,976 | 100% |
| Hangul Syllables | 11,172 | 100% |
| Hiragana | 93 | 97% |
| Katakana | 96 | 100% |
| Box Drawing | 128 | 100% |
| Math Operators | 74 | 29% |
| Currency Symbols | 32 | 67% |
| Arrows | 25 | 22% |

## Size guide

Pick only what you need:

| Use case | Blocks | Size at 24px |
|----------|--------|-------------|
| English only | basic_latin | **40KB** |
| Western European | + latin_supplement, latin_extended_a | **120KB** |
| Pan-European | + greek, cyrillic | **350KB** |
| Japanese | + hiragana, katakana, cjk_unified | **62MB** |
| Korean | + hangul_syllables | **27MB** |
| Full coverage | all 21 blocks | **648MB** |

## License

- Generator + renderer: MIT
- Glyph data: Apache 2.0 (Noto Sans by Google)
