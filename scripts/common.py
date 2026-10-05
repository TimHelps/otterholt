from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DATA = ROOT / "data"
CACHE = ROOT / ".cache"
WALK_MINUTES = [5, 10, 15, 20]
USER_AGENT = "otterholt-local/0.1 (personal London map)"


def ensure_directories() -> None:
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)


def request_json(
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    attempts: int = 5,
) -> Any:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
        **(headers or {}),
    }
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"

    for attempt in range(attempts):
        request = urllib.request.Request(
            url,
            data=body,
            headers=request_headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                detail = error.read().decode(errors="replace")
                raise RuntimeError(f"{url}: HTTP {error.code}: {detail}") from error
        except (TimeoutError, urllib.error.URLError, ConnectionError, OSError):
            if attempt == attempts - 1:
                raise
        time.sleep(2**attempt)

    raise RuntimeError(f"Request failed: {url}")


def request_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read().decode("utf-8")


def geocode_postcode(postcode: str) -> tuple[float, float]:
    normalised = " ".join(postcode.upper().split())
    url = f"https://api.postcodes.io/postcodes/{urllib.parse.quote(normalised)}"
    payload = request_json(url)
    result = payload.get("result")
    if not result:
        raise RuntimeError(f"Unknown postcode: {postcode}")
    return float(result["latitude"]), float(result["longitude"])


def write_json(path: Path, value: Any, *, compact: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        json.dump(
            value,
            output,
            ensure_ascii=False,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
        output.write("\n")


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def feature_collection(features: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": features}
