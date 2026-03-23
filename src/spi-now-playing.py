#!/usr/bin/env python3

from app.main import (
    main,
    detect_media_player,
    states_are_equal,
    should_resolve_artwork,
    artwork_identity_changed,
)

__all__ = [
    "main",
    "detect_media_player",
    "states_are_equal",
    "should_resolve_artwork",
    "artwork_identity_changed",
]


if __name__ == "__main__":
    main()
