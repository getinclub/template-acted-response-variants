"""A deliberately narrow, deterministic response-variant cache model."""
import math
import re
from copy import deepcopy
TOKEN = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")

def _number(value):
    try:
        finite = math.isfinite(value) if isinstance(value, (int, float)) else False
    except (OverflowError, ValueError):
        finite = False
    if isinstance(value, bool) or not finite or value < 0:
        raise ValueError("time and lifetime must be finite nonnegative numbers")
    return value

def _headers(headers):
    if not isinstance(headers, dict):
        raise ValueError("headers must be a dictionary")
    out = {}
    for name, value in headers.items():
        if not isinstance(name, str) or not TOKEN.fullmatch(name):
            raise ValueError("invalid header name")
        key = name.lower()
        if key in out or not isinstance(value, str) or "\r" in value or "\n" in value:
            raise ValueError("ambiguous header name or invalid value")
        out[key] = value
    return out

def _tokens(value, allowed=None):
    if not isinstance(value, str):
        raise ValueError("metadata must be a string")
    if value == "":
        return []
    parts = [x.strip(" \t").lower() for x in value.split(",")]
    if any(not TOKEN.fullmatch(x) for x in parts):
        raise ValueError("invalid comma-separated token list")
    if allowed is not None and any(x not in allowed for x in parts):
        raise ValueError("unsupported directive")
    return sorted(set(parts))

def _request(method, url, headers):
    if not isinstance(method, str) or not TOKEN.fullmatch(method):
        raise ValueError("invalid method")
    if not isinstance(url, str) or not url or any(c in url for c in "\r\n"):
        raise ValueError("invalid URL key")
    return _headers(headers)

def capture_entry(method, url, request_headers, body, *, vary="", cache_control="public", stored_at=0, max_age=60):
    """Capture a cache record, or None for a policy-excluded response."""
    headers = _request(method, url, request_headers)
    names = _tokens(vary)
    directives = _tokens(cache_control, {"public", "no-store"})
    _number(stored_at)
    _number(max_age)
    _number(stored_at + max_age)
    if not isinstance(body, str):
        raise ValueError("body must be a string")
    if method != "GET" or "*" in names or "no-store" in directives:
        return None
    return {"method": method, "url": url, "request_headers": headers,
            "body": body, "vary": names, "stored_at": stored_at, "max_age": max_age}

def _validated(entry):
    expected = {"method", "url", "request_headers", "body", "vary", "stored_at", "max_age"}
    if not isinstance(entry, dict) or set(entry) != expected:
        raise ValueError("invalid entry fields")
    names = entry["vary"]
    if not isinstance(names, list) or any(not isinstance(x, str) or not TOKEN.fullmatch(x) or x != x.lower() or x == "*" for x in names) or names != sorted(set(names)):
        raise ValueError("invalid captured vary names")
    record = capture_entry(entry["method"], entry["url"], entry["request_headers"], entry["body"], vary=",".join(names), stored_at=entry["stored_at"], max_age=entry["max_age"])
    if record is None or entry["request_headers"] != record["request_headers"]:
        raise ValueError("invalid captured entry")
    return record

def select_variant(entries, method, url, request_headers, now):
    """BUG: URL-only reuse. Repair this function to satisfy the README contract."""
    _request(method, url, request_headers)
    _number(now)
    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    records = [_validated(entry) for entry in entries]
    if method != "GET":
        return None
    for entry in reversed(records):
        if entry["url"] == url:
            return deepcopy(entry)
    return None
