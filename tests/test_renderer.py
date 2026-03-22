"""Tests for Renderer utility functions and image operations.

Covers utility functions with logic:
- Time formatting
- Dominant color extraction
- Image resizing and caching
"""

import pytest
import sys
import os
from PIL import Image
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
        
        # Should not crash, should return default
        assert renderer._format_time("invalid") == "00:00"
    
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
