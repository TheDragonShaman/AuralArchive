"""
Module Name: download_clients/__init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Download client implementations for torrent workflows with priority-based
    selection and automatic failover.

Location:
    /services/download_clients/__init__.py

"""

from .base_torrent_client import BaseTorrentClient, TorrentState
from .qbittorrent_client import QBittorrentClient

__all__ = [
    'BaseTorrentClient',
    'TorrentState',
    'QBittorrentClient'
]
