# Load parser — OpenAI vs Claude (API switch only)

The rate-con pipeline (acquisition, handoff v2, mechanical validation, workspace hydration) is **unchanged**. Only the semantic HTTP client swaps.

## Configuration (SSM → `/run/secrets/truckerp.env`)

| Env | Purpose |
|-----|---------|
| `LOAD_PARSER_LLM_PROVIDER` | `openai` (default) or `anthropic` / `claude` |
| `OPENAI_API_KEY` | Required when provider is `openai` |
| `OPENAI_EXTRACTION_MODEL` | e.g. `gpt-5-mini` |
| `LOAD_PARSER_REASONING_EFFORT` | GPT-5 only: `minimal`, `low`, `medium`, `high` |
| `ANTHROPIC_API_KEY` | Required when provider is `anthropic` |
| `ANTHROPIC_EXTRACTION_MODEL` or `LOAD_PARSER_ANTHROPIC_MODEL` | Default load parse: `claude-haiku-4-5-20251001` (alias `claude-haiku-4-5`) |

After changing provider or keys, restart `truckerp-api`.

## Parse response metadata

Successful parses include `context.llm_provider` and `context.llm_model` for verification.

## Code entrypoints

- Router: `app/services/load_document_parse_semantic_llm.py`
- OpenAI transport: `app/document_platform/capabilities/openai/chat_json_schema.py`
- Anthropic transport: `app/document_platform/capabilities/anthropic/chat_json_schema.py`
- Product path: `app/services/load_document_parse_rate_con.py` (unchanged flow)
