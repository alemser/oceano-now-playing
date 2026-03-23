"""Tests for fallback artwork providers."""

import io
import os
import sys
from unittest.mock import MagicMock, patch

import requests
from PIL import Image

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from artwork.providers import ArtworkLookup, CoverArtArchive


def _fake_image_bytes(color=(255, 0, 0)):
    """Build in-memory JPEG bytes for artwork tests."""
    image = Image.new('RGB', (10, 10), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format='JPEG')
    return buffer.getvalue()


class TestCoverArtArchive:
    """Test Cover Art Archive integration."""

    def test_album_query_candidates_strip_remaster_suffix(self):
        """Album candidates should include a normalized title without remaster suffix."""
        candidates = CoverArtArchive._album_query_candidates('Exodus (2013 Remaster)')

        assert candidates[0] == 'Exodus (2013 Remaster)'
        assert 'Exodus' in candidates

    @patch('artwork.providers.requests.get')
    def test_search_releases_uses_normalized_album_candidate(self, mock_get):
        """MusicBrainz lookup should retry with normalized album title."""
        first_response = MagicMock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {'releases': []}

        second_response = MagicMock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            'releases': [
                {
                    'id': 'release-123',
                    'title': 'Exodus',
                    'release-group': {'id': 'group-456'},
                }
            ]
        }

        mock_get.side_effect = [first_response, second_response]

        results = CoverArtArchive._search_releases('Bob Marley & The Wailers', 'Exodus (2013 Remaster)')

        assert len(results) == 1
        first_query = mock_get.call_args_list[0].kwargs['params']['query']
        second_query = mock_get.call_args_list[1].kwargs['params']['query']
        assert 'release:"Exodus (2013 Remaster)"' in first_query
        assert 'release:"Exodus"' in second_query

    @patch('artwork.providers.requests.get')
    def test_fetch_artwork_falls_back_to_release_group_front(self, mock_get):
        """Artwork fetch should try release-group front URL if release URLs 404."""
        search_response = MagicMock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            'releases': [
                {
                    'id': 'release-123',
                    'title': 'Exodus',
                    'release-group': {'id': 'group-456'},
                }
            ]
        }

        not_found_response = MagicMock(status_code=404)
        not_found_error = requests.HTTPError('404 not found', response=not_found_response)

        release_front_response = MagicMock()
        release_front_response.raise_for_status.side_effect = not_found_error

        release_front_250_response = MagicMock()
        release_front_250_response.raise_for_status.side_effect = not_found_error

        group_front_response = MagicMock()
        group_front_response.raise_for_status.return_value = None
        group_front_response.content = _fake_image_bytes()

        mock_get.side_effect = [
            search_response,
            release_front_response,
            release_front_250_response,
            group_front_response,
        ]

        image = CoverArtArchive.fetch_artwork('Bob Marley & The Wailers', 'Exodus (2013 Remaster)')

        assert image is not None
        assert image.size == (10, 10)
        requested_urls = [call.args[0] for call in mock_get.call_args_list]
        assert 'https://coverartarchive.org/release/release-123/front' in requested_urls
        assert 'https://coverartarchive.org/release-group/group-456/front' in requested_urls

    @patch('artwork.providers.requests.get')
    def test_fetch_artwork_returns_none_when_all_candidates_fail(self, mock_get):
        """Artwork fetch should return None if all Cover Art Archive URLs fail."""
        search_response = MagicMock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            'releases': [
                {
                    'id': 'release-123',
                    'title': 'Exodus',
                    'release-group': {'id': 'group-456'},
                }
            ]
        }

        not_found_response = MagicMock(status_code=404)
        not_found_error = requests.HTTPError('404 not found', response=not_found_response)

        failed_response = MagicMock()
        failed_response.raise_for_status.side_effect = not_found_error

        mock_get.side_effect = [
            search_response,
            failed_response,
            failed_response,
            failed_response,
            failed_response,
        ]

        image = CoverArtArchive.fetch_artwork('Bob Marley & The Wailers', 'Exodus (2013 Remaster)')

        assert image is None

    @patch('artwork.providers.Image.open')
    @patch('artwork.providers.requests.get')
    def test_fetch_artwork_decode_error_continues_to_next_candidate(self, mock_get, mock_image_open):
        """Decode errors should continue trying candidate URLs instead of aborting."""
        search_response = MagicMock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            'releases': [
                {
                    'id': 'release-123',
                    'title': 'Exodus',
                    'release-group': {'id': 'group-456'},
                }
            ]
        }

        image_response_1 = MagicMock()
        image_response_1.raise_for_status.return_value = None
        image_response_1.content = b'bad-image'

        image_response_2 = MagicMock()
        image_response_2.raise_for_status.return_value = None
        image_response_2.content = _fake_image_bytes(color=(10, 20, 30))

        mock_get.side_effect = [
            search_response,
            image_response_1,
            image_response_2,
        ]

        decode_error = OSError('cannot identify image file')
        decoded_image = Image.new('RGB', (10, 10), color=(10, 20, 30))
        mock_image_open.side_effect = [decode_error, decoded_image]

        image = CoverArtArchive.fetch_artwork('Bob Marley & The Wailers', 'Exodus (2013 Remaster)')

        assert image is not None
        assert image.size == (10, 10)
        assert mock_image_open.call_count == 2

    def test_fetch_artwork_missing_artist_album(self):
        """Missing artist or album should return None."""
        assert CoverArtArchive.fetch_artwork('', 'Album') is None
        assert CoverArtArchive.fetch_artwork('Artist', '') is None
        assert CoverArtArchive.fetch_artwork('', '') is None


class TestArtworkLookup:
    """Test ArtworkLookup caching and fallback logic."""

    def setup_method(self):
        """Clear cache before each test."""
        ArtworkLookup.clear_cache()

    @patch('artwork.providers.CoverArtArchive.fetch_artwork')
    def test_get_artwork_success(self, mock_fetch):
        """Get artwork for album with fallback source."""
        test_image = Image.new('RGB', (250, 250), color='blue')
        mock_fetch.return_value = test_image

        art = ArtworkLookup.get_artwork('Bob Marley', 'Exodus')

        assert art is not None
        assert isinstance(art, Image.Image)

    @patch('artwork.providers.CoverArtArchive.fetch_artwork')
    def test_get_artwork_caching(self, mock_fetch):
        """Artwork lookup caches results."""
        test_image = Image.new('RGB', (250, 250), color='green')
        mock_fetch.return_value = test_image

        art1 = ArtworkLookup.get_artwork('Bob Marley', 'Exodus', timeout=3.0)
        call_count_1 = mock_fetch.call_count

        art2 = ArtworkLookup.get_artwork('Bob Marley', 'Exodus', timeout=3.0)
        call_count_2 = mock_fetch.call_count

        assert call_count_1 == 1
        assert call_count_2 == 1
        assert art1 is art2

    @patch('artwork.providers.CoverArtArchive.fetch_artwork')
    def test_get_artwork_not_found_caching(self, mock_fetch):
        """Cache negative results to avoid repeated lookups."""
        mock_fetch.return_value = None

        art1 = ArtworkLookup.get_artwork('Unknown', 'Album', timeout=3.0)
        call_count_1 = mock_fetch.call_count

        art2 = ArtworkLookup.get_artwork('Unknown', 'Album', timeout=3.0)
        call_count_2 = mock_fetch.call_count

        assert art1 is None
        assert art2 is None
        assert call_count_1 == 1
        assert call_count_2 == 1

    def test_clear_cache(self):
        """Clear cache method works."""
        test_image = Image.new('RGB', (100, 100), color='yellow')
        ArtworkLookup._cache['test|key'] = test_image
        assert len(ArtworkLookup._cache) > 0

        ArtworkLookup.clear_cache()
        assert len(ArtworkLookup._cache) == 0

    @patch('artwork.providers.CoverArtArchive.fetch_artwork')
    def test_cache_overflow(self, mock_fetch):
        """Cache limit prevents unbounded memory growth."""
        original_size = ArtworkLookup.MAX_CACHE_SIZE
        ArtworkLookup.MAX_CACHE_SIZE = 5

        test_image = Image.new('RGB', (100, 100), color='red')
        mock_fetch.return_value = test_image

        for i in range(10):
            ArtworkLookup.get_artwork(f'Artist{i}', f'Album{i}', timeout=3.0)

        assert len(ArtworkLookup._cache) < 10

        ArtworkLookup.MAX_CACHE_SIZE = original_size
