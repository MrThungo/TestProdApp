from __future__ import annotations

from collections.abc import Callable, Iterable

from flask import Response, request, stream_with_context


ByteStream = Callable[[], Iterable[bytes]]
RangeByteStream = Callable[[int, int], Iterable[bytes]]


def inline_disposition(filename: str | None, fallback: str) -> str:
    safe_name = (filename or fallback or "media").strip()
    for character in ("\r", "\n", '"', "\\", "/"):
        safe_name = safe_name.replace(character, "_")
    return f'inline; filename="{safe_name or fallback or "media"}"'


def _parse_range_header(range_header: str, total_size: int) -> tuple[int, int] | None:
    if total_size <= 0 or not range_header.startswith("bytes="):
        return None

    spec = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
    if "-" not in spec:
        return None

    start_text, end_text = spec.split("-", 1)
    try:
        if not start_text:
            suffix_size = int(end_text)
            if suffix_size <= 0:
                return None
            return max(total_size - suffix_size, 0), total_size - 1

        start = int(start_text)
        end = int(end_text) if end_text else total_size - 1
    except ValueError:
        return None

    if start < 0 or start >= total_size or end < start:
        return None
    return start, min(end, total_size - 1)


def media_response(
    *,
    stream_factory: ByteStream,
    range_factory: RangeByteStream,
    mime_type: str,
    size_bytes: int,
    cache_control: str,
    content_disposition: str,
    etag: str | None = None,
) -> Response:
    base_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": cache_control,
        "Content-Disposition": content_disposition,
    }

    if etag and request.if_none_match.contains(etag):
        response = Response(status=304, headers={"Cache-Control": cache_control})
        response.set_etag(etag)
        return response

    byte_range = _parse_range_header(request.headers.get("Range", ""), size_bytes)
    if byte_range is not None:
        start, end = byte_range
        length = end - start + 1
        response = Response(
            stream_with_context(range_factory(start, length)),
            status=206,
            mimetype=mime_type,
            headers={
                **base_headers,
                "Content-Length": str(length),
                "Content-Range": f"bytes {start}-{end}/{size_bytes}",
            },
        )
    elif request.headers.get("Range"):
        response = Response(
            status=416,
            headers={**base_headers, "Content-Range": f"bytes */{size_bytes}"},
        )
    else:
        response = Response(
            stream_with_context(stream_factory()),
            mimetype=mime_type,
            headers={**base_headers, "Content-Length": str(size_bytes)},
        )

    if etag:
        response.set_etag(etag)
    return response
