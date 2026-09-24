"""Counter controller mixin — USB connect/clear/download removed (vendor software).

Kept as no-op stubs so install/pickup/setup call sites stay stable.
"""

from __future__ import annotations


class CounterControllerMixin:
    def _counter_selected_port(self) -> str | None:
        return None

    def _counter_list_ports(self) -> None:
        return

    def _counter_pause_gps(self) -> None:
        return

    def _counter_resume_gps(self) -> None:
        return

    def _counter_refresh_and_connect(self) -> None:
        return

    def _counter_connect_after_gps_pause(self) -> None:
        return

    def _planned_counter_unit_id(self) -> str:
        return ""

    def _update_counter_labels(self) -> None:
        return

    def _counter_set_busy(self, msg: str) -> None:
        return

    def _counter_clear_busy(self) -> None:
        return

    def _counter_show_memory(self, res: dict | None = None) -> None:
        return

    def _on_picocount_done(self, res: dict) -> None:
        return

    def _on_picocount_done_body(self, res: dict, op: str, resume_gps_holder: dict) -> None:
        return

    def _counter_read_serial(self, *, auto: bool = False) -> None:
        return

    def _counter_clear_configure(self) -> None:
        return

    def _counter_clear_configure_after_pause(self) -> None:
        return

    def _counter_autoname(self) -> None:
        return

    def _counter_download_pickup(self) -> None:
        return
