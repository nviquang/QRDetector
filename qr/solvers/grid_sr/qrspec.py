"""Phần đặc tả QR tự viết cho version 1-3: GF(256), Reed-Solomon sửa lỗi + xóa, bố cục ô, format, giải bit dòng, mã hóa."""
from __future__ import annotations

import numpy as np

# ---- GF(256) ---------------------------------------------------------------------------------------------------------
EXP = [0] * 512
LOG = [0] * 256
_x = 1
for _i in range(255):
    EXP[_i] = _x
    LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    EXP[_i] = EXP[_i - 255]


def gmul(a, b):
    return 0 if a == 0 or b == 0 else EXP[LOG[a] + LOG[b]]


def ginv(a):
    return EXP[255 - LOG[a]]


def poly_mul(p, q):
    """Đa thức hệ số bậc thấp trước."""
    r = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a:
            for j, b in enumerate(q):
                if b:
                    r[i + j] ^= EXP[LOG[a] + LOG[b]]
    return r


def poly_eval(p, x):
    y = 0
    for c in reversed(p):
        y = gmul(y, x) ^ c
    return y


_GEN = {}


def rs_generator(nsym):
    if nsym not in _GEN:
        g = [1]
        for i in range(nsym):
            g = poly_mul(g, [EXP[i], 1])
        _GEN[nsym] = g
    return _GEN[nsym]


def rs_encode(data, nsym):
    """Trả các byte EC của ``data`` (byte đầu là bậc cao nhất, như QR)."""
    gen = list(reversed(rs_generator(nsym)))  # bậc cao trước
    rem = [0] * nsym
    for b in data:
        f = b ^ rem[0]
        rem = rem[1:] + [0]
        if f:
            for j in range(nsym):
                rem[j] ^= gmul(f, gen[j + 1])
    return rem


def rs_decode(cw, nsym, erase=()):
    """Sửa lỗi và xóa. ``cw`` là n byte, byte 0 bậc cao nhất. Trả (bản đã sửa, số lỗi không kể xóa) hoặc None."""
    n = len(cw)
    synd = [0] * nsym
    for i in range(nsym):
        y = 0
        ax = EXP[i]
        for b in cw:
            y = gmul(y, ax) ^ b
        synd[i] = y
    if not any(synd):
        return list(cw), 0
    erase = sorted(set(erase))
    if len(erase) > nsym:
        return None
    # locator của các vị trí xóa
    gam = [1]
    for e in erase:
        gam = poly_mul(gam, [1, EXP[n - 1 - e]])
    # syndrome đã biến đổi (Forney)
    t = poly_mul(synd, gam)[:nsym]
    s = len(erase)
    # Berlekamp-Massey trên S[s:]
    sigma = [1]
    prev = [1]
    L = 0
    m = 1
    bb = 1
    for k in range(s, nsym):
        delta = t[k]
        for i in range(1, L + 1):
            if i < len(sigma):
                delta ^= gmul(sigma[i], t[k - i])
        if delta == 0:
            m += 1
        else:
            coef = gmul(delta, ginv(bb))
            tmp = list(sigma)
            shifted = [0] * m + [gmul(coef, c) for c in prev]
            sigma = [(sigma[i] if i < len(sigma) else 0) ^ (shifted[i] if i < len(shifted) else 0)
                     for i in range(max(len(sigma), len(shifted)))]
            if 2 * L <= k - s:
                L = k - s + 1 - L
                prev = tmp
                bb = delta
                m = 1
            else:
                m += 1
    while len(sigma) > 1 and sigma[-1] == 0:
        sigma.pop()
    nerr = len(sigma) - 1
    if nerr != L or 2 * nerr + s > nsym:
        return None
    loc = poly_mul(sigma, gam)
    # tìm nghiệm
    pos = []
    for i in range(n):
        if poly_eval(loc, EXP[(255 - (n - 1 - i)) % 255]) == 0:
            pos.append(i)
    if len(pos) != len(loc) - 1 or (len(loc) > 1 and loc[-1] == 0):
        return None
    omega = poly_mul(synd, loc)[:nsym]
    dloc = [loc[i] if i % 2 == 1 else 0 for i in range(1, len(loc))]
    out = list(cw)
    for p in pos:
        xi = EXP[n - 1 - p]
        xinv = ginv(xi)
        den = poly_eval(dloc, xinv)
        if den == 0:
            return None
        # fcr = 0 nên hệ số là X^(1-fcr) = X
        out[p] ^= gmul(gmul(xi, poly_eval(omega, xinv)), ginv(den))
    # kiểm tra lại
    for i in range(nsym):
        y = 0
        ax = EXP[i]
        for b in out:
            y = gmul(y, ax) ^ b
        if y:
            return None
    return out, nerr


# ---- Bố cục ----------------------------------------------------------------------------------------------------------
# (số byte EC mỗi khối, [(số khối, n, k)]) theo mức cho version 1..3; format mã hóa mức: L=1, M=0, Q=3, H=2
BLOCKS = {
    1: {1: [(1, 26, 19)], 0: [(1, 26, 16)], 3: [(1, 26, 13)], 2: [(1, 26, 9)]},
    2: {1: [(1, 44, 34)], 0: [(1, 44, 28)], 3: [(1, 44, 22)], 2: [(1, 44, 16)]},
    3: {1: [(1, 70, 55)], 0: [(1, 70, 44)], 3: [(2, 35, 17)], 2: [(2, 35, 13)]},
}
ALIGN = {1: [], 2: [6, 18], 3: [6, 22]}
FORMAT_MASK = 0x5412


def _bch_format(v):
    d = v << 10
    g = 0x537
    for i in range(14, 9, -1):
        if d >> i & 1:
            d ^= g << (i - 10)
    return ((v << 10) | d) ^ FORMAT_MASK


FORMAT_CODES = np.array([[(_bch_format(v) >> (14 - i)) & 1 for i in range(15)] for v in range(32)], np.uint8)


def format_positions(size):
    """Hai bản 15 ô format [(hàng, cột)], bit 14 (MSB) đứng trước, theo chuẩn."""
    a = [(8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8), (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8)]
    b = [(size - 1, 8), (size - 2, 8), (size - 3, 8), (size - 4, 8), (size - 5, 8), (size - 6, 8), (size - 7, 8),
         (8, size - 8), (8, size - 7), (8, size - 6), (8, size - 5), (8, size - 4), (8, size - 3), (8, size - 2),
         (8, size - 1)]
    return a, b


class Layout:
    """Với một version: giá trị ô chức năng cố định (1 = trắng), mặt nạ ô chức năng, thứ tự ô dữ liệu."""

    def __init__(self, version):
        self.version = version
        n = self.size = 17 + 4 * version
        known = np.full((n, n), -1, np.int8)  # -1: chưa biết, 0 đen, 1 trắng

        def finder(r0, c0):
            for r in range(-1, 8):
                for c in range(-1, 8):
                    rr, cc = r0 + r, c0 + c
                    if 0 <= rr < n and 0 <= cc < n:
                        ring = max(abs(r - 3), abs(c - 3))
                        known[rr, cc] = 0 if ring in (0, 1, 3) else 1

        finder(0, 0)
        finder(0, n - 7)
        finder(n - 7, 0)
        for i in range(8, n - 8):
            known[6, i] = known[i, 6] = 0 if i % 2 == 0 else 1
        if version >= 2:
            a = ALIGN[version][-1]
            for r in range(-2, 3):
                for c in range(-2, 3):
                    known[a + r, a + c] = 0 if max(abs(r), abs(c)) != 1 else 1
        known[n - 8, 8] = 0
        self.known = known
        fa, fb = format_positions(n)
        self.fmt = [np.array(fa), np.array(fb)]
        reserved = known >= 0
        for p in fa + fb:
            reserved[p] = True
        self.reserved = reserved
        order = []
        col = n - 1
        up = True
        while col > 0:
            if col == 6:
                col -= 1
            rows = range(n - 1, -1, -1) if up else range(n)
            for r in rows:
                for c in (col, col - 1):
                    if not reserved[r, c]:
                        order.append((r, c))
            up = not up
            col -= 2
        self.order = np.array(order)

    def mask(self, m):
        n = self.size
        r, c = np.mgrid[0:n, 0:n]
        return {0: (r + c) % 2 == 0, 1: r % 2 == 0, 2: c % 3 == 0, 3: (r + c) % 3 == 0,
                4: (r // 2 + c // 3) % 2 == 0, 5: (r * c) % 2 + (r * c) % 3 == 0,
                6: ((r * c) % 2 + (r * c) % 3) % 2 == 0, 7: ((r + c) % 2 + (r * c) % 3) % 2 == 0}[m]


def format_info(v):
    """v 5 bit -> (mức EC, mask)."""
    return v >> 3, v & 7


def codeword_map(layout, level):
    """Trả (cw_index[bit], bit_index[bit]) theo thứ tự ô dữ liệu và bảng khối, xem ``blocks_layout``."""
    blocks = expand_blocks(layout.version, level)
    data_seq, ec_seq = [], []
    max_k = max(k for _, k, _ in blocks)
    for i in range(max_k):
        for b, (_, k, off) in enumerate(blocks):
            if i < k:
                data_seq.append(off + i)
    max_e = max(n - k for n, k, _ in blocks)
    for i in range(max_e):
        for b, (n, k, off) in enumerate(blocks):
            if i < n - k:
                ec_seq.append(off + k + i)
    seq = np.array(data_seq + ec_seq)
    nb = len(layout.order)
    total = len(seq) * 8
    cw = seq[np.arange(total) // 8]
    bit = 7 - np.arange(total) % 8
    return cw, bit, nb


def expand_blocks(version, level):
    """[(n, k, vị trí đầu trong mảng codeword đã xếp theo khối)]."""
    out = []
    off = 0
    for cnt, n, k in BLOCKS[version][level]:
        for _ in range(cnt):
            out.append((n, k, off))
            off += n
    return out


def count_bits(mode):
    return {1: 10, 2: 9, 4: 8}.get(mode, 8)


ALNUM = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:"


class BitReader:
    def __init__(self, data):
        self.data = data
        self.pos = 0
        self.n = len(data) * 8

    def read(self, k):
        if self.pos + k > self.n:
            raise ValueError
        v = 0
        for i in range(k):
            v = v << 1 | (self.data[self.pos >> 3] >> (7 - self.pos % 8) & 1)
            self.pos += 1
        return v

    def left(self):
        return self.n - self.pos


def parse_payload(data):
    """Giải bit dòng (chỉ numeric/alnum/byte, cho version < 10). Trả dict hoặc None nếu vi phạm.

    Trả: text, end (byte đầu tiên sau phần có nghĩa, kể cả terminator), pad_ok (các byte sau terminator đúng EC/11).
    """
    br = BitReader(data)
    text = ""
    try:
        while True:
            if br.left() < 4:
                break
            mode = br.read(4)
            if mode == 0:
                break
            if mode not in (1, 2, 4):
                return None
            cnt = br.read(count_bits(mode))
            if cnt == 0:
                return None
            if mode == 1:
                c = cnt
                while c >= 3:
                    v = br.read(10)
                    if v >= 1000:
                        return None
                    text += f"{v:03d}"
                    c -= 3
                if c == 2:
                    v = br.read(7)
                    if v >= 100:
                        return None
                    text += f"{v:02d}"
                elif c == 1:
                    v = br.read(4)
                    if v >= 10:
                        return None
                    text += f"{v:d}"
            elif mode == 2:
                c = cnt
                while c >= 2:
                    v = br.read(11)
                    if v >= 45 * 45:
                        return None
                    text += ALNUM[v // 45] + ALNUM[v % 45]
                    c -= 2
                if c:
                    v = br.read(6)
                    if v >= 45:
                        return None
                    text += ALNUM[v]
            else:
                bs = bytes(br.read(8) for _ in range(cnt))
                try:
                    text += bs.decode("utf-8")
                except UnicodeDecodeError:
                    text += bs.decode("latin-1")
    except ValueError:
        return None
    if not text:
        return None
    # các bit lấp về biên byte phải bằng 0
    while br.pos % 8:
        if br.read(1):
            return None
    end = br.pos // 8
    pads = bytes(data[end:])
    good = sum(b == (0xEC if i % 2 == 0 else 0x11) for i, b in enumerate(pads))
    return dict(text=text, end=end, npad=len(pads), pad_good=good)


def pad_bytes(start, n):
    return [0xEC if (i - start) % 2 == 0 else 0x11 for i in range(start, n)]


def encode_payload(text, capacity):
    """Mã hóa 1 đoạn: numeric nếu toàn số, byte nếu không. Trả ``capacity`` byte dữ liệu, None nếu quá chỗ."""
    bits = []

    def put(v, k):
        for i in range(k - 1, -1, -1):
            bits.append(v >> i & 1)

    if text.isdigit():
        put(1, 4)
        put(len(text), 10)
        for i in range(0, len(text), 3):
            g = text[i:i + 3]
            put(int(g), {1: 4, 2: 7, 3: 10}[len(g)])
    else:
        raw = text.encode("utf-8")
        put(4, 4)
        put(len(raw), 8)
        for b in raw:
            put(b, 8)
    if len(bits) > capacity * 8:
        return None
    bits += [0] * min(4, capacity * 8 - len(bits))
    while len(bits) % 8:
        bits.append(0)
    data = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    return data + pad_bytes(len(data), capacity)
