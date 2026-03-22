import os
import time
import textwrap
import logging
from io import BytesIO
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont, ImageStat

logger = logging.getLogger(__name__)

class Renderer:
    def __init__(self, width=480, height=320, fb_device="/dev/fb0", color_format="RGB565", volumio_host="localhost"):
        self.width = width
        self.height = height
        self.fb_device = fb_device
        self.color_format = color_format.upper()
        self.volumio_host = volumio_host
        self.fb_handle = None
        self.art_cache = {}  # Cache for resized images and their dominant colors
        self.art_size = 320
        self.art_x, self.art_y = 10, 0
        
        # Default accent color (Volumio green)
        self.default_accent = (60, 180, 60)
        
        # Try to open the framebuffer once
        self._open_fb()

    def _open_fb(self):
        """Opens the framebuffer persistently and detects its real size."""
        if os.path.exists(self.fb_device):
            try:
                # Try to ensure permissions
                os.system(f"sudo chmod 666 {self.fb_device}")
                self.fb_handle = open(self.fb_device, "r+b") # Open for read and write
                
                # Detect the real size of the framebuffer
                self.fb_handle.seek(0, os.SEEK_END)
                self.real_fb_size = self.fb_handle.tell()
                self.fb_handle.seek(0)
                
                logger.info(f"Framebuffer {self.fb_device} opened. Detected size: {self.real_fb_size} bytes. Format: {self.color_format}")
            except Exception as e:
                logger.error(f"Could not open framebuffer {self.fb_device}: {e}")
        else:
            logger.error(f"Framebuffer device {self.fb_device} not found.")

    def close(self):
        """Closes the framebuffer handle."""
        if self.fb_handle:
            self.fb_handle.close()
            self.fb_handle = None

    def _rgb888_to_565(self, img):
        """Converts RGB888 to 565 according to format (RGB or BGR)."""
        img_array = np.array(img).astype(np.uint16)
        r, g, b = (img_array[:,:,0] >> 3), (img_array[:,:,1] >> 2), (img_array[:,:,2] >> 3)
        
        if self.color_format == "BGR565":
            # B (bits 11-15), G (bits 5-10), R (bits 0-4)
            return (b << 11 | g << 5 | r).tobytes()
        else:
            # Default: RGB565 - R (bits 11-15), G (bits 5-10), B (bits 0-4)
            return (r << 11 | g << 5 | b).tobytes()

    def clear(self, use_fsync=True):
        """Clears the framebuffer by filling the entire device with zeros."""
        try:
            if not self.fb_handle:
                self._open_fb()
            
            if self.fb_handle:
                self.fb_handle.seek(0)
                # Create a zero buffer of the REAL size of the device to ensure full clearing
                black_buffer = b'\x00' * self.real_fb_size
                self.fb_handle.write(black_buffer)
                self.fb_handle.flush()
                if use_fsync:
                    try:
                        os.fsync(self.fb_handle.fileno())
                    except OSError:
                        pass # Some devices do not support fsync
        except Exception as e:
            logger.error(f"Error clearing framebuffer: {e}")
            self.fb_handle = None

    def _write_to_fb(self, img):
        """Writes the image to the framebuffer as directly as possible."""
        if not self.fb_handle:
            self._open_fb()
        
        if self.fb_handle:
            try:
                raw = self._rgb888_to_565(img)
                self.fb_handle.seek(0)
                
                # Write exactly the number of bytes for the image (WIDTH * HEIGHT * 2)
                # without trying to fill the entire device to avoid misalignment
                img_bytes = self.width * self.height * 2
                self.fb_handle.write(raw[:img_bytes])
                
                self.fb_handle.flush()
                # Optional: fsync can cause slowness on some SPI drivers
                # but helps avoid 'tearing'
                try:
                    os.fsync(self.fb_handle.fileno())
                except:
                    pass
            except Exception as e:
                logger.error(f"Error writing to framebuffer: {e}")
                self.fb_handle = None

    def get_font(self, size, bold=False):
        """Tries to load common fonts or returns the default."""
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf" if bold else "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        for path in font_paths:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        return ImageFont.load_default()

    def _get_dominant_color(self, img):
        """Extracts the dominant color from an image."""
        small_img = img.resize((1, 1), Image.Resampling.BILINEAR)
        res = small_img.getpixel((0, 0))
        # Ensure it's not too dark to be visible
        if sum(res) < 60:
            return self.default_accent
        return res

    def _format_time(self, seconds):
        """Formats seconds into MM:SS."""
        if seconds is None: return "00:00"
        m, s = divmod(int(seconds), 60)
        return f"{m:02d}:{s:02d}"

    def _draw_centered_text(self, draw, text, y, font, fill, max_width=440):
        """Draws text centered on the screen, scaling font down if it overflows."""
        # Try to fit the text by reducing font size if necessary
        current_font = font
        font_size = getattr(font, 'size', 24)
        
        while font_size > 12:
            bbox = draw.textbbox((0, 0), text, font=current_font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                break
            font_size -= 2
            current_font = self.get_font(font_size, bold=True if font_size > 20 else False)
            
        bbox = draw.textbbox((0, 0), text, font=current_font)
        w = bbox[2] - bbox[0]
        draw.text(((self.width - w) // 2, y), text, fill=fill, font=current_font)
        return y + (bbox[3] - bbox[1]) + 10

    def render_idle_screen(self):
        """Renders a stylized grayscale logo for the idle/startup state."""
        img = Image.new('RGB', (self.width, self.height), color=(10, 10, 10))
        draw = ImageDraw.Draw(img)
        
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Draw a stylized icon (sound waves/bars)
        bar_width = 12
        gap = 8
        colors = [(40, 40, 40), (70, 70, 70), (100, 100, 100), (70, 70, 70), (40, 40, 40)]
        heights = [40, 70, 100, 70, 40]
        
        start_x = center_x - (len(heights) * (bar_width + gap) - gap) // 2
        for i, h in enumerate(heights):
            x = start_x + i * (bar_width + gap)
            draw.rounded_rectangle(
                (x, center_y - h // 2 - 30, x + bar_width, center_y + h // 2 - 30),
                radius=4,
                fill=colors[i]
            )
            
        # Draw text
        f_logo = self.get_font(28, bold=True)
        f_sub = self.get_font(16)
        
        text1 = "SPI NOW PLAYING"
        text2 = "Waiting for Volumio..."
        
        bbox1 = draw.textbbox((0, 0), text1, font=f_logo)
        w1 = bbox1[2] - bbox1[0]
        draw.text(((self.width - w1) // 2, center_y + 40), text1, fill=(140, 140, 140), font=f_logo)
        
        bbox2 = draw.textbbox((0, 0), text2, font=f_sub)
        w2 = bbox2[2] - bbox2[0]
        draw.text(((self.width - w2) // 2, center_y + 80), text2, fill=(80, 80, 80), font=f_sub)
        
        self._write_to_fb(img)
        return img

    def render(self, data, show_capa_mode=False):
        """Renders the complete V2 interface."""
        if not data:
            return

        # Ensure framebuffer is open
        if not self.fb_handle:
            logger.info("Framebuffer handle was closed, re-opening.")
            self._open_fb()

        img = Image.new('RGB', (self.width, self.height), color=(0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Fonts
        f_xl = self.get_font(42, bold=True)
        f_large = self.get_font(32, bold=True)
        f_med = self.get_font(24)
        f_small = self.get_font(18)
        f_tech = self.get_font(20, bold=True)

        # Data
        title = data.get('title', 'Unknown')
        artist = data.get('artist', 'Unknown')
        album = data.get('album', 'Unknown')
        samplerate = data.get('samplerate', '')
        bitdepth = data.get('bitdepth', '')
        albumart = data.get('albumart', '')
        status = data.get('status', 'stop')
        
        # Progress Calculation
        seek = data.get('seek', 0) or 0
        if seek is None:
            seek = 0
        seek = seek / 1000  # ms to s
        
        duration = data.get('duration', 0) or 0
        if duration is None:
            duration = 0
        
        progress = 0
        if duration > 0:
            progress = min(seek / duration, 1.0)

        # Get Art and Accent Color
        accent_color = self.default_accent
        art = None
        if albumart:
            art_data = self._get_cached_art(albumart)
            if art_data:
                art, accent_color = art_data

        # --- DRAW PROGRESS BAR (Common for both modes) ---
        pb_height = 6
        pb_y = self.height - pb_height
        draw.rectangle((0, pb_y, self.width, self.height), fill=(40, 40, 40)) # Background
        draw.rectangle((0, pb_y, int(self.width * progress), self.height), fill=accent_color) # Progress

        # --- DRAW STATUS ICON ---
        icon = "▶" if status == 'play' else "II"
        _, th = draw.textbbox((0, 0), icon, font=f_small)[2:]
        draw.text((10, pb_y - th - 10), icon, fill=accent_color, font=f_small)

        if not show_capa_mode:
            # --- MODE 1: CENTERED TEXT ---
            y_cursor = 35
            
            # Title (wrapped if needed, then centered)
            title_lines = textwrap.wrap(title, width=25)
            for line in title_lines[:2]:
                y_cursor = self._draw_centered_text(draw, line, y_cursor, f_xl, (255, 255, 255))
            
            y_cursor += 5
            # Artist
            y_cursor = self._draw_centered_text(draw, artist[:40], y_cursor, f_large, (200, 200, 200))
            
            # Album
            y_cursor = self._draw_centered_text(draw, album[:45], y_cursor, f_med, (120, 120, 120))
            
            # Tech Info at bottom center
            quality_str = f"{samplerate} | {bitdepth}" if samplerate and bitdepth else samplerate or bitdepth
            if quality_str:
                qw, qh = draw.textbbox((0, 0), quality_str, font=f_tech)[2:]
                box_y = pb_y - 50
                draw.rectangle(((self.width - qw) // 2 - 10, box_y, (self.width + qw) // 2 + 10, box_y + 30), outline=accent_color, width=2)
                draw.text(((self.width - qw) // 2, box_y + 3), quality_str, fill=accent_color, font=f_tech)

        else:
            # --- MODE 2: COVER (CENTERED) ---
            if art:
                # Center the album cover
                art_x = (self.width - self.art_size) // 2
                art_y = (self.height - self.art_size) // 2 - 10  # Slight upward offset for progress bar
                img.paste(art, (art_x, art_y))

        self._write_to_fb(img)

    def clear_art_cache(self):
        """Clears the album art cache."""
        self.art_cache.clear()

    def _get_cached_art(self, art_url):
        """Fetches and resizes the cover art, with caching and dominant color extraction."""
        if art_url in self.art_cache:
            return self.art_cache[art_url]

        try:
            if len(self.art_cache) > 10:
                self.art_cache.clear()

            # Build URL and add cache buster if it's a relative path from Volumio
            if art_url.startswith('/'):
                url = f"http://{self.volumio_host}:3000{art_url}"
                # Add a timestamp to bypass any server-side caching if the URL is too generic
                if "?" in url:
                    url += f"&t={int(time.time())}"
                else:
                    url += f"?t={int(time.time())}"
            else:
                url = art_url
            
            res = requests.get(url, timeout=3)
            art = Image.open(BytesIO(res.content)).convert("RGB")
            
            # Extract dominant color before resizing for display
            accent = self._get_dominant_color(art)
            
            # Resize for display
            art_resized = art.resize((self.art_size, self.art_size), Image.Resampling.LANCZOS)
            
            self.art_cache[art_url] = (art_resized, accent)
            return art_resized, accent
        except Exception as e:
            logger.warning(f"Error loading album art: {e}")
            return None
