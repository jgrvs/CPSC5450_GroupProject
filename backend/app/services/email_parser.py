import json
from pathlib import Path
from email import policy
from email.parser import BytesParser
from jsonschema import validate, ValidationError
from datetime import datetime, timezone
from fastapi import HTTPException
from email.utils import parseaddr
from email.utils import parsedate_to_datetime
import hashlib
import re
from urllib.parse import urlparse
import unicodedata
import ipaddress
from jsonschema import Draft202012Validator
from dataclasses import dataclass
from jsonschema import Draft202012Validator
from typing import Any

# --- IOC extraction helpers ---

URL_REGEX = re.compile(
    r"""(?ix)
    \b(
        (?:https?://|www\.)                # scheme or www
        [^\s<>"'(){}\[\]]+                 # everything up to a hard boundary
    )
    """
)

EMAIL_REGEX = re.compile(r"(?i)\b[a-z0-9._%+\-]+@([a-z0-9.\-]+\.[a-z]{2,})\b")
DOMAIN_REGEX = re.compile(
    r"""(?ix)
    \b(
        (?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+
        [a-z]{2,63}
    )\b
    """
)

# IPv4 only here; easy to extend to IPv6 if you want
IPV4_REGEX = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)

TRACKING_PARAM_REGEX = re.compile(r"(?i)\b(utm_[a-z0-9_]+|gclid|fbclid|mc_eid|mc_cid)\b")

COMMON_FREEMAIL = {
    "gmail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com", "aol.com", "proton.me", "protonmail.com"
}

def _normalize_url(u: str) -> str:
    u = u.strip().strip(".,;:!?)\"]}'")
    if u.lower().startswith("www."):
        u = "http://" + u  # parseable
    return u

def extract_urls(text: str | None) -> list[str]:
    if not text:
        return []
    found = []
    for m in URL_REGEX.finditer(text):
        u = _normalize_url(m.group(1))
        # filter obvious false positives
        try:
            p = urlparse(u)
            if p.netloc:
                found.append(u)
        except Exception:
            continue
    # de-dupe preserving order
    seen = set()
    out = []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out

def _registrable_domain(host: str) -> str:
    """
    Conservative "domain root" extractor WITHOUT public suffix list.
    For real accuracy you’d use tldextract + PSL, but this is dependency-free.
    """
    host = host.strip(".").lower()
    # remove port
    if ":" in host:
        host = host.split(":", 1)[0]
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])

def extract_domains(text: str | None, urls: list[str] | None = None) -> list[str]:
    domains = []

    if text:
        # domains in emails
        for m in EMAIL_REGEX.finditer(text):
            domains.append(m.group(1).lower())

        # bare domains
        for m in DOMAIN_REGEX.finditer(text):
            domains.append(m.group(1).lower())

    if urls:
        for u in urls:
            try:
                p = urlparse(_normalize_url(u))
                if p.netloc:
                    domains.append(p.netloc.lower())
            except Exception:
                pass

    # normalize to registrable domains (roughly)
    normalized = []
    for d in domains:
        d = d.strip().strip(".,;:!?)\"]}'")
        if d:
            normalized.append(_registrable_domain(d))

    # de-dupe preserving order
    seen = set()
    out = []
    for d in normalized:
        if d and d not in seen:
            seen.add(d)
            out.append(d)
    return out

def extract_ip_addresses(text: str | None) -> list[str]:
    if not text:
        return []
    ips = []
    for m in IPV4_REGEX.finditer(text):
        candidate = m.group(0)
        try:
            ipaddress.ip_address(candidate)
            ips.append(candidate)
        except ValueError:
            pass
    # de-dupe preserving order
    seen = set()
    out = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            out.append(ip)
    return out

# --- flag helpers ---

def has_unicode_tricks(s: str | None) -> bool:
    """
    Detects non-ASCII and some common Unicode confusables patterns.
    Conservative: flags if non-ASCII present in display name or local part.
    """
    if not s:
        return False
    # quick check
    if any(ord(ch) > 127 for ch in s):
        return True
    # also catch weird normalization differences
    return unicodedata.normalize("NFKC", s) != s

def display_name_mismatch(display_name: str | None, from_addr: str | None) -> bool:
    """
    Heuristic: flags if display name looks like a different email address or
    references a different domain than actual from domain.
    """
    if not display_name or not from_addr or "@" not in from_addr:
        return False

    from_domain = from_addr.split("@")[-1].lower()
    # display name contains an email address
    m = re.search(r"(?i)\b[a-z0-9._%+\-]+@([a-z0-9.\-]+\.[a-z]{2,})\b", display_name)
    if m:
        claimed_domain = m.group(1).lower()
        return _registrable_domain(claimed_domain) != _registrable_domain(from_domain)

    # display name contains a domain-like token
    dm = DOMAIN_REGEX.search(display_name)
    if dm:
        claimed_domain = dm.group(1).lower()
        return _registrable_domain(claimed_domain) != _registrable_domain(from_domain)

    return False

def sender_domain_mismatch(from_addr: str | None, return_path: str | None, reply_to: str | None) -> bool:
    """
    Heuristic: flags if return-path or reply-to domain differs from from domain.
    """
    if not from_addr or "@" not in from_addr:
        return False
    from_domain = _registrable_domain(from_addr.split("@")[-1])

    def get_domain(header_val: str | None) -> str | None:
        if not header_val:
            return None
        _, addr = parseaddr(header_val)
        if addr and "@" in addr:
            return _registrable_domain(addr.split("@")[-1])
        return None

    rp = get_domain(return_path)
    rt = get_domain(reply_to)

    # mismatch if either exists and differs
    if rp and rp != from_domain:
        return True
    if rt and rt != from_domain:
        return True
    return False

def lookalike_domain_detected(domains: list[str], from_addr: str | None) -> bool:
    """
    Basic heuristic: if any domain is very similar to sender domain
    (edit distance-ish without deps). We’ll do a cheap check:
    - same length and <=2 character differences
    - or contains "rn" vs "m", etc.
    """
    if not from_addr or "@" not in from_addr:
        return False
    sender = _registrable_domain(from_addr.split("@")[-1])

    def close(a: str, b: str) -> bool:
        if a == b:
            return False
        if abs(len(a) - len(b)) > 1:
            return False
        # cheap diff count
        diffs = sum(1 for x, y in zip(a, b) if x != y) + abs(len(a) - len(b))
        if diffs <= 2:
            return True
        # simple confusable patterns
        conf = [("rn", "m"), ("l", "1"), ("o", "0")]
        for x, y in conf:
            if a.replace(x, y) == b or b.replace(x, y) == a:
                return True
        return False

    for d in domains:
        if close(d, sender):
            return True
    return False

def internal_impersonation(display_name: str | None, from_addr: str | None, org_domains: set[str]) -> bool:
    """
    Flags cases where display name looks internal (CEO/CFO/IT) but sender domain is external.
    Keep org_domains configurable.
    """
    if not display_name or not from_addr or "@" not in from_addr:
        return False
    sender = _registrable_domain(from_addr.split("@")[-1])
    is_internal_sender = sender in org_domains

    # common internal impersonation cues (tune as needed)
    cues = re.compile(r"(?i)\b(it|helpdesk|security|payroll|hr|ceo|cfo|finance|accounts payable)\b")
    looks_internal = bool(cues.search(display_name))

    return looks_internal and not is_internal_sender

# --- keyword counting helpers ---

KEYWORD_SETS = {
    "urgency": [
        r"\burgent\b", r"\basap\b", r"\bimmediately\b", r"\baction required\b", r"\bfinal notice\b",
        r"\bwithin (?:\d+|24|48) hours\b", r"\btime[- ]sensitive\b"
    ],
    "credentials": [
        r"\bpassword\b", r"\blogin\b", r"\bsign[- ]in\b", r"\bverify your account\b", r"\bmfa\b",
        r"\bone[- ]time code\b", r"\botp\b"
    ],
    "payment": [
        r"\binvoice\b", r"\bwire\b", r"\bpayment\b", r"\btransfer\b", r"\bbank\b", r"\bbitcoin\b",
        r"\bgift ?card\b", r"\bpayroll\b"
    ],
    "threat": [
        r"\baccount will be (?:locked|suspended|terminated)\b", r"\blegal action\b", r"\bpolice\b",
        r"\bfraud\b", r"\bcompromised\b", r"\bbreach\b"
    ],
}

def count_keywords(text: str | None) -> dict[str, int | None]:
    if not text:
        return {k: None for k in KEYWORD_SETS.keys()}
    t = text.lower()
    out: dict[str, int | None] = {}
    for bucket, pats in KEYWORD_SETS.items():
        total = 0
        for pat in pats:
            total += len(re.findall(pat, t, flags=re.IGNORECASE))
        out[bucket] = total
    return out


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "email_schema.json"

def load_schema():
    try:
        return json.loads(SCHEMA_PATH.read_text())
    except FileNotFoundError:
        raise HTTPException(500, "Schema file not found.")
    except json.JSONDecodeError:
        raise HTTPException(500, "Invalid schema JSON.")

# Function to parse Auth-Results header    
def parse_auth_results(header_value: str | None) -> dict:
    if not header_value:
        return {"spf": None, "dkim": None, "dmarc": None}

    def extract(field):
        match = re.search(rf"{field}=([a-zA-Z]+)", header_value)
        return match.group(1).lower() if match else None

    return {
        "spf": extract("spf"),
        "dkim": extract("dkim"),
        "dmarc": extract("dmarc")
    }

def url_to_obj(u: str) -> dict | None:
    u = _normalize_url(u)
    p = urlparse(u)
    if not p.netloc:
        return None
    return {
        "url_actual": u,
        "url_display_text": None,
        "domain": _registrable_domain(p.netloc)
    }


def parse_eml_bytes(eml_bytes: bytes, email_id:str) -> dict:
    message = BytesParser(policy=policy.default).parsebytes(eml_bytes)

    # Extract body
    plain_text = None
    html_text = None

    if message.is_multipart():
        for part in message.walk():
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()

            if "attachment" in disp:
                continue

            if ctype == "text/plain" and plain_text is None:
                plain_text = part.get_content()
            elif ctype == "text/html" and html_text is None:
                html_text = part.get_content()
    else:
        content = message.get_content()
        if message.get_content_type() == "text/html":
            html_text = content
        else:
            plain_text = content

    # Extract Auth-Results
    auth_header = message.get("Authentication-Results")
    auth_results = parse_auth_results(auth_header)

    # Extract display name + address
    from_display_name, from_address = parseaddr(message.get("From") or "")

    # Attachments
    attachments = []
    for part in message.walk():
        disp = (part.get("Content-Disposition") or "").lower()
        if "attachment" in disp:
            filename = part.get_filename()
            if filename:
                ext = Path(filename).suffix or None
                attachments.append({"filename": filename, "file_ext": ext})

    # Date to ISO 8601
    raw_date = message.get("Date")
    dt = parsedate_to_datetime(raw_date) if raw_date else None
    iso_date = dt.isoformat() if dt else None

    # Generate message fingerprint
    fingerprint = hashlib.sha256(eml_bytes).hexdigest()

    # Canonical fingerprint: hash only stable fields (strips To, Date, Message-ID).
    # Two emails from the same phishing campaign share a canonical_fingerprint even
    # if they were sent to different recipients or at different times.
    _canonical_parts = "\n".join(filter(None, [
        (message.get("From") or "").strip().lower(),
        (message.get("Subject") or "").strip().lower(),
        (message.get("Reply-To") or "").strip().lower(),
        (message.get("Return-Path") or "").strip().lower(),
        (plain_text or "").strip(),
    ]))
    canonical_fingerprint = hashlib.sha256(_canonical_parts.encode("utf-8")).hexdigest()

    # --- NEW: build a text blob for indicator extraction and keyword analysis ---
    header_blob = " ".join(filter(None, [
        message.get("Subject"),
        message.get("From"),
        message.get("To"),
        message.get("Reply-To"),
        message.get("Return-Path"),
    ]))
    body_blob = " ".join(filter(None, [plain_text, html_text]))
    full_text = f"{header_blob}\n{body_blob}".strip()

    url_strings = extract_urls(full_text)
    urls = [obj for u in url_strings if (obj := url_to_obj(u)) is not None]

    # domains should include domains from urls too:
    domains = extract_domains(full_text, urls=url_strings)

    ips = extract_ip_addresses(full_text)

    # --- NEW: derived flags ---
    dn_mismatch = display_name_mismatch(from_display_name, from_address)
    sd_mismatch = sender_domain_mismatch(from_address, message.get("Return-Path"), message.get("Reply-To"))
    unicode_flag = has_unicode_tricks(from_display_name) or has_unicode_tricks(from_address)

    # set your org domains (tune for your environment / dataset)
    org_domains = {"example.com"}  # TODO: configure externally
    internal_imp = internal_impersonation(from_display_name, from_address, org_domains=org_domains)

    lookalike = lookalike_domain_detected(domains, from_address)

    # --- NEW: keyword counts ---
    kw = count_keywords(full_text)

    parsed_email = {
        "email_id": email_id, # this is unique per email
        "fingerprint": fingerprint,
        "canonical_fingerprint": canonical_fingerprint,
        "source": {
            "dataset": "unknown",
            "split": None
        },

        "headers": {
            "from_address": from_address or None,
            "from_display_name": from_display_name or None,
            "reply_to": message.get("Reply-To"),
            "return_path": message.get("Return-Path"),
            "to_address": message.get("To"),
            "subject": message.get("Subject"),
            "date": iso_date,
            "message_id": message.get("Message-ID"),

            "auth_results": {
                "spf": auth_results["spf"],
                "dkim": auth_results["dkim"],
                "dmarc": auth_results["dmarc"]
            }
        },

        "body": {
            "has_html": html_text is not None,
            "plain_text": plain_text,
            "attachments": attachments
        },

        "indicators": {
            "urls": urls,
            "domains": domains,
            "ip_addresses": ips
        },

        "derived_flags": {
            "display_name_mismatch": dn_mismatch,
            "sender_domain_mismatch": sd_mismatch,
            "lookalike_domain_detected": lookalike,
            "internal_impersonation": internal_imp,
            "unicode_trick_detected": unicode_flag
        },

        "keyword_counts": {
            "urgency": kw["urgency"],
            "credentials": kw["credentials"],
            "payment": kw["payment"],
            "threat": kw["threat"]
        },

        "label": None
    }

    return parsed_email

@dataclass
class PayloadValidationError(ValueError):
    path: str
    message: str

    def __str__(self) -> str:
        return f"Schema validation failed at {self.path}: {self.message}"


def validate_payload(payload: dict[str, Any]) -> None:
    schema = load_schema()
    v = Draft202012Validator(schema)

    errors = sorted(v.iter_errors(payload), key=lambda e: list(e.path))
    if not errors:
        return

    e = errors[0]

    # Build a JSONPath-ish string like $.headers.from_address or $.indicators.urls[0].domain
    path = "$"
    for part in e.path:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"

    raise PayloadValidationError(path=path, message=e.message)

