"""Live evals through the Anthropic Messages API (official `anthropic` SDK).

Install with `pip install 'aidlc-kit[anthropic]'`. Sampling parameters
(`temperature`) are not sent: the Messages API no longer accepts them.
Server-side refusal fallbacks are enabled; the model that actually answered
is recorded so the report can flag answers from a fallback model.
"""

import os
from typing import Any

from aidlc.evals.model import EvalError, Request, Response

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def complete(request: Request, settings: dict[str, Any]) -> Response:
    try:
        import anthropic
    except ImportError as exc:
        raise EvalError("Live evals with provider anthropic need its SDK: "
                        "pip install 'aidlc-kit[anthropic]'.") from exc
    key_env = settings.get("api_key_env")
    client = anthropic.Anthropic(api_key=os.environ[key_env]) if key_env and os.environ.get(key_env) \
        else anthropic.Anthropic()
    params: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "messages": [{"role": "user", "content": request.prompt}],
        "betas": [FALLBACK_BETA],
        "fallbacks": "default",
    }
    if request.system:
        params["system"] = request.system
    if request.effort:
        params["output_config"] = {"effort": request.effort}
    try:
        response = client.beta.messages.create(**params)
    except anthropic.AuthenticationError as exc:
        raise EvalError("The Anthropic API key was not accepted. Check the key named in "
                        "`eval.api_key_env`.") from exc
    except anthropic.NotFoundError as exc:
        raise EvalError(f"The model {request.model} was not found. Check `model` in the asset "
                        "or `eval.model` in aidlc.yaml.") from exc
    except anthropic.RateLimitError as exc:
        raise EvalError("The Anthropic API is rate limiting this key; try again shortly.") from exc
    except anthropic.APIStatusError as exc:
        raise EvalError(f"The Anthropic API returned an error ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise EvalError("Could not reach the Anthropic API. Check the network.") from exc
    # Served-by signal: an iteration of type fallback_message means a fallback model answered.
    fallback = any(getattr(it, "type", None) == "fallback_message"
                   for it in (getattr(response.usage, "iterations", None) or []))
    if response.stop_reason == "refusal":
        return Response("", "refusal", response.model, fallback)
    text = "".join(block.text for block in response.content if block.type == "text")
    return Response(text, response.stop_reason, response.model, fallback)
