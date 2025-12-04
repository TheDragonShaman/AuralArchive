"""
Download Clients Module
=======================

Download client implementations for torrents and usenet.
Supports multiple clients with priority-based selection and automatic failover.
"""

from .base_torrent_client import BaseTorrentClient, TorrentState
from .qbittorrent_client import QBittorrentClient

__all__ = [
    'BaseTorrentClient',
    'TorrentState',
    'QBittorrentClient'
]
