"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Indexer package exposing Torznab (Jackett) and direct provider
    implementations for audiobook searches.

Location:
    /services/indexers/__init__.py

"""

from .base_indexer import BaseIndexer, IndexerProtocol, IndexerType
from .jackett_indexer import JackettIndexer
from .direct_indexer import DirectIndexer
from .indexer_service_manager import IndexerServiceManager, get_indexer_service_manager

__all__ = [
    'BaseIndexer',
    'IndexerProtocol',
    'IndexerType',
    'JackettIndexer',
    'DirectIndexer',
    'IndexerServiceManager',
    'get_indexer_service_manager'
]
