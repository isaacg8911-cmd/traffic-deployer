"""When field mode is on, the app must not call the public internet."""
from __future__ import annotations

# Set from main window when offline_mode toggles or loads.
_field_mode: bool = False


def set_field_mode(on: bool) -> None:
    global _field_mode
    _field_mode = bool(on)


def field_mode() -> bool:
    return _field_mode


def internet_features_allowed() -> bool:
    """Address search, road download, online reverse geocode."""
    return not _field_mode
