"""StateFileClient — reads /tmp/oceano-state.json produced by oceano-state-manager.

Implements the same MediaPlayer interface as OceanoClient so the main loop
and renderer require no changes.

State file schema (written by oceano-state-manager):
{
  "source": "AirPlay | Physical | None",
  "state": "playing | stopped",
  "track": {
    "title": "...",
    "artist": "...",
    "album": "...",
    "duration_ms": 562000,
    "seek_ms": 12400,
    "seek_updated_at": "2026-03-29T20:30:00Z",
    "samplerate": "44.1 kHz",
    "bitdepth": "16 bit",
    "artwork_path": "/tmp/oceano-artwork-abc123.jpg"
  },
  "updated_at": "2026-03-29T20:30:05Z"
}

track is null when source is Physical (no metadata yet) or None.
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image

from media_players.base import MediaPlayer

logger = logging.getLogger(__name__)

POLL_INTERVAL = 0.5  # seconds between file stat checks


class StateFileClient(MediaPlayer):
    """Read unified playback state from oceano-state-manager output file."""

    def __init__(self, state_file: str) -> None:
        self.state_file = state_file

        self._last_mtime: float | None = None
        self._last_updated_at: str | None = None
        self._last_emitted: dict | None = None
        self._connected = False

    # ------------------------------------------------------------------ #
    # MediaPlayer interface                                                #
    # ------------------------------------------------------------------ #

    def connect(self) -> bool:
        if not os.path.exists(self.state_file):
            logger.warning("State file not found: %s", self.state_file)
            return False
        self._connected = True
        logger.info("StateFileClient connected to %s", self.state_file)
        return True

    def is_connected(self) -> bool:
        if self._connected and not os.path.exists(self.state_file):
            logger.warning("State file disappeared: %s", self.state_file)
            self._connected = False
        return self._connected

    def close(self) -> None:
        self._connected = False

    def get_state(self) -> None:
        # Force emit on next receive_message call by clearing last seen state.
        self._last_updated_at = None

    def receive_message(self, timeout: float = 0.5) -> dict | None:
        """Poll state file and return normalised state when it changes.

        Returns None when nothing has changed or the file is unreadable.
        Sleeps up to `timeout` seconds before returning to avoid busy-looping.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self._read_file()
            if raw is None:
                time.sleep(min(POLL_INTERVAL, deadline - time.monotonic()))
                continue

            updated_at = raw.get("updated_at")
            if updated_at == self._last_updated_at:
                time.sleep(min(POLL_INTERVAL, deadline - time.monotonic()))
                continue

            self._last_updated_at = updated_at
            state = self._normalise(raw)
            if state is not None:
                return state

        return None

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _read_file(self) -> dict | None:
        try:
            with open(self.state_file, "r") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("State file read error: %s", e)
            return None

    def _normalise(self, raw: dict) -> dict | None:
        """Convert oceano-state-manager schema to the renderer/main-loop contract.

        Output keys (must match what OceanoClient produced):
            title, artist, album       — track metadata strings
            status                     — "play" or "stop"
            seek                       — current position in milliseconds (interpolated)
            duration                   — track duration in milliseconds
            samplerate, bitdepth       — transport quality strings
            playback_source            — "AirPlay", "Physical", or ""
            _resolved_artwork          — resolved artwork dict or None
        """
        source = raw.get("source", "None")
        playing = raw.get("state") == "playing"
        track = raw.get("track")

        status = "play" if playing else "stop"

        if not playing or track is None:
            # For physical sources (vinyl/CD) the track may be null while recognition
            # is in progress. Use empty strings so the UI renders nothing rather than
            # showing "Unknown" placeholders.
            state = {
                "title": "",
                "artist": "",
                "album": "",
                "status": status,
                "seek": 0,
                "duration": 0,
                "samplerate": "",
                "bitdepth": "",
                "playback_source": source if source != "None" else "",
            }
            return state

        # Interpolate seek position from anchor timestamp.
        seek_ms = track.get("seek_ms", 0) or 0
        seek_updated_at = track.get("seek_updated_at")
        if seek_updated_at and status == "play":
            try:
                anchor = datetime.fromisoformat(seek_updated_at.replace("Z", "+00:00"))
                elapsed_ms = int((datetime.now(timezone.utc) - anchor).total_seconds() * 1000)
                seek_ms = max(seek_ms + elapsed_ms, 0)
            except ValueError:
                pass

        state = {
            "title": track.get("title") or "Unknown",
            "artist": track.get("artist") or "Unknown",
            "album": track.get("album") or "Unknown",
            "status": status,
            "seek": seek_ms,
            "duration": track.get("duration_ms", 0) or 0,
            "samplerate": track.get("samplerate") or "",
            "bitdepth": track.get("bitdepth") or "",
            "playback_source": source,
        }

        # Resolve artwork from file path provided by state manager.
        artwork_path = track.get("artwork_path")
        if artwork_path and os.path.exists(artwork_path):
            resolved = self._load_artwork(artwork_path)
            if resolved:
                state["_resolved_artwork"] = resolved

        return state

    def _load_artwork(self, path: str) -> dict | None:
        try:
            with open(path, "rb") as f:
                data = f.read()
            image = Image.open(BytesIO(data)).convert("RGB")
            digest = hashlib.sha1(data).hexdigest()[:16]
            return self._resolved_artwork(
                cache_key=f"statefile:{digest}",
                image=image,
                source="statefile",
            )
        except Exception as e:
            logger.debug("Failed to load artwork from %s: %s", path, e)
            return None
