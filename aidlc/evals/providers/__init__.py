"""Live model providers. Each module exposes `complete(request, settings)`
and imports its vendor SDK only when called (optional extras)."""

# Provider name (`eval.provider` in aidlc.yaml) -> module exposing `complete`.
PROVIDERS = {
    "anthropic": "anthropic_provider",
    "openai": "openai_provider",
    "openai_compatible": "openai_provider",
}
