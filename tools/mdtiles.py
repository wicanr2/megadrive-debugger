#!/usr/bin/env python3
"""Mega Drive 的 tile 與調色盤：認調色盤、把 4bpp tile 畫成圖。

Mega Drive 的色是 9-bit BGR 塞在 16-bit 裡：`0000 BBB0 GGG0 RRR0`，
也就是 `值 & 0x0EEE == 值`。隨機資料連續 16 個字全中這個遮罩的機率是
`(1/128)^16`，所以命中就是真的，不必再旁證。

**但調色盤不是找圖形的好入口** —— 有些區塊前面沒有調色盤（沿用上一次設的），
拿它當掃描起點會整批漏掉。找區塊請用 `mdlzss_scan.py` 的結構條件。
"""

from __future__ import annotations

import struct

PAL_MASK = 0x0EEE


def is_palette(d: bytes, off: int) -> bool:
    if off + 32 > len(d):
        return False
    v = struct.unpack_from(">16H", d, off)
    if any(x & ~PAL_MASK for x in v):
        return False
    return len(set(v)) >= 9 and sum(1 for x in v if x) >= 10


def palette(d: bytes, off: int):
    """9-bit BGR → RGB 0–255。每個分量只有 3 個有效位元，乘 17 展開。"""
    return [tuple(((struct.unpack_from(">H", d, off + 2 * i)[0] >> s) & 0xE) * 17
                  for s in (0, 4, 8))
            for i in range(16)]


def draw_tiles(d: bytes, off: int, n: int, pal, cols=32, scale=3):
    from PIL import Image

    rows = (n + cols - 1) // cols
    im = Image.new("RGB", (cols * 8, rows * 8), (255, 0, 255))
    for t in range(n):
        b = off + t * 32
        tx, ty = (t % cols) * 8, (t // cols) * 8
        for y in range(8):
            for x in range(0, 8, 2):
                k = b + y * 4 + x // 2
                if k >= len(d):
                    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)
                v = d[k]
                im.putpixel((tx + x, ty + y), pal[v >> 4])
                im.putpixel((tx + x + 1, ty + y), pal[v & 15])
    return im.resize((im.width * scale, im.height * scale), Image.NEAREST)


