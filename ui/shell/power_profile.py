"""Battery / work-laptop GPS and map timing — P46 extract from main.py."""

from __future__ import annotations

from core import power as laptop_power
from ui.simple_mode import timing_profile


class PowerProfileMixin:
    def _poll_power(self) -> None:
        snap = laptop_power.read_power()
        prev = self._power_on_ac
        self._power_on_ac = snap.on_ac
        self._power_label = snap.label
        if hasattr(self, "status_power"):
            if snap.on_ac is False:
                self.status_power.setText("Battery saver")
                tip = (
                    f"Laptop on battery ({snap.label}) — GPS/map throttled to save power. "
                    "Plug in for full refresh rate."
                )
                if self._work_laptop:
                    tip += " Work-laptop mode also limits map load on 4 GB RAM."
                self.status_power.setToolTip(tip)
            elif self._work_laptop:
                self.status_power.setText("Work laptop")
                self.status_power.setToolTip(
                    "Low-RAM tuning — map and GPS throttled for stability. "
                    "Use FOLLOW GPS for a leaner map while driving."
                )
            elif snap.on_ac is True:
                self.status_power.setText("Plugged in")
                self.status_power.setToolTip(f"AC power ({snap.label}) — full GPS/map rate.")
            else:
                self.status_power.setText("")
                self.status_power.setToolTip("")
        if prev != snap.on_ac:
            self._apply_power_profile(force=True)
            if snap.on_ac is False:
                self.statusBar().showMessage(
                    "Battery saver on — plug in for full GPS/map rate.", 8000)
            elif snap.on_ac is True and prev is False:
                self.statusBar().showMessage("Plugged in — full GPS/map rate restored.", 6000)

    def _apply_power_profile(self, *, force: bool = False) -> None:
        t = timing_profile(
            on_ac=self._power_on_ac, gps_follow=self._gps_follow, work_laptop=self._work_laptop,
        )
        self._gps_push_min_m = t["gps_push_min_m"]
        self._gps_push_heartbeat_s = t["gps_push_heartbeat_s"]
        self._strip_throttle_s = t["strip_throttle_s"]
        self._sync_gps_timer()
        self._sync_map_health_interval()
        if hasattr(self, "_periodic_save"):
            ms = int(t["periodic_save_ms"])
            if force or self._periodic_save.interval() != ms:
                self._periodic_save.setInterval(ms)
                if not self._periodic_save.isActive():
                    self._periodic_save.start(ms)

    def _sync_gps_timer(self) -> None:
        if not hasattr(self, "gps_timer"):
            return
        t = timing_profile(
            on_ac=self._power_on_ac, gps_follow=self._gps_follow, work_laptop=self._work_laptop,
        )
        ms = int(t["gps_tick_ms"])
        if self.gps_timer.interval() != ms:
            self.gps_timer.setInterval(ms)
        if not self.gps_timer.isActive():
            self.gps_timer.start(ms)

    def _sync_map_health_interval(self) -> None:
        if not hasattr(self, "_map_health"):
            return
        t = timing_profile(
            on_ac=self._power_on_ac, gps_follow=self._gps_follow, work_laptop=self._work_laptop,
        )
        if self._gps_follow:
            ms = int(t["map_health_drive_ms"])
        elif self.state.offline_mode:
            ms = int(t["map_health_field_ms"])
        else:
            ms = int(t["map_health_ms"])
        if self._map_health.interval() != ms:
            self._map_health.setInterval(ms)
        if not self._map_health.isActive():
            self._map_health.start(ms)
