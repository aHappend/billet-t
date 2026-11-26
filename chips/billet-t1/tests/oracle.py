"""Numerical reference for the normalized forward Q1.15 FFT."""

import cmath
from functools import lru_cache
import math
import random
import struct


SIZES = tuple(1 << k for k in range(1, 9))


def signed16(bits):
    return (bits & 0x7fff) - (bits & 0x8000)


def pack(sample):
    re, im = sample
    return (re & 0xffff) | ((im & 0xffff) << 16)


def unpack(word):
    return signed16(word), signed16(word >> 16)


def packed_bytes(samples):
    return b"".join(struct.pack("<I", pack(sample)) for sample in samples)


def clip(value):
    return min(32767, max(-32768, value))


def quantize(value):
    return clip(int(math.copysign(math.floor(abs(value) * 32768 + 0.5), value)))


@lru_cache(maxsize=None)
def twiddles(n):
    return tuple((quantize(math.cos(a)), quantize(math.sin(a)))
                 for a in (-math.tau * k / n for k in range(n // 2)))


def fft(samples):
    """Return natural-order signed bins and the number of clipped components."""
    if len(samples) not in SIZES:
        raise ValueError(f"unsupported FFT size: {len(samples)}")
    if any(not (-32768 <= re <= 32767 and -32768 <= im <= 32767) for re, im in samples):
        raise ValueError("FFT inputs must be signed Q1.15 components")

    def transform(seq):
        if len(seq) == 1:
            return list(seq), 0
        even, even_clamps = transform(seq[::2])
        odd, odd_clamps = transform(seq[1::2])
        clamps = even_clamps + odd_clamps
        lower, upper = [], []
        for (ar, ai), (br, bi), (wr, wi) in zip(even, odd, twiddles(len(seq))):
            tr = (br * wr - bi * wi) // 32768
            ti = (br * wi + bi * wr) // 32768
            for dest, sign in ((lower, 1), (upper, -1)):
                re, im = (ar + sign * tr) // 2, (ai + sign * ti) // 2
                dest.append((clip(re), clip(im)))
                clamps += (re != clip(re)) + (im != clip(im))
        return lower + upper, clamps

    return transform(samples)


def dft_quality(samples, observed):
    if len(observed) != len(samples):
        raise ValueError("quality comparison requires one observed bin per sample")
    n = len(samples)
    ideal = [sum(complex(*s) * cmath.exp(-math.tau * 1j * k * j / n)
                 for j, s in enumerate(samples)) / n for k in range(n)]
    actual = [complex(*s) for s in observed]
    signal = sum(abs(x) ** 2 for x in ideal)
    power = sum(abs(x) ** 2 for x in actual)
    error = sum(abs(x - y) ** 2 for x, y in zip(ideal, actual))
    if not signal or not power:
        raise ValueError("DFT quality requires nonzero signal and observed power")
    return {"cosine": sum((x.conjugate() * y).real for x, y in zip(ideal, actual))
            / math.sqrt(signal * power), "sqnr_db": 10 * math.log10(signal / error) if error else None}


def frame(n, kind, seed=0):
    if kind == "impulse":
        samples = [(0, 0)] * n
        samples[n // 2 - 1] = (19127, -24689)
        return samples
    if kind == "tone":
        return [(round(11000 * math.cos(a)), round(11000 * math.sin(a)))
                for a in (math.tau * 3 * j / n + 0.37 for j in range(n))]
    if kind == "broadband":
        rng = random.Random(seed)
        return [(rng.randint(-24000, 24000), rng.randint(-24000, 24000)) for _ in range(n)]
    if kind == "rails":
        # A quantized complex tone on the corners of the component range.
        return [(32767 if math.cos(a) >= 0 else -32768, 32767 if math.sin(a) >= 0 else -32768)
                for a in (math.tau * j / n + 0.13 for j in range(n))]
    raise ValueError(f"unknown frame kind: {kind}")


def board_frames():
    return {kind: frame(256, kind, seed=0xB111E7)
            for kind in ("impulse", "tone", "broadband")}
