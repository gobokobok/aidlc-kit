# AIDLC Kit

Take a feature from discovery to an engineering-ready handoff from your IDE,
in plain language, without touching Git.

> Work in progress. Build step 1 of 8 is done: artifact model and validator.
> Full setup and demo instructions arrive with step 8.

## Development

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/aidlc validate
```

See [CLAUDE.md](CLAUDE.md) for the build spec and
[docs/decisions.md](docs/decisions.md) for design decisions.
