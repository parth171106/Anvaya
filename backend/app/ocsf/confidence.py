"""Parse confidence (TRD.md §7.4): round_half_up(100 × (0.50·R + 0.30·T + 0.20·M/E))."""
from fractions import Fraction
from math import floor


def score(e: int, m: int, r_present: int, r_total: int, t_ok: int, t_total: int,
          fingerprint_confidence: float = 1.0) -> tuple[int, dict[str, float]]:
    r = Fraction(r_present, r_total) if r_total else Fraction(1)
    t = Fraction(t_ok, t_total) if t_total else Fraction(1)
    mapped = Fraction(m, e) if e else Fraction(0)
    s = floor(100 * (Fraction(1, 2) * r + Fraction(3, 10) * t + Fraction(1, 5) * mapped) + Fraction(1, 2))
    if fingerprint_confidence < 0.6:
        s = min(s, 60)
    return s, {"required": round(float(r), 4), "typed": round(float(t), 4), "mapped": round(float(mapped), 4)}
