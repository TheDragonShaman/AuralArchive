"""
Module Name: client_selector.py
Author: TheDragonShaman
Created: Aug 26 2025
Last Modified: Dec 24 2025
Description:
    Chooses the appropriate download client by type, capability, and priority.
    Currently selects qBittorrent for torrent workloads while caching configs
    and instances for reuse.

Location:
    /services/download_management/client_selector.py

"""

import re
from typing import Optional, Dict, Any

from utils.logger import get_module_logger
from utils.path_resolver import get_path_resolver


class ClientSelector:
    """
    Selects best download client for each download.

    Currently only qBittorrent is supported for torrent downloads.
    Additional clients (Deluge, Transmission) will be added.

    Selection criteria:
    1. Capability matching (torrent/magnet vs NZB)
    2. User-configured priority
    3. Client health and availability
    """

    def __init__(self, *, logger=None):
        """Initialize client selector."""
        self.logger = logger or get_module_logger("Service.DownloadManagement.ClientSelector")
        self._config_service = None
        self._client_cache: Dict[str, Any] = {}
        self._client_configs: Dict[str, Dict[str, Any]] = {}

    def _get_config_service(self):
        """Lazy load ConfigService."""
        if self._config_service is None:
            from services.service_manager import get_config_service

            self._config_service = get_config_service()
        return self._config_service

    def invalidate_cache(self, client_name: Optional[str] = None):
        """Invalidate cached client instances/config and close stale connections."""
        if client_name:
            targets = [client_name]
        else:
            targets = list(set(self._client_cache.keys()) | set(self._client_configs.keys()))

        for target in targets:
            client = self._client_cache.pop(target, None)
            self._client_configs.pop(target, None)

            if not client:
                continue

            disconnect = getattr(client, "disconnect", None)
            if callable(disconnect):
                try:
                    disconnect()
                except Exception as exc:
                    self.logger.debug(
                        "Ignoring client disconnect failure during cache invalidation",
                        extra={"client": target, "error": str(exc)},
                    )

    def select_client(self, download_type: str) -> Optional[str]:
        """
        Select best client for the provided download type.

        Args:
            download_type: "torrent", "magnet", or "nzb"

        Returns:
            The name of the client to use, or None if unsupported
        """

        if download_type in ("torrent", "magnet"):
            return self._select_torrent_client()

        if download_type == "nzb":
            return self._select_nzb_client()

        self.logger.error("Unknown download type", extra={
            "download_type": download_type
        })
        return None

    def _select_torrent_client(self) -> Optional[str]:
        """Select best available torrent client (currently qBittorrent)."""

        if not self._is_qbittorrent_enabled():
            self.logger.debug("No torrent client enabled", extra={
                "client": "qbittorrent"
            })
            return None

        self.logger.debug("Selecting torrent client", extra={
            "client": "qbittorrent"
        })
        return "qbittorrent"

    def _select_nzb_client(self) -> Optional[str]:
        """Select best available NZB client (SABnzbd preferred, then NZBGet)."""

        if self._is_sabnzbd_enabled():
            self.logger.debug("Selecting NZB client", extra={"client": "sabnzbd"})
            return "sabnzbd"

        if self._is_nzbget_enabled():
            self.logger.debug("Selecting NZB client", extra={"client": "nzbget"})
            return "nzbget"

        self.logger.debug("No NZB client enabled")
        return None

    def get_client(self, client_name: str):
        """
        Get client instance by name.

        Currently supported: "qbittorrent".
        Future support planned for: "deluge", "transmission".
        """

        if client_name in self._client_cache:
            return self._client_cache[client_name]

        try:
            if client_name == "qbittorrent":
                from services.download_clients.qbittorrent_client import QBittorrentClient

                config = self._load_client_config("qbittorrent")
                if not config.get("enabled"):
                    self.logger.debug("qBittorrent is disabled; skipping client init")
                    return None
                client = QBittorrentClient(config)
                client.connect()
                self._client_cache[client_name] = client
                self._client_configs[client_name] = config
                return client

            if client_name == "sabnzbd":
                from services.download_clients.sabnzbd_client import SABnzbdClient

                config = self._load_client_config("sabnzbd")
                if not config.get("enabled"):
                    self.logger.debug("SABnzbd is disabled; skipping client init")
                    return None
                client = SABnzbdClient(config)
                client.connect()
                self._client_cache[client_name] = client
                self._client_configs[client_name] = config
                return client

            if client_name == "nzbget":
                from services.download_clients.nzbget_client import NZBGetClient

                config = self._load_client_config("nzbget")
                if not config.get("enabled"):
                    self.logger.debug("NZBGet is disabled; skipping client init")
                    return None
                client = NZBGetClient(config)
                client.connect()
                self._client_cache[client_name] = client
                self._client_configs[client_name] = config
                return client

            if client_name in ("deluge", "transmission"):
                self.logger.warning("Client not yet implemented", extra={
                    "client": client_name
                })
                return None

            self.logger.error("Unknown client", extra={
                "client": client_name
            })
            return None

        except Exception as exc:
            self.logger.exception("Error loading client", extra={
                "client": client_name,
                "error": str(exc)
            })
            return None

    def get_client_config(self, client_name: str, *, refresh: bool = False) -> Dict[str, Any]:
        """Return cached configuration for a download client."""

        if refresh:
            self._client_configs.pop(client_name, None)

        if client_name in self._client_configs:
            return self._client_configs[client_name]

        config = self._load_client_config(client_name)
        if config:
            self._client_configs[client_name] = config
        return config

    def _load_client_config(self, client_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific download client.

        Args:
            client_name: Client identifier (e.g., "qbittorrent")

        Returns:
            Dictionary of configuration values expected by the client implementation.
        """

        config_service = self._get_config_service()

        if client_name == "qbittorrent":
            config_parser = config_service.load_config()
            section_name = "qbittorrent"

            if config_parser.has_section(section_name):
                section = config_parser[section_name]

                def _get(option: str, fallback: str = "") -> str:
                    return section.get(option, fallback)

                def _get_bool(option: str, fallback: bool = False) -> bool:
                    try:
                        return section.getboolean(option, fallback=fallback)
                    except ValueError:
                        return fallback

                def _clean_path(value: Optional[str]) -> str:
                    if not value:
                        return ""
                    return str(value).strip()

                raw_password = _get("qb_password", "adminpass")
                password = raw_password.strip()
                if password.startswith('"') and password.endswith('"'):
                    password = password[1:-1]

                mapping_buckets = {}
                for option, value in section.items():
                    option_lower = option.lower()
                    match = re.match(r"path_mapping_(\d+)_(qb_path|host_path|remote|local)", option_lower)
                    if not match:
                        continue

                    index = int(match.group(1))
                    bucket = mapping_buckets.setdefault(index, {"remote": "", "local": ""})
                    trimmed_value = str(value or "").strip()

                    if match.group(2) in {"qb_path", "remote"}:
                        bucket["remote"] = trimmed_value
                    else:
                        bucket["local"] = trimmed_value

                path_mappings = [
                    mapping
                    for _, mapping in sorted(mapping_buckets.items(), key=lambda item: item[0])
                    if mapping["remote"] or mapping["local"]
                ]

                if not path_mappings:
                    raw_mappings = _get("path_mappings", "")
                    if raw_mappings:
                        for entry in str(raw_mappings).split(';'):
                            if '|' not in entry:
                                continue
                            remote, local = entry.split('|', 1)
                            remote = remote.strip()
                            local = local.strip()
                            if remote or local:
                                path_mappings.append({"remote": remote, "local": local})

                remote_root = path_mappings[0]["remote"] if path_mappings else ""
                local_root = path_mappings[0]["local"] if path_mappings else ""

                legacy_remote = _clean_path(
                    _get("download_path")
                    or _get("download_path_remote")
                    or _get("save_path_root")
                    or _get("save_path")
                )
                legacy_local = _clean_path(_get("download_path_local") or _get("local_save_path"))

                if not remote_root:
                    remote_root = legacy_remote

                if not local_root:
                    local_root = legacy_local or remote_root

                config_dict = {
                    "enabled": _get_bool("enabled", False),
                    "host": _get("qb_host", "localhost"),
                    "port": int(_get("qb_port", "8080") or 8080),
                    "username": _get("qb_username", "admin"),
                    "password": password,
                    "use_ssl": _get_bool("use_ssl", False),
                    "category": _get("category", "auralarchive"),
                    "download_path_remote": _clean_path(remote_root),
                    "download_path_local": _clean_path(local_root),
                    "path_mappings": path_mappings,
                }

                verify_cert_value = section.get("verify_cert", fallback=None)
                if verify_cert_value is not None:
                    config_dict["verify_cert"] = _get_bool("verify_cert", True)

                return config_dict

            self.logger.warning("qBittorrent config not found, using defaults")
            return {
                "enabled": False,
                "host": "localhost",
                "port": 8080,
                "username": "admin",
                "password": "adminpass",
                "use_ssl": False,
                "category": "auralarchive",
                "download_path_remote": "",
                "download_path_local": "",
                "path_mappings": [],
            }

        if client_name == "sabnzbd":
            config_parser = config_service.load_config()
            section_name = "sabnzbd"
            dm_section = config_service.get_section("download_management") or {}
            dm_downloads_path = str(dm_section.get("downloads_path") or "").strip()
            default_local_downloads = dm_downloads_path or get_path_resolver().get_downloads_dir()

            if config_parser.has_section(section_name):
                section = config_parser[section_name]

                def _get(option: str, fallback: str = "") -> str:
                    return section.get(option, fallback)

                def _get_bool(option: str, fallback: bool = False) -> bool:
                    try:
                        return section.getboolean(option, fallback=fallback)
                    except ValueError:
                        return fallback

                def _clean_path(value: Optional[str]) -> str:
                    if not value:
                        return ""
                    return str(value).strip()

                remote_path = _clean_path(
                    _get("remote_path")
                    or _get("download_path_remote")
                    or "/downloads"
                )
                local_path = _clean_path(
                    _get("local_path")
                    or _get("download_path_local")
                    or dm_downloads_path
                )

                return {
                    "enabled":     _get_bool("enabled", False),
                    "host":        _get("host", "localhost"),
                    "port":        int(_get("port", "8080") or 8080),
                    "api_key":     _get("api_key", ""),
                    "use_ssl":     _get_bool("use_ssl", False),
                    "verify_cert": _get_bool("verify_cert", True),
                    "category":    _get("category", ""),
                    "url_base":    _get("url_base", "/sabnzbd/api"),
                    "remote_path": remote_path,
                    "local_path":  local_path,
                }

            self.logger.warning("SABnzbd config not found, using defaults")
            return {
                "enabled": False,
                "host": "localhost",
                "port": 8080,
                "api_key": "",
                "use_ssl": False,
                "verify_cert": True,
                "category": "",
                "url_base": "/sabnzbd/api",
                "remote_path": "/downloads",
                "local_path": default_local_downloads,
            }

        if client_name == "nzbget":
            config_parser = config_service.load_config()
            section_name = "nzbget"

            if config_parser.has_section(section_name):
                section = config_parser[section_name]

                def _get(option: str, fallback: str = "") -> str:
                    return section.get(option, fallback)

                def _get_bool(option: str, fallback: bool = False) -> bool:
                    try:
                        return section.getboolean(option, fallback=fallback)
                    except ValueError:
                        return fallback

                return {
                    "enabled":     _get_bool("enabled", False),
                    "host":        _get("host", "localhost"),
                    "port":        int(_get("port", "6789") or 6789),
                    "username":    _get("username", "nzbget"),
                    "password":    _get("password", "tegbzn6789"),
                    "use_ssl":     _get_bool("use_ssl", False),
                    "verify_cert": _get_bool("verify_cert", True),
                    "category":    _get("category", ""),
                }

            self.logger.warning("NZBGet config not found, using defaults")
            return {
                "enabled": False,
                "host": "localhost",
                "port": 6789,
                "username": "nzbget",
                "password": "tegbzn6789",
                "use_ssl": False,
                "verify_cert": True,
                "category": "",
            }

        return {}

    def _is_qbittorrent_enabled(self) -> bool:
        config = self._load_client_config("qbittorrent")
        return bool(config.get("enabled"))

    def _is_sabnzbd_enabled(self) -> bool:
        config = self._load_client_config("sabnzbd")
        return bool(config.get("enabled"))

    def _is_nzbget_enabled(self) -> bool:
        config = self._load_client_config("nzbget")
        return bool(config.get("enabled"))
