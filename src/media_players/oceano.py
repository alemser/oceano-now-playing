import base64
import hashlib
import logging
import os
import re
import select
from io import BytesIO

from PIL import Image

from media_players.base import MediaPlayer

logger = logging.getLogger(__name__)
AIRPLAY_TRANSPORT_SAMPLERATE = "44.1 kHz"
AIRPLAY_TRANSPORT_BITDEPTH = "16 bit"
SOURCE_AIRPLAY = "AirPlay"
SOURCE_BLUETOOTH = "Bluetooth"
SOURCE_UPNP = "UPnP"

ITEM_PATTERN = re.compile(
    rb"<item>\s*<type>([0-9a-fA-F]{8})</type>\s*<code>([0-9a-fA-F]{8})</code>\s*<length>(\d+)</length>\s*(?:<data encoding=\"base64\">(.*?)</data>)?\s*</item>",
    re.DOTALL,
)


class OceanoClient(MediaPlayer):
    """Read AirPlay metadata from shairport-sync metadata pipe."""

    def __init__(
        self,
        metadata_pipe: str,
        external_artwork_enabled: bool = True,
    ) -> None:
        self.metadata_pipe = metadata_pipe
        self.external_artwork_enabled = external_artwork_enabled
        self.fd: int | None = None
        self._buffer = b""
        self._state = {
            "title": "Unknown",
            "artist": "Unknown",
            "album": "Unknown",
            "status": "stop",
            "seek": 0,
            "duration": 0,
            # AirPlay metadata typically exposes transport characteristics.
            "samplerate": AIRPLAY_TRANSPORT_SAMPLERATE,
            "bitdepth": AIRPLAY_TRANSPORT_BITDEPTH,
            "playback_source": SOURCE_AIRPLAY,
        }
        self._has_new_state = False

    def _clear_embedded_artwork_on_metadata_change(self, field: str, value: str) -> None:
        """Drop previous embedded artwork when incoming core metadata changes."""
        if (self._state.get(field) or "") == value:
            return
        self._state.pop("_resolved_artwork", None)

    def connect(self) -> bool:
        """Open shairport-sync metadata FIFO in non-blocking mode."""
        try:
            if not os.path.exists(self.metadata_pipe):
                logger.warning(
                    "Oceano metadata pipe not found: %s",
                    self.metadata_pipe,
                )
                return False
            self.fd = os.open(self.metadata_pipe, os.O_RDONLY | os.O_NONBLOCK)
            self._buffer = b""
            return True
        except Exception as e:
            logger.error("Error connecting to Oceano metadata pipe %s: %s", self.metadata_pipe, e)
            self.fd = None
            return False

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Read metadata events and return normalized playback state.

        Returns state keys compatible with the renderer/main loop contract:
        - title/artist/album (str)
        - status ("play" or "stop")
        - seek (milliseconds), duration (milliseconds)
        - optional _resolved_artwork payload with PIL image
        """
        if self.fd is None:
            return None

        try:
            rlist, _, _ = select.select([self.fd], [], [], timeout)
            if not rlist:
                return None

            chunk = os.read(self.fd, 65536)
            if not chunk:
                logger.debug("EOF on Oceano metadata pipe, closing descriptor")
                self.close()
                return None
            self._buffer += chunk

            parsed_any = False
            for item in self._extract_items():
                parsed_any = True
                self._apply_item(item)

            if parsed_any and self._has_new_state:
                self._has_new_state = False
                return self._state.copy()
        except Exception as e:
            logger.debug("Oceano metadata receive error: %s", e)

        return None

    def is_connected(self) -> bool:
        return self.fd is not None

    def close(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except Exception:
                pass
            self.fd = None

    def _extract_items(self) -> list[dict]:
        """Extract metadata items from XML-ish stream payload."""
        items: list[dict] = []

        last_end = 0
        for match in ITEM_PATTERN.finditer(self._buffer):
            last_end = match.end()
            type_hex = match.group(1).decode("ascii")
            code_hex = match.group(2).decode("ascii")
            data_b64 = match.group(4) or b""
            raw_data = b""
            if data_b64:
                try:
                    raw_data = base64.b64decode(data_b64)
                except Exception:
                    raw_data = b""
            items.append(
                {
                    "type": self._decode_tag(type_hex),
                    "code": self._decode_tag(code_hex),
                    "data": raw_data,
                }
            )

        if last_end > 0:
            self._buffer = self._buffer[last_end:]
        elif len(self._buffer) > 262144:
            # Prevent unbounded growth on malformed streams.
            self._buffer = self._buffer[-8192:]

        return items

    def _decode_tag(self, hex_tag: str) -> str:
        try:
            return bytes.fromhex(hex_tag).decode("ascii", errors="ignore")
        except Exception:
            return ""

    def _ticks_diff(self, start: int, end: int) -> int:
        """Return RTP tick delta, handling 32-bit wraparound."""
        if end >= start:
            return end - start
        return (1 << 32) - start + end

    def _classify_playback_source(self, hint: str) -> str | None:
        """Map backend hint text to normalized source labels."""
        normalized = hint.strip().lower()
        if not normalized:
            return None

        if "bluetooth" in normalized or "a2dp" in normalized:
            return SOURCE_BLUETOOTH

        if "upnp" in normalized or "dlna" in normalized:
            return SOURCE_UPNP

        if any(token in normalized for token in ("airplay", "raop", "shairport", "itunes", "iphone", "ios")):
            return SOURCE_AIRPLAY

        return None

    def _update_playback_source(self, hint: str) -> None:
        """Update playback source from metadata hint when identifiable."""
        source = self._classify_playback_source(hint)
        if source and source != self._state.get("playback_source"):
            self._state["playback_source"] = source
            self._has_new_state = True

    def _apply_item(self, item: dict) -> None:
        item_type = item.get("type", "")
        code = item.get("code", "")
        data = item.get("data", b"")

        if item_type == "core":
            value = data.decode("utf-8", errors="ignore").strip()
            if code == "minm" and value:
                self._clear_embedded_artwork_on_metadata_change("title", value)
                self._state["title"] = value
                self._has_new_state = True
            elif code == "asar" and value:
                self._clear_embedded_artwork_on_metadata_change("artist", value)
                self._state["artist"] = value
                self._has_new_state = True
            elif code == "asal" and value:
                self._clear_embedded_artwork_on_metadata_change("album", value)
                self._state["album"] = value
                self._has_new_state = True
            elif code in {"snua", "asai", "asar", "asal", "minm"} and value:
                self._update_playback_source(value)
            return

        if item_type != "ssnc":
            if item_type and data:
                hint = data.decode("utf-8", errors="ignore").strip()
                if hint:
                    self._update_playback_source(hint)
            return

        if code in {"snua", "stal", "styp", "snam", "acre", "daid"} and data:
            hint = data.decode("utf-8", errors="ignore").strip()
            if hint:
                self._update_playback_source(hint)

        if code == "pbeg":
            self._state["status"] = "play"
            self._state["seek"] = 0
            self._state["duration"] = 0
            self._has_new_state = True
            return

        if code == "prsm":
            self._state["status"] = "play"
            self._has_new_state = True
            return

        if code in {"pend", "pfls", "stop"}:
            self._state["status"] = "stop"
            self._has_new_state = True
            return

        if code == "prgr":
            value = data.decode("utf-8", errors="ignore").strip()
            # prgr is "start/current/end" RTP ticks at ~44.1kHz.
            # Renderer expects seek and duration in milliseconds.
            parts = re.findall(r"\d+", value)
            if len(parts) >= 3:
                start, current, end = (int(parts[0]), int(parts[1]), int(parts[2]))
                seek_ticks = self._ticks_diff(start, current)
                duration_ticks = self._ticks_diff(start, end)
                seek_ms = max(int(seek_ticks * 1000 // 44100), 0)
                duration_ms = max(int(duration_ticks * 1000 // 44100), 0)
                # When attaching mid-session we may see prgr before pbeg/prsm.
                # Mark playback active so the app can leave idle immediately.
                self._state["status"] = "play"
                self._state["seek"] = seek_ms
                self._state["duration"] = duration_ms
                self._has_new_state = True
            return

        if code == "PICT" and data:
            try:
                image = Image.open(BytesIO(data)).convert("RGB")
                digest = hashlib.sha1(data).hexdigest()[:16]
                self._state["_resolved_artwork"] = self._resolved_artwork(
                    cache_key=f"oceano:{digest}",
                    image=image,
                    source="oceano",
                )
                self._has_new_state = True
            except Exception as e:
                logger.debug("Could not decode AirPlay artwork: %s", e)

