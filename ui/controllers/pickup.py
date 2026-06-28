"""Pickup controller mixin — P46 E1.5 extract from main.py."""

from __future__ import annotations


class PickupControllerMixin:
    # -------------------------------------------------------- Pickup UI/flow
    def _installed_stops(self):
        items = [s for s in self.state.stops if s.get("installed")]
        items = self._stops_matching_day_filter(items)
        if getattr(self, "chk_pickup_pending", None) and self.chk_pickup_pending.isChecked():
            items = [s for s in items if not s.get("picked_up")]
        return items

    def _refresh_pickup(self):
        self._update_counter_labels()
        done, total = self.state.progress_pickup()
        pending = sum(
            1 for s in self._stops_matching_day_filter()
            if s.get("installed") and not s.get("picked_up"))
        day_tag = f" · {self._day_filter_value()}" if self._day_filter_active() else ""
        self.lbl_pickup_prog.setText(
            f"Pick-up: {done}/{total} done · {pending} pending{day_tag}")
        self.list_pickup.clear()
        for i, s in enumerate(self._installed_stops()):
            mark = "OK" if s.get("picked_up") else "--"
            sheet = f" · {s.get('sheet')}" if s.get("sheet") and not self._day_filter_active() else ""
            self.list_pickup.addItem(
                f"[{mark}] {i + 1}. Site {s['id']}{sheet} — {self._street_label(s)}")
        self._refresh_pickup_cur()
        self._refresh_field_alerts()

    def _refresh_pickup_cur(self):
        items = self._installed_stops()
        if items and self.pickup_index < len(items):
            s = items[self.pickup_index]
            self.lbl_pickup_cur.setText(f"Current: Site {s['id']} - {self._street_label(s)}")
        else:
            self.lbl_pickup_cur.setText("No pick-up selected.")

    def _pickup_item_clicked(self, item):
        self.pickup_index = self.list_pickup.row(item)
        self._refresh_pickup_cur()
        items = self._installed_stops()
        if self.pickup_index < len(items):
            lat, lon = self.state.point(items[self.pickup_index])
            self.bridge.fly_to(lat, lon, 13)

    def _mark_pickup(self):
        items = self._installed_stops()
        if not items or self.pickup_index >= len(items):
            return
        s = items[self.pickup_index]
        self._push_undo(
            "pickup",
            s["uid"],
            self._snapshot_stop(s),
            site_id=s["id"],
            pickup_index=self.pickup_index,
        )
        s["picked_up"] = True
        self._persist_shift(quiet=True)
        self._counter_inventory_shift()
        self.pickup_index = min(len(items) - 1, self.pickup_index + 1)
        self._refresh_pickup()
        self._push_state()
        self._refresh_audit()

    def _nav_pickup(self, step: int):
        items = self._installed_stops()
        if not items:
            return
        self.pickup_index = max(0, min(len(items) - 1, self.pickup_index + step))
        self._refresh_pickup_cur()
        lat, lon = self.state.point(items[self.pickup_index])
        self.bridge.fly_to(lat, lon, 14)
