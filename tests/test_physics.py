import math
import pytest
from tools import physics as P


def test_inverse_square():
    assert P.flux_ratio_from_distance_ratio(10) == pytest.approx(0.01)
    assert P.flux(4 * math.pi, 1) == pytest.approx(1)


def test_factor_100_is_5_mag():
    assert P.delta_mag_from_flux_ratio(0.01) == pytest.approx(5)
    assert P.flux_ratio_from_delta_mag(5) == pytest.approx(0.01)
    assert 100 ** 0.2 == pytest.approx(2.512, abs=1e-3)


def test_distance_modulus():
    assert P.distance_modulus(10) == pytest.approx(0)
    assert P.distance_modulus(100) == pytest.approx(5)
    assert P.distance_from_modulus(10) == pytest.approx(1000)
    assert P.distance_from_modulus(10, 1.5) == pytest.approx(10 ** 2.7)
    assert P.absolute_magnitude(9.5, 200) == pytest.approx(9.5 - 5 * math.log10(20))


def test_combined_and_parallax():
    assert P.combined_magnitude([1, 1]) == pytest.approx(1 - 2.5 * math.log10(2))
    assert P.parallax_distance_pc(0.1) == pytest.approx(10)
    assert P.luminosity_ratio_from_abs_mags(0, 5) == pytest.approx(100)


@pytest.mark.parametrize("claim,ok", [
    ({"type": "flux_ratio_from_distance", "distance_ratio": 10, "flux_ratio": 0.01}, True),
    ({"type": "flux_ratio_from_distance", "distance_ratio": 10, "flux_ratio": 0.1}, False),
    ({"type": "delta_mag_from_flux_ratio", "flux_ratio": 0.01, "delta_mag": 5}, True),
    ({"type": "delta_mag_from_flux_ratio", "flux_ratio": 0.01, "delta_mag": -5}, False),  # sign flip
    ({"type": "distance_modulus", "d_pc": 100, "mu": 5}, True),
    ({"type": "distance_from_modulus", "mu": 5, "d_pc": 100}, True),
    ({"type": "absolute_magnitude", "m": 10, "d_pc": 100, "M": 5}, True),
    ({"type": "combined_magnitude", "mags": [1, 1], "m_total": 0.25}, True),
    ({"type": "combined_magnitude", "mags": [1, 1], "m_total": 2}, False),  # added magnitudes
    ({"type": "parallax_distance", "p_arcsec": 0.1, "d_pc": 10}, True),
    ({"type": "arithmetic", "expr": "2.5*log10(100)", "value": 5}, True),
    ({"type": "arithmetic", "expr": "2.5*log10(100)", "value": 4}, False),
    ({"type": "nonsense"}, False),
    ({"type": "distance_modulus", "d_pc": "abc"}, False),
])
def test_check_claim(claim, ok):
    assert P.check_claim(claim).ok is ok


def test_safe_eval_refuses_code():
    with pytest.raises(ValueError):
        P.safe_eval("__import__('os').system('echo hi')")
    assert P.safe_eval("10^2 × 3") == 300
