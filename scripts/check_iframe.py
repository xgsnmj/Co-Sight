#!/usr/bin/env python3
import sys
import re
from typing import Optional, Tuple

import requests


def _safe_get(url: str, method: str = "HEAD", timeout: float = 10.0) -> requests.Response:
    try:
        if method.upper() == "HEAD":
            resp = requests.head(url, allow_redirects=True, timeout=timeout, headers={
                "User-Agent": "iframe-checker/1.0"
            })
        else:
            resp = requests.get(url, allow_redirects=True, timeout=timeout, headers={
                "User-Agent": "iframe-checker/1.0"
            }, stream=True)
        return resp
    except requests.RequestException as e:
        raise RuntimeError(f"request failed: {e}")


def parse_xfo(xfo: Optional[str]) -> Optional[str]:
    if not xfo:
        return None
    value = xfo.strip().lower()
    # Normalize common values
    return value


def parse_csp_frame_ancestors(csp: Optional[str]) -> Optional[str]:
    if not csp:
        return None
    # Split directives by ';'
    directives = [d.strip() for d in csp.split(';') if d.strip()]
    for d in directives:
        if d.lower().startswith('content-security-policy:'):
            # Sometimes servers accidentally repeat header name
            d = d.split(':', 1)[1].strip()
        parts = d.split(None, 1)
        if not parts:
            continue
        if parts[0].lower() == 'frame-ancestors':
            return parts[1].strip() if len(parts) > 1 else ""
    return None


def extract_meta_csp(html_sample: str) -> Optional[str]:
    # Look for <meta http-equiv="Content-Security-Policy" content="...">
    pattern = re.compile(r'<meta[^>]*http-equiv=["\']content-security-policy["\'][^>]*content=["\']([^"\']+)["\'][^>]*>', re.I)
    m = pattern.search(html_sample)
    if m:
        return m.group(1)
    return None


def decide_iframe_allowed(xfo: Optional[str], fa: Optional[str]) -> Tuple[bool, str]:
    # X-Frame-Options precedence: if present and DENY/SAMEORIGIN typically blocks embedding across sites
    if xfo:
        if 'deny' in xfo:
            return False, f"Blocked by X-Frame-Options: {xfo}"
        if 'sameorigin' in xfo:
            return False, f"Likely blocked by X-Frame-Options: {xfo}"
        if 'allow-from' in xfo:
            return False, f"Non-standard X-Frame-Options: {xfo} (likely restricted)"

    # CSP frame-ancestors: if specified and not '*' or 'self', treat as restricted for generic embedding
    if fa is not None:
        fa_l = fa.lower()
        if fa_l in ('\'none\'', "'none'"):
            return False, "Blocked by CSP frame-ancestors 'none'"
        # If only specific origins are allowed, be conservative and say restricted
        tokens = fa_l.split()
        if "*" in tokens:
            return True, "Allowed by CSP frame-ancestors *"
        if "'self'" in tokens or "'self'" in fa_l:
            return False, "Likely restricted to same-origin by CSP frame-ancestors"
        # Specific origins present -> likely restricted
        return False, f"Likely restricted by CSP frame-ancestors: {fa}"

    # No blocking headers found
    return True, "No X-Frame-Options or CSP frame-ancestors restrictions detected"


def main():
    # 在此处配置检测用 URL 与超时时间（秒）
    url = 'https://www.tripadvisor.ie/ShowTopic-g187768-i20-k15202342-Italy_Trip_Reviews_October_2024-Italy.html'
    timeout_seconds = 10.0

    try:
        # Try HEAD first
        resp = _safe_get(url, method="HEAD", timeout=timeout_seconds)
        xfo = parse_xfo(resp.headers.get('X-Frame-Options') or resp.headers.get('x-frame-options'))
        fa = parse_csp_frame_ancestors(resp.headers.get('Content-Security-Policy') or resp.headers.get('content-security-policy'))

        # Some servers do not provide useful headers in HEAD; try GET (stream) to sample meta tag CSP
        sample_meta_fa = None
        if fa is None:
            try:
                get_resp = _safe_get(url, method="GET", timeout=timeout_seconds)
                # Read a small portion to find meta tag
                chunk = next(get_resp.iter_content(chunk_size=8192), b"") if hasattr(get_resp, 'iter_content') else get_resp.content[:8192]
                sample = chunk.decode(get_resp.encoding or 'utf-8', errors='ignore') if isinstance(chunk, (bytes, bytearray)) else str(chunk)
                meta_csp = extract_meta_csp(sample) if sample else None
                if meta_csp:
                    sample_meta_fa = parse_csp_frame_ancestors(meta_csp)
            except Exception:
                pass

        final_fa = fa if fa is not None else sample_meta_fa
        allowed, reason = decide_iframe_allowed(xfo, final_fa)

        print("URL:", url)
        print("Status:", resp.status_code)
        print("X-Frame-Options:", xfo or "<none>")
        print("CSP frame-ancestors:", final_fa or "<none>")
        print("Decision:", "Embeddable" if allowed else "Not embeddable")
        print("Reason:", reason)

        sys.exit(0 if allowed else 1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()

