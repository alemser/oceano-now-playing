import json
import logging
import time
import os
import hashlib
from io import BytesIO
from urllib.parse import urlparse

import requests
from PIL import Image
from websocket import create_connection

from artwork_providers import ArtworkLookup
from media_player import MediaPlayer

logger = logging.getLogger(__name__)

VOLUMIO_PLACEHOLDER_SHA256_HASHES = {
    "d38e8d8533672451d5a3572c0c8c7d4e89218277116bc24afe33af545597ec85",
}
VOLUMIO_DEFAULT_PLACEHOLDER_PATH = "/volumio/app/plugins/miscellanea/albumart/default.png"

class VolumioClient(MediaPlayer):
    def __init__(self, url: str) -> None:
        self.url = url
        self.ws = None
        parsed = urlparse(url)
        self.host = parsed.hostname or "localhost"
        self.placeholder_dhash = os.getenv("VOLUMIO_PLACEHOLDER_DHASH", "").lower()
        if not self.placeholder_dhash:
            self.placeholder_dhash = self._load_default_placeholder_dhash()

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
            
            # Socket.io heartbeat
            if result == '2':
                self.ws.send('3')
                return None
                
            # Check if it's a state message (pushState or getState response)
            if '"pushState"' in result:
                start = result.find('{')
                end = result.rfind('}')
                if start != -1 and end != -1:
                    json_str = result[start:end+1]
                    return json.loads(json_str)
        except (TimeoutError, Exception):
            # Timeouts are expected if Volumio doesn't send anything
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

    def _compute_dhash(self, image: Image.Image, hash_size: int = 8) -> str:
        """Compute a simple difference hash for perceptual matching."""
        gray = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
        bits = []
        for y in range(hash_size):
            for x in range(hash_size):
                left = gray.getpixel((x, y))
                right = gray.getpixel((x + 1, y))
                bits.append("1" if right > left else "0")
        return f"{int(''.join(bits), 2):0{hash_size * hash_size // 4}x}"

    def _load_default_placeholder_dhash(self) -> str:
        """Load dHash from Volumio's bundled default artwork when available."""
        try:
            if not os.path.exists(VOLUMIO_DEFAULT_PLACEHOLDER_PATH):
                return ""
            with open(VOLUMIO_DEFAULT_PLACEHOLDER_PATH, "rb") as f:
                default_img = Image.open(BytesIO(f.read())).convert("RGB")
            dhash = self._compute_dhash(default_img)
            return dhash
        except Exception as e:
            logger.debug(f"[ART PLACEHOLDER] Could not load default placeholder dHash: {e}")
            return ""

    def _hamming_distance(self, hex_a: str, hex_b: str) -> int:
        """Compute Hamming distance between two equal-length hex strings."""
        if len(hex_a) != len(hex_b):
            return 999
        return (int(hex_a, 16) ^ int(hex_b, 16)).bit_count()

    def _is_placeholder_image(self, image_bytes: bytes, image: Image.Image) -> tuple[bool, str, str]:
        """Detect Volumio's default placeholder artwork."""
        sha256 = hashlib.sha256(image_bytes).hexdigest()
        if sha256 in VOLUMIO_PLACEHOLDER_SHA256_HASHES:
            return True, "exact-sha256-match", sha256

        if self.placeholder_dhash:
            fetched_dhash = self._compute_dhash(image)
            distance = self._hamming_distance(fetched_dhash, self.placeholder_dhash)
            if distance <= 6:
                return True, f"perceptual-dhash-match(distance={distance})", sha256

        return False, "no-match", sha256

    def resolve_artwork(self, state: dict, timeout: float = 3.0) -> dict | None:
        """Resolve Volumio artwork, replacing placeholders with fallback art."""
        art_url = state.get("albumart", "")
        if not art_url:
            return None

        artist = state.get("artist", "")
        album = state.get("album", "")
        full_url = self._build_artwork_url(art_url)

        try:
            response = requests.get(full_url, timeout=timeout)
            response.raise_for_status()

            art_bytes = response.content
            art_image = Image.open(BytesIO(art_bytes)).convert("RGB")

            is_placeholder, reason, sha256 = self._is_placeholder_image(art_bytes, art_image)
            if is_placeholder:
                logger.warning(
                    f"[ART PLACEHOLDER] Detected Volumio default artwork ({reason}) sha256={sha256}"
                )
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

            return {
                "cache_key": art_url,
                "image": art_image,
                "source": "volumio",
            }
        except requests.RequestException as e:
            logger.warning(f"[ART ERROR] Failed to load artwork from {art_url}: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[ART ERROR] Failed to decode artwork from {art_url}: {type(e).__name__}: {e}")
            return None
