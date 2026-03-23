import json
import logging
import time
import hashlib
from io import BytesIO
from urllib.parse import urlparse

import requests
from PIL import Image
from websocket import create_connection

from artwork.providers import ArtworkLookup
from media_players.base import MediaPlayer

logger = logging.getLogger(__name__)

VOLUMIO_PLACEHOLDER_SHA256_HASHES = {
    "c9c0eb5de9ba0d540f0784f2de757a18ef095005032e97fd559ce74430167db1",
    "d38e8d8533672451d5a3572c0c8c7d4e89218277116bc24afe33af545597ec85",
}
ARTWORK_PLACEHOLDER_RETRY_DELAY_SECONDS = 0.7


class VolumioClient(MediaPlayer):
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws = None
        parsed = urlparse(url)
        self.host = parsed.hostname or "localhost"

    def connect(self) -> bool:
        """Connects to Volumio's WebSocket.

        Returns:
            True if connection was successful, False otherwise.
        """
        try:
            self.ws = create_connection(self.url, timeout=10)
            self.ws.send('42["getState"]')
            return True
        except Exception as e:
            logger.error(f"Error connecting to Volumio at {self.url}: {e}")
            return False

    def get_state(self) -> None:
        """Requests the current state explicitly."""
        if self.ws:
            try:
                self.ws.send('42["getState"]')
            except Exception as e:
                logger.error(f"Error requesting state from Volumio: {e}")
                self.ws = None

    def receive_message(self, timeout: float = 1.0) -> dict | None:
        """Receives and processes WebSocket messages.

        Args:
            timeout: Maximum seconds to wait for a message.

        Returns:
            A state dictionary when a new playback state is available,
            or None if no message arrived within the timeout.
        """
        if not self.ws:
            return None

        try:
            self.ws.settimeout(timeout)
            result = self.ws.recv()

            if result == '2':
                self.ws.send('3')
                return None

            if '"pushState"' in result:
                start = result.find('{')
                end = result.rfind('}')
                if start != -1 and end != -1:
                    json_str = result[start:end + 1]
                    return json.loads(json_str)
        except (TimeoutError, Exception):
            pass
        return None

    def is_connected(self) -> bool:
        """Checks if the connection is active.

        Returns:
            True if the connection is active, False otherwise.
        """
        return self.ws is not None

    def close(self) -> None:
        """Closes the connection."""
        if self.ws:
            self.ws.close()
            self.ws = None

    def _build_artwork_url(self, art_url: str) -> str:
        """Build a full artwork URL from a Volumio albumart path."""
        if art_url.startswith('/'):
            url = f"http://{self.host}:3000{art_url}"
            if "?" in url:
                return f"{url}&t={int(time.time())}"
            return f"{url}?t={int(time.time())}"
        return art_url

    def _is_placeholder_image(self, image_bytes: bytes, image: Image.Image) -> tuple[bool, str, str]:
        """Detect Volumio's default placeholder artwork."""
        sha256 = hashlib.sha256(image_bytes).hexdigest()
        if sha256 in VOLUMIO_PLACEHOLDER_SHA256_HASHES:
            return True, "exact-sha256-match", sha256

        return False, "no-match", sha256

    def resolve_artwork(self, state: dict, timeout: float = 3.0) -> dict | None:
        """Resolve Volumio artwork, replacing placeholders with fallback art."""
        art_url = state.get("albumart", "")
        if not art_url:
            return None

        artist = state.get("artist", "")
        album = state.get("album", "")
        for attempt in (1, 2):
            full_url = self._build_artwork_url(art_url)
            try:
                response = requests.get(full_url, timeout=timeout)
                response.raise_for_status()

                art_bytes = response.content
                art_image = Image.open(BytesIO(art_bytes)).convert("RGB")

                is_placeholder, reason, sha256 = self._is_placeholder_image(art_bytes, art_image)
                if not is_placeholder:
                    if attempt > 1:
                        logger.info(f"[ART RETRY] Volumio artwork recovered after placeholder for {artist} - {album}")
                    return {
                        "cache_key": art_url,
                        "image": art_image,
                        "source": "volumio",
                    }

                logger.warning(
                    f"[ART PLACEHOLDER] Detected Volumio default artwork ({reason}) sha256={sha256}"
                )
                if attempt == 1:
                    time.sleep(ARTWORK_PLACEHOLDER_RETRY_DELAY_SECONDS)
                    continue

                fallback_art = ArtworkLookup.get_artwork(artist, album, timeout=timeout)
                if fallback_art:
                    logger.info(f"[ART FALLBACK] Using Cover Art Archive for {artist} - {album}")
                    return {
                        "cache_key": f"fallback:{artist}|{album}",
                        "image": fallback_art,
                        "source": "fallback",
                    }

                logger.warning(f"[ART FALLBACK] No fallback artwork for {artist} - {album}")
                return None
            except requests.RequestException as e:
                logger.warning(f"[ART ERROR] Failed to load artwork from {art_url}: {type(e).__name__}: {e}")
                return None
            except Exception as e:
                logger.warning(f"[ART ERROR] Failed to decode artwork from {art_url}: {type(e).__name__}: {e}")
                return None

        return None
