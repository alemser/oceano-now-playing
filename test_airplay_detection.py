#!/usr/bin/env python3
"""
Quick diagnostic test for AirPlay/streaming detection logic.

This script tests the detection methods independently to verify they work
before deploying to the actual MoOde device.

Run with: python3 test_airplay_detection.py
"""

import os
import sys
import time
import logging
import tempfile

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from media_players.moode import MoodeClient

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_shairport_process_detection():
    """Test shairport-sync process detection."""
    print("\n=== TEST 1: Shairport Process Detection ===")
    client = MoodeClient()
    
    result = client._check_shairport_running()
    print(f"shairport-sync process running: {result}")
    print("  (Expected: False on dev machine, True on MoOde with AirPlay configured)")
    return result

def test_alsa_audio_detection():
    """Test ALSA audio active detection."""
    print("\n=== TEST 2: ALSA Audio Detection ===")
    client= MoodeClient()
    
    result = client._check_alsa_audio_active()
    print(f"ALSA audio active: {result}")
    print("  (Expected: False when no audio playing, True during playback)")
    return result

def test_metadata_file() -> bool:
    """Test metadata file reading and parsing."""
    print("\n=== TEST 3: Metadata File Parsing ===")
    
    # Create a temporary metadata file like shairport-sync would
    with tempfile.NamedTemporaryFile(mode='w', suffix='.metadata', delete=False) as f:
        f.write("artist=Test Artist\n")
        f.write("title=Test Song\n")
        f.write("album=Test Album\n")
        f.write("songalbumartist=Album Artist\n")
        temp_file = f.name
    
    # Monkey-patch the SHAIRPORT_METADATA_FILE path
    import media_players.moode as moode_module
    original_path = moode_module.SHAIRPORT_METADATA_FILE
    original_cache = moode_module._METADATA_CACHE.copy()
    
    try:
        moode_module.SHAIRPORT_METADATA_FILE = temp_file
        moode_module._METADATA_CACHE = {"mtime": 0, "data": None}
        
        client = MoodeClient()
        metadata = client._get_airplay_metadata()
        
        print(f"Parsed metadata: {metadata}")
        assert metadata is not None, "Metadata should not be None"
        assert metadata.get("artist") == "Test Artist", "Artist mismatch"
        assert metadata.get("title") == "Test Song", "Title mismatch"
        assert metadata.get("album") == "Test Album", "Album mismatch"
        print("✓ Metadata parsing works correctly")
        return True
    finally:
        # Guarantee restoration of module state even on exception
        moode_module.SHAIRPORT_METADATA_FILE = original_path
        moode_module._METADATA_CACHE = original_cache
        os.unlink(temp_file)

def test_empty_metadata_file():
    """Test handling of empty/missing metadata file."""
    print("\n=== TEST 4: Empty/Missing Metadata File ===")
    
    # Test non-existent file
    import media_players.moode as moode_module
    original_path = moode_module.SHAIRPORT_METADATA_FILE
    original_cache = moode_module._METADATA_CACHE.copy()
    
    try:
        moode_module.SHAIRPORT_METADATA_FILE = "/nonexistent/path/metadata"
        moode_module._METADATA_CACHE = {"mtime": 0, "data": None}
        
        client = MoodeClient()
        metadata = client._get_airplay_metadata()
        print(f"Non-existent file result: {metadata}")
        assert metadata is None, "Should return None for non-existent file"
        print("✓ Non-existent file handled correctly")
    finally:
        moode_module.SHAIRPORT_METADATA_FILE = original_path
        moode_module._METADATA_CACHE = original_cache

def test_state_normalization():
    """Test state normalization with streaming detection."""
    print("\n=== TEST 5: State Normalization with Streaming ===")
    
    client = MoodeClient()
    
    # Simulate MoOde API response when MPD is stopped but streaming via AirPlay
    raw_state = {
        "state": "stop",  # MPD reports stop because not playing from queue
        "elapsed": "125.5",
        "time": "245.0",
        "title": "Queue Title",  # From MPD queue, not current stream
        "artist": "Queue Artist",
        "album": "Queue Album",
        "bitrate": "320 kbps",
        "encoded": "MP3",
        "volume": "80",
        "coverurl": "/images/default-album-cover.png",
    }
    
    normalized = client._normalize_state(raw_state)
    
    print(f"Normalized state:")
    print(f"  status: {normalized['status']}")
    print(f"  title: {normalized['title']}")
    print(f"  artist: {normalized['artist']}")
    print(f"  seek: {normalized['seek']} ms")
    print(f"  duration: {normalized['duration']} ms")
    print(f"  quality: {normalized['quality']}")
    
    # With streaming detection, should override to "play"
    print(f"\n  Expected on MoOde+AirPlay:")
    print(f"    status: 'play' (detected from streaming)")
    print(f"    title: <streamed title> (from shairport metadata)")
    
    return normalized

def main():
    print("=" * 70)
    print("AirPlay/Streaming Detection Diagnostic Tests")
    print("=" * 70)
    
    try:
        test_shairport_process_detection()
        test_alsa_audio_detection()
        test_metadata_file()
        test_empty_metadata_file()
        test_state_normalization()
        
        print("\n" + "=" * 70)
        print("✓ All diagnostic tests completed successfully")
        print("=" * 70)
        print("\nNext steps:")
        print("1. Deploy code to MoOde with: ./update.sh")
        print("2. Start AirPlay stream from iPhone/Mac")
        print("3. Check logs: systemctl status moode-now-playing")
        print("4. Look for detection messages like:")
        print("   - '✓ Streaming renderer detected'")
        print("   - '✓ Using streaming metadata'")
        print("5. Display should show playback info instead of idle logo")
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
