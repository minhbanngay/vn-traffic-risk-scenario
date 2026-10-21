"""Acknowledge commands before the sole simulation tick advances physics."""
from ..carla_runtime import require_carla


def _submit(client, commands):
    responses = client.apply_batch_sync(commands, False)
    if len(responses) != len(commands) or any(response.error for response in responses):
        raise RuntimeError(f"CARLA command batch failed: {[response.error for response in responses]}")


def apply_controls(client, actors, controls):
    carla = require_carla()
    _submit(client, [carla.command.ApplyVehicleControl(actors[role].id,control) for role,control in controls.items()])


def initialize_motion(client, actors, transforms, speeds):
    carla = require_carla()
    commands = []
    for role, actor in actors.items():
        forward = transforms[role].rotation.get_forward_vector()
        commands.append(carla.command.ApplyVehicleControl(actor.id,carla.VehicleControl()))
        commands.append(carla.command.ApplyTargetVelocity(actor.id,carla.Vector3D(
            x=forward.x*speeds[role],y=forward.y*speeds[role],z=forward.z*speeds[role])))
    _submit(client,commands)
