"""Independent integer transform and direct mathematical cross-check."""
import cmath
import math


def twiddles():
    def quantize(x):
        return max(-32768, min(32767, round(x * 32768)))
    return [(quantize(math.cos(2 * math.pi * k / 256)),
             quantize(-math.sin(2 * math.pi * k / 256))) for k in range(128)]


TWIDDLES = twiddles()


def transform(samples, inverse, mode, mask):
    """Recursive even/odd decomposition, then complete-level normalization."""
    n = len(samples)
    levels = n.bit_length() - 1
    # Each leaf-to-root level is one complete radix-2 stage across all groups.
    # Recursive leaf ordering is independent of the DUT address equations.
    def leaves(xs):
        if len(xs) == 1:
            return [xs]
        return leaves(xs[::2]) + leaves(xs[1::2])
    groups = leaves(samples)
    exponent = 0
    stages = []
    for level in range(levels):
        raw_groups = []
        triggers = []
        for g in range(0, len(groups), 2):
            left, right = groups[g:g + 2]
            upper, lower = [], []
            for j, (a, b) in enumerate(zip(left, right)):
                wr, wi = TWIDDLES[j * 256 // (2 * len(left))]
                if inverse:
                    wi = -wi
                tr = (b[0] * wr - b[1] * wi) // 32768
                ti = (b[0] * wi + b[1] * wr) // 32768
                u, v = (a[0] + tr, a[1] + ti), (a[0] - tr, a[1] - ti)
                upper.append(u)
                lower.append(v)
                triggers.append(any(x < -32768 or x > 32767 for x in (*u, *v)))
            raw_groups.append(upper + lower)
        raw = [x for group in raw_groups for x in group]
        shift = int(mode == 0 or (mode == 1 and bool(mask & (1 << level)))
                    or (mode == 2 and any(triggers)))
        exponent += shift
        increments = []
        normalized = []
        for pair in raw:
            shifted = tuple(x // (1 << shift) for x in pair)
            increments.append(sum(not -32768 <= x <= 32767 for x in shifted))
            normalized.append(tuple(max(-32768, min(32767, x)) for x in shifted))
        width = 1 << (level + 1)
        groups = [normalized[i:i + width] for i in range(0, n, width)]
        stages.append({"shift": shift, "increments": increments,
                       "last_only": triggers[-1] and not any(triggers[:-1]),
                       "raw_min": min(x for p in raw for x in p),
                       "raw_max": max(x for p in raw for x in p)})
    return groups[0], exponent, stages


def dft(samples, inverse=False):
    sign = 1 if inverse else -1
    n = len(samples)
    return [sum(complex(*x) * cmath.exp(sign * 2j * math.pi * k * j / n)
                for j, x in enumerate(samples)) for k in range(n)]


def spectral_error(actual, exponent, mathematical):
    return sum(abs(complex(*x) * (1 << exponent) - y) ** 2
               for x, y in zip(actual, mathematical))
