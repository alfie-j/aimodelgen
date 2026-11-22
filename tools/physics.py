"""Reference physics for the Teach Bot topic: brightness and distance.

Every number the filter checks and every answer the evaluation grades is
computed here, so there is one source of truth for the physics.

Conventions
-----------
* Flux F = L / (4 pi d^2). Light per unit area falls with the square of distance.
* Pogson's relation: m2 - m1 = -2.5 log10(F2 / F1).
  Brighter means a SMALLER (more negative) magnitude.
* Distance modulus: m - M = 5 log10(d / 10 pc)  (+ A for extinction).
* Parallax: d [pc] = 1 / p [arcsec].
"""

from __future__ import annotations

import ast
import math
import operator
from dataclasses import dataclass
from typing import Any, Callable

PC_IN_LY = 3.26156
PC_IN_AU = 206264.806
AU_IN_M = 1.495978707e11
PC_IN_M = PC_IN_AU * AU_IN_M
L_SUN_W = 3.828e26
M_BOL_SUN = 4.74


# --------------------------------------------------------------------------- #
# S1 inverse-square law
# --------------------------------------------------------------------------- #
def flux(luminosity: float, distance: float) -> float:
    """Energy per unit area per unit time at distance d from a source of luminosity L."""
    if distance <= 0:
        raise ValueError("distance must be positive")
    return luminosity / (4 * math.pi * distance**2)


def flux_ratio_from_distance_ratio(distance_ratio: float) -> float:
    """If you are k times farther away, the flux is 1/k^2 of what it was."""
    if distance_ratio <= 0:
        raise ValueError("distance ratio must be positive")
    return 1.0 / distance_ratio**2


# --------------------------------------------------------------------------- #
# S2/S3 magnitudes
# --------------------------------------------------------------------------- #
def delta_mag_from_flux_ratio(flux_ratio: float) -> float:
    """m2 - m1 given F2/F1. A fainter object (ratio < 1) gives a positive difference."""
    if flux_ratio <= 0:
        raise ValueError("flux ratio must be positive")
    return -2.5 * math.log10(flux_ratio)


def flux_ratio_from_delta_mag(delta_mag: float) -> float:
    """F2/F1 given m2 - m1."""
    return 10 ** (-0.4 * delta_mag)


def combined_magnitude(mags: list[float]) -> float:
    """Magnitude of several unresolved sources: add fluxes, not magnitudes."""
    if not mags:
        raise ValueError("need at least one magnitude")
    total = sum(10 ** (-0.4 * m) for m in mags)
    return -2.5 * math.log10(total)


# --------------------------------------------------------------------------- #
# S4 distance modulus, S5 parallax, S6 extinction
# --------------------------------------------------------------------------- #
def distance_modulus(d_pc: float, extinction: float = 0.0) -> float:
    if d_pc <= 0:
        raise ValueError("distance must be positive")
    return 5 * math.log10(d_pc / 10) + extinction


def distance_from_modulus(mu: float, extinction: float = 0.0) -> float:
    return 10 ** ((mu - extinction) / 5 + 1)


def absolute_magnitude(m: float, d_pc: float, extinction: float = 0.0) -> float:
    return m - distance_modulus(d_pc, extinction)


def apparent_magnitude(M: float, d_pc: float, extinction: float = 0.0) -> float:
    return M + distance_modulus(d_pc, extinction)


def parallax_distance_pc(p_arcsec: float) -> float:
    if p_arcsec <= 0:
        raise ValueError("parallax must be positive")
    return 1.0 / p_arcsec


def luminosity_ratio_from_abs_mags(M1: float, M2: float) -> float:
    """L1/L2 from absolute magnitudes."""
    return 10 ** (-0.4 * (M1 - M2))


def bolometric_luminosity_lsun(M_bol: float) -> float:
    return 10 ** (-0.4 * (M_bol - M_BOL_SUN))


# --------------------------------------------------------------------------- #
# Safe arithmetic evaluation (for "arithmetic" claims the teacher writes)
# --------------------------------------------------------------------------- #
_BIN = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS: dict[str, Callable[..., float]] = {
    "log10": math.log10,
    "log": math.log10,  # astronomers' "log" is base 10
    "ln": math.log,
    "sqrt": math.sqrt,
    "exp": math.exp,
    "abs": abs,
}
_CONSTS = {"pi": math.pi, "e": math.e}


def safe_eval(expr: str) -> float:
    """Evaluate a plain arithmetic expression. No names except log10/sqrt/pi etc."""
    expr = expr.replace("^", "**").replace("×", "*").replace("−", "-").replace("÷", "/")
    tree = ast.parse(expr, mode="eval")

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _BIN[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            return _UNARY[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
            return float(_FUNCS[node.func.id](*[ev(a) for a in node.args]))
        if isinstance(node, ast.Name) and node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"unsupported expression element: {ast.dump(node)[:60]}")

    return ev(tree)


# --------------------------------------------------------------------------- #
# Claim checking: the teacher model lists every number it used in a <checks>
# block; each entry is recomputed here.
# --------------------------------------------------------------------------- #
@dataclass
class CheckResult:
    ok: bool
    kind: str
    expected: float | None
    claimed: float | None
    detail: str = ""


def _close(expected: float, claimed: float, rel: float, abs_tol: float) -> bool:
    return math.isclose(expected, claimed, rel_tol=rel, abs_tol=abs_tol)


def _f(x: Any) -> float:
    if isinstance(x, str):
        return safe_eval(x)
    return float(x)


def check_claim(claim: dict[str, Any], rel: float = 0.03, mag_abs: float = 0.06) -> CheckResult:
    """Recompute one claim. Magnitudes get an absolute tolerance (rounding to 0.05)."""
    kind = str(claim.get("type", "")).strip()
    try:
        if kind == "flux_ratio_from_distance":
            exp = flux_ratio_from_distance_ratio(_f(claim["distance_ratio"]))
            got = _f(claim["flux_ratio"])
            return CheckResult(_close(exp, got, rel, 1e-12), kind, exp, got)
        if kind == "delta_mag_from_flux_ratio":
            exp = delta_mag_from_flux_ratio(_f(claim["flux_ratio"]))
            got = _f(claim["delta_mag"])
            return CheckResult(_close(exp, got, 0, mag_abs), kind, exp, got)
        if kind == "flux_ratio_from_delta_mag":
            exp = flux_ratio_from_delta_mag(_f(claim["delta_mag"]))
            got = _f(claim["flux_ratio"])
            return CheckResult(_close(exp, got, rel, 1e-12), kind, exp, got)
        if kind == "distance_modulus":
            exp = distance_modulus(_f(claim["d_pc"]), _f(claim.get("extinction", 0)))
            got = _f(claim["mu"])
            return CheckResult(_close(exp, got, 0, mag_abs), kind, exp, got)
        if kind == "distance_from_modulus":
            exp = distance_from_modulus(_f(claim["mu"]), _f(claim.get("extinction", 0)))
            got = _f(claim["d_pc"])
            return CheckResult(_close(exp, got, rel, 1e-9), kind, exp, got)
        if kind == "absolute_magnitude":
            exp = absolute_magnitude(_f(claim["m"]), _f(claim["d_pc"]), _f(claim.get("extinction", 0)))
            got = _f(claim["M"])
            return CheckResult(_close(exp, got, 0, mag_abs), kind, exp, got)
        if kind == "apparent_magnitude":
            exp = apparent_magnitude(_f(claim["M"]), _f(claim["d_pc"]), _f(claim.get("extinction", 0)))
            got = _f(claim["m"])
            return CheckResult(_close(exp, got, 0, mag_abs), kind, exp, got)
        if kind == "combined_magnitude":
            exp = combined_magnitude([_f(m) for m in claim["mags"]])
            got = _f(claim["m_total"])
            return CheckResult(_close(exp, got, 0, mag_abs), kind, exp, got)
        if kind == "parallax_distance":
            exp = parallax_distance_pc(_f(claim["p_arcsec"]))
            got = _f(claim["d_pc"])
            return CheckResult(_close(exp, got, rel, 1e-9), kind, exp, got)
        if kind == "luminosity_ratio":
            exp = luminosity_ratio_from_abs_mags(_f(claim["M1"]), _f(claim["M2"]))
            got = _f(claim["L1_over_L2"])
            return CheckResult(_close(exp, got, rel, 1e-12), kind, exp, got)
        if kind == "arithmetic":
            exp = safe_eval(str(claim["expr"]))
            got = _f(claim["value"])
            return CheckResult(_close(exp, got, rel, 1e-6), kind, exp, got)
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError, SyntaxError) as e:
        return CheckResult(False, kind or "?", None, None, f"malformed claim: {e}")
    return CheckResult(False, kind or "?", None, None, "unknown claim type")


CLAIM_TYPES = [
    "flux_ratio_from_distance",
    "delta_mag_from_flux_ratio",
    "flux_ratio_from_delta_mag",
    "distance_modulus",
    "distance_from_modulus",
    "absolute_magnitude",
    "apparent_magnitude",
    "combined_magnitude",
    "parallax_distance",
    "luminosity_ratio",
    "arithmetic",
]
