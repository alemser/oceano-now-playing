"""Tests for Oceano shairport-sync metadata backend."""

import base64
import select

from PIL import Image

from media_players.oceano import OceanoClient, TRACK_METADATA_GRACE_SECONDS


def _item_hex(tag: str) -> str:
    return tag.encode("ascii").hex()


def _xml_item(type_tag: str, code_tag: str, payload: bytes = b"") -> bytes:
    data_part = ""
    if payload:
        encoded = base64.b64encode(payload).decode("ascii")
        data_part = f'<data encoding="base64">{encoded}</data>'
    return (
        f"<item><type>{_item_hex(type_tag)}</type>"
        f"<code>{_item_hex(code_tag)}</code>"
        f"<length>{len(payload)}</length>{data_part}</item>"
    ).encode("ascii")


def test_oceano_extracts_core_metadata():
    client = OceanoClient("/tmp/nonexistent")
    client._buffer = (
        _xml_item("core", "minm", b"Track Name")
        + _xml_item("core", "asar", b"Artist Name")
        + _xml_item("core", "asal", b"Album Name")
    )
    for item in client._extract_items():
        client._apply_item(item)

    assert client._state["title"] == "Track Name"
    assert client._state["artist"] == "Artist Name"
    assert client._state["album"] == "Album Name"


def test_oceano_extracts_core_metadata_with_multiline_formatting():
    """Parser should accept shairport items with newlines between tags."""
    client = OceanoClient("/tmp/nonexistent")
    encoded = base64.b64encode(b"Breathe Again").decode("ascii")
    client._buffer = (
        "<item><type>636f7265</type><code>6d696e6d</code><length>13</length>\n"
        f"<data encoding=\"base64\">\n{encoded}</data></item>"
    ).encode("ascii")

    items = client._extract_items()
    assert len(items) == 1

    client._apply_item(items[0])
    assert client._state["title"] == "Breathe Again"


def test_oceano_parses_status_and_progress_units():
    client = OceanoClient("/tmp/nonexistent")
    client._apply_item({"type": "ssnc", "code": "pbeg", "data": b""})
    assert client._state["status"] == "play"
    assert client._state["samplerate"] == "44.1 kHz"
    assert client._state["bitdepth"] == "16 bit"

    # 44.1k ticks -> 1 second, so seek should be 1000ms and duration 3000ms.
    client._apply_item({"type": "ssnc", "code": "prgr", "data": b"0/44100/132300"})
    assert client._state["seek"] == 1000
    assert client._state["duration"] == 3000

    client._apply_item({"type": "ssnc", "code": "pend", "data": b""})
    assert client._state["status"] == "stop"


def test_oceano_prgr_marks_playing_when_attaching_mid_session():
    """Progress events should mark playback active even without pbeg/prsm."""
    client = OceanoClient("/tmp/nonexistent")
    assert client._state["status"] == "stop"

    client._apply_item({"type": "ssnc", "code": "prgr", "data": b"0/88200/264600"})

    assert client._state["status"] == "play"
    assert client._state["seek"] == 2000
    assert client._state["duration"] == 6000


def test_oceano_prgr_parses_with_extra_whitespace():
    """Progress parsing should tolerate spacing around slash-delimited ticks."""
    client = OceanoClient("/tmp/nonexistent")
    client._apply_item({"type": "ssnc", "code": "prgr", "data": b"0 / 44100 / 132300"})

    assert client._state["seek"] == 1000
    assert client._state["duration"] == 3000


def test_oceano_prgr_handles_rtp_wraparound():
    """Progress parsing should remain valid when RTP counters wrap at 32-bit."""
    client = OceanoClient("/tmp/nonexistent")
    # start near uint32 max, current/end after wrap
    client._apply_item({
        "type": "ssnc",
        "code": "prgr",
        "data": b"4294967200/43000/129200",
    })

    # seek ticks: 96 + 43000 = 43096 -> 977 ms
    # duration ticks: 96 + 129200 = 129296 -> 2931 ms
    assert client._state["seek"] == 977
    assert client._state["duration"] == 2931


def test_oceano_pbeg_resets_progress_counters():
    """A new AirPlay playback begin event should reset seek/duration."""
    client = OceanoClient("/tmp/nonexistent")
    client._apply_item({"type": "ssnc", "code": "prgr", "data": b"0/88200/264600"})
    assert client._state["seek"] == 2000
    assert client._state["duration"] == 6000

    client._apply_item({"type": "ssnc", "code": "pbeg", "data": b""})
    assert client._state["status"] == "play"
    assert client._state["seek"] == 0
    assert client._state["duration"] == 0


def test_oceano_core_metadata_promotes_play_without_status_event():
    """Core metadata should wake playback state when status events are delayed."""
    client = OceanoClient("/tmp/nonexistent")
    assert client._state["status"] == "stop"

    client._apply_item({"type": "core", "code": "minm", "data": b"Breathe Again"})

    assert client._state["status"] == "play"
    assert client._state["title"] == "Breathe Again"


def test_oceano_state_has_transport_quality_defaults():
    """Oceano should expose AirPlay transport quality for renderer badges."""
    client = OceanoClient("/tmp/nonexistent")
    assert client._state["samplerate"] == "44.1 kHz"
    assert client._state["bitdepth"] == "16 bit"
    assert client._state["playback_source"] == "AirPlay"


def test_oceano_source_classifier_supports_three_source_labels():
    """Source mapping should normalize hints into AirPlay/Bluetooth/UPnP."""
    client = OceanoClient("/tmp/nonexistent")

    assert client._classify_playback_source("My Bluetooth Receiver") == "Bluetooth"
    assert client._classify_playback_source("UPnP renderer") == "UPnP"
    assert client._classify_playback_source("AirPlay/iOS") == "AirPlay"


def test_oceano_updates_playback_source_from_metadata_hint():
    """Metadata hints should update playback_source when recognizable."""
    client = OceanoClient("/tmp/nonexistent")
    assert client._state["playback_source"] == "AirPlay"

    client._apply_item({"type": "ssnc", "code": "snua", "data": b"Bluetooth A2DP"})
    assert client._state["playback_source"] == "Bluetooth"

    client._apply_item({"type": "ssnc", "code": "snua", "data": b"UPnP DLNA"})
    assert client._state["playback_source"] == "UPnP"


def test_oceano_decodes_pict_artwork():
    client = OceanoClient("/tmp/nonexistent")
    img = Image.new("RGB", (4, 4), color="red")
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    payload = buf.getvalue()

    client._apply_item({"type": "ssnc", "code": "PICT", "data": payload})
    resolved = client._state.get("_resolved_artwork")

    assert resolved is not None
    assert resolved["source"] == "oceano"
    assert resolved["cache_key"].startswith("oceano:")
    assert resolved["image"].size == (4, 4)


def test_oceano_clears_old_embedded_artwork_when_track_changes():
    """Embedded art from previous song must not leak into a new song state."""
    client = OceanoClient("/tmp/nonexistent")

    # First track arrives with embedded artwork.
    img = Image.new("RGB", (4, 4), color="red")
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    client._apply_item({"type": "ssnc", "code": "PICT", "data": buf.getvalue()})
    assert "_resolved_artwork" in client._state

    # New track metadata should invalidate old embedded artwork.
    client._apply_item({"type": "core", "code": "asar", "data": b"Sade"})
    client._apply_item({"type": "core", "code": "minm", "data": b"No Ordinary Love"})

    assert "_resolved_artwork" not in client._state


def test_oceano_receive_message_closes_on_fifo_eof(monkeypatch):
    """FIFO EOF should mark Oceano disconnected so the app can reconnect."""
    client = OceanoClient("/tmp/nonexistent")
    client.fd = 123

    monkeypatch.setattr(select, "select", lambda r, w, x, timeout: ([123], [], []))
    monkeypatch.setattr("os.read", lambda fd, size: b"")

    closed_fds = []

    def fake_close(fd):
        closed_fds.append(fd)

    monkeypatch.setattr("os.close", fake_close)

    assert client.receive_message(timeout=0.1) is None
    assert client.is_connected() is False
    assert closed_fds == [123]


def test_oceano_briefly_defers_placeholder_play_state_after_pbeg(monkeypatch):
    """Track-start play state should wait briefly for metadata before emitting."""
    client = OceanoClient("/tmp/nonexistent")
    client.fd = 123

    pbeg_xml = _xml_item("ssnc", "pbeg", b"")

    select_calls = {"count": 0}

    def fake_select(r, w, x, timeout):
        select_calls["count"] += 1
        if select_calls["count"] == 1:
            # First receive_message call has data.
            return ([123], [], [])
        # No more bytes pending for drain or subsequent poll.
        return ([], [], [])

    read_calls = {"count": 0}

    def fake_read(fd, size):
        read_calls["count"] += 1
        if read_calls["count"] == 1:
            return pbeg_xml
        return b""

    monotonic_values = iter([
        100.0,  # pbeg grace deadline set at track start
        100.1,  # still in grace window -> defer
        100.1 + TRACK_METADATA_GRACE_SECONDS + 0.01,  # grace expired
    ])

    monkeypatch.setattr(select, "select", fake_select)
    monkeypatch.setattr("os.read", fake_read)
    monkeypatch.setattr("time.monotonic", lambda: next(monotonic_values))

    # First call parses pbeg but defers placeholder-only state.
    assert client.receive_message(timeout=0.1) is None

    # Next poll emits pending state once grace expires.
    emitted = client.receive_message(timeout=0.1)
    assert emitted is not None
    assert emitted["status"] == "play"

