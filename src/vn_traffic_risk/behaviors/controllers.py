"""Actor-only gain configuration; ego always keeps the shared legacy policy."""
from ..control import ControllerGains, SimpleVehicleController


def vehicle_controller(actor, dt, config, role):
    options = config["risk_actor"].get("controller_gains", {}) if role == "primary_risk_actor" else {}
    if options:
        return SimpleVehicleController(actor, dt, ControllerGains(**options))
    return SimpleVehicleController(actor, dt)
