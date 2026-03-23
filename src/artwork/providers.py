"""Fallback artwork providers for albums without usable artwork."""

import difflib
import logging
import re
import time
from io import BytesIO
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)


def _remaining_timeout(deadline: float | None, timeout: float) -> float | None:
    """Return remaining request timeout under a global lookup deadline."""
    if deadline is None:
        return timeout

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None
    return min(timeout, remaining)


def _normalize_text(value: str) -> str:
    """Normalize text for fuzzy matching across providers."""
    if not value:
        return ""

    normalized = value.lower().strip()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _artist_variants(artist: str) -> list[str]:
    """Generate common artist-name variants for matching."""
    base = _normalize_text(artist)
    if not base:
        return []

    variants = {base}
    variants.add(base.replace(" and ", " "))
    variants.add(base.replace(" the ", " "))

    cleaned = re.sub(r"\b(feat|featuring|ft)\b.*$", "", base).strip()
    if cleaned:
        variants.add(cleaned)

    return [variant for variant in variants if variant]


def _similarity(a: str, b: str) -> float:
    """Return fuzzy similarity ratio between two strings."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _best_artist_similarity(requested_artist: str, candidate_artist: str) -> float:
    """Return best artist similarity across common normalized variants."""
    requested_variants = _artist_variants(requested_artist)
    candidate_variants = _artist_variants(candidate_artist)

    best = 0.0
    for requested in requested_variants:
        for candidate in candidate_variants:
            best = max(best, _similarity(requested, candidate))
    return best


def _match_score(
    requested_artist: str,
    requested_album: str,
    candidate_artist: str,
    candidate_album: str,
) -> float:
    """Calculate weighted album/artist confidence score for a provider candidate."""
    requested_album_n = _normalize_text(requested_album)
    candidate_album_n = _normalize_text(candidate_album)

    album_score = _similarity(requested_album_n, candidate_album_n)
    artist_score = _best_artist_similarity(requested_artist, candidate_artist)

    # Album title should dominate ranking to avoid artist-level false positives.
    return (0.72 * album_score) + (0.28 * artist_score)


class CoverArtArchive:
    """Fetch artwork from Cover Art Archive via MusicBrainz lookup."""

    MUSICBRAINZ_API = "https://musicbrainz.org/ws/2"
    COVER_ART_ARCHIVE_API = "https://coverartarchive.org"
    USER_AGENT = "spi-now-playing/1.0 (https://github.com/alemser/spi-now-playing)"
    MIN_MATCH_SCORE = 0.66

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
    def _search_releases(
        artist: str,
        album: str,
        timeout: float = 3.0,
        deadline: float | None = None,
    ) -> list[dict]:
        """Search MusicBrainz for candidate releases given artist and album."""
        if not artist or not album:
            return []

        matches = []
        seen_release_ids = set()

        try:
            url = f"{CoverArtArchive.MUSICBRAINZ_API}/release"
            for candidate_index, candidate_album in enumerate(CoverArtArchive._album_query_candidates(album)):
                request_timeout = _remaining_timeout(deadline, timeout)
                if request_timeout is None:
                    break

                params = {
                    "query": f'artist:"{artist}" release:"{candidate_album}"',
                    "limit": 12,
                    "fmt": "json",
                }
                response = requests.get(
                    url,
                    params=params,
                    headers=CoverArtArchive._request_headers(),
                    timeout=request_timeout,
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
                    artist_credit = release.get("artist-credit") or []

                    artist_names = []
                    for entry in artist_credit:
                        artist_obj = entry.get("artist") if isinstance(entry, dict) else None
                        if isinstance(artist_obj, dict):
                            name = artist_obj.get("name")
                            if name:
                                artist_names.append(name)

                    release_title = release.get("title", "")
                    candidate_artist = " ".join(artist_names) if artist_names else artist
                    score_original = _match_score(
                        requested_artist=artist,
                        requested_album=album,
                        candidate_artist=candidate_artist,
                        candidate_album=release_title,
                    )
                    score_candidate = _match_score(
                        requested_artist=artist,
                        requested_album=candidate_album,
                        candidate_artist=candidate_artist,
                        candidate_album=release_title,
                    )
                    # Later fallback queries use simplified album candidates and should
                    # be slightly penalized to avoid overconfident wrong-edition matches.
                    candidate_penalty = 0.15 * candidate_index
                    score = max(score_original, score_candidate - candidate_penalty)

                    if score < CoverArtArchive.MIN_MATCH_SCORE:
                        continue

                    matches.append(
                        {
                            "release_id": release_id,
                            "release_group_id": release_group.get("id"),
                            "title": release_title,
                            "artist": candidate_artist,
                            "score": score,
                        }
                    )

            return sorted(matches, key=lambda item: item.get("score", 0.0), reverse=True)

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
    def fetch_artwork(
        artist: str,
        album: str,
        timeout: float = 3.0,
        deadline: float | None = None,
    ) -> Optional[Image.Image]:
        """Fetch album artwork image from Cover Art Archive."""
        candidates = CoverArtArchive._search_releases(
            artist,
            album,
            timeout=timeout,
            deadline=deadline,
        )
        if not candidates:
            return None

        for candidate in candidates:
            for url in CoverArtArchive._candidate_artwork_urls(candidate):
                try:
                    request_timeout = _remaining_timeout(deadline, timeout)
                    if request_timeout is None:
                        return None

                    response = requests.get(
                        url,
                        headers=CoverArtArchive._request_headers(),
                        timeout=request_timeout,
                    )
                    response.raise_for_status()
                    logger.info(
                        "[ART PROVIDER] CoverArtArchive selected score=%.3f artist='%s' album='%s' url=%s",
                        candidate.get("score", 0.0),
                        candidate.get("artist", ""),
                        candidate.get("title", ""),
                        url,
                    )
                    return Image.open(BytesIO(response.content)).convert("RGB")
                except requests.HTTPError as e:
                    status_code = getattr(e.response, "status_code", None)
                    if status_code == 404:
                        continue
                    logger.warning(f"[CAA] Artwork fetch failed: {type(e).__name__}: {e}")
                except requests.RequestException as e:
                    logger.warning(f"[CAA] Artwork fetch failed: {type(e).__name__}: {e}")
                except Exception as e:
                    logger.warning(f"[CAA] Artwork decode failed: {type(e).__name__}: {e}")
                    continue

        return None


class ITunesArtworkProvider:
    """Fallback artwork lookup via iTunes Search API."""

    SEARCH_API = "https://itunes.apple.com/search"
    MIN_MATCH_SCORE = 0.62

    @staticmethod
    def fetch_artwork(
        artist: str,
        album: str,
        timeout: float = 3.0,
        deadline: float | None = None,
    ) -> Optional[Image.Image]:
        """Fetch artwork from iTunes using album-level search and confidence scoring."""
        if not artist or not album:
            return None

        try:
            request_timeout = _remaining_timeout(deadline, timeout)
            if request_timeout is None:
                return None

            params = {
                "term": f"{artist} {album}",
                "entity": "album",
                "media": "music",
                "limit": 10,
            }
            response = requests.get(ITunesArtworkProvider.SEARCH_API, params=params, timeout=request_timeout)
            response.raise_for_status()
            results = response.json().get("results") or []

            ranked = []
            for item in results:
                candidate_album = item.get("collectionName", "")
                candidate_artist = item.get("artistName", "")
                score = _match_score(artist, album, candidate_artist, candidate_album)
                if score >= ITunesArtworkProvider.MIN_MATCH_SCORE:
                    ranked.append((score, item))

            if not ranked:
                return None

            ranked.sort(key=lambda row: row[0], reverse=True)
            best = ranked[0][1]
            best_score = ranked[0][0]

            artwork_url = best.get("artworkUrl100")
            if not artwork_url:
                return None

            # Request larger art where available.
            artwork_url = artwork_url.replace("100x100bb", "600x600bb")
            logger.info(
                "[ART PROVIDER] iTunes selected score=%.3f artist='%s' album='%s' url=%s",
                best_score,
                best.get("artistName", ""),
                best.get("collectionName", ""),
                artwork_url,
            )
            image_timeout = _remaining_timeout(deadline, timeout)
            if image_timeout is None:
                return None

            art_response = requests.get(artwork_url, timeout=image_timeout)
            art_response.raise_for_status()
            return Image.open(BytesIO(art_response.content)).convert("RGB")
        except requests.RequestException as e:
            logger.warning(f"[ITUNES] Artwork fetch failed: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[ITUNES] Artwork decode failed: {type(e).__name__}: {e}")
            return None


class DeezerArtworkProvider:
    """Fallback artwork lookup via Deezer album search API."""

    SEARCH_API = "https://api.deezer.com/search/album"
    MIN_MATCH_SCORE = 0.62

    @staticmethod
    def fetch_artwork(
        artist: str,
        album: str,
        timeout: float = 3.0,
        deadline: float | None = None,
    ) -> Optional[Image.Image]:
        """Fetch artwork from Deezer using album search and confidence scoring."""
        if not artist or not album:
            return None

        try:
            request_timeout = _remaining_timeout(deadline, timeout)
            if request_timeout is None:
                return None

            params = {
                "q": f'artist:"{artist}" album:"{album}"',
                "limit": 10,
            }
            response = requests.get(DeezerArtworkProvider.SEARCH_API, params=params, timeout=request_timeout)
            response.raise_for_status()
            results = response.json().get("data") or []

            ranked = []
            for item in results:
                candidate_album = item.get("title", "")
                candidate_artist = (item.get("artist") or {}).get("name", "")
                score = _match_score(artist, album, candidate_artist, candidate_album)
                if score >= DeezerArtworkProvider.MIN_MATCH_SCORE:
                    ranked.append((score, item))

            if not ranked:
                return None

            ranked.sort(key=lambda row: row[0], reverse=True)
            best = ranked[0][1]
            best_score = ranked[0][0]

            artwork_url = best.get("cover_xl") or best.get("cover_big") or best.get("cover")
            if not artwork_url:
                return None

            logger.info(
                "[ART PROVIDER] Deezer selected score=%.3f artist='%s' album='%s' url=%s",
                best_score,
                (best.get("artist") or {}).get("name", ""),
                best.get("title", ""),
                artwork_url,
            )
            image_timeout = _remaining_timeout(deadline, timeout)
            if image_timeout is None:
                return None

            art_response = requests.get(artwork_url, timeout=image_timeout)
            art_response.raise_for_status()
            return Image.open(BytesIO(art_response.content)).convert("RGB")
        except requests.RequestException as e:
            logger.warning(f"[DEEZER] Artwork fetch failed: {type(e).__name__}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[DEEZER] Artwork decode failed: {type(e).__name__}: {e}")
            return None


class ArtworkLookup:
    """Cached fallback lookup for artwork providers."""

    _cache = {}
    MAX_CACHE_SIZE = 50
    PROVIDERS = (
        CoverArtArchive,
        ITunesArtworkProvider,
        DeezerArtworkProvider,
    )

    @classmethod
    def get_artwork(cls, artist: str, album: str, timeout: float = 3.0) -> Optional[Image.Image]:
        """Get fallback artwork from providers with simple in-memory cache."""
        key = f"{artist}|{album}"
        if key in cls._cache:
            return cls._cache[key]

        if len(cls._cache) > cls.MAX_CACHE_SIZE:
            cls._cache.clear()

        deadline = time.monotonic() + max(timeout, 0.0)
        art = None
        for provider in cls.PROVIDERS:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning(
                    "[ART FALLBACK] Resolve budget exhausted for artist='%s' album='%s'",
                    artist,
                    album,
                )
                break

            art = provider.fetch_artwork(
                artist,
                album,
                timeout=remaining,
                deadline=deadline,
            )
            if art is not None:
                logger.info(
                    "[ART FALLBACK] Selected provider=%s for artist='%s' album='%s'",
                    provider.__name__,
                    artist,
                    album,
                )
                break

            logger.debug(
                "[ART FALLBACK] Provider %s had no match for artist='%s' album='%s'",
                provider.__name__,
                artist,
                album,
            )

        cls._cache[key] = art
        return art

    @classmethod
    def clear_cache(cls) -> None:
        """Clear internal fallback artwork cache."""
        cls._cache.clear()
