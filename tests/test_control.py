import pytest

from vn_traffic_risk.control import EgoRiskResponse
from vn_traffic_risk.math_utils import kmh_to_mps


def test_ego_risk_response_slows_holds_and_recovers() -> None:
    response = EgoRiskResponse(
        {
            "reaction_delay_seconds": 0.5,
            "risk_slowdown_speed_kmh": 12.5,
            "risk_slowdown_hold_seconds": 0.3,
            "risk_slowdown_max_seconds": 1.0,
        },
        fixed_delta_seconds=0.1,
    )
    cruise = kmh_to_mps(25.0)
    slow = kmh_to_mps(12.5)
    response.trigger(0)

    assert response.target_speed(4, cruise, cruise) == pytest.approx(cruise)
    assert response.target_speed(5, slow, cruise) == pytest.approx(slow)
    assert response.target_speed(7, slow, cruise) == pytest.approx(slow)
    assert response.target_speed(8, slow, cruise) == pytest.approx(cruise)
    assert response.target_speed(9, slow, cruise) == pytest.approx(cruise)
