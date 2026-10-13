"""Standard curves for a plate (app/plates.py): a line, a line on log–log
axes, or a four-parameter logistic, fitted to the standards and read
backwards to give each sample's concentration.

Pure Python (the app carries no numpy): the 4PL is fitted with a small
Levenberg–Marquardt, from starting values read off the standards, for a
bounded number of steps. A fit that doesn't settle, or settles somewhere
no plate's standards would put it (the middle of the curve far past the
standards, a slope that is a cliff or flat), is refused in words rather
than used.

Each fit is a dict: `model` ("linear", "loglog", "4pl"), its parameters,
`r2` (on the signal for linear and 4PL, on log signal for log–log) and
`rmse`, the typical distance of a standard from the curve in signal units.
`concentration(fit, signal)` reads a signal back; None when the curve
never reaches it (past a 4PL's plateau, or a signal of nothing on log
axes).
"""
from __future__ import annotations

import math

from .i18n import gettext

MODELS = ("linear", "loglog", "4pl")
MAX_STEPS = 200
MIN_R2 = 0.9        # a 4PL that explains less of the standards than this didn't find their curve


class CurveError(ValueError):
    """A curve that can't be fitted to these standards, in words."""


def _tidy(x: float) -> float:
    return float(f"{x:.6g}")


def _r2(ys: list[float], fitted: list[float]) -> float:
    my = sum(ys) / len(ys)
    sst = sum((y - my) ** 2 for y in ys)
    sse = sum((y - f) ** 2 for y, f in zip(ys, fitted))
    return 1.0 if sst == 0 else max(0.0, 1 - sse / sst)


def _rmse(ys: list[float], fitted: list[float], params: int) -> float:
    sse = sum((y - f) ** 2 for y, f in zip(ys, fitted))
    return math.sqrt(sse / max(1, len(ys) - params))


def _line(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return (slope, my - slope * mx) if slope != 0 else None


# ---------------------------------------------------------------- the three curves

def linear(points: list[tuple[float, float]]) -> dict:
    """signal = slope × concentration + intercept."""
    if len({x for x, _ in points}) < 2:
        raise CurveError(gettext("A standard curve needs standards of at least two concentrations."))
    xs, ys = [x for x, _ in points], [y for _, y in points]
    found = _line(xs, ys)
    if found is None:
        raise CurveError(gettext("The standards all give the same signal, so no curve can be read off them."))
    slope, intercept = found
    fitted = [slope * x + intercept for x in xs]
    return {"model": "linear", "slope": _tidy(slope), "intercept": _tidy(intercept),
            "r2": round(_r2(ys, fitted), 4), "rmse": _tidy(_rmse(ys, fitted, 2)), "n": len(points)}


def loglog(points: list[tuple[float, float]]) -> dict:
    """log10 signal = slope × log10 concentration + intercept: a straight
    line through standards that span several tenfold dilutions. Standards
    of no concentration, or no signal once the blank is off, have no
    logarithm and are left out (`left_out`)."""
    usable = [(x, y) for x, y in points if x > 0 and y > 0]
    if len({x for x, _ in usable}) < 2:
        raise CurveError(gettext("A log–log curve needs standards of at least two concentrations above zero, each with a signal above zero."))  # noqa: E501
    lx, ly = [math.log10(x) for x, _ in usable], [math.log10(y) for _, y in usable]
    found = _line(lx, ly)
    if found is None:
        raise CurveError(gettext("The standards all give the same signal, so no curve can be read off them."))
    slope, intercept = found
    fitted = [slope * x + intercept for x in lx]
    signal = [y for _, y in usable]
    return {"model": "loglog", "slope": _tidy(slope), "intercept": _tidy(intercept),
            "r2": round(_r2(ly, fitted), 4),
            "rmse": _tidy(_rmse(signal, [10 ** f for f in fitted], 2)),
            "n": len(usable), "left_out": len(points) - len(usable)}


def logistic(x: float, a: float, b: float, c: float, d: float) -> float:
    """The 4PL: signal a at no concentration, d at a great deal, half-way at
    c (the EC50), with slope b."""
    if x <= 0:
        return a
    z = math.exp(max(-50.0, min(50.0, b * (math.log(x) - math.log(c)))))
    return d + (a - d) / (1 + z)


def _solve(m: list[list[float]], v: list[float]) -> list[float] | None:
    """m · x = v for a small square system (Gaussian elimination, partial pivoting)."""
    n = len(v)
    a = [row[:] + [v[i]] for i, row in enumerate(m)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-300:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, n):
            f = a[r][col] / a[col][col]
            for k in range(col, n + 1):
                a[r][k] -= f * a[col][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (a[r][n] - sum(a[r][k] * x[k] for k in range(r + 1, n))) / a[r][r]
    return x


def _start(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Starting values from the standards' means: the plateaus a little past
    the lowest and highest concentrations' signals, the middle where the
    signal crosses half-way (on log concentration), and a slope of 1."""
    by: dict[float, list[float]] = {}
    for x, y in points:
        by.setdefault(x, []).append(y)
    means = sorted((x, sum(v) / len(v)) for x, v in by.items())
    low, high = means[0][1], means[-1][1]
    span = high - low
    a, d = low - 0.05 * span, high + 0.05 * span
    half = (low + high) / 2
    positive = [(x, y) for x, y in means if x > 0]
    c = math.exp(sum(math.log(x) for x, _ in positive) / len(positive))
    for (x1, y1), (x2, y2) in zip(positive, positive[1:]):
        if (y1 - half) * (y2 - half) <= 0 and y1 != y2:
            t = (half - y1) / (y2 - y1)
            c = math.exp(math.log(x1) + t * (math.log(x2) - math.log(x1)))
            break
    return a, 1.0, c, d


def four_pl(points: list[tuple[float, float]]) -> dict:
    """The four-parameter logistic, the usual for an ELISA, by
    Levenberg–Marquardt on (a, d, ln c, ln b), so the middle and the slope
    stay above zero. A CurveError, in words, with fewer than five
    concentrations or when the fit doesn't settle."""
    concs = sorted({x for x, _ in points})
    positive = [x for x in concs if x > 0]
    if len(concs) < 5 or len(positive) < 4:
        raise CurveError(gettext("A 4PL curve needs standards of at least five concentrations: use Linear or Log–log with fewer."))  # noqa: E501
    xs, ys = [x for x, _ in points], [y for _, y in points]
    if max(ys) == min(ys):
        raise CurveError(gettext("The standards all give the same signal, so no curve can be read off them."))
    a0, b0, c0, d0 = _start(points)
    p = [a0, d0, math.log(c0), math.log(b0)]

    def model(q):
        return [logistic(x, q[0], math.exp(q[3]), math.exp(q[2]), q[1]) for x in xs]

    def sse(q):
        return sum((y - f) ** 2 for y, f in zip(ys, model(q)))

    def jacobian(q):
        a, d, b, c = q[0], q[1], math.exp(q[3]), math.exp(q[2])
        rows = []
        for x in xs:
            if x <= 0:
                rows.append([1.0, 0.0, 0.0, 0.0])
                continue
            lr = math.log(x) - math.log(c)
            z = math.exp(max(-50.0, min(50.0, b * lr)))
            den = 1 + z
            rows.append([1 / den, z / den, (a - d) * b * z / den ** 2, -(a - d) * z * lr * b / den ** 2])
        return rows

    lam, current, settled = 1e-3, sse(p), False
    scale = max(1e-300, sum((y - sum(ys) / len(ys)) ** 2 for y in ys))
    for _step in range(MAX_STEPS):
        j = jacobian(p)
        resid = [y - f for y, f in zip(ys, model(p))]
        jtj = [[sum(r[i] * r[k] for r in j) for k in range(4)] for i in range(4)]
        jtr = [sum(r[i] * e for r, e in zip(j, resid)) for i in range(4)]
        accepted = None
        while lam < 1e12:
            damped = [[jtj[i][k] + (lam * max(jtj[i][i], 1e-12) if i == k else 0.0) for k in range(4)]
                      for i in range(4)]
            delta = _solve(damped, jtr)
            trial = [p[i] + delta[i] for i in range(4)] if delta else None
            if trial and all(math.isfinite(v) for v in trial) and abs(trial[2]) < 700 and abs(trial[3]) < 5:
                new = sse(trial)
                if new < current:
                    accepted = (trial, new)
                    break
            lam *= 10
        if accepted is None:
            settled = True          # no step, however small, lowers it: a minimum
            break
        gain = current - accepted[1]
        p, current = accepted
        lam = max(lam / 10, 1e-12)
        if gain <= 1e-12 * scale:
            settled = True
            break
    a, d, c, b = p[0], p[1], math.exp(p[2]), math.exp(p[3])
    fitted = model(p)
    hi, lo = positive[-1], positive[0]
    # Somewhere no plate's standards would put it: the middle far off the
    # standards, a slope like a cliff or a flat line, the plateaus the same,
    # or a curve that misses most of the standards.
    wild = (not (lo / 100 <= c <= hi * 100) or not 0.05 <= b <= 20 or abs(a - d) < 1e-9 * (1 + abs(a))
            or _r2(ys, fitted) < MIN_R2)
    if not settled or wild or not all(math.isfinite(v) for v in (a, b, c, d)):
        raise CurveError(gettext("A 4PL curve didn't settle on these standards (they may not trace an S-shaped curve): choose Linear or Log–log, or check the standards' concentrations."))  # noqa: E501
    return {"model": "4pl", "a": _tidy(a), "b": _tidy(b), "c": _tidy(c), "d": _tidy(d),
            "r2": round(_r2(ys, fitted), 4), "rmse": _tidy(_rmse(ys, fitted, 4)), "n": len(points),
            "_exact": (a, b, c, d)}


# ---------------------------------------------------------------- choosing, reading back, drawing

def fit(points: list[tuple[float, float]], model: str | None = None) -> dict:
    """The curve asked for, or (no model) the usual: a 4PL when there are
    five or more concentrations spanning at least a tenfold dilution and it
    settles, a line otherwise (`auto` says it was chosen)."""
    if model in ("linear", "loglog", "4pl"):
        return {"linear": linear, "loglog": loglog, "4pl": four_pl}[model](points)
    positive = sorted({x for x, _ in points if x > 0})
    if len({x for x, _ in points}) >= 5 and len(positive) >= 4 and positive[-1] >= 10 * positive[0]:
        try:
            return {**four_pl(points), "auto": True}
        except CurveError:
            pass
    return {**linear(points), "auto": True}


def concentration(f: dict, signal: float) -> float | None:
    """The concentration a signal reads as on the curve; None where the
    curve never reaches it."""
    if f["model"] == "linear":
        return (signal - f["intercept"]) / f["slope"]
    if f["model"] == "loglog":
        if signal <= 0:
            return None
        return 10 ** ((math.log10(signal) - f["intercept"]) / f["slope"])
    a, b, c, d = f.get("_exact") or (f["a"], f["b"], f["c"], f["d"])
    if signal == d:
        return None
    ratio = (a - d) / (signal - d) - 1
    if ratio <= 0:
        return 0.0 if signal == a else None
    return c * ratio ** (1 / b)


def below(f: dict, signal: float) -> bool:
    """Whether a signal the curve never reaches is on the side of no
    concentration (under what the assay detects), not past its top."""
    if f["model"] != "4pl":
        return True
    a, _b, _c, d = f.get("_exact") or (f["a"], f["b"], f["c"], f["d"])
    return (signal - a) * (d - a) <= 0


def signal_at(f: dict, conc: float) -> float | None:
    if f["model"] == "linear":
        return f["slope"] * conc + f["intercept"]
    if f["model"] == "loglog":
        return 10 ** (f["slope"] * math.log10(conc) + f["intercept"]) if conc > 0 else None
    a, b, c, d = f.get("_exact") or (f["a"], f["b"], f["c"], f["d"])
    return logistic(conc, a, b, c, d)


def drawn(f: dict, concs: list[float], steps: int = 48) -> dict:
    """The curve as points to draw over the standards: on log
    concentration for log–log and 4PL (from the lowest standard above
    zero), on plain concentration for a line."""
    log = f["model"] != "linear"
    xs = [x for x in concs if x > 0] if log else list(concs)
    if not xs:
        return {"log": log, "line": []}
    lo, hi = min(xs), max(xs)
    if hi == lo:
        return {"log": log, "line": []}
    line = []
    for i in range(steps + 1):
        x = 10 ** (math.log10(lo) + (math.log10(hi) - math.log10(lo)) * i / steps) if log else lo + (hi - lo) * i / steps
        y = signal_at(f, x)
        if y is not None and math.isfinite(y):
            line.append([_tidy(x), _tidy(y)])
    return {"log": log, "line": line}


def public(f: dict) -> dict:
    """The fit as answered and kept (without the unrounded parameters)."""
    return {k: v for k, v in f.items() if not k.startswith("_")}
