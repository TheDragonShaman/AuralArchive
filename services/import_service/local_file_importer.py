import hashlib
import logging
import os
import re
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from services.conversion_service.format_detector import FormatDetector
from services.service_manager import (
    get_database_service,
    get_import_service,
    get_metadata_update_service,
    get_hybrid_audiobook_service,
    get_audnexus_service,
    get_file_naming_service,
)

from .filename_matcher import FilenameMatcher
from .local_metadata_extractor import LocalMetadataExtractor


class LocalFileImportCoordinator:
    """High-level helper that turns local audiobook files into library imports."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("ImportService.LocalCoordinator")
        self.database_service = get_database_service()
        self.import_service = get_import_service()
        self.metadata_service = get_metadata_update_service()
        self.format_detector = FormatDetector()
        self.metadata_extractor = LocalMetadataExtractor()
        self.matcher = FilenameMatcher()
        self.file_naming_service = get_file_naming_service()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def preview_files(self, file_paths: List[str]) -> Dict[str, Any]:
        """Collect lightweight metadata for UI preview before importing."""
        entries = [self._preview_single(path.strip()) for path in file_paths if path and path.strip()]

        summary = {
            'total': len(entries),
            'ready': len([e for e in entries if e['status'] == 'ready']),
            'missing': len([e for e in entries if e['status'] == 'missing']),
            'invalid': len([e for e in entries if e['status'] == 'invalid']),
            'errors': len([e for e in entries if e['status'] == 'error'])
        }

        return {'entries': entries, 'summary': summary}

    def import_files(
        self,
        jobs: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute imports for provided file jobs."""
        options = options or {}
        template = options.get('template_name')
        library_path = options.get('library_path')
        default_move = options.get('move', True)

        results: List[Dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for job in jobs:
            result = self._import_single(job, template, library_path, default_move)
            results.append(result)
            if result.get('success'):
                success_count += 1
            else:
                failure_count += 1

        summary = {
            'total': len(jobs),
            'successful': success_count,
            'failed': failure_count
        }
        return {'summary': summary, 'results': results}

    # ------------------------------------------------------------------
    # Batch preview helpers (new staged workflow)
    # ------------------------------------------------------------------
    def build_batch_preview(
        self,
        file_paths: List[str],
        template_name: Optional[str] = None,
        library_path: Optional[str] = None
    ) -> Dict[str, Any]:
        template_name, library_path = self._resolve_destination_defaults(template_name, library_path)
        cards: List[Dict[str, Any]] = []
        summary = {
            'total': 0,
            'ready': 0,
            'pending': 0,
            'invalid': 0,
            'missing': 0,
            'error': 0,
            'imported': 0
        }

        for file_path in file_paths:
            if not file_path:
                continue
            card = self._build_card_entry(file_path.strip(), template_name, library_path)
            cards.append(card)
            summary['total'] += 1
            summary_key = card.get('status', 'pending')
            if summary_key not in summary:
                summary_key = 'pending'
            summary[summary_key] += 1

        return {
            'cards': cards,
            'summary': summary,
            'template': template_name,
            'library_path': library_path
        }

    def refresh_card_metadata(
        self,
        card: Dict[str, Any],
        asin: Optional[str] = None,
        metadata_override: Optional[Dict[str, Any]] = None,
        template_name: Optional[str] = None,
        library_path: Optional[str] = None
    ) -> Dict[str, Any]:
        template_name, library_path = self._resolve_destination_defaults(
            template_name or card.get('template'),
            library_path or card.get('library_path')
        )

        extracted = card.get('extracted') or {}
        asin_hint = asin or extracted.get('asin')
        title_hint = metadata_override.get('title') if metadata_override else None
        author_hint = metadata_override.get('author') if metadata_override else None

        if not title_hint:
            title_hint = card.get('metadata', {}).get('Title') or extracted.get('title') or extracted.get('clean_title')
        title_hint = self._normalize_search_title(title_hint) if title_hint else None
        if not author_hint:
            author_hint = card.get('metadata', {}).get('Author') or extracted.get('author') or extracted.get('album_artist')

        match_context = {'strategy': 'manual_override', 'confidence': None}
        if metadata_override:
            normalized = self._normalize_metadata(metadata_override, asin_hint, title_hint, author_hint, extracted)
            source = metadata_override.get('source', 'manual_override')
        else:
            normalized, match_context = self._resolve_metadata_snapshot(asin_hint, title_hint, author_hint, extracted)
            source = normalized.get('source', 'manual_import') if normalized else 'manual_import'

        if not normalized:
            normalized = self._build_fallback_book(asin_hint, title_hint, author_hint, extracted)
            source = 'manual_import'
            match_context = {'strategy': 'fallback', 'confidence': None}

        normalized = self._persist_metadata_for_card(normalized) or normalized

        destination = self._generate_destination_preview(normalized, template_name, library_path, card['source_path'])

        card.update({
            'metadata': normalized,
            'source': source,
            'destination': destination,
            'template': template_name,
            'library_path': library_path,
            'status': 'ready' if card.get('status') == 'ready' else card.get('status', 'pending'),
            'match': match_context
        })
        return card

    def import_prepared_cards(
        self,
        cards: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        options = options or {}
        template = options.get('template_name')
        library_path = options.get('library_path')
        move = options.get('move', True)

        results: List[Dict[str, Any]] = []
        success = failure = 0

        for card in cards:
            metadata = (card.get('metadata') or {}).copy()
            if not metadata:
                failure += 1
                results.append({
                    'path': card.get('source_path'),
                    'success': False,
                    'message': 'No metadata available for this card',
                    'destination_path': None
                })
                continue

            metadata = self._persist_metadata_for_card(metadata) or metadata

            template_name, library_root = self._resolve_destination_defaults(
                card.get('template') or template,
                card.get('library_path') or library_path
            )

            import_source = card.get('source') or metadata.get('source')
            if not import_source or import_source in ('audible', 'audible_catalog'):
                import_source = 'manual_import'

            try:
                ok, message, destination = self.import_service.import_book(
                    source_file_path=card['source_path'],
                    book_data=metadata,
                    template_name=template_name,
                    library_path=library_root,
                    move=move,
                    import_source=import_source
                )
            except Exception as exc:  # pragma: no cover - defensive
                ok, message, destination = False, str(exc), None

            if ok:
                success += 1
            else:
                failure += 1

            results.append({
                'path': card.get('source_path'),
                'success': ok,
                'message': message,
                'destination_path': destination
            })

        return {
            'summary': {
                'total': len(cards),
                'successful': success,
                'failed': failure
            },
            'results': results
        }

    def search_metadata_candidates(
        self,
        query: Optional[str] = None,
        author: Optional[str] = None,
        asin: Optional[str] = None,
        limit: int = 10
    ) -> Dict[str, Any]:
        """Return potential metadata matches for manual remapping UI."""

        limit = max(1, min(limit or 10, 50))
        raw_query = (query or '').strip()
        normalized_query = self._normalize_search_title(raw_query) if raw_query else ''
        search_query = normalized_query or raw_query
        query_display = raw_query or search_query
        author = (author or '').strip()
        asin = asin.strip().upper() if isinstance(asin, str) and asin.strip() else None

        results: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        extracted_stub = {
            'source_path': '',
            'clean_title': search_query,
            'title': search_query,
            'author': author
        }

        def add_candidate(metadata: Optional[Dict[str, Any]], strategy: str, confidence: Optional[float]) -> None:
            if not metadata:
                return
            asin_value = metadata.get('ASIN') or metadata.get('asin') or asin
            title_hint_raw = metadata.get('Title') or metadata.get('title') or search_query
            title_hint = self._normalize_search_title(title_hint_raw) if title_hint_raw else search_query
            author_hint_local = metadata.get('Author') or metadata.get('author') or author

            enriched = metadata
            if asin_value:
                try:
                    existing = self.database_service.get_book_by_asin(asin_value)
                except Exception:
                    existing = None
                if existing:
                    enriched = existing
                elif not self._metadata_has_multiple_authors(metadata):
                    external = self._lookup_external_metadata(asin_value, title_hint or query, author_hint_local or author)
                    if external:
                        enriched = external

            normalized = self._normalize_metadata(
                enriched,
                asin_value,
                title_hint,
                author_hint_local,
                extracted_stub
            )
            candidate_asin = normalized.get('ASIN')
            dedupe_key = candidate_asin or f"{normalized.get('Title')}::{normalized.get('Author')}"
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            results.append({
                'asin': candidate_asin,
                'metadata': normalized,
                'source': normalized.get('source', strategy),
                'match': {'strategy': strategy, 'confidence': confidence}
            })

        if asin:
            try:
                existing = self.database_service.get_book_by_asin(asin)
            except Exception:
                existing = None
            add_candidate(existing, 'library_asin', 1.0)

            if len(results) < limit:
                external = self._lookup_external_metadata(asin, search_query or None, author or None)
                add_candidate(external, 'external_asin', 0.9)

        if search_query:
            try:
                library_matches = self.database_service.search_books(search_query)
            except Exception:
                library_matches = []

            for match in library_matches:
                add_candidate(match, 'library_search', 0.75)
                if len(results) >= limit:
                    break

            if len(results) < limit:
                try:
                    hybrid_service = get_hybrid_audiobook_service()
                except Exception:
                    hybrid_service = None

                if hybrid_service:
                    try:
                        hybrid_matches = hybrid_service.search_books(search_query, num_results=max(limit * 2, 10)) or []
                    except Exception:
                        hybrid_matches = []

                    title_lower = search_query.lower()
                    author_lower = author.lower() if author else ''
                    for candidate in hybrid_matches:
                        cand_title = (candidate.get('Title') or candidate.get('title') or '').strip()
                        if not cand_title:
                            continue
                        cand_author = (candidate.get('Author') or candidate.get('author') or '').strip()
                        score = SequenceMatcher(None, title_lower, cand_title.lower()).ratio()
                        if author_lower and cand_author:
                            cand_author_lower = cand_author.lower()
                            if author_lower in cand_author_lower or cand_author_lower in author_lower:
                                score += 0.1
                        if score < 0.45:
                            continue
                        add_candidate(candidate, 'hybrid_search', min(score, 1.0))
                        if len(results) >= limit:
                            break

            if len(results) < limit and author:
                audnexus_candidate = self._lookup_audnexus_metadata(search_query, author)
                add_candidate(audnexus_candidate, 'audnexus_search', 0.65)

        return {
            'query': query_display,
            'normalized_query': search_query,
            'author': author,
            'asin': asin,
            'results': results[:limit],
            'count': min(len(results), limit)
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _preview_single(self, file_path: str) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            'path': file_path,
            'status': 'pending',
            'messages': [],
            'size_bytes': None,
            'format': 'unknown',
            'asin': None,
            'title': None,
            'author': None,
            'narrator': None,
            'series': None,
            'sequence': None,
            'duration_seconds': None,
            'exists_in_library': False
        }

        if not file_path:
            entry['status'] = 'error'
            entry['messages'].append('No file path provided')
            return entry

        if not os.path.exists(file_path):
            entry['status'] = 'missing'
            entry['messages'].append('File not found on server')
            return entry

        try:
            entry['size_bytes'] = os.path.getsize(file_path)
        except OSError as exc:
            entry['messages'].append(f'Unable to read file size: {exc}')

        validation = self.format_detector.validate_input_file(file_path)
        if validation.get('valid'):
            entry['format'] = validation.get('format', 'unknown')
            entry['status'] = 'ready'
        else:
            entry['status'] = 'invalid'
            if validation.get('error'):
                entry['messages'].append(validation['error'])

        extracted = self.metadata_extractor.extract_metadata(file_path)
        entry['asin'] = extracted.get('asin')
        entry['title'] = extracted.get('title') or extracted.get('clean_title')
        entry['author'] = extracted.get('author') or extracted.get('album_artist')
        entry['narrator'] = extracted.get('narrator')
        entry['series'] = extracted.get('series')
        entry['sequence'] = extracted.get('sequence')
        entry['duration_seconds'] = extracted.get('duration_seconds')

        asin = entry['asin']
        if asin:
            try:
                entry['exists_in_library'] = self.database_service.get_book_by_asin(asin) is not None
            except Exception as exc:  # pragma: no cover - defensive path
                entry['messages'].append(f'Database lookup failed: {exc}')

        entry['messages'].extend(extracted.get('warnings', []))
        return entry

    def _import_single(
        self,
        job: Dict[str, Any],
        template: Optional[str],
        library_path: Optional[str],
        default_move: bool
    ) -> Dict[str, Any]:
        file_path = (job.get('path') or '').strip()
        response: Dict[str, Any] = {
            'path': file_path,
            'success': False,
            'message': None,
            'destination_path': None,
            'asin': None,
            'title': None
        }

        if not file_path:
            response['message'] = 'No file path provided'
            return response

        if not os.path.exists(file_path):
            response['message'] = 'File does not exist or is not accessible to the server'
            return response

        validation = self.format_detector.validate_input_file(file_path)
        if not validation.get('valid'):
            response['message'] = validation.get('error', 'Unsupported or unreadable audio file')
            return response

        extracted = self.metadata_extractor.extract_metadata(file_path)
        asin_hint = job.get('asin') or extracted.get('asin')
        if not asin_hint:
            asin_hint = self.matcher.extract_asin_from_filename(extracted.get('filename') or os.path.basename(file_path))
        title_hint = job.get('title') or extracted.get('title') or extracted.get('clean_title') or extracted.get('filename')
        title_hint = self._normalize_search_title(title_hint) if title_hint else None
        author_hint = job.get('author') or extracted.get('author') or extracted.get('album_artist')

        try:
            book_data = self._resolve_book_record(asin_hint, title_hint, author_hint, extracted)
        except Exception as exc:
            self.logger.error("Unable to resolve metadata for %s: %s", file_path, exc, exc_info=True)
            response['message'] = f'Metadata resolution failed: {exc}'
            return response

        if not book_data:
            response['message'] = 'Unable to determine metadata for this file'
            return response

        asin = book_data.get('ASIN') or book_data.get('asin')
        response['asin'] = asin
        response['title'] = book_data.get('Title') or book_data.get('title')

        move_flag = bool(job.get('move', default_move))
        job_source = job.get('source') or book_data.get('source')
        if not job_source or job_source in ('audible', 'audible_catalog'):
            job_source = 'manual_import'

        success, message, destination = self.import_service.import_book(
            source_file_path=file_path,
            book_data=book_data,
            template_name=job.get('template_name', template),
            library_path=job.get('library_path', library_path),
            move=move_flag,
            import_source=job_source
        )

        response['success'] = success
        response['message'] = message
        response['destination_path'] = destination
        return response

    def _resolve_book_record(
        self,
        asin_hint: Optional[str],
        title_hint: Optional[str],
        author_hint: Optional[str],
        extracted: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        metadata, _ = self._resolve_metadata_snapshot(asin_hint, title_hint, author_hint, extracted)
        if not metadata:
            return None
        return self._ensure_book_in_database(metadata)

    def _resolve_metadata_snapshot(
        self,
        asin_hint: Optional[str],
        title_hint: Optional[str],
        author_hint: Optional[str],
        extracted: Dict[str, Any]
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        match_context = {'strategy': 'fallback', 'confidence': None}
        if title_hint:
            title_hint = self._normalize_search_title(title_hint)
        asin = asin_hint.upper() if asin_hint else None

        if asin:
            existing = self.database_service.get_book_by_asin(asin)
            if existing:
                match_context = {'strategy': 'library_asin', 'confidence': 1.0}
                return existing, match_context

        existing = self._find_existing_by_title_author(title_hint, author_hint)
        if existing:
            match_context = {'strategy': 'library_title', 'confidence': 0.9}
            return existing, match_context

        lookup_source = None
        metadata_payload = self._lookup_external_metadata(asin, title_hint, author_hint)
        if metadata_payload:
            lookup_source = 'audible_metadata'
        else:
            metadata_payload = self._lookup_hybrid_metadata(title_hint, author_hint)
            if metadata_payload:
                lookup_source = 'hybrid_search'
            else:
                metadata_payload = self._lookup_audnexus_metadata(title_hint, author_hint)
                if metadata_payload:
                    lookup_source = 'audnexus_author'

        if metadata_payload:
            normalized = self._normalize_metadata(metadata_payload, asin, title_hint, author_hint, extracted)
            match_context = {
                'strategy': lookup_source or 'external_lookup',
                'confidence': metadata_payload.get('_match_confidence') if isinstance(metadata_payload, dict) else None
            }
        else:
            normalized = self._build_fallback_book(asin, title_hint, author_hint, extracted)
            match_context = {'strategy': 'fallback', 'confidence': None}

        return normalized, match_context

    def _find_existing_by_title_author(self, title: Optional[str], author: Optional[str]) -> Optional[Dict[str, Any]]:
        if not title:
            return None
        try:
            matches = self.database_service.search_books(title)
        except Exception:
            return None

        title_lower = title.lower()
        author_lower = author.lower() if author else None
        for match in matches:
            match_title = (match.get('Title') or '').lower()
            if title_lower not in match_title and match_title not in title_lower:
                continue
            if author_lower:
                match_author = (match.get('Author') or '').lower()
                if match_author and author_lower not in match_author and match_author not in author_lower:
                    continue
            return match
        return None

    def _lookup_external_metadata(
        self,
        asin: Optional[str],
        title: Optional[str],
        author: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        if not self.metadata_service:
            return None
        try:
            prepare = getattr(self.metadata_service, '_ensure_dependencies', None)
            if callable(prepare):
                prepare()
            searcher = getattr(self.metadata_service, 'search_strategies', None)
            if not searcher:
                return None
            return searcher.search_for_book_metadata(title or '', author or '', asin or '')
        except Exception as exc:
            self.logger.warning("Metadata lookup failed for %s/%s: %s", title, author, exc)
            return None

    def _lookup_hybrid_metadata(
        self,
        title: Optional[str],
        author: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Fallback search using the hybrid catalog service when metadata strategies fail."""

        if not title:
            return None

        try:
            hybrid_service = get_hybrid_audiobook_service()
        except Exception as exc:
            self.logger.debug("Hybrid service unavailable for title '%s': %s", title, exc)
            return None

        if not hybrid_service:
            return None

        queries: List[str] = []
        title_clean = title.strip()
        author_clean = (author or '').strip()

        if title_clean and author_clean:
            queries.append(f"{title_clean} {author_clean}")
        if title_clean:
            queries.append(title_clean)

        for query in queries:
            try:
                results = hybrid_service.search_books(query, num_results=15)
            except Exception as exc:
                self.logger.debug("Hybrid search failed for query '%s': %s", query, exc)
                continue

            best_match = self._select_best_hybrid_match(results, title_clean, author_clean)
            if best_match:
                self.logger.info("Hybrid lookup matched '%s' to '%s'", title_clean, best_match.get('Title'))
                return best_match

        self.logger.debug("Hybrid lookup found no suitable matches for '%s'", title_clean)
        return None

    def _lookup_audnexus_metadata(
        self,
        title: Optional[str],
        author: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Fallback search using the Audnexus author catalog when Audible APIs fail."""

        if not title or not author:
            return None

        try:
            audnexus_service = get_audnexus_service()
        except Exception as exc:
            self.logger.debug("Audnexus service unavailable for '%s': %s", title, exc)
            return None

        if not audnexus_service:
            return None

        title_clean = title.strip()
        author_clean = author.strip()
        if not title_clean or not author_clean:
            return None

        try:
            author_details = audnexus_service.find_author_by_name(author_clean)
        except Exception as exc:
            self.logger.debug("Audnexus author lookup failed for '%s': %s", author_clean, exc)
            return None

        if not author_details:
            return None

        candidates = author_details.get('titles', []) or []
        if not candidates:
            self.logger.debug("Audnexus author '%s' has no titles to evaluate", author_clean)
            return None

        best_match = self._select_best_audnexus_match(candidates, title_clean)
        if not best_match:
            self.logger.debug("Audnexus lookup found author '%s' but no matching title for '%s'", author_clean, title_clean)
            return None

        region = author_details.get('region', 'us') if isinstance(author_details, dict) else 'us'
        asin = best_match.get('asin') or best_match.get('ASIN')

        if asin:
            try:
                detailed = audnexus_service.get_book_details(asin, region=region)
            except Exception as exc:
                self.logger.debug("Audnexus book detail fetch failed for %s: %s", asin, exc)
            else:
                if detailed:
                    formatted = audnexus_service.format_book_for_compatibility(detailed)
                    formatted['source'] = 'audnexus'
                    self.logger.info("Audnexus lookup matched '%s' to '%s'", title_clean, formatted.get('Title'))
                    return formatted

        formatted = audnexus_service.format_book_for_compatibility(best_match)
        formatted['source'] = 'audnexus'
        self.logger.info("Audnexus lookup matched '%s' via author '%s' without detail fetch", title_clean, author_clean)
        return formatted

    def _select_best_hybrid_match(
        self,
        candidates: List[Dict[str, Any]],
        title_hint: str,
        author_hint: str
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None

        title_lower = title_hint.lower()
        author_lower = author_hint.lower() if author_hint else ''
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for candidate in candidates:
            cand_title = (candidate.get('Title') or '').strip()
            cand_author = (candidate.get('Author') or '').strip()
            cand_title_lower = cand_title.lower()
            cand_author_lower = cand_author.lower()

            if not cand_title:
                continue

            title_score = SequenceMatcher(None, title_lower, cand_title_lower).ratio()

            if title_lower in cand_title_lower or cand_title_lower in title_lower:
                title_score += 0.2

            if author_lower:
                if author_lower in cand_author_lower or cand_author_lower in author_lower:
                    title_score += 0.1

            if title_score > best_score and title_score >= 0.55:
                best_score = title_score
                best = candidate

            if title_score >= 0.95:
                return candidate

        return best

    def _select_best_audnexus_match(
        self,
        candidates: List[Dict[str, Any]],
        title_hint: str
    ) -> Optional[Dict[str, Any]]:
        if not candidates:
            return None

        title_lower = title_hint.lower()
        best: Optional[Dict[str, Any]] = None
        best_score = 0.0

        for candidate in candidates:
            cand_title = (candidate.get('Title') or candidate.get('title') or '').strip()
            if not cand_title:
                continue

            cand_lower = cand_title.lower()
            score = SequenceMatcher(None, title_lower, cand_lower).ratio()
            if title_lower in cand_lower or cand_lower in title_lower:
                score += 0.25

            if score > best_score and score >= 0.5:
                best_score = score
                best = candidate

            if score >= 0.95:
                return candidate

        return best

    def _normalize_metadata(
        self,
        metadata: Dict[str, Any],
        asin_hint: Optional[str],
        title_hint: Optional[str],
        author_hint: Optional[str],
        extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        def pick(*keys: str, default: Optional[str] = None) -> Optional[str]:
            for key in keys:
                if key in metadata and metadata[key]:
                    value = metadata[key]
                    if isinstance(value, list):
                        flattened = [str(item).strip() for item in value if item]
                        if flattened:
                            return ', '.join(flattened)
                        continue
                    return value
            return default

        title = pick('Title', 'title', default=title_hint)
        authors_value = pick('Author', 'author', 'authors', default=author_hint)
        if isinstance(authors_value, list):
            author = ', '.join(authors_value)
        else:
            author = authors_value

        asin = asin_hint or pick('ASIN', 'asin')
        narrator = pick('Narrator', 'narrator', default=extracted.get('narrator'))
        series = pick('Series', 'series', default=extracted.get('series') or '').strip()
        if series.upper() == 'N/A':
            series = ''

        sequence = pick('Sequence', 'sequence', default=extracted.get('sequence') or '').strip()
        if sequence.upper() == 'N/A':
            sequence = ''
        publisher = pick('Publisher', 'publisher', default=extracted.get('publisher') or 'Unknown Publisher')
        release = pick('Release Date', 'release_date', default=extracted.get('year') or 'Unknown Release Date')
        runtime_minutes = metadata.get('runtime_length_min') or metadata.get('runtime_length')
        runtime = self._format_runtime(runtime_minutes, extracted.get('duration_seconds'))
        summary = pick('Summary', 'summary') or f'Manually imported audiobook ({title or "Unknown Title"}).'
        cover_image = pick('Cover Image', 'cover_image', 'cover_image_url') or ''

        normalized = {
            'ASIN': asin or self._generate_manual_asin(title or extracted.get('filename')),
            'Title': title or extracted.get('clean_title') or extracted.get('filename') or 'Untitled Import',
            'Author': author or 'Unknown Author',
            'Narrator': narrator or 'Unknown Narrator',
            'Series': series or '',
            'Sequence': sequence,
            'Publisher': publisher,
            'Release Date': release,
            'Runtime': runtime,
            'Summary': summary,
            'Cover Image': cover_image,
            'Language': pick('Language', 'language', default='English'),
            'Overall Rating': pick('Overall Rating', 'overall_rating', 'rating', default='N/A'),
            'Rating': pick('Rating', 'rating', default='N/A'),
            'num_ratings': metadata.get('num_ratings') or metadata.get('ratings', 0),
            'source': metadata.get('source', 'audible'),
            'ownership_status': 'owned',
            'Status': 'Owned',
            'file_path': extracted.get('source_path')
        }
        return normalized

    def _build_fallback_book(
        self,
        asin_hint: Optional[str],
        title_hint: Optional[str],
        author_hint: Optional[str],
        extracted: Dict[str, Any]
    ) -> Dict[str, Any]:
        runtime = self._format_runtime(None, extracted.get('duration_seconds'))
        series = (extracted.get('series') or '').strip()
        if series.upper() == 'N/A':
            series = ''

        sequence = (extracted.get('sequence') or '').strip()
        if sequence.upper() == 'N/A':
            sequence = ''
        return {
            'ASIN': asin_hint or self._generate_manual_asin(title_hint or extracted.get('filename')),
            'Title': title_hint or extracted.get('clean_title') or extracted.get('filename') or 'Untitled Import',
            'Author': author_hint or extracted.get('author') or 'Unknown Author',
            'Narrator': extracted.get('narrator') or 'Unknown Narrator',
            'Series': series,
            'Sequence': sequence,
            'Publisher': extracted.get('publisher') or 'Unknown Publisher',
            'Release Date': extracted.get('year') or 'Unknown Release Date',
            'Runtime': runtime or 'Unknown Runtime',
            'Summary': f'Manually imported from {os.path.basename(extracted.get("source_path", "unknown"))}',
            'Cover Image': '',
            'Language': 'English',
            'Overall Rating': 'N/A',
            'Rating': 'N/A',
            'num_ratings': 0,
            'source': 'manual_import',
            'ownership_status': 'owned',
            'Status': 'Owned',
            'file_path': extracted.get('source_path')
        }

    def _get_existing_book(self, asin: Optional[str]) -> Optional[Dict[str, Any]]:
        if not asin:
            return None
        try:
            return self.database_service.get_book_by_asin(asin)
        except Exception as exc:
            self.logger.debug("Unable to load existing metadata for %s: %s", asin, exc)
            return None

    def _format_runtime(self, runtime_minutes: Optional[Any], duration_seconds: Optional[Any]) -> Optional[str]:
        minutes = None
        if runtime_minutes:
            try:
                minutes = float(runtime_minutes)
            except (TypeError, ValueError):
                minutes = None
        if minutes is None and duration_seconds:
            try:
                minutes = float(duration_seconds) / 60.0
            except (TypeError, ValueError):
                minutes = None
        if minutes is None:
            return None
        hours = int(minutes // 60)
        mins = int(round(minutes % 60))
        return f"{hours} hrs {mins} mins"

    def _generate_manual_asin(self, seed: Optional[str]) -> str:
        cleaned = (seed or 'MANUAL').upper().replace(' ', '')[:6]
        return f"MANUAL-{cleaned}-{uuid.uuid4().hex[:6].upper()}"

    @staticmethod
    def _metadata_has_multiple_authors(metadata: Optional[Dict[str, Any]]) -> bool:
        if not metadata:
            return False
        author_fields = []
        for key in ('Authors', 'authors', 'Author', 'author'):
            value = metadata.get(key)
            if value:
                author_fields.append(value)
        for value in author_fields:
            if isinstance(value, list) and len(value) > 1:
                return True
            if isinstance(value, str) and ',' in value:
                return True
        return False

    # ------------------------------------------------------------------
    # Internal helpers for batch mode
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_search_title(raw: Optional[str]) -> str:
        if not raw:
            return ''

        text = str(raw).strip()
        # Drop directory paths and extensions (in case a filename slipped through)
        text = os.path.basename(text)
        text = os.path.splitext(text)[0]

        # Remove trailing bracketed tags like [MANUAL-XXXX]
        text = re.sub(r"\s*\[[^\]]+\]\s*$", '', text)

        # Replace underscores/double spaces with single spaces
        text = text.replace('_', ' ')

        # Normalize numbered book indicators (Book 002 -> Book 2)
        def _normalize_number(match: re.Match) -> str:
            label = match.group(1)
            number = match.group(2)
            try:
                number_val = str(int(number))
            except ValueError:
                number_val = number.lstrip('0') or number
            return f"{label} {number_val}"

        text = re.sub(
            r"\b(Book|Bk|Volume|Vol|Part|Episode)\s+0*([0-9]+)\b",
            _normalize_number,
            text,
            flags=re.IGNORECASE
        )

        # Collapse repeated punctuation/whitespace and trim
        text = re.sub(r"\s+", ' ', text)
        text = re.sub(r"\s*[:;,]\s*", lambda m: f"{m.group(0).strip()} ", text)
        text = text.strip(" .-:_")
        return text

    def _build_card_entry(
        self,
        file_path: str,
        template_name: str,
        library_path: str
    ) -> Dict[str, Any]:
        extracted = self.metadata_extractor.extract_metadata(file_path)
        preview = self._preview_single(file_path)
        card_id = hashlib.sha1(file_path.encode('utf-8')).hexdigest()

        card = {
            'card_id': card_id,
            'source_path': file_path,
            'status': preview['status'],
            'format': preview.get('format'),
            'size_bytes': preview.get('size_bytes'),
            'duration_seconds': preview.get('duration_seconds'),
            'messages': preview.get('messages', []),
            'extracted': extracted,
            'template': template_name,
            'library_path': library_path,
        }

        if preview['status'] == 'ready':
            try:
                metadata, match_context = self._resolve_metadata_snapshot(
                    preview.get('asin'),
                    preview.get('title'),
                    preview.get('author'),
                    extracted
                )
            except Exception as exc:  # pragma: no cover - defensive
                self.logger.warning("Unable to resolve metadata for %s: %s", file_path, exc)
                metadata, match_context = None, {'strategy': 'error', 'confidence': None}
        else:
            metadata, match_context = None, {'strategy': preview['status'], 'confidence': None}

        if not metadata:
            metadata = self._build_fallback_book(preview.get('asin'), preview.get('title'), preview.get('author'), extracted)
            card['status'] = 'invalid' if preview['status'] != 'ready' else 'ready'
            match_context = {'strategy': 'fallback', 'confidence': None}

        metadata = self._persist_metadata_for_card(metadata) or metadata

        card['metadata'] = metadata
        card['destination'] = self._generate_destination_preview(metadata, template_name, library_path, file_path)
        card['source'] = metadata.get('source', 'manual_import')
        card['match'] = match_context
        return card

    def _persist_metadata_for_card(self, metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not metadata:
            return None
        asin = metadata.get('ASIN') or metadata.get('asin')
        try:
            stored = self._get_existing_book(asin)
            if stored:
                if asin and stored.get('ASIN') != asin:
                    self.logger.debug("Metadata ASIN remapped from %s to %s", asin, stored.get('ASIN'))
                return stored
        except Exception as exc:
            self.logger.warning("Unable to load existing metadata for '%s': %s", metadata.get('Title'), exc)
        return metadata

    def _generate_destination_preview(
        self,
        metadata: Dict[str, Any],
        template_name: str,
        library_path: str,
        source_path: str
    ) -> Dict[str, Any]:
        try:
            file_extension = Path(source_path).suffix.lstrip('.') or 'm4b'
            full_path = self.file_naming_service.generate_file_path(
                book_data=metadata,
                base_path=library_path,
                template_name=template_name,
                file_extension=file_extension
            )
            return {
                'full_path': full_path,
                'folder': os.path.dirname(full_path),
                'filename': os.path.basename(full_path),
                'template': template_name,
                'library_path': library_path
            }
        except Exception as exc:
            self.logger.warning("Unable to generate destination preview for %s: %s", metadata.get('Title'), exc)
            return {
                'full_path': None,
                'folder': None,
                'filename': None,
                'error': str(exc)
            }

    def _resolve_destination_defaults(
        self,
        template_name: Optional[str],
        library_path: Optional[str]
    ) -> Tuple[str, str]:
        load_config = getattr(self.import_service, '_load_configuration', None)
        if callable(load_config):
            load_config()

        default_template = getattr(self.import_service, 'naming_template', 'standard')
        default_library = getattr(self.import_service, 'library_base_path', '/mnt/audiobooks')

        return template_name or default_template, library_path or default_library


__all__ = ['LocalFileImportCoordinator']
