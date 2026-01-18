"""
Module Name: __init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
	Package initializer for metadata services. Exposes the metadata update
	service used to refresh book records.

Location:
	/services/metadata/__init__.py

"""

from .metadata_service import MetadataUpdateService

__all__ = ['MetadataUpdateService']
