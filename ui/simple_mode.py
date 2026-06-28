"""Product shape: one default path, advanced pick/wizard tucked away."""
from __future__ import annotations

# Director-approved simple operator UX (2026-06-07).
SIMPLE_MODE = True
# Tighter panels — one screen per tab, less hint noise.
COMPACT_UI = SIMPLE_MODE
COMPACT_PAD = 12

BUILD_LABEL = "BUILD ROUTE" if SIMPLE_MODE else "PLAN ROUTE — pick stop order"

# Field shell: after READY FOR OFFLINE, hide Setup (home-only tools).
FIELD_SHELL = SIMPLE_MODE
FIELD_NAV_INDICES = (1, 2, 3, 4)  # Route, Install, Pickup, Audit

# Battery + bridge throttle (SwiftShader map is CPU-heavy — fewer JS pushes help).
GPS_TICK_MS = 1000
GPS_TICK_DRIVE_MS = 450
GPS_PUSH_MIN_M = 6.0
GPS_PUSH_HEARTBEAT_S = 5.0
MAP_HEALTH_MS = 30_000
MAP_HEALTH_FIELD_MS = 120_000
MAP_HEALTH_DRIVE_MS = 180_000
PERIODIC_SAVE_MS = 45_000
STRIP_THROTTLE_S = 2.0

# Unplugged laptop — fewer map/GPS pushes, longer health polls (field day battery).
BATTERY_GPS_TICK_MS = 2000
BATTERY_GPS_TICK_DRIVE_MS = 900
BATTERY_GPS_PUSH_MIN_M = 12.0
BATTERY_GPS_PUSH_HEARTBEAT_S = 10.0
BATTERY_MAP_HEALTH_MS = 60_000
BATTERY_MAP_HEALTH_FIELD_MS = 300_000
BATTERY_MAP_HEALTH_DRIVE_MS = 300_000
BATTERY_PERIODIC_SAVE_MS = 60_000
BATTERY_STRIP_THROTTLE_S = 4.0

# Intel N200 / 4 GB work laptops — throttle even on AC (SwiftShader is CPU-heavy).
WORK_LAPTOP_GPS_TICK_MS = 1500
WORK_LAPTOP_GPS_TICK_DRIVE_MS = 650
WORK_LAPTOP_GPS_PUSH_MIN_M = 10.0
WORK_LAPTOP_GPS_PUSH_HEARTBEAT_S = 8.0
WORK_LAPTOP_MAP_HEALTH_MS = 45_000
WORK_LAPTOP_MAP_HEALTH_FIELD_MS = 180_000
WORK_LAPTOP_MAP_HEALTH_DRIVE_MS = 240_000
WORK_LAPTOP_PERIODIC_SAVE_MS = 50_000
WORK_LAPTOP_STRIP_THROTTLE_S = 3.0

HIDE_PANEL_THEMES = SIMPLE_MODE


def timing_profile(
    *, on_ac: bool | None, gps_follow: bool, work_laptop: bool = False,
) -> dict:
    """Active intervals — saver when on battery; work-laptop tier when low RAM."""
    if work_laptop and on_ac is False:
        saver = True
    elif work_laptop:
        return {
            "gps_tick_ms": WORK_LAPTOP_GPS_TICK_DRIVE_MS if gps_follow else WORK_LAPTOP_GPS_TICK_MS,
            "gps_push_min_m": WORK_LAPTOP_GPS_PUSH_MIN_M,
            "gps_push_heartbeat_s": WORK_LAPTOP_GPS_PUSH_HEARTBEAT_S,
            "map_health_ms": WORK_LAPTOP_MAP_HEALTH_MS,
            "map_health_field_ms": WORK_LAPTOP_MAP_HEALTH_FIELD_MS,
            "map_health_drive_ms": WORK_LAPTOP_MAP_HEALTH_DRIVE_MS,
            "periodic_save_ms": WORK_LAPTOP_PERIODIC_SAVE_MS,
            "strip_throttle_s": WORK_LAPTOP_STRIP_THROTTLE_S,
            "battery_saver": False,
            "work_laptop": True,
        }
    else:
        saver = on_ac is False
    if saver:
        return {
            "gps_tick_ms": BATTERY_GPS_TICK_DRIVE_MS if gps_follow else BATTERY_GPS_TICK_MS,
            "gps_push_min_m": BATTERY_GPS_PUSH_MIN_M,
            "gps_push_heartbeat_s": BATTERY_GPS_PUSH_HEARTBEAT_S,
            "map_health_ms": BATTERY_MAP_HEALTH_MS,
            "map_health_field_ms": BATTERY_MAP_HEALTH_FIELD_MS,
            "map_health_drive_ms": BATTERY_MAP_HEALTH_DRIVE_MS,
            "periodic_save_ms": BATTERY_PERIODIC_SAVE_MS,
            "strip_throttle_s": BATTERY_STRIP_THROTTLE_S,
            "battery_saver": True,
            "work_laptop": False,
        }
    return {
        "gps_tick_ms": GPS_TICK_DRIVE_MS if gps_follow else GPS_TICK_MS,
        "gps_push_min_m": GPS_PUSH_MIN_M,
        "gps_push_heartbeat_s": GPS_PUSH_HEARTBEAT_S,
        "map_health_ms": MAP_HEALTH_MS,
        "map_health_field_ms": MAP_HEALTH_FIELD_MS,
        "map_health_drive_ms": MAP_HEALTH_DRIVE_MS,
        "periodic_save_ms": PERIODIC_SAVE_MS,
        "strip_throttle_s": STRIP_THROTTLE_S,
        "battery_saver": False,
        "work_laptop": False,
    }
