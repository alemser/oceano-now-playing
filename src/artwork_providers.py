"""Fallback artwork providers for albums without usable artwork."""

import logging
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


class CoverArtArchive:
    """Fetch artwork from Cover Art Archive via MusicBrainz lookup."""

    MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
    COVER_ART_ARCHIVE_API = "https://coverartarchive.org"

    @staticmethod
    def _search_release(artist: str, album: str, timeout: float = 3.0) -> Optional[str]:
        """Search MusicBrainz for release MBID given artist and album."""
        if not artist or not album:
            return None

        try:
            url = f"{CoverArtArchive.MUSICBRAINZ_API}/release"
            params = {
                "query": f'artist:"{artist}" release:"{album}"',
                "limit": 1,
                "fmt": "json",
            }
            headers = {
                "User-Agent": (
                    "spi-now-playing/1.0 "
                    "(https://github.com/alemser/spi-now-playing)"
                )
            }

            response = requests.get(url, params=params, headers=headers, timeout=timeout)
            response.raise_for_status()

            data = response.json()
            releases = data.get("releases") or []
            if releases:
                return releases[0].get("id")
            return None

        except requests.RequestException as e:
            logger.warning(f"[CAA] MusicBrainz search failed: {type(e).__name__}: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.warning(f"[CAA] Invalid MusicBrainz response: {e}")
            return None

    @staticmethod
    def fetch_artwork(artist: str, album: str, timeout: float = 3.0) -> Optional[Image.Image]:
        """Fetch album artwork image from Cover Art Archive."""
        mbid = CoverArtArchive._search_release(artist, album, timeout=timeout)
        if not mbid:
            return None

        try:
            url = f"{CoverArtArchive.COVER_ART_ARCHIVE_API}/release/{mbid}/front-250.jpg"
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")

        except requests.RequestException as e:
            logger.warning(f"[CAA] Artwork fetch failed: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[CAA] Artwork decode failed: {type(e).__name__}: {e}")
            return None


class ArtworkLookup:
    """Cached fallback lookup for artwork providers."""

    _cache = {}
    MAX_CACHE_SIZE = 50

    @classmethod
    def get_artwork(cls, artist: str, album: str, timeout: float = 3.0) -> Optional[Image.Image]:
        """Get fallback artwork from providers with simple in-memory cache."""
        key = f"{artist}|{album}"
        if key in cls._cache:
            return cls._cache[key]

        if len(cls._cache) > cls.MAX_CACHE_SIZE:
            cls._cache.clear()

        art = CoverArtArchive.fetch_artwork(artist, album, timeout=timeout)
        cls._cache[key] = art
        return art

    @classmethod
    def clear_cache(cls) -> None:
        """Clear internal fallback artwork cache."""
        cls._cache.clear()
