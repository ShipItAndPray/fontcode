/*
 * fontcode.h — Zero-dependency font rendering for C
 *
 * Usage:
 *   #include "fontcode.h"
 *   #include "font_basic_latin_16px.h"  // or any block/size
 *
 *   // Register font blocks
 *   fontcode_init();
 *   fontcode_add_block(fontcode_basic_latin_16px, FONTCODE_BASIC_LATIN_16PX_COUNT);
 *
 *   // Render a string to a framebuffer
 *   uint8_t fb[800 * 600];
 *   memset(fb, 0, sizeof(fb));
 *   fontcode_render_string(fb, 800, 600, 10, 30, "Hello, World!", 0xFF);
 *
 *   // Or look up individual glyphs
 *   const fontcode_glyph_16px_t *g = fontcode_find_glyph(0x0041); // 'A'
 *   if (g && g->bitmap) { ... }
 *
 * License: MIT (renderer) + Apache 2.0 (Noto Sans glyph data)
 */

#ifndef FONTCODE_H
#define FONTCODE_H

#include <stdint.h>
#include <string.h>

/* ═══════════════════════════════════════════════════════════
 * Glyph struct (same as in generated headers)
 * ═══════════════════════════════════════════════════════════ */

#ifndef FONTCODE_GLYPH_DEFINED
#define FONTCODE_GLYPH_DEFINED
typedef struct {
    uint32_t codepoint;
    uint8_t  width;
    uint8_t  height;
    int8_t   bearing_x;
    int8_t   bearing_y;
    uint8_t  advance_x;
    const uint8_t *bitmap;
} fontcode_glyph_t;
#endif

/* Alias for size-specific types */
typedef fontcode_glyph_t fontcode_glyph_16px_t;
typedef fontcode_glyph_t fontcode_glyph_24px_t;
typedef fontcode_glyph_t fontcode_glyph_32px_t;
typedef fontcode_glyph_t fontcode_glyph_48px_t;

/* ═══════════════════════════════════════════════════════════
 * Block registry — up to 64 font blocks can be registered
 * ═══════════════════════════════════════════════════════════ */

#define FONTCODE_MAX_BLOCKS 64

static const fontcode_glyph_t *fc_blocks[FONTCODE_MAX_BLOCKS];
static int fc_block_counts[FONTCODE_MAX_BLOCKS];
static int fc_num_blocks = 0;

static inline void fontcode_init(void) {
    fc_num_blocks = 0;
    memset(fc_blocks, 0, sizeof(fc_blocks));
    memset(fc_block_counts, 0, sizeof(fc_block_counts));
}

static inline void fontcode_add_block(const fontcode_glyph_t *glyphs, int count) {
    if (fc_num_blocks < FONTCODE_MAX_BLOCKS) {
        fc_blocks[fc_num_blocks] = glyphs;
        fc_block_counts[fc_num_blocks] = count;
        fc_num_blocks++;
    }
}

/* ═══════════════════════════════════════════════════════════
 * Glyph lookup — binary search within blocks
 * ═══════════════════════════════════════════════════════════ */

static inline const fontcode_glyph_t *fontcode_find_glyph(uint32_t codepoint) {
    for (int b = 0; b < fc_num_blocks; b++) {
        const fontcode_glyph_t *glyphs = fc_blocks[b];
        int count = fc_block_counts[b];
        if (!glyphs || count == 0) continue;

        /* Check if codepoint is in this block's range */
        if (codepoint < glyphs[0].codepoint || codepoint > glyphs[count - 1].codepoint)
            continue;

        /* Binary search */
        int lo = 0, hi = count - 1;
        while (lo <= hi) {
            int mid = (lo + hi) / 2;
            if (glyphs[mid].codepoint == codepoint) return &glyphs[mid];
            else if (glyphs[mid].codepoint < codepoint) lo = mid + 1;
            else hi = mid - 1;
        }
    }
    return NULL; /* Not found */
}

/* ═══════════════════════════════════════════════════════════
 * Render a single glyph to a framebuffer (8-bit grayscale)
 * ═══════════════════════════════════════════════════════════ */

static inline int fontcode_render_glyph(
    uint8_t *fb, int fb_width, int fb_height,
    int x, int y, /* baseline position */
    const fontcode_glyph_t *glyph,
    uint8_t color /* 0-255 intensity */
) {
    if (!glyph || !glyph->bitmap || glyph->width == 0 || glyph->height == 0)
        return glyph ? glyph->advance_x : 0;

    int gx = x + glyph->bearing_x;
    int gy = y - glyph->bearing_y;

    for (int row = 0; row < glyph->height; row++) {
        int py = gy + row;
        if (py < 0 || py >= fb_height) continue;

        for (int col = 0; col < glyph->width; col++) {
            int px = gx + col;
            if (px < 0 || px >= fb_width) continue;

            uint8_t alpha = glyph->bitmap[row * glyph->width + col];
            if (alpha == 0) continue;

            /* Alpha blend */
            int idx = py * fb_width + px;
            uint16_t existing = fb[idx];
            uint16_t blended = (existing * (255 - alpha) + color * alpha) / 255;
            fb[idx] = (uint8_t)(blended > 255 ? 255 : blended);
        }
    }
    return glyph->advance_x;
}

/* ═══════════════════════════════════════════════════════════
 * Render a UTF-8 string
 * ═══════════════════════════════════════════════════════════ */

/* Decode one UTF-8 character, advance pointer */
static inline uint32_t fc_utf8_decode(const char **s) {
    const uint8_t *p = (const uint8_t *)*s;
    uint32_t cp;
    int len;

    if (p[0] < 0x80)      { cp = p[0]; len = 1; }
    else if (p[0] < 0xC0) { cp = 0xFFFD; len = 1; } /* invalid */
    else if (p[0] < 0xE0) { cp = p[0] & 0x1F; len = 2; }
    else if (p[0] < 0xF0) { cp = p[0] & 0x0F; len = 3; }
    else                   { cp = p[0] & 0x07; len = 4; }

    for (int i = 1; i < len; i++) {
        if ((p[i] & 0xC0) != 0x80) { *s += 1; return 0xFFFD; }
        cp = (cp << 6) | (p[i] & 0x3F);
    }
    *s += len;
    return cp;
}

static inline int fontcode_render_string(
    uint8_t *fb, int fb_width, int fb_height,
    int x, int y, /* starting baseline position */
    const char *text,
    uint8_t color
) {
    int cursor_x = x;
    while (*text) {
        uint32_t cp = fc_utf8_decode(&text);
        if (cp == '\n') {
            cursor_x = x;
            y += 20; /* line height — adjust for your font size */
            continue;
        }
        const fontcode_glyph_t *g = fontcode_find_glyph(cp);
        if (g) {
            cursor_x += fontcode_render_glyph(fb, fb_width, fb_height, cursor_x, y, g, color);
        } else {
            cursor_x += 8; /* missing glyph: advance by space width */
        }
    }
    return cursor_x - x; /* total width rendered */
}

/* ═══════════════════════════════════════════════════════════
 * Measure string width without rendering
 * ═══════════════════════════════════════════════════════════ */

static inline int fontcode_measure_string(const char *text) {
    int width = 0;
    while (*text) {
        uint32_t cp = fc_utf8_decode(&text);
        const fontcode_glyph_t *g = fontcode_find_glyph(cp);
        width += g ? g->advance_x : 8;
    }
    return width;
}

/* ═══════════════════════════════════════════════════════════
 * Export framebuffer as PGM (for testing)
 * ═══════════════════════════════════════════════════════════ */

static inline int fontcode_save_pgm(
    const char *path,
    const uint8_t *fb, int width, int height
) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    fprintf(f, "P5\n%d %d\n255\n", width, height);
    fwrite(fb, 1, width * height, f);
    fclose(f);
    return 0;
}

#endif /* FONTCODE_H */
