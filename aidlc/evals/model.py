"""Model clients for evals.

`cached` (the default, and the only mode CI uses) answers from
`evals/cache/<hash>.json`; a missing entry is an error, never a pass.
`live` calls the provider configured in aidlc.yaml and writes the cache.
The hash covers provider, model, settings, asset ID and version, and the
fully rendered prompt, so any change to them needs a new live run.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from aidlc import artifacts as art
from aidlc.evals.providers import PROVIDERS


class EvalError(RuntimeError):
    """A plain-language reason the eval could not run."""


class CacheMiss(EvalError):
    pass


@dataclass(frozen=True)
class Request:
    provider: str
    model: str
    system: str | None
    prompt: str
    max_tokens: int
    effort: str | None
    temperature: float | None
    asset: str  # "ASSET-001@2"

    def key(self) -> str:
        canonical = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Response:
    text: str
    stop_reason: str | None = None
    served_by: str | None = None  # the model that actually answered
    fallback: bool = False        # a fallback model answered after a refusal


Provider = Callable[[Request, dict[str, Any]], Response]
Client = Callable[[Request], Response]


class Cache:
    def __init__(self, folder: Path):
        self.folder = folder

    def path(self, request: Request) -> Path:
        return self.folder / f"{request.key()}.json"

    def get(self, request: Request) -> Response | None:
        path = self.path(request)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Response(data["output"], data.get("stop_reason"), data.get("served_by"),
                        bool(data.get("fallback")))

    def put(self, request: Request, response: Response, now: datetime) -> Path:
        path = self.path(request)
        path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"request": asdict(request), "output": response.text, "stop_reason": response.stop_reason,
                 "served_by": response.served_by, "fallback": response.fallback,
                 "created_at": art.format_ts(now)}
        path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


def cached_client(cache: Cache) -> Client:
    def complete(request: Request) -> Response:
        hit = cache.get(request)
        if hit is None:
            raise CacheMiss("no cached answer for this exact prompt; a live run (/eval --live) creates it")
        return hit
    return complete


def live_client(cache: Cache, provider: Provider, settings: dict[str, Any], now: datetime) -> Client:
    def complete(request: Request) -> Response:
        response = provider(request, settings)
        cache.put(request, response, now)
        return response
    return complete


def load_provider(name: str) -> Provider:
    if name not in PROVIDERS:
        raise EvalError(f"Live evals need `eval.provider` in aidlc.yaml, one of: {', '.join(PROVIDERS)}.")
    module = import_module(f"aidlc.evals.providers.{PROVIDERS[name]}")
    return module.complete
