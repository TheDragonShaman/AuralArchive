"""
Module Name: debug_tools.py
Author: TheDragonShaman
Created: July 18, 2025
Last Modified: December 23, 2025
Description:
    Debug-only routes for probing Audible APIs and rendering a protected debug UI.
Location:
    /routes/debug_tools.py

"""

import os
from typing import Optional

from flask import Blueprint, render_template, request, abort, current_app

from services.audible.audible_metadata_sync_service.audible_api_helper import (
    AudibleApiHelper,
)
from utils.logger import get_module_logger

logger = get_module_logger("Routes.DebugTools")

debug_bp = Blueprint("debug_tools", __name__)

DEFAULT_RESPONSE_GROUPS = (
    "contributors, media, price, product_attrs, product_desc, product_details, "
    "product_extended_attrs, product_plan_details, product_plans, rating, sample, sku, "
    "series, reviews, ws4v, origin, relationships, review_attrs, categories, "
    "badge_types, category_ladders, claim_code_url, is_downloaded, is_finished, "
    "is_returnable, origin_asin, pdf_url, percent_complete, periodicals, provided_review"
)


def _get_helper() -> Optional[AudibleApiHelper]:
    helper = AudibleApiHelper()
    if not helper.is_available():
        return None
    return helper


@debug_bp.route("/debug/audible", methods=["GET", "POST"])
def audible_debug_panel():
    """Render debug UI and proxy Audible API calls."""
    asin = (request.form.get("asin") or request.args.get("asin") or "").strip()
    call_type = (
        request.form.get("call_type")
        or request.args.get("call_type")
        or "library_item"
    )
    response_groups = (
        request.form.get("response_groups")
        or request.args.get("response_groups")
        or DEFAULT_RESPONSE_GROUPS
    )

    result = None
    error = None

    if request.method == "POST" and asin:
        helper = _get_helper()
        if not helper:
            error = "Audible authentication is missing. Re-authenticate and try again."
        else:
            try:
                if call_type == "library_item":
                    result = helper.get_library_item(asin, response_groups)
                else:
                    error = f"Unsupported call type: {call_type}"
            except Exception as exc:  # pragma: no cover - debug convenience
                error = str(exc)
                logger.debug("Audible debug call failed: %s", exc, exc_info=True)

    return render_template(
        "debug_audible.html",
        asin=asin,
        call_type=call_type,
        response_groups=response_groups,
        result=result,
        error=error,
    )
