"""Media player integrations."""

from media_players.base import MediaPlayer
from media_players.oceano import OceanoClient

__all__ = [
    "MediaPlayer",
    "OceanoClient",
]
