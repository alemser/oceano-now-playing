import math
import os
import textwrap
import logging
from dataclasses import dataclass
import numpy as np
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutProfile:
    """Visual profile for text and artwork layouts."""

    name: str
    bg_color: tuple[int, int, int]
    title_color: tuple[int, int, int]
    artist_color: tuple[int, int, int]
    album_color: tuple[int, int, int]
    quality_text_color: tuple[int, int, int]
    quality_box_color: tuple[int, int, int]
    progress_track_color: tuple[int, int, int]
    progress_height: int
    status_icon_size: int
    title_font_size: int
    artist_font_size: int
    album_font_size: int
    quality_font_size: int


LAYOUT_PROFILES = {
    "classic": LayoutProfile(
        name="classic",
        bg_color=(0, 0, 0),
        title_color=(255, 255, 255),
        artist_color=(200, 200, 200),
        album_color=(120, 120, 120),
        quality_text_color=(255, 255, 255),
        quality_box_color=(255, 255, 255),
        progress_track_color=(40, 40, 40),
        progress_height=6,
        status_icon_size=18,
        title_font_size=42,
        artist_font_size=32,
        album_font_size=24,
        quality_font_size=20,
    ),
    "high_contrast": LayoutProfile(
        name="high_contrast",
        bg_color=(6, 6, 6),
        title_color=(255, 255, 255),
        artist_color=(195, 215, 230),
        album_color=(170, 170, 170),
        quality_text_color=(255, 255, 255),
        quality_box_color=(255, 255, 255),
        progress_track_color=(30, 30, 30),
        progress_height=10,
        status_icon_size=24,
        title_font_size=54,
        artist_font_size=30,
        album_font_size=22,
        quality_font_size=24,
    ),
}

class Renderer:
    def __init__(
        self,
        width=480,
        height=320,
        fb_device="/dev/fb0",
        color_format="RGB565",
        layout_profile="high_contrast",
    ):
        self.width = width
        self.height = height
        self.fb_device = fb_device
        self.color_format = color_format.upper()
        self.layout_profile_name = layout_profile.lower()
        self.layout_profile = LAYOUT_PROFILES.get(
            self.layout_profile_name,
            LAYOUT_PROFILES["high_contrast"],
        )
        self.fb_handle = None
        self.art_cache = {}  # Cache for resized images and their dominant colors
        self.art_cache_meta = {}  # Cache metadata keyed by artwork URL
        self.art_size = 320
        self.art_x, self.art_y = 10, 0
        
        # Default accent color
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
        
        text1 = "Oceano Player"
        text2 = "Waiting for media..."
        
        bbox1 = draw.textbbox((0, 0), text1, font=f_logo)
        w1 = bbox1[2] - bbox1[0]
        draw.text(((self.width - w1) // 2, center_y + 40), text1, fill=(140, 140, 140), font=f_logo)
        
        bbox2 = draw.textbbox((0, 0), text2, font=f_sub)
        w2 = bbox2[2] - bbox2[0]
        draw.text(((self.width - w2) // 2, center_y + 80), text2, fill=(80, 80, 80), font=f_sub)
        
        self._write_to_fb(img)
        return img

    def _render_missing_artwork_card(self, title, artist, album):
        """Render a built-in placeholder card when artwork is unavailable."""
        card = Image.new('RGB', (self.art_size, self.art_size), color=(18, 18, 18))
        draw = ImageDraw.Draw(card)

        accent = self.default_accent
        muted = (90, 90, 90)
        panel = (28, 28, 28)
        highlight = (210, 210, 210)

        draw.rounded_rectangle((0, 0, self.art_size - 1, self.art_size - 1), radius=28, fill=panel)
        draw.rounded_rectangle((12, 12, self.art_size - 13, self.art_size - 13), radius=22, outline=accent, width=3)

        for stripe_y in (36, 58, 80):
            draw.rounded_rectangle((28, stripe_y, self.art_size - 28, stripe_y + 6), radius=3, fill=(40, 40, 40))

        center_x = self.art_size // 2
        center_y = 150
        draw.ellipse((center_x - 62, center_y - 62, center_x + 62, center_y + 62), outline=highlight, width=4)
        draw.ellipse((center_x - 18, center_y - 18, center_x + 18, center_y + 18), fill=accent)
        draw.arc((center_x - 82, center_y - 82, center_x + 82, center_y + 82), start=210, end=332, fill=accent, width=5)

        label_font = self.get_font(18, bold=True)
        title_font = self.get_font(24, bold=True)
        meta_font = self.get_font(16)

        label = "NO COVER"
        label_box = draw.textbbox((0, 0), label, font=label_font)
        label_width = label_box[2] - label_box[0]
        draw.text(((self.art_size - label_width) // 2, 230), label, fill=highlight, font=label_font)

        title_text = (title or album or "Unknown Album")[:22]
        artist_text = (artist or album or "Unknown Artist")[:28]
        album_text = album[:28] if album else "Artwork unavailable"

        title_box = draw.textbbox((0, 0), title_text, font=title_font)
        title_width = title_box[2] - title_box[0]
        draw.text(((self.art_size - title_width) // 2, 256), title_text, fill=(255, 255, 255), font=title_font)

        artist_box = draw.textbbox((0, 0), artist_text, font=meta_font)
        artist_width = artist_box[2] - artist_box[0]
        draw.text(((self.art_size - artist_width) // 2, 286), artist_text, fill=(175, 175, 175), font=meta_font)

        album_box = draw.textbbox((0, 0), album_text, font=meta_font)
        album_width = album_box[2] - album_box[0]
        draw.text(((self.art_size - album_width) // 2, 306), album_text, fill=muted, font=meta_font)

        return card

    def render(self, data, show_artwork_mode=False, show_hybrid_mode=False):
        """Renders the complete V2 interface."""
        if not data:
            return

        # Ensure framebuffer is open
        if not self.fb_handle:
            logger.info("Framebuffer handle was closed, re-opening.")
            self._open_fb()

        profile = self.layout_profile
        img = Image.new('RGB', (self.width, self.height), color=profile.bg_color)
        draw = ImageDraw.Draw(img)

        # Fonts
        f_xl = self.get_font(profile.title_font_size, bold=True)
        f_large = self.get_font(profile.artist_font_size, bold=True)
        f_med = self.get_font(profile.album_font_size, bold=True if profile.name == "high_contrast" else False)
        f_small = self.get_font(profile.status_icon_size)
        f_tech = self.get_font(profile.quality_font_size, bold=True)

        # Data
        title = data.get('title', 'Unknown')
        artist = data.get('artist', 'Unknown')
        album = data.get('album', 'Unknown')
        samplerate = data.get('samplerate', '')
        bitdepth = data.get('bitdepth', '')
        playback_source = data.get('playback_source', '')
        albumart = data.get('albumart', '')
        status = data.get('status', 'stop')
        
        # Progress Calculation
        seek = data.get('seek', 0) or 0
        if seek is None:
            seek = 0
        
        duration = data.get('duration', 0) or 0
        if duration is None:
            duration = 0
        
        progress = 0
        if duration > 0:
            # Keep both values in milliseconds to avoid unit mismatch.
            progress = min(seek / duration, 1.0)

        # Get Art and Accent Color
        accent_color = self.default_accent
        art = None
        resolved_artwork = data.get('_resolved_artwork')
        if resolved_artwork:
            art_data = self._get_cached_art(
                resolved_artwork.get('cache_key'),
                resolved_artwork.get('image'),
                source=resolved_artwork.get('source', 'unknown')
            )
            if art_data:
                art, accent_color = art_data
            else:
                logger.warning(f"[RENDER] Failed to load artwork, using default accent")
        elif albumart:
            logger.debug("[RENDER] Media player did not provide resolved artwork")
        else:
            logger.debug(f"[RENDER] No albumart provided by media player")

        # --- DRAW PROGRESS BAR (Common for both modes) ---
        pb_height = profile.progress_height
        pb_y = self.height - pb_height
        progress_color = accent_color
        draw.rectangle((0, pb_y, self.width, self.height), fill=profile.progress_track_color) # Background
        draw.rectangle((0, pb_y, int(self.width * progress), self.height), fill=progress_color) # Progress

        # --- DRAW STATUS ICON ---
        icon = "▶" if status == 'play' else "II"
        _, th = draw.textbbox((0, 0), icon, font=f_small)[2:]
        draw.text((10, pb_y - th - 10), icon, fill=progress_color, font=f_small)

        if show_hybrid_mode:
            # --- MODE 3: HYBRID (ART + TEXT ON THE SAME SCREEN) ---
            hybrid_art_size = 184 if profile.name == "high_contrast" else 170
            art_x = 16
            art_y = 14

            if art:
                hybrid_art = art.resize((hybrid_art_size, hybrid_art_size), Image.Resampling.LANCZOS)
            else:
                placeholder_art = self._render_missing_artwork_card(title, artist, album)
                hybrid_art = placeholder_art.resize((hybrid_art_size, hybrid_art_size), Image.Resampling.LANCZOS)
            img.paste(hybrid_art, (art_x, art_y))

            text_x = art_x + hybrid_art_size + 16
            text_w = self.width - text_x - 12
            y_cursor = 16

            title_wrap_width = 14 if profile.name == "high_contrast" else 16
            title_lines = textwrap.wrap(title, width=title_wrap_width)[:2]
            for line in title_lines:
                draw.text((text_x, y_cursor), line, fill=profile.title_color, font=f_large)
                line_h = draw.textbbox((0, 0), line, font=f_large)[3]
                y_cursor += line_h + 4

            artist_text = textwrap.shorten(artist, width=30, placeholder="...")
            draw.text((text_x, y_cursor + 4), artist_text, fill=profile.artist_color, font=f_med)
            y_cursor += draw.textbbox((0, 0), artist_text, font=f_med)[3] + 8

            album_text = textwrap.shorten(album, width=32, placeholder="...")
            draw.text((text_x, y_cursor), album_text, fill=profile.album_color, font=f_med)

            quality_str = f"{samplerate} | {bitdepth}" if samplerate and bitdepth else samplerate or bitdepth
            if quality_str:
                quality_text = textwrap.shorten(quality_str, width=28, placeholder="...")
                qw, qh = draw.textbbox((0, 0), quality_text, font=f_tech)[2:]
                box_y = pb_y - (qh + 20)
                box_x1 = text_x
                box_x2 = min(text_x + text_w, text_x + qw + 16)
                draw.rectangle(
                    (box_x1, box_y, box_x2, box_y + qh + 12),
                    fill=(0, 0, 0),
                    outline=accent_color,
                    width=2,
                )
                draw.text((text_x + 8, box_y + 6), quality_text, fill=profile.quality_text_color, font=f_tech)

        elif not show_artwork_mode:
            # --- MODE 1: CENTERED TEXT ---
            y_cursor = 18 if profile.name == "high_contrast" else 35
            
            # Title (wrapped if needed, then centered)
            title_wrap_width = 20 if profile.name == "high_contrast" else 25
            title_lines = textwrap.wrap(title, width=title_wrap_width)
            for line in title_lines[:2]:
                y_cursor = self._draw_centered_text(draw, line, y_cursor, f_xl, profile.title_color)
            
            y_cursor += 14 if profile.name == "high_contrast" else 5
            # Artist
            artist_max_chars = 34 if profile.name == "high_contrast" else 40
            y_cursor = self._draw_centered_text(draw, artist[:artist_max_chars], y_cursor, f_large, profile.artist_color)
            
            # Album
            album_max_chars = 40 if profile.name == "high_contrast" else 45
            y_cursor = self._draw_centered_text(draw, album[:album_max_chars], y_cursor, f_med, profile.album_color)
            
            # Tech Info at bottom center
            quality_parts = []
            if playback_source:
                quality_parts.append(playback_source)
            if samplerate:
                quality_parts.append(samplerate)
            if bitdepth:
                quality_parts.append(bitdepth)
            quality_str = " | ".join(quality_parts)
            if quality_str:
                qw, qh = draw.textbbox((0, 0), quality_str, font=f_tech)[2:]
                if profile.name == "high_contrast":
                    box_y = pb_y - 56
                    draw.rectangle(
                        ((self.width - qw) // 2 - 16, box_y, (self.width + qw) // 2 + 16, box_y + 36),
                        fill=(0, 0, 0),
                        outline=profile.quality_box_color,
                        width=3,
                    )
                    draw.text(((self.width - qw) // 2, box_y + 5), quality_str, fill=profile.quality_text_color, font=f_tech)
                else:
                    box_y = pb_y - 50
                    draw.rectangle(
                        ((self.width - qw) // 2 - 10, box_y, (self.width + qw) // 2 + 10, box_y + 30),
                        outline=accent_color,
                        width=2,
                    )
                    draw.text(((self.width - qw) // 2, box_y + 3), quality_str, fill=accent_color, font=f_tech)

        else:
            # --- MODE 2: COVER (CENTERED) ---
            art_x = (self.width - self.art_size) // 2
            art_y = (self.height - self.art_size) // 2 - 10  # Slight upward offset for progress bar
            if art:
                img.paste(art, (art_x, art_y))
            else:
                placeholder_art = self._render_missing_artwork_card(title, artist, album)
                img.paste(placeholder_art, (art_x, art_y))

        self._write_to_fb(img)

    def clear_art_cache(self):
        """Clears the album art cache."""
        self.art_cache.clear()
        self.art_cache_meta.clear()

    def _prepare_artwork_on_cache_miss(self, artwork_image):
        """Resize resolved artwork and compute its dominant color."""
        accent = self._get_dominant_color(artwork_image)

        art_resized = artwork_image.resize((self.art_size, self.art_size), Image.Resampling.LANCZOS)
        return art_resized, accent

    # ------------------------------------------------------------------ #
    # VU meter rendering                                                   #
    # ------------------------------------------------------------------ #

    # Gauge geometry (PIL angles: 0=east, clockwise, y-down)
    _VU_ARC_START = 210   # upper-left  → −40 dB
    _VU_ARC_END   = 330   # upper-right → +3 dB
    _VU_DB_MIN    = -40.0
    _VU_DB_MAX    =   3.0

    @staticmethod
    def _db_to_vu_angle(db: float) -> float:
        """Map a dBFS value to a PIL gauge angle (210°–330°)."""
        t = (db - Renderer._VU_DB_MIN) / (Renderer._VU_DB_MAX - Renderer._VU_DB_MIN)
        return Renderer._VU_ARC_START + t * (Renderer._VU_ARC_END - Renderer._VU_ARC_START)

    @staticmethod
    def _rms_to_db(rms: float) -> float:
        """Convert linear RMS [0, 1] to dBFS, clamped to [DB_MIN, DB_MAX]."""
        if rms < 1e-7:
            return Renderer._VU_DB_MIN
        return max(Renderer._VU_DB_MIN, min(20.0 * math.log10(rms), Renderer._VU_DB_MAX))

    def render_vu(
        self,
        vu_left: float,
        vu_right: float,
        peak_left: float,
        peak_right: float,
        state: dict | None,
    ) -> None:
        """Render two analog needle VU meters inspired by the Magnat MR 780.

        Layout (480×320):
          - Two gauge arcs (amber/orange on black) occupying the upper ~260 px
          - Footer strip (52 px): centered title + artist, source badge
          - Progress bar (8 px) at the very bottom in amber
        """
        if not self.fb_handle:
            self._open_fb()

        img = Image.new("RGB", (self.width, self.height), (6, 6, 6))
        draw = ImageDraw.Draw(img)

        FOOTER_H = 52
        PB_H = 8
        GAUGE_AREA_H = self.height - FOOTER_H - PB_H  # 260 px
        RADIUS = 108
        PIVOT_Y = GAUGE_AREA_H - 14           # 246: pivot near bottom of gauge area
        LEFT_CX = self.width // 4              # 120
        RIGHT_CX = 3 * self.width // 4        # 360

        for rms, peak, cx, ch_label in (
            (vu_left,  peak_left,  LEFT_CX,  "L"),
            (vu_right, peak_right, RIGHT_CX, "R"),
        ):
            self._draw_vu_gauge(draw, cx, PIVOT_Y, RADIUS, rms, peak, ch_label)

        # Footer ── title + artist
        if state:
            title  = state.get("title")  or ""
            artist = state.get("artist") or ""
            source = state.get("playback_source") or ""

            footer_y = GAUGE_AREA_H + 6
            f_title  = self.get_font(20, bold=True)
            f_artist = self.get_font(16)
            f_source = self.get_font(13)

            if title and title != "Unknown":
                t = textwrap.shorten(title, width=42, placeholder="…")
                bx = draw.textbbox((0, 0), t, font=f_title)
                tw = bx[2] - bx[0]
                draw.text(((self.width - tw) // 2, footer_y), t,
                          fill=(240, 240, 240), font=f_title)

            if artist and artist != "Unknown":
                a = textwrap.shorten(artist, width=50, placeholder="…")
                bx = draw.textbbox((0, 0), a, font=f_artist)
                aw = bx[2] - bx[0]
                draw.text(((self.width - aw) // 2, footer_y + 26), a,
                          fill=(160, 175, 190), font=f_artist)

            if source:
                bx = draw.textbbox((0, 0), source, font=f_source)
                sw, sh = bx[2] - bx[0], bx[3] - bx[1]
                bx1 = self.width - sw - 20
                by1 = footer_y + 4
                draw.rectangle((bx1 - 5, by1 - 2, bx1 + sw + 5, by1 + sh + 2),
                                outline=(100, 65, 15), width=1)
                draw.text((bx1, by1), source, fill=(170, 110, 35), font=f_source)

        # Progress bar
        status   = (state or {}).get("status", "stop")
        seek     = (state or {}).get("seek", 0) or 0
        duration = (state or {}).get("duration", 0) or 0
        progress = min(seek / duration, 1.0) if duration > 0 else 0.0
        pb_y = self.height - PB_H
        draw.rectangle((0, pb_y, self.width, self.height), fill=(20, 12, 4))
        if progress > 0:
            draw.rectangle(
                (0, pb_y, int(self.width * progress), self.height),
                fill=(210, 105, 20),
            )

        self._write_to_fb(img)

    def _draw_vu_gauge(
        self,
        draw: ImageDraw.ImageDraw,
        cx: int,
        cy: int,
        r: int,
        rms: float,
        peak: float,
        label: str,
    ) -> None:
        """Draw one VU needle gauge centred at (cx, cy) with the given radius."""
        bbox = [cx - r, cy - r, cx + r, cy + r]

        # 1. Color zone arcs (scale background)
        zones = [
            (self._VU_ARC_START,       self._db_to_vu_angle(-10), (0, 110, 35)),
            (self._db_to_vu_angle(-10), self._db_to_vu_angle(0),  (170, 120, 0)),
            (self._db_to_vu_angle(0),   self._VU_ARC_END,         (170, 25, 15)),
        ]
        for z_start, z_end, color in zones:
            draw.arc(bbox, z_start, z_end, fill=color, width=5)

        # 2. Tick marks + labels
        DB_TICKS  = (-40, -30, -20, -10, -7, -5, -3, 0, 3)
        DB_LABELS = {-20, -10, 0, 3}
        f_tick = self.get_font(11)

        for db in DB_TICKS:
            angle_rad = math.radians(self._db_to_vu_angle(db))
            major     = db in DB_LABELS
            outer_r   = r
            inner_r   = r - (14 if major else 8)
            ox = cx + outer_r * math.cos(angle_rad)
            oy = cy + outer_r * math.sin(angle_rad)
            ix = cx + inner_r * math.cos(angle_rad)
            iy = cy + inner_r * math.sin(angle_rad)
            tick_fill = (190, 115, 20) if major else (110, 65, 10)
            draw.line([(ix, iy), (ox, oy)], fill=tick_fill, width=2 if major else 1)

            if db in DB_LABELS:
                label_r = r - 27
                lx = cx + label_r * math.cos(angle_rad)
                ly = cy + label_r * math.sin(angle_rad)
                text = f"+{db}" if db > 0 else str(db)
                draw.text((lx, ly), text, fill=(150, 85, 15), font=f_tick, anchor="mm")

        # 3. Peak hold dot
        if peak > 1e-6:
            db_peak   = self._rms_to_db(peak)
            angle_rad = math.radians(self._db_to_vu_angle(db_peak))
            px = cx + (r - 3) * math.cos(angle_rad)
            py = cy + (r - 3) * math.sin(angle_rad)
            draw.ellipse([px - 4, py - 4, px + 4, py + 4], fill=(255, 248, 200))

        # 4. Needle
        db_rms        = self._rms_to_db(rms)
        needle_ang    = math.radians(self._db_to_vu_angle(db_rms))
        needle_len    = r - 12
        nx = cx + needle_len * math.cos(needle_ang)
        ny = cy + needle_len * math.sin(needle_ang)

        draw.line([(cx, cy), (nx, ny)], fill=(55, 30, 5), width=5)   # shadow
        draw.line([(cx, cy), (nx, ny)], fill=(255, 140, 0), width=2)  # needle

        # 5. Pivot
        draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=(190, 95, 10))
        draw.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=(255, 175, 55))

        # 6. Channel label (L / R) above arc
        f_lbl = self.get_font(14, bold=True)
        lbl_y = cy - r - 18
        bx    = draw.textbbox((0, 0), label, font=f_lbl)
        lw    = bx[2] - bx[0]
        draw.text((cx - lw // 2, lbl_y), label, fill=(175, 95, 20), font=f_lbl)

    def _get_cached_art(self, cache_key, artwork_image, source="unknown"):
        """Cache resized artwork and accent color using a media-player-provided key."""
        if not cache_key or artwork_image is None:
            return None

        if cache_key in self.art_cache:
            return self.art_cache[cache_key]

        try:
            if len(self.art_cache) > 10:
                self.art_cache.clear()
                self.art_cache_meta.clear()
            art_resized, accent = self._prepare_artwork_on_cache_miss(artwork_image)
            
            self.art_cache[cache_key] = (art_resized, accent)
            self.art_cache_meta[cache_key] = {"source": source}
            return art_resized, accent
        except Exception as e:
            logger.warning(f"[ART ERROR] Failed to prepare artwork {cache_key}: {type(e).__name__}: {e}")
            return None
