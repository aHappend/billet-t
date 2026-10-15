"""Deterministic public-pin workloads. Coverage is credited by observed comparisons."""
import random

DEFAULT = (4, 0, 0, 0, 0, 0)


class Scenario:
    def __init__(self, name, kind="top", isolated=False):
        self.name, self.kind, self.isolated = name, kind, isolated
        self.rows = []
        self.seed = None
        self.reset()

    def command(self, op=0, count=1, cfg=DEFAULT, ch=0, re=0, im=0,
                ready=1, last=0, valid=0):
        self.rows.append(tuple(map(int, (op, count, valid, last, re, im, ch, *cfg, ready))))

    def reset(self):
        self.command(4, 2)

    def idle(self, cycles, ready=1, cfg=DEFAULT, ch=0):
        self.command(count=cycles, ready=ready, cfg=cfg, ch=ch)

    def send(self, samples, cfg=DEFAULT, ch=0, ready=1, perturb=True):
        for i, (r, im) in enumerate(samples):
            pins = cfg if not perturb or i == 0 else (15, 1, 3, 255, 1, 3)
            self.command(1, cfg=pins, ch=ch, re=r, im=im, ready=ready,
                         valid=1, last=int(i % 3 == 0))

    def drain(self, frames=1, ready=1):
        self.command(2, frames, ready=ready)
        self.idle(3, ready=ready)

    def wait_valid(self, last=False):
        self.command(3, int(last), ready=0)


def data(n, rng, pattern):
    if pattern == 0:
        return [(32767 if i % 2 else -32768, -32768 if i % 3 else 32767)
                for i in range(n)]
    if pattern == 1:
        return [(rng.randint(-32768, 32767), rng.randint(-32768, 32767))
                for _ in range(n)]
    if pattern == 2:
        return [(32767, 32767)] * n
    if pattern == 3:
        return [(-32768, -32768)] * n
    if pattern == 4:
        return [(16384, -8192)] + [(0, 0)] * (n - 1)
    return [(rng.randint(-64, 64), rng.randint(-64, 64)) for _ in range(n)]


def matrix(probe=False):
    rng = random.Random(1701)
    s = Scenario("numerical-matrix", isolated=True)
    s.seed = 1701
    configs = [(l, inv, scale, (0, 0x55, 0)[scale], 0, win)
               for l in range(4, 9) for inv in range(2)
               for scale in range(3) for win in range(3)]
    if probe:
        configs = [configs[0], (4, 1, 2, 0, 0, 2), (8, 0, 1, 0, 0, 1)]
    for i, cfg in enumerate(configs):
        samples = data(1 << cfg[0], rng, i % 6)
        s.send(samples, cfg, i % 4)
        s.drain()
    return s


def compatibility(probe=False):
    rng = random.Random(8917)
    s = Scenario("gen2-continuity", kind="core", isolated=True)
    s.seed = 8917
    configs = [(l, inv, scale, mask, 0, 0)
               for l in range(4, 9) for inv in range(2)
               for scale, mask in [(0, 0), (1, 0), (1, 255), (1, 170), (2, 0)]]
    if probe:
        configs = [configs[0], (4, 1, 2, 0, 0, 0)]
    for i, cfg in enumerate(configs):
        s.send(data(1 << cfg[0], rng, i % 6), cfg)
        s.drain()
    return s


def overlap(probe=False):
    rng = random.Random(291)
    s = Scenario("overlap-repeated-wrap")
    s.seed = 291
    for logn in ([4] if probe else [4, 8]):
        s.reset()
        configs = [(logn, ch % 2, ch % 3, 0x96, 1, ch % 3) for ch in range(4)]
        n = 1 << logn
        for frame in range(7):
            # Round-robin sample interleaving, with independent captured contexts.
            count = n if frame == 0 else n // 2
            for i in range(count):
                for ch in range(4):
                    pins = configs[ch] if frame == 0 and i == 0 else (
                        0, 1, 3, 255, 0, 3)
                    r, im = data(1, rng, 1)[0]
                    s.command(1, cfg=pins, ch=ch, re=r, im=im, valid=1,
                              last=(i % 5 == 0))
            s.drain(4)
        # N+H-1 cannot emit a further frame. Observe longer than one FFT.
        for ch in range(4):
            s.send(data(n // 2 - 1, rng, 1), configs[ch], ch)
        s.idle(3 * n * logn + 4 * n + 30)
        for ch in range(4):
            s.send([(ch + 73, -ch - 19)], configs[ch], ch)
        s.drain(4)
    return s


def boundaries():
    rng = random.Random(73)
    s = Scenario("boundaries-invalid-reset-stalls")
    s.seed = 73
    # Exhaust the invalid encodings; cfg_error must not depend on in_valid.
    for ch in range(4):
        for l in list(range(4)) + list(range(9, 16)):
            for valid in range(2):
                s.command(5, cfg=(l, 0, 0, 0, 0, 0), ch=ch, valid=valid)
        for bad in [(4, 0, 3, 0, 0, 0), (8, 0, 0, 0, 1, 3)]:
            for valid in range(2):
                s.command(5, cfg=bad, ch=ch, valid=valid)
    # N-1 boundary for both actual length extremes, then final Nth sample.
    for logn in [4, 8]:
        s.reset()
        cfg = (logn, 0, 2, 0, 0, 2)
        s.send(data((1 << logn) - 1, rng, 1), cfg, 3)
        s.idle(3 * (1 << logn) * logn + 40, cfg=cfg, ch=3)
        s.send([(32767, -32768)], cfg, 3)
        s.wait_valid()
        s.idle(13, ready=0)
        s.idle(2, ready=1)
        s.idle(7, ready=0)
        s.command(6, ready=1)  # Advance to last, holding it before acceptance.
        s.drain()
    # Stall a complete output while filling all four new reservations.
    s.reset()
    s.send(data(16, rng, 1), ch=0)
    s.wait_valid()
    for ch in range(4):
        s.send(data(16, rng, 1), cfg=(4, ch % 2, 1, 0, 0, ch % 3),
               ch=ch, ready=0)
    s.idle(11, ready=0)
    s.drain(5)
    # Last output beat is offered but must not complete during stalls.
    s.send(data(16, rng, 3), ch=3)
    s.command(6, 0, ready=1)  # stop on offered last, do not accept it
    s.idle(19, ready=0)
    s.drain()
    # Reset aborts empty, partial, pending, processing and stalled-last work.
    for phase in range(5):
        s.reset()
        if phase:
            s.send(data(7 if phase == 1 else 16, rng, 1), ch=3, ready=0)
        if phase == 2:
            s.send(data(16, rng, 1), ch=1, ready=0)
        if phase == 3:
            s.idle(31, ready=0)
        if phase == 4:
            s.command(6, 0, ready=1)
        s.command(7)  # Abort without a clock edge while reset is asserted.
        s.idle(300)
        s.send(data(16, rng, 4), ch=0)
        s.drain()
    return s


def buffer():
    rng = random.Random(51)
    s = Scenario("channel-buffer-contract", kind="buffer")
    s.seed = 51
    # No sink progress until all four frame reservations exist.
    for ch in range(4):
        cfg = (4, ch % 2, ch % 3, 0x5a, 1, ch % 3)
        s.send(data(16, rng, 1), cfg, ch, ready=0)
    s.idle(9, ready=0)
    s.command(6, ready=1)
    s.idle(5, ready=0)
    s.drain(4)
    for repeat in range(6):
        for ch in [3, 2, 1, 0]:
            # Captured overlap configurations ignore invalid live pins.
            s.send(data(8, rng, 1), (15, 1, 3, 0, 0, 3), ch, ready=0)
        s.idle(4, ready=0)
        s.drain(4)
    s.reset()
    # Reconfiguration and both ring wrap boundaries under alternating ready.
    for l in [8, 4, 8]:
        for ch in range(4):
            s.send(data(1 << l, rng, 1), (l, 1, 2, 0, 0, 2), ch, ready=0)
        s.drain(4)
    s.reset()
    s.send(data(16, rng, 1), ch=0)
    s.send(data(16, rng, 1), ch=3)
    s.drain(2)
    s.reset()
    s.send(data(16, rng, 1), ch=0, ready=0)
    # Keep this next-epoch beat offered throughout the old frame reservation.
    s.send([(101, -55)], ch=0, ready=1)
    s.send(data(15, rng, 1), ch=0)
    s.drain()
    s.reset()
    s.send(data(15, rng, 1), ch=3, ready=0)
    s.idle(20, ready=0)
    s.reset()
    s.idle(20)
    return s
