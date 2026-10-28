"""Live evals through OpenAI or any OpenAI-compatible endpoint (official
`openai` SDK): set `eval.base_url` for Azure OpenAI, a gateway or a local
model server. Install with `pip install 'aidlc-kit[openai]'`."""

import os
from typing import Any

from aidlc.evals.model import EvalError, Request, Response


def complete(request: Request, settings: dict[str, Any]) -> Response:
    try:
        import openai
    except ImportError as exc:
        raise EvalError("Live evals with an OpenAI-style provider need its SDK: "
                        "pip install 'aidlc-kit[openai]'.") from exc
    key_env = settings.get("api_key_env")
    api_key = os.environ.get(key_env) if key_env else None
    if not api_key and not settings.get("base_url"):
        raise EvalError(f"Set the API key in the environment variable named by `eval.api_key_env` "
                        f"({key_env or 'not set'}).")
    client = openai.OpenAI(api_key=api_key or "unused", base_url=settings.get("base_url") or None)
    messages = ([{"role": "system", "content": request.system}] if request.system else []) + [
        {"role": "user", "content": request.prompt}]
    params: dict[str, Any] = {"model": request.model, "messages": messages}
    if request.temperature is not None:
        params["temperature"] = request.temperature
    try:
        response = client.chat.completions.create(**params)
    except openai.AuthenticationError as exc:
        raise EvalError("The API key was not accepted. Check `eval.api_key_env`.") from exc
    except openai.NotFoundError as exc:
        raise EvalError(f"The model {request.model} was not found at this endpoint.") from exc
    except openai.RateLimitError as exc:
        raise EvalError("The endpoint is rate limiting this key; try again shortly.") from exc
    except openai.APIStatusError as exc:
        raise EvalError(f"The endpoint returned an error ({exc.status_code}).") from exc
    except openai.APIConnectionError as exc:
        raise EvalError("Could not reach the model endpoint. Check `eval.base_url` and the network.") from exc
    choice = response.choices[0]
    return Response(choice.message.content or "", choice.finish_reason, response.model)
