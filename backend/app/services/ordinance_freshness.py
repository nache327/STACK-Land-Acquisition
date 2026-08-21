"""Ordinance freshness fingerprints — the primary-source drift sentinel.

Verified verdicts rot silently: zone_use_matrix rows are grounded against the
ordinance as of a date, and nothing detects a later amendment (the Chelmsford
CBLT district, the Hudson recodification). This module fingerprints a muni's
PRIMARY ordinance host — not a vendor mirror, which can only lag the host it
scrapes — so a monthly tick can compare against the baseline captured when the
muni was grounded and route drift to targeted human re-verification.

Signals, by host:
  * eCode360 (~92% of the grounded-muni URL surface): the server-rendered
    "New Laws (N)" badge on any code page (fires within days of adoption,
    BEFORE codification) + a text hash of the zoning chapter via the print
    endpoint (`/print/{CLIENT}?guid={node}&children=true`, whole chapter in
    one static fetch — the CLAUDE.md unlock, now codified).
  * Municode: `api.municode.com/Jobs/latest/{productId}` — a changed job id
    IS a new codification (near-zero false positives); BannerText carries the
    human-readable "Codified through Ord. N" stamp. Needs the per-muni
    productId (recorded in apply scripts for munis grounded via Municode).
  * Everything else: content hash — raw bytes for PDFs, normalized text for
    static HTML. Hosts we can't fetch honestly report an error instead of
    pretending freshness.

No Playwright anywhere: headless Chromium OOMs the Railway cron container
(see pipeline.py's auto-discovery note), and the dominant host needs none.
Drift *decisions* are pure functions, unit-tested without network or DB.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from app.services.ordinance_fetcher import _BROWSER_HEADERS

_FETCH_TIMEOUT = 30.0
# eCode360 TLS-fingerprints Python clients (httpx 403s on any header set, HTTP/1.1
# and h2 alike) but serves curl+browser-UA reliably — the banked CLAUDE.md unlock.
# curl is present both on the laptop (ships with Windows) and in the backend
# image (Dockerfile apt-gets it), so eCode360 fetches subprocess curl.
_CURL_TIMEOUT_S = 45

# eCode360 client codes are 2 letters + 4 digits (PL2424, DO1312, DE3083),
# linked site-wide as /<CLIENT>/laws, /<CLIENT>/home, ...
_ECODE_CLIENT_RE = re.compile(r"/([A-Z]{2}\d{4})/(?:laws|home|about|search)")
# Server-rendered badge on every code page: `New Laws (9)`.
_ECODE_NEW_LAWS_RE = re.compile(r"New Laws \((\d+)\)")
# Node id from a directory-style ordinance_url: https://ecode360.com/8919723
_ECODE_NODE_RE = re.compile(r"ecode360\.com/(\d{5,})")

_MUNICODE_JOBS_LATEST = "https://api.municode.com/Jobs/latest/{product_id}"


@dataclass
class Fingerprint:
    host_kind: str  # ecode360 | municode | generic_html | pdf | error
    chapter_hash: str | None = None
    new_laws_count: int | None = None
    municode_job_id: str | None = None
    codified_through: str | None = None  # human-readable host stamp when offered
    error: str | None = None


# ─── Pure helpers (unit-tested, no I/O) ──────────────────────────────────────

def detect_host_kind(url: str) -> str:
    u = (url or "").lower()
    if "ecode360.com" in u:
        return "ecode360"
    if "municode.com" in u:
        return "municode"
    if u.endswith(".pdf"):
        return "pdf"
    return "generic_html"


def normalize_text(text: str) -> str:
    """Whitespace-insensitive form so reflows/indentation never read as drift."""
    return " ".join((text or "").split())


def sha256_hex(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


def extract_ecode360_client_code(html: str) -> str | None:
    m = _ECODE_CLIENT_RE.search(html or "")
    return m.group(1) if m else None


def extract_new_laws_count(html: str) -> int | None:
    m = _ECODE_NEW_LAWS_RE.search(html or "")
    return int(m.group(1)) if m else None


def extract_ecode360_node_id(url: str) -> str | None:
    m = _ECODE_NODE_RE.search(url or "")
    return m.group(1) if m else None


def html_to_hash(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(("script", "style", "noscript")):
        tag.decompose()
    return sha256_hex(normalize_text(soup.get_text(" ")))


def decide_drift(
    *,
    baseline_hash: str | None,
    baseline_new_laws: int | None,
    baseline_job_id: str | None,
    current: Fingerprint,
) -> tuple[bool, str | None]:
    """Compare a stored baseline against a fresh fingerprint.

    Returns (drifted, reason). A signal only participates when BOTH sides have
    it — a fetch that lost a signal (print endpoint down, badge missing) must
    surface as a fetch problem, never as phantom drift. New-laws drift fires on
    any CHANGE, not just increase: laws leaving the badge mean they were just
    codified into the chapter text.
    """
    reasons: list[str] = []
    if baseline_job_id and current.municode_job_id and baseline_job_id != current.municode_job_id:
        reasons.append(
            f"municode job {baseline_job_id} -> {current.municode_job_id}"
            + (f" ({current.codified_through})" if current.codified_through else "")
        )
    if (
        baseline_new_laws is not None
        and current.new_laws_count is not None
        and baseline_new_laws != current.new_laws_count
    ):
        reasons.append(f"new-laws badge {baseline_new_laws} -> {current.new_laws_count}")
    if baseline_hash and current.chapter_hash and baseline_hash != current.chapter_hash:
        reasons.append("chapter text hash changed")
    return (bool(reasons), "; ".join(reasons) or None)


# ─── Fetchers ────────────────────────────────────────────────────────────────

async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    resp = await client.get(url, headers=_BROWSER_HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return resp


async def _curl_get_bytes(url: str) -> bytes:
    """GET via subprocess curl with a browser UA (the eCode360 TLS unlock)."""
    proc = await asyncio.create_subprocess_exec(
        "curl",
        "-sL",
        "--fail",
        "--max-time",
        str(_CURL_TIMEOUT_S),
        "-A",
        _BROWSER_HEADERS["User-Agent"],
        url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_CURL_TIMEOUT_S + 15)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"curl timed out after {_CURL_TIMEOUT_S}s: {url}")
    if proc.returncode != 0:
        raise RuntimeError(
            f"curl exited {proc.returncode} for {url}: {stderr.decode(errors='replace')[:200]}"
        )
    return stdout


async def _curl_get_text(url: str) -> str:
    return (await _curl_get_bytes(url)).decode("utf-8", errors="replace")


async def fingerprint_ecode360(client: httpx.AsyncClient, url: str) -> Fingerprint:
    fp = Fingerprint(host_kind="ecode360")
    try:
        page_html = await _curl_get_text(url)
    except Exception as exc:  # noqa: BLE001 — one muni's host must not sink the batch
        return Fingerprint(host_kind="ecode360", error=f"code page fetch failed: {exc}")

    fp.new_laws_count = extract_new_laws_count(page_html)
    client_code = extract_ecode360_client_code(page_html)
    node_id = extract_ecode360_node_id(url)
    if client_code and node_id:
        print_url = f"https://ecode360.com/print/{client_code}?guid={node_id}&children=true"
        try:
            fp.chapter_hash = html_to_hash(await _curl_get_text(print_url))
        except Exception as exc:  # noqa: BLE001
            fp.error = f"print endpoint failed ({print_url}): {exc}"
    else:
        fp.error = f"no client code / node id on page (client={client_code}, node={node_id})"
    if fp.new_laws_count is None and fp.chapter_hash is None:
        fp.host_kind = "error"
    return fp


async def fingerprint_municode(
    client: httpx.AsyncClient, url: str, product_id: int | None
) -> Fingerprint:
    if not product_id:
        return Fingerprint(
            host_kind="municode",
            error="needs municode_product_id (see the muni's apply script or resolve via api.municode.com)",
        )
    try:
        resp = await _get(client, _MUNICODE_JOBS_LATEST.format(product_id=product_id))
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return Fingerprint(host_kind="municode", error=f"Jobs/latest failed: {exc}")
    banner = normalize_text(data.get("BannerText") or "")
    return Fingerprint(
        host_kind="municode",
        municode_job_id=str(data.get("Id")) if data.get("Id") is not None else None,
        codified_through=banner[:300] or None,
    )


async def fingerprint_generic(client: httpx.AsyncClient, url: str) -> Fingerprint:
    content: bytes
    content_type = ""
    try:
        resp = await _get(client, url)
        content = resp.content
        content_type = (resp.headers.get("content-type") or "").lower()
    except Exception as httpx_exc:  # noqa: BLE001
        # Town sites behind the same TLS fingerprinting get one curl retry.
        try:
            content = await _curl_get_bytes(url)
        except Exception:  # noqa: BLE001 — report the primary failure
            return Fingerprint(host_kind="error", error=f"fetch failed: {httpx_exc}")
    if "pdf" in content_type or url.lower().endswith(".pdf") or content[:5] == b"%PDF-":
        return Fingerprint(host_kind="pdf", chapter_hash=sha256_hex(content))
    return Fingerprint(
        host_kind="generic_html",
        chapter_hash=html_to_hash(content.decode("utf-8", errors="replace")),
    )


async def fingerprint_url(
    url: str, *, municode_product_id: int | None = None, client: httpx.AsyncClient | None = None
) -> Fingerprint:
    """Fingerprint one ordinance URL. Never raises — errors land in .error."""
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=_FETCH_TIMEOUT)
    try:
        kind = detect_host_kind(url)
        if kind == "ecode360":
            return await fingerprint_ecode360(client, url)
        if kind == "municode":
            return await fingerprint_municode(client, url, municode_product_id)
        return await fingerprint_generic(client, url)
    finally:
        if own_client:
            await client.aclose()
