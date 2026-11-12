"""PNG lesen und schreiben mit der Standardbibliothek (zlib), für selbst gezeichnete Kartenkacheln.

decode liest 8-Bit-Bilder ohne Zeilensprung (Graustufen, RGB, Palette auch mit 1, 2 oder 4 Bit, mit und ohne Alpha) und
gibt immer RGBA zurück. encode schreibt RGBA. Langsam im Vergleich zu einer C-Bibliothek, aber nur für wenige kleine
Bilder gedacht (Kachelsätze zu 512 × 512 Pixeln, die der Abgleich einmal liest)."""
import struct
import zlib

SIG = b"\x89PNG\r\n\x1a\n"


class PNGError(ValueError):
    pass


def _chunks(data):
    if data[:8] != SIG:
        raise PNGError("kein PNG")
    i = 8
    while i + 8 <= len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        yield kind, data[i + 8:i + 8 + n]
        i += 12 + n
        if kind == b"IEND":
            return


def _unfilter(raw, h, stride, bpp):
    out = bytearray(h * stride)
    prev = bytearray(stride)
    pos = 0
    for y in range(h):
        ft = raw[pos]
        line = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif ft == 3:
            for i in range(stride):
                left = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif ft != 0:
            raise PNGError(f"unbekannter Filter {ft}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def decode(data):
    """PNG-Bytes → (Breite, Höhe, RGBA-Bytes)."""
    ihdr, pal, trns, idat = None, b"", b"", []
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            pal = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
    if not ihdr:
        raise PNGError("ohne Kopf")
    w, h, depth, ctype, _, _, interlace = ihdr
    if interlace:
        raise PNGError("Zeilensprung wird nicht gelesen")
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if not chans or (depth != 8 and not (ctype in (0, 3) and depth in (1, 2, 4))):
        raise PNGError(f"Farbtyp {ctype} mit {depth} Bit wird nicht gelesen")
    bits = chans * depth
    stride = (w * bits + 7) // 8
    px = _unfilter(zlib.decompress(b"".join(idat)), h, stride, max(1, bits // 8))
    if depth < 8:                 # gepackte Indizes oder Grauwerte auf ein Byte je Pixel auspacken
        per, mask = 8 // depth, (1 << depth) - 1
        un = bytearray(w * h)
        for y in range(h):
            row = px[y * stride:(y + 1) * stride]
            for x in range(w):
                un[y * w + x] = (row[x // per] >> (8 - depth * (x % per + 1))) & mask
        px = un
        if ctype == 0:
            scale = 255 // mask
            px = bytearray(v * scale for v in px)
    if ctype == 6:
        return w, h, bytes(px)
    if ctype == 3:
        lut = []
        for i in range(256):
            rgb = pal[i * 3:i * 3 + 3] or b"\0\0\0"
            lut.append(rgb + bytes([trns[i] if i < len(trns) else 255]))
        return w, h, b"".join(lut[v] for v in px)
    if ctype == 2:
        key = trns[1::2][:3] if len(trns) == 6 else None
        out = bytearray(w * h * 4)
        out[0::4], out[1::4], out[2::4] = px[0::3], px[1::3], px[2::3]
        out[3::4] = b"\xff" * (w * h)
        if key:
            for i in range(w * h):
                if px[i * 3:i * 3 + 3] == key:
                    out[i * 4 + 3] = 0
        return w, h, bytes(out)
    if ctype == 4:
        out = bytearray(w * h * 4)
        out[0::4] = out[1::4] = out[2::4] = px[0::2]
        out[3::4] = px[1::2]
        return w, h, bytes(out)
    out = bytearray(w * h * 4)            # Graustufen
    out[0::4] = out[1::4] = out[2::4] = px
    out[3::4] = b"\xff" * (w * h)
    return w, h, bytes(out)


def _chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def encode(w, h, rgba, level=6):
    """RGBA-Bytes → PNG-Bytes (Filter 0 je Zeile)."""
    stride = w * 4
    raw = b"".join(b"\0" + rgba[y * stride:(y + 1) * stride] for y in range(h))
    return (SIG + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, level)) + _chunk(b"IEND", b""))
