"""Independent integer spectral oracle; only Python's standard library is used.

Requirements: SPEC arithmetic/windows/power -> transform/window/twiddle;
stream epochs/overlap -> accepted samples in Scoreboard (verify.py).
No DUT tables, storage indices, state, or implementation code are imported.
"""
import cmath
import math


def clamp(x):
    return max(-32768, min(32767, x))


def twiddle(k, inverse):
    angle = 2 * math.pi * k / 256
    real = clamp(round(32768 * math.cos(angle)))
    imag = clamp(round(-32768 * math.sin(angle)))
    return real, -imag if inverse else imag


def coefficient(n, index, mode):
    if mode == 0:
        return None
    index = min(index, n - 1 - index)
    c = math.cos(2 * math.pi * index / (n - 1))
    w = (0.5 - 0.5 * c) if mode == 1 else (0.54 - 0.46 * c)
    return min(32767, math.floor(32768 * w + 0.5))


def window(samples, mode):
    result = []
    for i, (r, im) in enumerate(samples):
        q = coefficient(len(samples), i, mode)
        result.append((r, im) if q is None else (r * q >> 15, im * q >> 15))
    return result


def butterfly(a, b, w):
    tr = (b[0] * w[0] - b[1] * w[1]) >> 15
    ti = (b[0] * w[1] + b[1] * w[0]) >> 15
    return (a[0] + tr, a[1] + ti), (a[0] - tr, a[1] - ti)


def transform(samples, cfg):
    """Breadth-wise recursive even/odd transforms, globally normalized per level.

    A forest entry is a mathematical transform of one decimated subsequence;
    there are no bit-reversed storage addresses or cycle/FSM predictions here.
    """
    logn, inverse, scale, mask, overlap, win = cfg
    samples = window(samples, win)
    n = len(samples)
    assert n == 1 << logn
    forest = {i: [v] for i, v in enumerate(samples)}
    exponent = saturations = 0
    stages = []
    for stage in range(logn):
        length = 1 << (stage + 1)
        stride = n // length
        raw = {}
        for offset in range(stride):
            even, odd = forest[offset], forest[offset + stride]
            low, high = [], []
            for j in range(length // 2):
                p, q = butterfly(even[j], odd[j], twiddle(j * 256 // length, inverse))
                low.append(p)
                high.append(q)
            raw[offset] = low + high
        shift = (scale == 0 or (scale == 1 and bool(mask & (1 << stage)))
                 or (scale == 2 and any(not -32768 <= x <= 32767
                     for group in raw.values() for pair in group for x in pair)))
        exponent += shift
        forest = {}
        stage_saturations = 0
        for offset, group in raw.items():
            normalized = []
            for r, im in group:
                r, im = r >> shift, im >> shift
                stage_saturations += int(r != clamp(r)) + int(im != clamp(im))
                normalized.append((clamp(r), clamp(im)))
            forest[offset] = normalized
        saturations += stage_saturations
        stages.append({"shift": int(shift), "saturations": stage_saturations})
    return {"bins": forest[0], "exponent": exponent,
            "saturations": saturations, "stages": stages}


def dft(samples, inverse):
    sign = 1 if inverse else -1
    n = len(samples)
    return [sum(complex(*x) * cmath.exp(sign * 2j * math.pi * k * j / n)
                for j, x in enumerate(samples)) for k in range(n)]
