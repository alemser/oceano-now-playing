"""Fallback artwork providers for albums without usable artwork."""

import logging
import re
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


class CoverArtArchive:
    """Fetch artwork from Cover Art Archive via MusicBrainz lookup."""

    MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
    COVER_ART_ARCHIVE_API = "https://coverartarchive.org"
    USER_AGENT = "spi-now-playing/1.0 (https://github.com/alemser/spi-now-playing)"

    @staticmethod
    def _request_headers() -> dict:
        """Return standard headers for external artwork lookups."""
        return {"User-Agent": CoverArtArchive.USER_AGENT}

    @staticmethod
    def _album_query_candidates(album: str) -> list[str]:
        """Build normalized album title candidates for MusicBrainz lookup."""
        if not album:
            return []

        candidates = [album.strip()]
        stripped = album.strip()

        # Remove trailing edition/remaster qualifiers progressively.
        while True:
            updated = re.sub(r"\s*([\[(]).*?([\])])\s*$", "", stripped).strip()
            if updated == stripped:
                break
            stripped = updated
            if stripped:
                candidates.append(stripped)

        simplified = re.sub(
            r"\b(remaster(?:ed)?|deluxe|edition|expanded|anniversary|bonus track version)\b",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        simplified = re.sub(r"\s{2,}", " ", simplified).strip(" -")
        if simplified:
            candidates.append(simplified)

        unique_candidates = []
        seen = set()
        for candidate in candidates:
            lowered = candidate.lower()
            if candidate and lowered not in seen:
                seen.add(lowered)
                unique_candidates.append(candidate)
        return unique_candidates

    @staticmethod
    def _search_releases(artist: str, album: str, timeout: float = 3.0) -> list[dict]:
        """Search MusicBrainz for candidate releases given artist and album."""
        if not artist or not album:
            return []

        matches = []
        seen_release_ids = set()

        try:
            url = f"{CoverArtArchive.MUSICBRAINZ_API}/release"
            for candidate_album in CoverArtArchive._album_query_candidates(album):
                params = {
                    "query": f'artist:"{artist}" release:"{candidate_album}"',
                    "limit": 5,
                    "fmt": "json",
                }
                response = requests.get(
                    url,
                    params=params,
                    headers=CoverArtArchive._request_headers(),
                    timeout=timeout,
                )
                response.raise_for_status()

                data = response.json()
                releases = data.get("releases") or []
                for release in releases:
                    release_id = release.get("id")
                    if not release_id or release_id in seen_release_ids:
                        continue

                    seen_release_ids.add(release_id)
                    release_group = release.get("release-group") or {}
                    matches.append(
                        {
                            "release_id": release_id,
                            "release_group_id": release_group.get("id"),
                            "title": release.get("title", ""),
                        }
                    )

                if matches:
                    logger.info(
                        f"[CAA] MusicBrainz candidates for {artist} - {album}: {len(matches)}"
                    )
                    break

            return matches

        except requests.RequestException as e:
            logger.warning(f"[CAA] MusicBrainz search failed: {type(e).__name__}: {e}")
            return []
        except (KeyError, ValueError) as e:
            logger.warning(f"[CAA] Invalid MusicBrainz response: {e}")
            return []

    @staticmethod
    def _candidate_artwork_urls(candidate: dict) -> list[str]:
        """Build fallback artwork URLs for one MusicBrainz candidate."""
        urls = []
        release_id = candidate.get("release_id")
        release_group_id = candidate.get("release_group_id")

        if release_id:
            urls.append(f"{CoverArtArchive.COVER_ART_ARCHIVE_API}/release/{release_id}/front")
            urls.append(f"{CoverArtArchive.COVER_ART_ARCHIVE_API}/release/{release_id}/front-250.jpg")

        if release_group_id:
            urls.append(f"{CoverArtArchive.COVER_ART_ARCHIVE_API}/release-group/{release_group_id}/front")
            urls.append(f"{CoverArtArchive.COVER_ART_ARCHIVE_API}/release-group/{release_group_id}/front-250.jpg")

        return urls

    @staticmethod
    def fetch_artwork(artist: str, album: str, timeout: float = 3.0) -> Optional[Image.Image]:
        """Fetch album artwork image from Cover Art Archive."""
        candidates = CoverArtArchive._search_releases(artist, album, timeout=timeout)
        if not candidates:
            return None

        for candidate in candidates:
            for url in CoverArtArchive._candidate_artwork_urls(candidate):
                try:
                    response = requests.get(
                        url,
                        headers=CoverArtArchive._request_headers(),
                        timeout=timeout,
                    )
                    response.raise_for_status()
                    logger.info(f"[CAA] Artwork found via {url}")
                    return Image.open(BytesIO(response.content)).convert("RGB")
                except requests.HTTPError as e:
                    status_code = getattr(e.response, "status_code", None)
                    if status_code == 404:
                        logger.info(f"[CAA] Artwork not found at {url}")
                        continue
                    logger.warning(f"[CAA] Artwork fetch failed: {type(e).__name__}: {e}")
                except requests.RequestException as e:
                    logger.warning(f"[CAA] Artwork fetch failed: {type(e).__name__}: {e}")
                except Exception as e:
                    logger.warning(f"[CAA] Artwork decode failed: {type(e).__name__}: {e}")
                    return None

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
