"""Offline/online field mode alignment — P46 extract from main.py."""

from __future__ import annotations

from core import offline_policy


class FieldModeMixin:
    def _internet_allowed(self) -> bool:
        """Online features (address search, road download) only before Ready for Offline."""
        return not self.state.offline_mode

    def _sync_field_mode(self) -> None:
        """Keep geo/connectivity aligned with offline_mode (no public internet on road)."""
        offline_policy.set_field_mode(bool(self.state.offline_mode))
