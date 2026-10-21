from __future__ import annotations

import math

from ..models import ActorState


def footprint(state: ActorState) -> list[tuple[float, float]]:
    body_yaw = math.radians(state.rotation.z)
    center_x = state.location.x + math.cos(body_yaw)*state.bbox_offset.x - math.sin(body_yaw)*state.bbox_offset.y
    center_y = state.location.y + math.sin(body_yaw)*state.bbox_offset.x + math.cos(body_yaw)*state.bbox_offset.y
    yaw = math.radians(state.rotation.z + state.bbox_rotation.z)
    c, s = math.cos(yaw), math.sin(yaw)
    return [(center_x + c*x - s*y, center_y + s*x + c*y)
            for x, y in ((-state.bbox_extent.x, -state.bbox_extent.y),
                         (state.bbox_extent.x, -state.bbox_extent.y),
                         (state.bbox_extent.x, state.bbox_extent.y),
                         (-state.bbox_extent.x, state.bbox_extent.y))]


def corridor_metrics(ego: ActorState, actor: ActorState, forward: tuple[float, float]) -> dict:
    fx, fy = forward
    intervals = []
    for ax, ay in ((fx, fy), (-fy, fx)):
        ep = [x*ax+y*ay for x, y in footprint(ego)]
        ap = [x*ax+y*ay for x, y in footprint(actor)]
        intervals.append((min(ep), max(ep), min(ap), max(ap)))
    emin, emax, amin, amax = intervals[0]
    ahead = (amin + amax) >= (emin + emax)
    gap = amin - emax if ahead else emin - amax
    ev = ego.velocity.x*fx + ego.velocity.y*fy
    av = actor.velocity.x*fx + actor.velocity.y*fy
    speed, closing = (ev, ev-av) if ahead else (av, av-ev)
    lateral = intervals[1]
    overlap = max(lateral[0], lateral[2]) <= min(lateral[1], lateral[3])
    return {
        "longitudinal_distance_m": (actor.location.x-ego.location.x)*fx + (actor.location.y-ego.location.y)*fy,
        "lateral_distance_m": abs(-(actor.location.x-ego.location.x)*fy + (actor.location.y-ego.location.y)*fx),
        "bumper_gap_m": gap,
        "time_headway_seconds": gap/max(speed, 0.5) if gap >= 0 else 0.0,
        "ttc_seconds": gap/closing if overlap and gap > 0 and closing > 0.1 else None,
        "corridor_overlap": overlap,
        "actor_ahead": ahead,
        "distance_m": math.hypot(actor.location.x-ego.location.x, actor.location.y-ego.location.y),
    }


def lateral_clearance_metrics(ego: ActorState, actor: ActorState, forward: tuple[float, float]) -> dict:
    """Signed body-to-body separation on road axes (not center distance)."""
    fx, fy = forward
    bounds = []
    for ax, ay in ((fx, fy), (-fy, fx)):
        values = [[x*ax+y*ay for x, y in footprint(state)] for state in (ego, actor)]
        bounds.append([(min(v), max(v)) for v in values])
    (emin, emax), (amin, amax) = bounds[0]
    (eln, elx), (aln, alx) = bounds[1]
    return {"longitudinal_overlap": max(emin, amin) <= min(emax, amax),
            "lateral_clearance_m": max(aln-elx, eln-alx)}
