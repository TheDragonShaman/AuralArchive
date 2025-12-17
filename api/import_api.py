"""API endpoints for manual audiobook imports."""

import os
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from flask import Blueprint, jsonify, request  # type: ignore

from services.import_service import LocalFileImportCoordinator
from services.service_manager import get_config_service
from utils.logger import get_module_logger

logger = get_module_logger("API.Import")

import_api_bp = Blueprint('import_api', __name__, url_prefix='/api/import')

DEFAULT_IMPORT_DIRECTORY = '/downloads/import'
DEFAULT_EXTENSIONS = {'.m4b', '.mp3', '.m4a', '.aac', '.flac', '.ogg', '.wav'}

BATCH_CACHE: Dict[str, Dict[str, Any]] = {}
BATCH_CACHE_TTL_SECONDS = 60 * 60  # one hour


def _cleanup_batch_cache() -> None:
    now = time.time()
    expired: List[str] = []
    for batch_id, batch in BATCH_CACHE.items():
        last_touch = batch.get('updated_at') or batch.get('created_at') or now
        if now - last_touch > BATCH_CACHE_TTL_SECONDS:
            expired.append(batch_id)
    for batch_id in expired:
        BATCH_CACHE.pop(batch_id, None)


def _get_batch_record(batch_id: str) -> Dict[str, Any]:
    _cleanup_batch_cache()
    batch = BATCH_CACHE.get(batch_id)
    if not batch:
        raise KeyError(batch_id)
    batch['accessed_at'] = time.time()
    return batch


def _ordered_cards(batch: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards = batch.get('cards', {})
    order = batch.get('order') or list(cards.keys())
    return [cards[card_id] for card_id in order if card_id in cards]


def _compute_card_summary(cards: List[Dict[str, Any]]) -> Dict[str, int]:
    summary: Dict[str, int] = {
        'total': len(cards),
        'ready': 0,
        'pending': 0,
        'invalid': 0,
        'missing': 0,
        'error': 0,
        'imported': 0
    }
    for card in cards:
        status = card.get('status', 'pending')
        if status not in summary:
            summary[status] = 0
        summary[status] += 1
    return summary


def _serialize_batch(batch: Dict[str, Any]) -> Dict[str, Any]:
    cards = _ordered_cards(batch)
    summary = _compute_card_summary(cards)
    batch['summary'] = summary
    return {
        'batch_id': batch['batch_id'],
        'template': batch.get('template'),
        'library_path': batch.get('library_path'),
        'created_at': batch.get('created_at'),
        'updated_at': batch.get('updated_at'),
        'summary': summary,
        'cards': cards
    }


def _store_batch_record(preview: Dict[str, Any]) -> Dict[str, Any]:
    batch_id = str(uuid.uuid4())
    cards = preview.get('cards') or []
    cards_by_id: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for card in cards:
        card_id = card.get('card_id') or str(uuid.uuid4())
        card['card_id'] = card_id
        cards_by_id[card_id] = card
        order.append(card_id)

    record = {
        'batch_id': batch_id,
        'template': preview.get('template'),
        'library_path': preview.get('library_path'),
        'cards': cards_by_id,
        'order': order,
        'created_at': time.time(),
        'updated_at': time.time(),
        'summary': preview.get('summary') or {}
    }
    BATCH_CACHE[batch_id] = record
    return record


def _select_card_ids(batch: Dict[str, Any], requested_ids: Optional[List[str]]) -> List[str]:
    cards = batch.get('cards', {})
    order = batch.get('order') or list(cards.keys())
    if requested_ids:
        requested_set = {card_id for card_id in requested_ids if card_id in cards}
        return [card_id for card_id in order if card_id in requested_set]
    return [card_id for card_id in order if cards[card_id].get('status') == 'ready']


def _resolve_paths(payload: Dict[str, Any]) -> List[str]:
    paths = payload.get('paths') or payload.get('files') or payload.get('entries') or []
    if isinstance(paths, list):
        return [str(item) for item in paths if item]
    return []


def _get_import_directory() -> str:
    config_service = get_config_service()
    if not config_service:
        return DEFAULT_IMPORT_DIRECTORY

    import_config = config_service.get_section('import') or {}
    path = import_config.get('import_directory') or DEFAULT_IMPORT_DIRECTORY
    return os.path.abspath(path)


def _safe_join(base_path: str, relative_path: str) -> str:
    sanitized = relative_path.strip().lstrip('/') if relative_path else ''
    candidate = os.path.abspath(os.path.join(base_path, sanitized))
    if os.path.commonpath([candidate, base_path]) != base_path:
        raise ValueError('Requested path escapes the configured import directory')
    return candidate


def _relative_path(target_path: str, base_path: str) -> str:
    rel = os.path.relpath(target_path, base_path)
    return '' if rel in ('.', './') else rel


def _describe_path(path: str, base_path: str) -> Dict[str, Any]:
    try:
        stat_result = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise FileNotFoundError(f'Unable to stat path: {exc}') from exc

    is_dir = os.path.isdir(path)
    extension = os.path.splitext(path)[1].lower() if not is_dir else ''
    rel_path = _relative_path(path, base_path)

    return {
        'name': os.path.basename(path),
        'path': rel_path,
        'absolute_path': path,
        'is_dir': is_dir,
        'size_bytes': None if is_dir else stat_result.st_size,
        'modified': datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
        'extension': extension,
        'can_import': (not is_dir) and (extension in DEFAULT_EXTENSIONS)
    }


def _list_directory(path: str, base_path: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    with os.scandir(path) as iterator:
        for entry in iterator:
            # Skip hidden files/dirs by default? We'll include but mark.
            try:
                stat_result = entry.stat(follow_symlinks=False)
            except OSError:
                continue

            entry_path = entry.path
            is_dir = entry.is_dir(follow_symlinks=False)
            extension = os.path.splitext(entry.name)[1].lower() if not is_dir else ''
            rel_path = _relative_path(entry_path, base_path)
            entries.append({
                'name': entry.name,
                'path': rel_path,
                'absolute_path': entry_path,
                'is_dir': is_dir,
                'size_bytes': None if is_dir else stat_result.st_size,
                'modified': datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
                'extension': extension,
                'can_import': (not is_dir) and (extension in DEFAULT_EXTENSIONS)
            })

    entries.sort(key=lambda item: (not item['is_dir'], item['name'].lower()))
    return entries


def _parse_extensions(raw_extensions: Optional[str]) -> Optional[Set[str]]:
    if not raw_extensions:
        return None
    tokens = {token.strip().lower() for token in raw_extensions.split(',') if token.strip()}
    if not tokens:
        return None
    return {token if token.startswith('.') else f'.{token}' for token in tokens}


@import_api_bp.route('/preview', methods=['POST'])
def preview_import_files():
    """Return metadata preview for the provided file paths."""
    try:
        payload = request.get_json(silent=True) or {}
        paths = _resolve_paths(payload)
        if not paths:
            return jsonify({'success': False, 'error': 'Provide a list of file paths to preview'}), 400

        coordinator = LocalFileImportCoordinator()
        preview = coordinator.preview_files(paths)
        return jsonify({'success': True, **preview})

    except Exception as exc:
        logger.error("Import preview failed: %s", exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/batch/preview', methods=['POST'])
def create_batch_preview():
    """Generate staged import cards for the requested files."""
    try:
        payload = request.get_json(silent=True) or {}
        paths = _resolve_paths(payload)
        if not paths:
            return jsonify({'success': False, 'error': 'Provide at least one file path to stage'}), 400

        template_name = payload.get('template_name')
        library_path = payload.get('library_path')
        coordinator = LocalFileImportCoordinator()
        preview = coordinator.build_batch_preview(paths, template_name, library_path)
        record = _store_batch_record(preview)
        response = _serialize_batch(record)
        response['success'] = True
        return jsonify(response)

    except Exception as exc:
        logger.error("Batch preview creation failed: %s", exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/batch/<batch_id>', methods=['GET'])
def get_batch_preview(batch_id: str):
    try:
        batch = _get_batch_record(batch_id)
        response = _serialize_batch(batch)
        response['success'] = True
        return jsonify(response)
    except KeyError:
        return jsonify({'success': False, 'error': 'Batch not found'}), 404
    except Exception as exc:
        logger.error("Failed to fetch batch %s: %s", batch_id, exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/batch/<batch_id>', methods=['DELETE'])
def delete_batch_preview(batch_id: str):
    try:
        removed = BATCH_CACHE.pop(batch_id, None)
        if not removed:
            return jsonify({'success': False, 'error': 'Batch not found'}), 404
        return jsonify({'success': True, 'batch_id': batch_id})
    except Exception as exc:
        logger.error("Failed to delete batch %s: %s", batch_id, exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/batch/<batch_id>/card/<card_id>/refresh', methods=['POST'])
def refresh_batch_card(batch_id: str, card_id: str):
    try:
        batch = _get_batch_record(batch_id)
        card = batch.get('cards', {}).get(card_id)
        if not card:
            return jsonify({'success': False, 'error': 'Card not found in batch'}), 404

        payload = request.get_json(silent=True) or {}
        metadata_override = payload.get('metadata') if isinstance(payload.get('metadata'), dict) else None
        asin_override = payload.get('asin')
        template_name = payload.get('template_name')
        library_path = payload.get('library_path')

        coordinator = LocalFileImportCoordinator()
        updated_card = coordinator.refresh_card_metadata(
            card,
            asin=asin_override,
            metadata_override=metadata_override,
            template_name=template_name,
            library_path=library_path
        )
        batch['cards'][card_id] = updated_card
        batch['updated_at'] = time.time()
        summary = _compute_card_summary(_ordered_cards(batch))
        batch['summary'] = summary

        return jsonify({'success': True, 'card': updated_card, 'summary': summary})

    except KeyError:
        return jsonify({'success': False, 'error': 'Batch not found'}), 404
    except Exception as exc:
        logger.error("Failed to refresh card %s/%s: %s", batch_id, card_id, exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/batch/<batch_id>/import', methods=['POST'])
def import_batch_cards(batch_id: str):
    try:
        batch = _get_batch_record(batch_id)
        payload = request.get_json(silent=True) or {}
        requested_ids = payload.get('card_ids')
        if requested_ids is not None and not isinstance(requested_ids, list):
            return jsonify({'success': False, 'error': 'card_ids must be a list of IDs'}), 400

        selected_ids = _select_card_ids(batch, requested_ids)
        if not selected_ids:
            return jsonify({'success': False, 'error': 'No cards available for import'}), 400

        cards = [batch['cards'][card_id] for card_id in selected_ids]
        options = {
            'template_name': payload.get('template_name') or batch.get('template'),
            'library_path': payload.get('library_path') or batch.get('library_path'),
            'move': payload.get('move', True)
        }

        coordinator = LocalFileImportCoordinator()
        result = coordinator.import_prepared_cards(cards, options)

        for index, outcome in enumerate(result['results']):
            card_id = selected_ids[index] if index < len(selected_ids) else None
            if not card_id or card_id not in batch['cards']:
                continue
            card = batch['cards'][card_id]
            card['status'] = 'imported' if outcome.get('success') else 'error'
            card.setdefault('messages', [])
            outcome_message = outcome.get('message')
            if outcome_message:
                card['messages'].append(outcome_message)
            destination = card.setdefault('destination', {})
            if outcome.get('destination_path'):
                destination['final_path'] = outcome.get('destination_path')
            outcome['card_id'] = card_id

        batch['updated_at'] = time.time()
        summary = _compute_card_summary(_ordered_cards(batch))
        batch['summary'] = summary

        return jsonify({'success': True, 'result': result, 'summary': summary})

    except KeyError:
        return jsonify({'success': False, 'error': 'Batch not found'}), 404
    except Exception as exc:
        logger.error("Batch import failed for %s: %s", batch_id, exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/metadata/search', methods=['GET'])
def search_import_metadata():
    try:
        query = request.args.get('q') or request.args.get('query') or ''
        author = request.args.get('author')
        asin = request.args.get('asin')
        try:
            limit = int(request.args.get('limit', '10'))
        except ValueError:
            limit = 10

        coordinator = LocalFileImportCoordinator()
        result = coordinator.search_metadata_candidates(query=query, author=author, asin=asin, limit=limit)
        return jsonify({'success': True, **result})

    except Exception as exc:
        logger.error("Metadata search failed: %s", exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/jobs', methods=['POST'])
def run_import_jobs():
    """Execute imports for the provided file jobs."""
    try:
        payload = request.get_json(silent=True) or {}
        jobs = payload.get('jobs') or payload.get('entries')
        if not isinstance(jobs, list) or not jobs:
            return jsonify({'success': False, 'error': 'Provide a list of jobs to import'}), 400

        options = payload.get('options') or {}
        coordinator = LocalFileImportCoordinator()
        result = coordinator.import_files(jobs, options)
        return jsonify({'success': True, **result})

    except Exception as exc:
        logger.error("Import job execution failed: %s", exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


@import_api_bp.route('/staging', methods=['GET'])
def list_import_staging_directory():
    """List subdirectories and files inside the configured import staging directory."""
    try:
        base_path = _get_import_directory()
        if not os.path.exists(base_path):
            return jsonify({'success': False, 'error': f'Import directory not found: {base_path}'}), 404
        if not os.path.isdir(base_path):
            return jsonify({'success': False, 'error': f'Import directory is not a folder: {base_path}'}), 400

        relative_path = request.args.get('path', '').strip()
        target_path = _safe_join(base_path, relative_path)
        if not os.path.exists(target_path):
            return jsonify({'success': False, 'error': f'Path not found: {relative_path or "."}'}), 404
        if not os.path.isdir(target_path):
            return jsonify({'success': False, 'error': 'Provide a directory path to list.'}), 400

        entries = _list_directory(target_path, base_path)
        breadcrumbs = _build_breadcrumbs(base_path, target_path)

        return jsonify({
            'success': True,
            'root': base_path,
            'path': _relative_path(target_path, base_path),
            'breadcrumbs': breadcrumbs,
            'entries': entries,
            'summary': {
                'directories': len([entry for entry in entries if entry['is_dir']]),
                'files': len([entry for entry in entries if not entry['is_dir']])
            }
        })
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to list import staging directory: %s", exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500


def _build_breadcrumbs(base_path: str, target_path: str) -> List[Dict[str, str]]:
    breadcrumbs: List[Dict[str, str]] = [
        {'label': 'Import Root', 'path': ''}
    ]
    rel_path = _relative_path(target_path, base_path)
    if not rel_path:
        return breadcrumbs

    running_path = []
    for segment in rel_path.split(os.sep):
        running_path.append(segment)
        breadcrumbs.append({'label': segment, 'path': '/'.join(running_path)})
    return breadcrumbs


@import_api_bp.route('/staging/scan', methods=['GET'])
def scan_import_staging_directory():
    """Return a flattened list of files under the staging directory (optionally recursive)."""
    try:
        base_path = _get_import_directory()
        if not os.path.exists(base_path):
            return jsonify({'success': False, 'error': f'Import directory not found: {base_path}'}), 404
        if not os.path.isdir(base_path):
            return jsonify({'success': False, 'error': f'Import directory is not a folder: {base_path}'}), 400

        relative_path = request.args.get('path', '').strip()
        target_path = _safe_join(base_path, relative_path)
        if not os.path.exists(target_path):
            return jsonify({'success': False, 'error': f'Path not found: {relative_path or "."}'}), 404
        if not os.path.isdir(target_path):
            return jsonify({'success': False, 'error': 'Provide a directory path to scan.'}), 400
        extensions = _parse_extensions(request.args.get('extensions')) or DEFAULT_EXTENSIONS
        recursive = request.args.get('recursive', 'true').lower() in {'true', '1', 'yes'}
        limit_param = request.args.get('limit')
        try:
            max_entries = int(limit_param) if limit_param else 500
        except ValueError:
            max_entries = 500
        max_entries = max(1, min(max_entries, 5000))

        files: List[Dict[str, Any]] = []
        for root, dirs, filenames in os.walk(target_path):
            filenames.sort()
            for filename in filenames:
                ext = os.path.splitext(filename)[1].lower()
                if extensions and ext not in extensions:
                    continue
                file_path = os.path.join(root, filename)
                try:
                    files.append(_describe_path(file_path, base_path))
                except FileNotFoundError:
                    continue

                if len(files) >= max_entries:
                    break
            if len(files) >= max_entries or not recursive:
                break

        return jsonify({
            'success': True,
            'root': base_path,
            'path': _relative_path(target_path, base_path),
            'count': len(files),
            'limit': max_entries,
            'extensions': sorted(list(extensions)) if extensions else None,
            'files': files
        })
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to scan import staging directory: %s", exc, exc_info=True)
        return jsonify({'success': False, 'error': str(exc)}), 500
