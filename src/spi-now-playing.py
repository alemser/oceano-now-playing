#!/usr/bin/env python3

from app.main import (
    main,
    detect_media_player,
    states_are_equal,
    should_resolve_artwork,
    artwork_identity_changed,
    should_reconnect_player,
)

__all__ = [
    "main",
    "detect_media_player",
    "states_are_equal",
    "should_resolve_artwork",
    "artwork_identity_changed",
    "should_reconnect_player",
]


if __name__ == "__main__":
    main()
