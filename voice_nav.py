"""Offline turn-by-turn voice — Windows SAPI via pyttsx3 (no internet).

Modes:
  female — clear female guide (Zira, Jenny, Aria, …)
  vader  — deep helmet-style voice (pitch-shift + muffled filter, still offline)
"""
from __future__ import annotations

import os
import queue
import re
import tempfile
import threading
import wave

import numpy as np

_HAS_TTS = False
_TTS_ERR = ""

try:
    import pyttsx3
    _HAS_TTS = True
except Exception as exc:  # noqa: BLE001
    _TTS_ERR = str(exc)

VOICE_FEMALE = "female"
VOICE_VADER = "vader"
VOICE_STYLES = (VOICE_FEMALE, VOICE_VADER)

_FEMALE_HINTS = (
    "zira", "jenny", "aria", "susan", "hazel", "eva", "samantha",
    "female", "woman", "girl", "catherine", "linda", "heera",
)
_MALE_HINTS = (
    "david", "mark", "george", "james", "richard", "guy", "male", "daniel",
)

_DIST_BANDS = (800, 400, 150)


def tts_available() -> bool:
    return _HAS_TTS


def tts_error() -> str:
    return _TTS_ERR


def normalize_voice_style(style: str | None) -> str:
    s = str(style or VOICE_FEMALE).strip().lower()
    return s if s in VOICE_STYLES else VOICE_FEMALE


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


def _score_voice(v, hints: tuple[str, ...], *, prefer_female: bool | None) -> int:
    blob = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')}".lower()
    gender = str(getattr(v, "gender", "") or "").lower()
    s = 0
    if prefer_female is True and ("female" in gender or gender in ("f", "woman")):
        s += 50
    if prefer_female is False and ("male" in gender or gender in ("m", "man")):
        s += 50
    for i, hint in enumerate(hints):
        if hint in blob:
            s += 40 - i
    if "en" in blob or "english" in blob:
        s += 5
    if prefer_female is True and "male" in blob and "female" not in blob:
        s -= 30
    if prefer_female is False and "female" in blob:
        s -= 20
    return s


def _pick_voice(engine, hints: tuple[str, ...], *, prefer_female: bool | None) -> tuple[str, str]:
    voices = engine.getProperty("voices") or []
    if not voices:
        return "", "System default"
    best = max(voices, key=lambda v: _score_voice(v, hints, prefer_female=prefer_female))
    name = getattr(best, "name", "") or getattr(best, "id", "Voice")
    return getattr(best, "id", ""), name.split(" - ")[0].strip()


def _vaderify_wav(src: str, dst: str):
    """Pitch-down + muffled filter for helmet-style voice (offline, numpy only)."""
    with wave.open(src, "rb") as w:
        n_channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        raw = w.readframes(w.getnframes())

    if sampwidth != 2 or not raw:
        with open(src, "rb") as fin, open(dst, "wb") as fout:
            fout.write(fin.read())
        return

    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64)
    if n_channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1)

    pitch = 0.68
    new_len = max(1, int(len(samples) / pitch))
    pitched = np.interp(
        np.linspace(0, len(samples) - 1, new_len),
        np.arange(len(samples)),
        samples,
    )

    k = 9
    if len(pitched) > k:
        pitched = np.convolve(pitched, np.ones(k) / k, mode="same")

    peaked = float(np.max(np.abs(pitched))) or 1.0
    if peaked > 28000:
        pitched *= 28000 / peaked

    out = pitched.astype(np.int16)
    with wave.open(dst, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(framerate)
        w.writeframes(out.tobytes())


def _play_wav(path: str):
    import winsound
    winsound.PlaySound(path, winsound.SND_FILENAME)


class NavVoice:
    """Thread-safe offline speech queue with female or Vader style."""

    def __init__(self):
        self._q: queue.Queue[str | None] = queue.Queue()
        self._enabled = True
        self._mode = VOICE_FEMALE
        self._female_name = "Unavailable"
        self._vader_base = "Unavailable"
        self._voice_name = "Unavailable"
        self._ready = False
        self._lock = threading.Lock()
        self._tmp_dir = tempfile.mkdtemp(prefix="tds_voice_")
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
        return self._mode

    @mode.setter
    def mode(self, style: str):
        self._mode = normalize_voice_style(style)
        self._refresh_label()

    @property
    def voice_name(self) -> str:
        return self._voice_name

    @property
    def ready(self) -> bool:
        return self._ready

    def _refresh_label(self):
        if self._mode == VOICE_VADER:
            self._voice_name = f"Darth Vader (via {self._vader_base})"
        else:
            self._voice_name = self._female_name

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
        if self._mode == VOICE_VADER:
            return (
                "I find your lack of faith in this route disturbing. "
                "Navigation is online."
            )
        return "Navigation voice is on. Drive safely."

    def test(self):
        self.speak(self.test_phrase(), interrupt=True)

    def shutdown(self):
        self._q.put(None)
        try:
            import shutil
            shutil.rmtree(self._tmp_dir, ignore_errors=True)
        except Exception:
            pass

    def _configure_engine(self, engine, mode: str):
        if mode == VOICE_VADER:
            vid, name = _pick_voice(engine, _MALE_HINTS, prefer_female=False)
            if not vid:
                vid, name = _pick_voice(engine, _FEMALE_HINTS, prefer_female=True)
            self._vader_base = name or "System"
            engine.setProperty("rate", 148)
        else:
            vid, name = _pick_voice(engine, _FEMALE_HINTS, prefer_female=True)
            self._female_name = name or "System"
            engine.setProperty("rate", 172)
        if vid:
            engine.setProperty("voice", vid)
        engine.setProperty("volume", 0.98)

    def _speak_direct(self, engine, text: str):
        engine.stop()
        engine.say(text)
        engine.runAndWait()

    def _speak_vader(self, engine, text: str):
        raw = os.path.join(self._tmp_dir, "raw.wav")
        fx = os.path.join(self._tmp_dir, "vader.wav")
        engine.stop()
        engine.save_to_file(text, raw)
        engine.runAndWait()
        if not os.path.isfile(raw) or os.path.getsize(raw) < 44:
            self._speak_direct(engine, text)
            return
        _vaderify_wav(raw, fx)
        _play_wav(fx)

    def _worker(self):
        if not _HAS_TTS:
            return
        engine = None
        active_mode = None
        try:
            engine = pyttsx3.init("sapi5")
            self._configure_engine(engine, self._mode)
            self._refresh_label()
            active_mode = self._mode
            self._ready = True
        except Exception:
            self._voice_name = "Unavailable"
            return

        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                with self._lock:
                    if self._mode != active_mode:
                        self._configure_engine(engine, self._mode)
                        active_mode = self._mode
                        self._refresh_label()
                    if self._mode == VOICE_VADER:
                        self._speak_vader(engine, text)
                    else:
                        self._speak_direct(engine, text)
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
        if self._voice.mode == VOICE_VADER:
            msg = f"Navigation engaged. Proceed to site {site_id}{extra}, apprentice."
        else:
            msg = f"Navigation started. Proceed to site {site_id}{extra}."
        self._voice.speak(msg, interrupt=True)
        self.reset()

    def reroute(self):
        if self._voice.mode == VOICE_VADER:
            self._voice.speak("Recalculating your route. Do not fail me again.", interrupt=True)
        else:
            self._voice.speak("Recalculating your route.", interrupt=True)
        self._keys.clear()

    def plan_ready(self):
        if self._voice.mode == VOICE_VADER:
            self._voice.speak("Turn-by-turn directions are ready. Move out.")
        else:
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
                if self._voice.mode == VOICE_VADER:
                    self._voice.speak(f"You have arrived at site {tid}. Good.")
                else:
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
