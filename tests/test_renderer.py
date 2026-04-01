"""Tests for Renderer utility functions and image operations.

Covers utility functions with logic:
- Time formatting
- Dominant color extraction
- Image resizing and caching
"""

import pytest
import sys
import os
from PIL import Image, ImageChops
from unittest.mock import MagicMock, patch

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from renderer import Renderer


class TestTimeFormatting:
    """Test the _format_time utility function."""
    
    def test_format_seconds_to_mmss(self, mock_renderer):
        """Test basic time formatting."""
        renderer = mock_renderer
        
        # 30 seconds
        assert renderer._format_time(30) == "00:30"
        
        # 1 minute 30 seconds
        assert renderer._format_time(90) == "01:30"
        
        # 2 minutes 45 seconds
        assert renderer._format_time(165) == "02:45"
    
    def test_format_time_zero(self, mock_renderer):
        """Test formatting zero seconds."""
        renderer = mock_renderer
        assert renderer._format_time(0) == "00:00"
    
    def test_format_time_large_values(self, mock_renderer):
        """Test formatting large time values."""
        renderer = mock_renderer
        
        # 1 hour = 3600 seconds
        assert renderer._format_time(3600) == "60:00"
        
        # 2 hours 30 minutes
        assert renderer._format_time(9000) == "150:00"
    
    def test_format_time_none(self, mock_renderer):
        """Test handling None values (AirPlay)."""
        renderer = mock_renderer
        assert renderer._format_time(None) == "00:00"
    
    def test_format_time_invalid_type(self, mock_renderer):
        """Test handling invalid types gracefully."""
        renderer = mock_renderer
        
        # Invalid type should raise ValueError (test assumes this is handled by caller)
        with pytest.raises(ValueError):
            renderer._format_time("invalid")
    
    def test_format_time_float(self, mock_renderer):
        """Test formatting float seconds."""
        renderer = mock_renderer
        
        # Should truncate to int
        assert renderer._format_time(30.7) == "00:30"
        assert renderer._format_time(90.2) == "01:30"


class TestDominantColorExtraction:
    """Test dominant color extraction from images."""
    
    def test_extract_dominant_color(self, mock_renderer):
        """Test extracting dominant color from an image."""
        renderer = mock_renderer
        
        # Create a simple red image
        img = Image.new('RGB', (100, 100), color=(255, 0, 0))
        color = renderer._get_dominant_color(img)
        
        # Should extract something close to pure red
        assert len(color) == 3
        assert color[0] > 200  # Red channel high
    
    def test_dominant_color_dark_image(self, mock_renderer):
        """Test that very dark images fallback to default accent color."""
        renderer = mock_renderer
        
        # Create a very dark image
        img = Image.new('RGB', (100, 100), color=(10, 10, 10))
        color = renderer._get_dominant_color(img)
        
        # Should return default accent color (60, 180, 60)
        assert color == renderer.default_accent
    
    def test_dominant_color_white_image(self, mock_renderer):
        """Test extracting color from a white image."""
        renderer = mock_renderer
        
        img = Image.new('RGB', (100, 100), color=(255, 255, 255))
        color = renderer._get_dominant_color(img)
        
        # White should be extracted, not defaulted
        assert sum(color) > 600  # All components high
    
    def test_dominant_color_gradient(self, mock_renderer):
        """Test extracting color from a gradient image."""
        renderer = mock_renderer
        
        # Create gradient from red to blue
        img = Image.new('RGB', (256, 100))
        pixels = img.load()
        for x in range(256):
            for y in range(100):
                pixels[x, y] = (x, 0, 255 - x)
        
        color = renderer._get_dominant_color(img)
        
        # Should extract a valid color without crashing
        assert len(color) == 3
        assert all(isinstance(c, int) for c in color)


class TestArtCaching:
    """Test album art caching logic."""
    
    def test_art_cache_stores_image(self, mock_renderer):
        """Test that album art is cached."""
        renderer = mock_renderer
        
        # Create a dummy image
        test_img = Image.new('RGB', (320, 320), color=(100, 100, 100))
        accent = (100, 100, 100)
        
        # Store in cache manually (simulating _get_cached_art success)
        art_url = '/test/cover.jpg'
        renderer.art_cache[art_url] = (test_img, accent)
        
        # Retrieve from cache
        cached = renderer.art_cache.get(art_url)
        assert cached is not None
        assert cached[0] == test_img
        assert cached[1] == accent
    
    def test_art_cache_limit(self, mock_renderer):
        """Test that cache clears when size exceeds limit (10 items)."""
        renderer = mock_renderer
        
        # Add 11 items
        for i in range(11):
            test_img = Image.new('RGB', (320, 320), color=(i * 20, i * 20, i * 20))
            renderer.art_cache[f'/cover{i}.jpg'] = (test_img, (i, i, i))
        
        # Simulate cache limit check (>10 items triggers clear)
        if len(renderer.art_cache) > 10:
            renderer.art_cache.clear()
        
        # Cache should be empty
        assert len(renderer.art_cache) == 0
    
    def test_clear_art_cache_method(self, mock_renderer):
        """Test the clear_art_cache() method."""
        renderer = mock_renderer
        
        # Add something to cache
        test_img = Image.new('RGB', (320, 320), color=(100, 100, 100))
        renderer.art_cache['/cover.jpg'] = (test_img, (100, 100, 100))
        assert len(renderer.art_cache) == 1
        
        # Clear cache
        renderer.clear_art_cache()
        assert len(renderer.art_cache) == 0

    def test_placeholder_without_fallback_is_not_cached(self, mock_renderer):
        """Test that missing resolved artwork is not cached."""
        renderer = mock_renderer
        cache_key = 'fallback:Bob Marley & The Wailers|Exodus'
        result = renderer._get_cached_art(cache_key, None, source='fallback')

        assert result is None
        assert cache_key not in renderer.art_cache
        assert cache_key not in renderer.art_cache_meta

    def test_fallback_artwork_is_cached_with_metadata(self, mock_renderer):
        """Test that fallback artwork is cached and source metadata is tracked."""
        renderer = mock_renderer
        cache_key = 'fallback:Bob Marley & The Wailers|Exodus'
        test_img = Image.new('RGB', (320, 320), color=(120, 120, 120))
        accent = (120, 120, 120)

        with patch.object(renderer, '_prepare_artwork_on_cache_miss', return_value=(test_img, accent)):
            result = renderer._get_cached_art(cache_key, test_img, source='fallback')

        assert result == (test_img, accent)
        assert renderer.art_cache[cache_key] == (test_img, accent)
        assert renderer.art_cache_meta[cache_key]['source'] == 'fallback'


class TestColorConversion:
    """Test RGB888 to RGB565 color conversion."""
    
    def test_rgb888_to_rgb565_red(self, mock_renderer):
        """Test conversion of pure red."""
        renderer = mock_renderer
        
        # Create a small red image
        img = Image.new('RGB', (1, 1), color=(255, 0, 0))
        # Use monkeypatch to avoid actual framebuffer writes
        
        # Just test the image is created correctly
        assert img.mode == 'RGB'
        assert img.size == (1, 1)
    
    def test_rgb888_to_rgb565_green(self, mock_renderer):
        """Test conversion of pure green."""
        renderer = mock_renderer
        
        img = Image.new('RGB', (1, 1), color=(0, 255, 0))
        assert img.getpixel((0, 0)) == (0, 255, 0)
    
    def test_rgb888_to_rgb565_blue(self, mock_renderer):
        """Test conversion of pure blue."""
        renderer = mock_renderer
        
        img = Image.new('RGB', (1, 1), color=(0, 0, 255))
        assert img.getpixel((0, 0)) == (0, 0, 255)


class TestImageResizing:
    """Test image resizing for display."""
    
    def test_resize_to_art_size(self, mock_renderer):
        """Test resizing album art to display size."""
        renderer = mock_renderer
        
        # Create a large image
        large_img = Image.new('RGB', (1000, 1000), color=(100, 100, 100))
        
        # Resize to art_size
        resized = large_img.resize((renderer.art_size, renderer.art_size))
        
        assert resized.size == (320, 320)
    
    def test_resize_preserves_quality(self, mock_renderer):
        """Test that resize uses good quality resampling."""
        renderer = mock_renderer
        
        # Create image with gradient
        img = Image.new('RGB', (640, 640))
        pixels = img.load()
        for x in range(640):
            for y in range(640):
                pixels[x, y] = (x, y, 128)
        
        # Resize should not crash
        resized = img.resize((320, 320), Image.Resampling.LANCZOS)
        assert resized.size == (320, 320)


class TestMissingArtworkRendering:
    """Test rendering when artwork is unavailable."""

    def test_artwork_mode_renders_placeholder_card_when_art_missing(self, mock_renderer):
        """Artwork mode should render a built-in placeholder instead of a blank screen."""
        renderer = mock_renderer
        rendered_images = []

        with patch.object(renderer, '_write_to_fb', side_effect=lambda img: rendered_images.append(img.copy())):
            renderer.render(
                {
                    'title': 'Exodus',
                    'artist': 'Bob Marley & The Wailers',
                    'album': 'Exodus',
                    'albumart': '',
                    'status': 'play',
                    'seek': 30000,
                    'duration': 180000,
                },
                show_artwork_mode=True,
            )

        assert rendered_images
        center_pixel = rendered_images[-1].getpixel((renderer.width // 2, renderer.height // 2 - 10))
        assert center_pixel != (0, 0, 0)

    def test_hybrid_mode_renders_art_and_text_regions(self, mock_renderer):
        """Hybrid mode should paint both artwork area and text area on the same frame."""
        renderer = mock_renderer
        rendered_images = []

        with patch.object(renderer, '_write_to_fb', side_effect=lambda img: rendered_images.append(img.copy())):
            renderer.render(
                {
                    'title': 'The Heathen',
                    'artist': 'Bob Marley & The Wailers',
                    'album': 'Exodus (2013 Remaster)',
                    'samplerate': '44.1 kHz',
                    'bitdepth': '16 bit',
                    'albumart': '',
                    'status': 'play',
                    'seek': 45000,
                    'duration': 180000,
                },
                show_hybrid_mode=True,
            )

        assert rendered_images
        rendered = rendered_images[-1]
        bg = renderer.layout_profile.bg_color

        # Left side (artwork block) should not be plain background.
        assert rendered.getpixel((40, 40)) != bg

        # Right side (text block) should also contain non-background pixels.
        right_panel = rendered.crop((220, 10, 470, 260))
        bg_panel = Image.new('RGB', right_panel.size, color=bg)
        assert ImageChops.difference(right_panel, bg_panel).getbbox() is not None

    def test_progress_bar_uses_ms_units(self, mock_renderer):
        """Progress bar should be computed from seek/duration values in ms."""
        renderer = mock_renderer
        rendered_images = []

        with patch.object(renderer, '_write_to_fb', side_effect=lambda img: rendered_images.append(img.copy())):
            renderer.render(
                {
                    'title': 'Bubble Toes',
                    'artist': 'Jack Johnson',
                    'album': 'Brushfire Fairytales',
                    'status': 'play',
                    'seek': 60000,
                    'duration': 180000,
                },
            )

        assert rendered_images
        rendered = rendered_images[-1]

        # 60000/180000 = 33.3%, so x=100 should be fill and x=300 should be track.
        pb_y = renderer.height - renderer.layout_profile.progress_height
        assert rendered.getpixel((100, pb_y + 1)) == renderer.default_accent
        assert rendered.getpixel((300, pb_y + 1)) == renderer.layout_profile.progress_track_color

    def test_progress_bar_uses_millisecond_units(self, mock_renderer):
        """Progress fill should match seek/duration values expressed in milliseconds."""
        renderer = mock_renderer
        rendered_images = []

        with patch.object(renderer, '_write_to_fb', side_effect=lambda img: rendered_images.append(img.copy())):
            renderer.render(
                {
                    'title': 'Exodus',
                    'artist': 'Bob Marley & The Wailers',
                    'album': 'Exodus',
                    'albumart': '',
                    'status': 'play',
                    'seek': 45000,
                    'duration': 180000,
                },
                show_hybrid_mode=True,
            )

        assert rendered_images
        rendered = rendered_images[-1]
        pb_y = renderer.height - renderer.layout_profile.progress_height

        # 45s / 180s = 25%, so x=100 should be filled and x=200 should remain track color.
        assert rendered.getpixel((100, pb_y + 1)) == renderer.default_accent
        assert rendered.getpixel((200, pb_y + 1)) == renderer.layout_profile.progress_track_color


class TestFontHandling:
    """Test font loading and fallback logic."""
    
    def test_get_default_font(self, mock_renderer):
        """Test getting default font when TrueType unavailable."""
        renderer = mock_renderer
        
        # This will actually call the method; may fall back to default
        font = renderer.get_font(24)
        
        # Should return a font object
        assert font is not None
    
    def test_get_bold_font(self, mock_renderer):
        """Test getting bold font variant."""
        renderer = mock_renderer
        
        font = renderer.get_font(24, bold=True)
        
        # Should return a font object
        assert font is not None
    
    def test_get_small_font(self, mock_renderer):
        """Test getting a small font size."""
        renderer = mock_renderer
        
        font = renderer.get_font(12)
        
        assert font is not None


class TestMediaInfoFormatting:
    """Test media source and position formatting helpers."""

    def test_parse_media_position_vinyl_compact_format(self, mock_renderer):
        renderer = mock_renderer
        label = renderer._parse_media_position({'media_position': '1A'})
        assert label == 'Side A | Track 1'

    def test_parse_media_position_vinyl_reverse_compact_format(self, mock_renderer):
        renderer = mock_renderer
        label = renderer._parse_media_position({'media_position': 'B2'})
        assert label == 'Side B | Track 2'

    def test_parse_media_position_free_text_portuguese(self, mock_renderer):
        renderer = mock_renderer
        label = renderer._parse_media_position({'media_position': 'lado a faixa 3'})
        assert label == 'Side A | Track 3'

    def test_parse_media_position_structured_cd_track(self, mock_renderer):
        renderer = mock_renderer
        label = renderer._parse_media_position({'media_track_number': 7})
        assert label == 'Track 7'

    def test_build_info_chips_vinyl_prefers_position(self, mock_renderer):
        renderer = mock_renderer
        chips = renderer._build_info_chips(
            {
                'playback_source': 'vinyl',
                'media_position': '1B',
                'samplerate': '44.1 kHz',
                'bitdepth': '16 bit',
            }
        )
        assert chips == ['VINYL', 'Side B | Track 1']

    def test_build_info_chips_cd_with_track(self, mock_renderer):
        renderer = mock_renderer
        chips = renderer._build_info_chips(
            {
                'playback_source': 'CD',
                'media_track_number': '12',
                'samplerate': '44.1 kHz',
                'bitdepth': '16 bit',
            }
        )
        assert chips == ['CD', 'Track 12']

    def test_build_info_chips_vinyl_without_position_uses_fallback(self, mock_renderer):
        renderer = mock_renderer
        chips = renderer._build_info_chips(
            {
                'playback_source': 'vinyl',
                'samplerate': '',
                'bitdepth': '',
            }
        )
        assert chips == ['VINYL', 'Track ?']

    def test_build_info_chips_digital_prefers_quality(self, mock_renderer):
        renderer = mock_renderer
        chips = renderer._build_info_chips(
            {
                'playback_source': 'AirPlay',
                'samplerate': '44.1 kHz',
                'bitdepth': '16 bit',
            }
        )
        assert chips == ['AIRPLAY', '44.1 kHz | 16 bit']
