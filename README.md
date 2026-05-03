# CredexAI SEO Content Agent with Verification

Generates SEO-optimized content and verifies every factual claim through the CredexAI 5-verifier Consensus Verification API before publishing. Returns content with per-claim confidence scores and provenance certificates.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    SEO Content Agent                             │
├─────────────────────────────────────────────────────────────────┤
│  POST /generate                                                 │
│    ├── 1. Generate SEO-optimized content (LLM)                  │
│    ├── 2. Extract factual claims (regex + NLP patterns)         │
│    ├── 3. Verify each claim via CredexAI 5-verifier API         │
│    └── 4. Issue provenance certificate with content hash        │
├─────────────────────────────────────────────────────────────────┤
│  CREDX Transactions:                                            │
│    • 1 CREDX per factual claim verification                     │
│    • Typical blog post: 5–15 CREDX (depends on claim density)   │
│    • All tx hashes stored in provenance audit trail             │
└─────────────────────────────────────────────────────────────────┘
```

## API Reference

### `POST /generate`

Submit a content generation and verification job. Returns immediately with a job ID for polling.

**Request Body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `topic` | string | Yes | Topic or title for the content (5–500 chars) |
| `keywords` | array | Yes | Target SEO keywords (1–20 keywords) |
| `content_type` | string | No | One of: blog_post, landing_page, product_description, technical_article |
| `target_word_count` | integer | No | Target word count (200–5000, default: 800) |
| `tone` | string | No | One of: professional, casual, technical, persuasive |
| `verify_claims` | boolean | No | Whether to verify claims (default: true) |

**Response (202 Accepted):**

```json
{
  "job_id": "uuid",
  "status": "pending",
  "poll_url": "/content/{job_id}"
}
```

### `GET /content/{job_id}`

Retrieve content generation results with verification details.

**Response:**

```json
{
  "job_id": "uuid",
  "status": "completed",
  "content": "# Article Title\n\nContent with verified facts...",
  "content_metadata": {
    "word_count": 823,
    "keywords_used": ["blockchain", "defi"],
    "content_type": "blog_post"
  },
  "verified_claims": [
    {
      "claim_id": "claim-abc12345",
      "claim_text": "The global market reached $4.2 billion in 2025",
      "verification_status": "verified",
      "confidence_score": 0.92,
      "verification_tx_hash": "SIM_NO_XRPL_WALLET_a1b2c3d4",
      "source_sentence": "..."
    }
  ],
  "total_claims": 7,
  "verified_count": 5,
  "failed_count": 2,
  "total_credx_spent": 7,
  "transaction_hashes": ["SIM_NO_XRPL_WALLET_..."],
  "provenance_certificate": { ... }
}
```

### `GET /health`

Health check for container orchestration.

## Environment Setup

```bash
cp .env.example .env
# Edit .env with your configuration

# Required:
# - PROVENANCE_SIGNING_KEY: Generate with `openssl rand -hex 32`
# - CREDEXAI_API_KEY: From https://credexai.live/dashboard

# Optional:
# - OPENAI_API_KEY: For LLM-powered content generation
# - XRPL_WALLET_SEED: Leave empty for simulation mode
```

## Running Locally

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8008 --reload
```

## Docker

```bash
docker build -t credexai-seo-content .
docker run -p 8008:8008 --env-file .env credexai-seo-content
```

## Verification Pipeline

The agent extracts factual claims by identifying sentences containing:

- Statistical figures and percentages
- Dollar amounts and market valuations
- Historical dates and events
- Named entities with quantitative assertions
- Cited sources and reports

Each extracted claim is submitted to the CredexAI 5-verifier Consensus Verification API, where 5 independent GPT-4.1-mini verifiers evaluate the claim's accuracy. Claims that fail verification are flagged with `"verification_status": "FAILED"` — failures are never masked as successes.

Placeholder text and generic headings are automatically skipped during claim extraction.

## Transaction Model

Each content generation job produces multiple CREDX transactions:

- One transaction per factual claim verified (typically 5–15 per blog post)
- All transaction hashes are stored in the provenance certificate audit trail
- The provenance certificate includes a SHA-256 hash of the content for integrity verification

## Integration with Other Agents

- **Delegation Agent**: Can orchestrate this agent for bulk content production pipelines with scheduled publishing
- **Invoice Processing Agent**: Can track content production costs and CREDX expenditure for accounting

## Simulation Mode

When `XRPL_WALLET_SEED` is not configured, the agent operates in simulation mode:
- Transaction hashes are prefixed with `SIM_NO_XRPL_WALLET_` to clearly indicate they are not real
- Content generation uses template-based output
- No real transactions are submitted to the XRPL

## License

MIT — see [LICENSE](./LICENSE)
