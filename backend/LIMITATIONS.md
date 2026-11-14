# Limitations and deployment notes

## What works

- Local Git history analysis.
- Python symbol lineage.
- Pull request, review, and issue ingestion.
- Explanations with mechanical quote verification.
- Tested against real PostgreSQL 16 and a real clone of `pallets/click` with a local Ollama model.

## Security and deployment

- The service has no authentication. Bind it to `127.0.0.1` only.
- Keep `ALLOW_LOCAL_REMOTES=false` outside tests.
- Put tokens and API keys in environment variables only. Never commit or paste them anywhere.
- Use a read-only `GITHUB_TOKEN` for public repositories.

## Analysis limits

- Python is the only supported analysis language.
- `--first-parent` flattens side branches into the merge commit.
- `--follow` is a heuristic for tracking renamed files.
- A symbol renamed and edited in the same change appears as removed plus added. For example, a class renamed with a changed body will be shown as one removed class and one added class.
- Symbols with equal hashes are paired by source order.
- With `max_commits`, the oldest included commit becomes the baseline, so every symbol appears added.
- Removed-event rows store the last live location of the symbol.
- Only SHA-1 repositories are supported.

## Ingestion limits

- GitHub rate limits allow about 60 requests per hour without a token.
- Ingestion makes one API call per commit.
- Cross-repository references are not resolved.
- Cloning runs inside the request and has a 300-second timeout.
- Private repositories are not supported.
- Concurrent clone requests are not locked against each other.

## Explain limits

- Quotes are mechanically verified against evidence. The surrounding summary is the model's interpretation and is always labeled `inferred`.
- Small local models, such as `llama3.2:3b`, often fail the exact-quote check and return `insufficient_evidence`.
- `EXPLAIN_PROVIDER` selects `anthropic` or `ollama` and defaults to `anthropic`.
- `OLLAMA_BASE_URL` defaults to `http://localhost:11434`.
- `OLLAMA_MODEL` defaults to `llama3.2:3b`.

## Extractive mode

Extractive mode returns original sentences from linked commits, pull requests, reviews, and
issues. It does not generate text or explain why a change happened by itself.

## Testing

- The PostgreSQL test is opt-in. Set `TEST_POSTGRES_URL` and run `pytest -m postgres`.
- The default test suite never touches the network.
