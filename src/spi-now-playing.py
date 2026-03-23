#!/usr/bin/env python3

from app.main import (
    main,
    detect_media_player,
    states_are_equal,
    should_resolve_artwork,
)

__all__ = [
    "main",
    "detect_media_player",
    "states_are_equal",
    "should_resolve_artwork",
]


if __name__ == "__main__":
    main()
