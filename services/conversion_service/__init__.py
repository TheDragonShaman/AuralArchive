"""
Module Name: conversion_service/__init__.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Package exports for audiobook conversion services and helper utilities.

Location:
    /services/conversion_service/__init__.py

"""

from .conversion_service import ConversionService
from .ffmpeg_handler import FFmpegHandler
from .format_detector import FormatDetector
from .metadata_processor import MetadataProcessor
from .quality_manager import QualityManager

__all__ = [
    "ConversionService",
    "FFmpegHandler",
    "FormatDetector",
    "MetadataProcessor",
    "QualityManager",
]