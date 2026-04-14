"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Mar 31 2026
Description:
    Indexer package exposing Torznab (Jackett), Prowlarr, NZBHydra2, and
    direct provider implementations for audiobook searches.

Location:
    /services/indexers/__init__.py

"""

from .base_indexer import BaseIndexer, IndexerProtocol, IndexerType
from .jackett_indexer import JackettIndexer
from .prowlarr_indexer import ProwlarrIndexer
from .nzbhydra2_indexer import NZBHydra2Indexer
from .direct_indexer import DirectIndexer
from .indexer_service_manager import IndexerServiceManager, get_indexer_service_manager

__all__ = [
    'BaseIndexer',
    'IndexerProtocol',
    'IndexerType',
    'JackettIndexer',
    'ProwlarrIndexer',
    'NZBHydra2Indexer',
    'DirectIndexer',
    'IndexerServiceManager',
    'get_indexer_service_manager'
]
