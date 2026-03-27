from .base import MediaPlayer
import json
import time
from typing import Optional


class OceanoAnalogClient(MediaPlayer):
    """
    Media player client for analog sources (Vinyl, CD, Standby) via oceano-source.json.
    """

    def close(self) -> None:
        """No resources to clean up for analog client."""
        pass

    def __init__(self, source_file: str = "/tmp/oceano-source.json"):
        self.source_file = source_file
        self.last_state = None
        self.last_update = 0.0
        self.poll_interval = 1.0  # seconds

    def connect(self) -> bool:
        """No-op for analog source. Always 'connected'."""
        return True

    def is_connected(self) -> bool:
        return True

    def receive_message(self, timeout: float = 1.0) -> Optional[dict]:
        """Polls the source file for updates and returns state dict if changed."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                with open(self.source_file, "r") as f:
                    data = json.load(f)
                updated_at = data.get("updated_at")
                if updated_at != self.last_update:
                    self.last_update = updated_at
                    state = self._parse_state(data)
                    self.last_state = state
                    return state
            except (FileNotFoundError, json.JSONDecodeError):
                pass
            time.sleep(self.poll_interval)
        return None

    def _parse_state(self, data: dict) -> dict:
        """Converts oceano-source.json to player state dict."""
        source = data.get("source")
        if source == "Vinyl":
            quality = "Vinyl"
            status = "play"
        elif source == "CD":
            quality = "CD"
            status = "play"
        elif not source or source == "Standby":
            # None, missing, or Standby: idle
            quality = "Standby"
            status = "stop"
        else:
            quality = str(source)
            status = "stop"
        return {
            "title": "Analog source" if status == "play" else "",
            "artist": "",
            "album": "",
            "quality": quality,
            "samplerate": 44100 if source == "CD" else None,
            "status": status,
        }
