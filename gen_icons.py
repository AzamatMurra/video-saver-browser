#!/usr/bin/env python3
"""Генерирует PNG-иконки расширения (синий скруглённый квадрат + белая стрелка вниз)."""
import os, struct, zlib

BG = (37, 99, 235)
FG = (255, 255, 255)


def chunk(t, d):
    c = struct.pack(">I", len(d)) + t + d
    return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)


def write_png(path, size, pix):
    raw = b"".join(b"\x00" + bytes(r) for r in pix)
    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)


def inside_round(size, x, y):
    r = size * 0.22
    cx = cy = size / 2
    half = size / 2 - r
    dx = max(abs(x - cx) - half, 0.0)
    dy = max(abs(y - cy) - half, 0.0)
    return dx * dx + dy * dy <= r * r


def in_arrow(size, x, y):
    cx = size / 2
    y1, y2 = size * 0.30, size * 0.58  # треугольник
    ys1, ys2 = size * 0.50, size * 0.78  # стержень
    sw = size * 0.16
    if y1 <= y < y2:
        w = (0.42 * size) * (y - y1) / (y2 - y1)
        return abs(x - cx) <= w
    if ys1 <= y <= ys2:
        return abs(x - cx) <= sw / 2
    return False


def draw(size):
    pix = []
    for y in range(size):
        row = []
        for x in range(size):
            px = x + 0.5
            py = y + 0.5
            if in_arrow(size, px, py):
                row += list(FG)
            elif inside_round(size, px, py):
                row += list(BG)
            else:
                row += [0, 0, 0, 0]
        pix.append(row)
    return pix


here = os.path.dirname(os.path.abspath(__file__))
for s in (16, 48, 128):
    write_png(os.path.join(here, "extension", "icon%d.png" % s), s, draw(s))
    print("icon%d.png ok" % s)
