from __future__ import annotations

from math import ceil

from flask import request, url_for


DEFAULT_PER_PAGE = 10


def current_page(default: int = 1) -> int:
    try:
        page = int(request.args.get("page", default))
    except (TypeError, ValueError):
        page = default
    return max(1, page)


def build_pagination(total: int, page: int, per_page: int = DEFAULT_PER_PAGE) -> dict[str, int | bool]:
    total = max(0, int(total or 0))
    per_page = max(1, int(per_page or DEFAULT_PER_PAGE))
    pages = max(1, ceil(total / per_page))
    page = min(max(1, int(page or 1)), pages)
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
        "offset": (page - 1) * per_page,
        "has_prev": page > 1,
        "has_next": page < pages,
        "prev_page": max(1, page - 1),
        "next_page": min(pages, page + 1),
        "start": 0 if total == 0 else ((page - 1) * per_page) + 1,
        "end": min(total, page * per_page),
    }


def page_url(page: int, endpoint: str | None = None) -> str:
    view_args = dict(request.view_args or {})
    args = request.args.to_dict(flat=True)
    args["page"] = page
    return url_for(endpoint or request.endpoint, **view_args, **args)
