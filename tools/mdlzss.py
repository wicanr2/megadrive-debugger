#!/usr/bin/env python3
"""Mega Drive 常見的 LZSS 解壓（4096 環形緩衝、初值 0x20）。

逐行重寫自一款 1991 年 Mega Drive RPG 的 ROM `0x29954` 解壓常式。
同一族的解碼器在多款 Mega Drive 遊戲上通用，但**每一款都要自己驗**：
LZSS 這種解碼器餵什麼都吐得出東西，所以「輸出看起來合理」不能當證據，
要有宣告長度之類的獨立條件（見 `mdlzss_scan.py` 的驗收方式）。

三個框架級的前提，猜錯會讓參數搜尋全滅而且症狀像「還沒試對」：

  - **偏移是環形緩衝的絕對位置，不是「往回幾個位元組」。** 兩者在資料中段
    等價，開頭不等價 —— 緩衝預先填了 0x20，所以串流一開始就能引用
    「還沒輸出過」的內容。用回退距離實作會在第一個 match 就越界。
  - **輸出長度在 src+4、位元流在 src+8。**
  - 被當成 magic 的 `F0FF` 其實是位元流本身。
"""

from __future__ import annotations


def lzss(d: bytes, src: int, out_len: int):
    """ROM 0x29954 的逐行重寫。回傳 (輸出, 吃掉的位元組數)。"""
    ring = bytearray(b"\x20" * 4096)
    r = 0xFEE
    out = bytearray()
    p = src
    flags = 0
    while len(out) < out_len:
        flags >>= 1
        if not flags & 0x100:
            # 原版用 `ori.w #$FF00,d6` 把高位元組填滿當計數器：
            # 低 8 位用完之後 0x100 那一位就會是 0，不必另外數。
            flags = d[p] | 0xFF00
            p += 1
        if flags & 1:
            b = d[p]
            p += 1
            out.append(b)
            ring[r] = b
            r = (r + 1) & 0xFFF
        else:
            lo, hi = d[p], d[p + 1]
            p += 2
            off = lo | ((hi & 0xF0) << 4)
            for k in range((hi & 0x0F) + 3):
                b = ring[(off + k) & 0xFFF]
                out.append(b)
                ring[r] = b
                r = (r + 1) & 0xFFF
                if len(out) >= out_len:
                    break
    return bytes(out), p - src
