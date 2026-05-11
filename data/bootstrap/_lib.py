"""
Shared helpers for bootstrap scripts. Stdlib + boto3 only.
"""

from __future__ import annotations

import hashlib
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SOURCES_DIR = REPO_ROOT / "data" / "sources"
MANIFESTS_DIR = REPO_ROOT / "data" / "manifests"

# LocalStack endpoint per infra/docker/docker-compose.yml.
S3_ENDPOINT = "http://localhost:4566"
S3_REGION = "us-east-1"
S3_KNOWLEDGE_RAW = "bny-ddq-knowledge-raw"


def load_user_agent() -> str:
    """Read User-Agent from the Day 1-2 manifest. SEC EDGAR fair-access policy
    requires `User-Agent: <Name> <email>` per DATA-PLAN §3.3.
    """
    manifest = json.loads((SOURCES_DIR / "manifest.json").read_text(encoding="utf-8"))
    return manifest["user_agent"]


class TokenBucket:
    """Simple sliding-window rate limiter.

    SEC EDGAR enforces 10 req/sec/IP. We cap at 8/sec to leave headroom and
    avoid getting flagged on any one-second slice. Thread-safe so callers
    could parallelize later.
    """

    def __init__(self, max_per_second: int = 8) -> None:
        self.max = max_per_second
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                while self._times and now - self._times[0] >= 1.0:
                    self._times.popleft()
                if len(self._times) < self.max:
                    self._times.append(now)
                    return
                wait = 1.0 - (now - self._times[0])
            if wait > 0:
                time.sleep(wait)


def http_get(url: str, ua: str, timeout: int = 60) -> tuple[bytes, dict]:
    """GET url with the configured UA. Returns (body, headers-dict).

    Raises on non-2xx. Caller is responsible for rate limiting.
    """
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        headers = dict(resp.headers.items())
    return body, headers


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def s3_client():
    """boto3 S3 client targeting LocalStack with path-style addressing."""
    import boto3  # local import — bootstrap scripts may run without boto3 if not uploading
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=S3_REGION,
        config=Config(s3={"addressing_style": "path"}),
    )


def s3_put(bucket: str, key: str, body: bytes, content_type: str | None = None,
           metadata: dict | None = None) -> dict:
    """Upload bytes to LocalStack S3. Returns put-object response."""
    s3 = s3_client()
    extra: dict = {}
    if content_type:
        extra["ContentType"] = content_type
    if metadata:
        # S3 metadata values must be ASCII strings.
        extra["Metadata"] = {k: str(v) for k, v in metadata.items()}
    return s3.put_object(Bucket=bucket, Key=key, Body=body, **extra)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False), encoding="utf-8")


def safe_get(url: str, ua: str, bucket: TokenBucket, timeout: int = 60) -> tuple[bytes | None, dict | None, str | None]:
    """Rate-limited GET. Returns (body, headers, error). On failure body is None."""
    bucket.acquire()
    try:
        body, headers = http_get(url, ua, timeout=timeout)
        return body, headers, None
    except urllib.error.HTTPError as e:
        return None, None, f"HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, None, f"URL error: {e.reason}"
    except (TimeoutError, socket.timeout):
        return None, None, "timeout"
    except OSError as e:
        return None, None, f"OS error: {e}"
