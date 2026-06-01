"""Offline turn-by-turn voice — Windows SAPI via pyttsx3 (female guide)."""
from __future__ import annotations

import queue
import re
import threading

_HAS_TTS = False
_TTS_ERR = ""

try:
    import pyttsx3
    _HAS_TTS = True
except Exception as exc:  # noqa: BLE001
    _TTS_ERR = str(exc)

VOICE_FEMALE = "female"

_FEMALE_HINTS = (
    "zira", "jenny", "aria", "susan", "hazel", "eva", "samantha",
    "female", "woman", "girl", "catherine", "linda", "heera",
)

_DIST_BANDS = (800, 400, 150)


def tts_available() -> bool:
    return _HAS_TTS


def tts_error() -> str:
    return _TTS_ERR


def normalize_voice_style(style: str | None) -> str:
    return VOICE_FEMALE


def _clean_street(name: str | None) -> str:
    s = str(name or "").strip()
    if not s or s.lower() in ("road", "none", "nan"):
        return "the road"
    s = re.sub(r"\bSt\.?\b", "Street", s, flags=re.I)
    s = re.sub(r"\bAve\.?\b", "Avenue", s, flags=re.I)
    s = re.sub(r"\bBlvd\.?\b", "Boulevard", s, flags=re.I)
    s = re.sub(r"\bDr\.?\b", "Drive", s, flags=re.I)
    s = re.sub(r"\bCt\.?\b", "Court", s, flags=re.I)
    s = re.sub(r"\bLn\.?\b", "Lane", s, flags=re.I)
    s = re.sub(r"\bRd\.?\b", "Road", s, flags=re.I)
    return s


def maneuver_phrase(mtype: str, street: str) -> str:
    st = _clean_street(street)
    t = (mtype or "straight").lower()
    if t == "left":
        return f"Turn left onto {st}."
    if t == "right":
        return f"Turn right onto {st}."
    if t == "uturn":
        return f"Make a U-turn onto {st}."
    if t == "depart":
        return f"Head out on {st}."
    if t == "arrive":
        return "You have arrived."
    return f"Continue on {st}."


def _pick_female_voice(engine) -> tuple[str, str]:
    voices = engine.getProperty("voices") or []
    if not voices:
        return "", "System default"
    blob = lambda v: f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
    for hint in _FEMALE_HINTS:
        for v in voices:
            if hint in blob(v):
                name = getattr(v, "name", "") or getattr(v, "id", "Voice")
                return getattr(v, "id", ""), name.split(" - ")[0].strip()
    best = max(
        voices,
        key=lambda v: (
            50 if "female" in str(getattr(v, "gender", "")).lower() else 0,
            -50 if "david" in blob(v) or "mark" in blob(v) else 0,
        ),
    )
    name = getattr(best, "name", "") or getattr(best, "id", "Voice")
    return getattr(best, "id", ""), name.split(" - ")[0].strip()


class NavVoice:
    """Thread-safe offline speech queue (female Windows voice)."""

    def __init__(self):
        self._q: queue.Queue[str | None] = queue.Queue()
        self._enabled = True
        self._voice_name = "Starting…"
        self._ready = False
        self._thread = threading.Thread(target=self._worker, name="NavVoice", daemon=True)
        self._thread.start()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, on: bool):
        self._enabled = bool(on)
        if not on:
            self.flush()

    @property
    def mode(self) -> str:
        return VOICE_FEMALE

    @mode.setter
    def mode(self, _style: str):
        pass  # female only

    @property
    def voice_name(self) -> str:
        return self._voice_name

    @property
    def ready(self) -> bool:
        return self._ready

    def speak(self, text: str, *, interrupt: bool = False):
        if not self._enabled or not text or not _HAS_TTS:
            return
        if interrupt:
            self.flush()
        self._q.put(text.strip())

    def flush(self):
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def test_phrase(self) -> str:
        return "Navigation voice is on. Drive safely."

    def test(self):
        self.speak(self.test_phrase(), interrupt=True)

    def shutdown(self):
        self._q.put(None)

    def _worker(self):
        if not _HAS_TTS:
            return
        try:
            engine = pyttsx3.init("sapi5")
            vid, name = _pick_female_voice(engine)
            if vid:
                engine.setProperty("voice", vid)
            engine.setProperty("rate", 175)
            engine.setProperty("volume", 1.0)
            self._voice_name = name or "System"
            self._ready = True
        except Exception:
            self._voice_name = "Unavailable"
            return

        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                engine.stop()
                engine.say(text)
                engine.runAndWait()
            except Exception:
                pass


class DriveVoiceAnnouncer:
    """Decide *when* to speak during GPS navigation (deduped, distance-aware)."""

    def __init__(self, voice: NavVoice):
        self._voice = voice
        self._keys: set[str] = set()
        self._last_step = -1

    def reset(self):
        self._keys.clear()
        self._last_step = -1

    def navigation_started(self, site_id: str, street: str = ""):
        st = _clean_street(street) if street else ""
        extra = f" on {st}" if st and st != "the road" else ""
        self._voice.speak(f"Navigation started. Proceed to site {site_id}{extra}.", interrupt=True)
        self.reset()

    def reroute(self):
        self._voice.speak("Recalculating your route.", interrupt=True)
        self._keys.clear()

    def plan_ready(self):
        self._voice.speak("Turn-by-turn directions are ready.")

    def on_step(
        self,
        step: int,
        mtype: str,
        street: str,
        dist_ft: float,
        *,
        site_id: str | None = None,
    ):
        if not self._voice.enabled:
            return

        step_changed = step != self._last_step
        if step_changed:
            self._last_step = step
            self._keys = {k for k in self._keys if k.startswith(f"{step}:")}

        dist = max(0.0, float(dist_ft))
        tid = str(site_id) if site_id else ""

        if mtype == "arrive":
            if self._say_once(f"{step}:arrive", dist < 130):
                self._voice.speak(f"You have arrived at site {tid}.")
            elif self._say_once(f"{step}:approach", 350 < dist < 550):
                self._voice.speak(f"In about 400 feet, you will arrive at site {tid}.")
            return

        phrase = maneuver_phrase(mtype, street)
        short = phrase[:-1] if phrase.endswith(".") else phrase

        if step_changed:
            if self._say_once(f"{step}:now", True):
                if dist > 900:
                    self._voice.speak(phrase)
                elif dist > 180:
                    self._voice.speak(f"In {int(round(dist / 50.0) * 50)} feet, {short.lower()}.")
                else:
                    self._voice.speak(phrase)
            return

        for band in _DIST_BANDS:
            lo, hi = band - 55, band + 55
            if lo <= dist <= hi and self._say_once(f"{step}:d{band}", True):
                if band >= 400:
                    self._voice.speak(f"In {band} feet, {short.lower()}.")
                else:
                    self._voice.speak(phrase)
                break

    def _say_once(self, key: str, condition: bool) -> bool:
        if not condition or key in self._keys:
            return False
        self._keys.add(key)
        return True
