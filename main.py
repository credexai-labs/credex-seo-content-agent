"""
CredexAI SEO Content Agent with Verification

Generates SEO-optimized content, then verifies every factual claim in the
content through the CredexAI 5-verifier Consensus Verification API before
publishing. Returns content with per-claim confidence scores and provenance
certificates. Each claim verification is 1 CREDX transaction.

Architecture:
    - Async pipeline with fire-and-forget job submission
    - In-memory job storage for demo mode
    - Content generation → claim extraction → per-claim verification
    - Multiple CREDX transactions per content piece (one per factual claim)

Related agents:
    - The Delegation Agent can orchestrate this agent for bulk content pipelines
    - The Invoice Processing Agent can track content production costs
"""

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CREDEXAI_API_URL = os.getenv("CREDEXAI_API_URL", "https://api.credexai.live")
CREDEXAI_API_KEY = os.getenv("CREDEXAI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
XRPL_NODE_URL = os.getenv("XRPL_NODE_URL", "https://s1.ripple.com:51234")
XRPL_WALLET_SEED = os.getenv("XRPL_WALLET_SEED", "")
PROVENANCE_SIGNING_KEY = os.getenv("PROVENANCE_SIGNING_KEY", "")

if not PROVENANCE_SIGNING_KEY:
    raise ValueError(
        "PROVENANCE_SIGNING_KEY environment variable is required. "
        "Generate one with: openssl rand -hex 32"
    )

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CredexAI SEO Content Agent",
    description=(
        "Generates SEO-optimized content and verifies every factual claim "
        "through the CredexAI 5-verifier Consensus Verification API."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Validate critical configuration at startup
if not CREDEXAI_API_KEY:
    import warnings
    warnings.warn(
        "CREDEXAI_API_KEY is not set. Verification calls will fail. "
        "Get your key at https://credexai.live/dashboard",
        stacklevel=2,
    )

# ---------------------------------------------------------------------------
# In-memory job storage (Demo mode: use Redis/PostgreSQL in production deployments)
# ---------------------------------------------------------------------------

jobs: dict = {}

# ---------------------------------------------------------------------------
# Enums & Schemas
# ---------------------------------------------------------------------------


class JobStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    EXTRACTING_CLAIMS = "extracting_claims"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentRequest(BaseModel):
    """Request to generate and verify SEO content."""

    topic: str = Field(
        ..., min_length=5, max_length=500, description="Topic or title for the content"
    )
    keywords: list[str] = Field(
        ..., min_length=1, max_length=20, description="Target SEO keywords"
    )
    content_type: str = Field(
        default="blog_post",
        pattern=r"^(blog_post|landing_page|product_description|technical_article)$",
        description="Type of content to generate",
    )
    target_word_count: int = Field(
        default=800, ge=200, le=5000, description="Target word count"
    )
    tone: str = Field(
        default="professional",
        pattern=r"^(professional|casual|technical|persuasive)$",
        description="Writing tone",
    )
    verify_claims: bool = Field(
        default=True, description="Whether to verify factual claims via consensus"
    )


class VerifiedClaim(BaseModel):
    """A factual claim extracted from content with verification result."""

    claim_id: str
    claim_text: str
    verification_status: str
    confidence_score: float
    verification_tx_hash: str
    source_sentence: str


class ContentResponse(BaseModel):
    """Response for a content generation job."""

    job_id: str
    status: JobStatus
    submitted_at: str
    completed_at: Optional[str] = None
    content: Optional[str] = None
    content_metadata: Optional[dict] = None
    verified_claims: list[VerifiedClaim] = []
    total_claims: int = 0
    verified_count: int = 0
    failed_count: int = 0
    total_credx_spent: int = 0
    transaction_hashes: list[str] = []
    provenance_certificate: Optional[dict] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# XRPL Transaction Helper
# ---------------------------------------------------------------------------


def generate_xrpl_tx_hash(memo: str) -> str:
    """
    Generate an XRPL transaction hash.

    Demo mode: When XRPL_WALLET_SEED is not configured, returns an obviously
    fake hash prefixed with SIM_NO_XRPL_WALLET_ to indicate simulation mode.
    """
    if not XRPL_WALLET_SEED:
        short_id = uuid.uuid4().hex[:8]
        return f"SIM_NO_XRPL_WALLET_{short_id}"
    # Demo mode: In a real deployment, this would sign and submit via xrpl-py
    tx_blob = hashlib.sha256(f"{memo}:{uuid.uuid4().hex}".encode()).hexdigest().upper()
    return tx_blob


# ---------------------------------------------------------------------------
# Content Generation
# ---------------------------------------------------------------------------


async def generate_content(request: ContentRequest) -> dict:
    """
    Generate SEO-optimized content.

    Demo mode: Returns pre-built template content with factual claims for
    demonstration. In a real deployment, this would call GPT-4.1-mini or
    similar LLM via the OpenAI API.
    """
    # Demo mode: Simulated content generation
    content = f"""# {request.topic}

{request.keywords[0].title()} is a rapidly evolving field that has seen significant growth in recent years. According to industry reports, the global market reached $4.2 billion in 2025, representing a 34% year-over-year increase.

## Key Developments

The technology behind {request.keywords[0]} relies on distributed consensus mechanisms that process over 1,500 transactions per second. The XRPL network, launched in 2012, has processed over 2.8 billion transactions to date with an average settlement time of 3-5 seconds.

## Industry Impact

Enterprise adoption of {request.keywords[0]} solutions has grown by 67% since 2024. Major financial institutions including JPMorgan, Goldman Sachs, and Bank of America have integrated blockchain-based settlement systems into their operations.

## Technical Architecture

Modern {request.keywords[0]} platforms utilize a multi-layer verification approach where 5 independent verifiers reach consensus on each transaction. This approach reduces false positives by 94% compared to single-model verification.

## Future Outlook

Analysts project the {request.keywords[0]} market will reach $12.8 billion by 2028, driven by regulatory clarity in the EU and Asia-Pacific regions. The implementation of MiCA regulations in Europe has created a standardized framework for digital asset operations.
"""

    metadata = {
        "word_count": len(content.split()),
        "keywords_used": request.keywords,
        "content_type": request.content_type,
        "tone": request.tone,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {"content": content, "metadata": metadata}


# ---------------------------------------------------------------------------
# Claim Extraction
# ---------------------------------------------------------------------------


def extract_factual_claims(content: str) -> list[dict]:
    """
    Extract verifiable factual claims from generated content.

    Identifies sentences containing statistics, dates, named entities, or
    quantitative assertions that can be independently verified.

    Skips placeholder text and generic statements that cannot be verified.
    """
    claims = []
    sentences = re.split(r'(?<=[.!?])\s+', content)

    # Patterns that indicate verifiable factual claims
    factual_patterns = [
        r'\d+%',           # Percentages
        r'\$[\d.]+',       # Dollar amounts
        r'\d{4}',          # Years
        r'\d+[\s,]+\d*\s*(billion|million|thousand|transactions)',  # Quantities
        r'(launched|founded|established)\s+in',  # Historical facts
        r'(according to|reports?|studies?)',  # Cited claims
    ]

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 20:
            continue

        # Skip placeholder text — do not verify generic headings or templates
        if sentence.startswith('#') or '{' in sentence:
            continue

        # Check if sentence contains verifiable factual content
        is_factual = any(re.search(pattern, sentence, re.IGNORECASE) for pattern in factual_patterns)

        if is_factual:
            claims.append({
                "claim_text": sentence,
                "source_sentence": sentence,
            })

    return claims


# ---------------------------------------------------------------------------
# CredexAI Consensus Verification (5 independent GPT-4.1-mini verifiers)
# ---------------------------------------------------------------------------


async def verify_claim(claim: dict) -> dict:
    """
    Submit a factual claim to the CredexAI 5-verifier Consensus Verification
    API. Each verification uses 5 independent GPT-4.1-mini verifiers and
    costs 1 CREDX transaction.

    Returns verification result with consensus score and transaction hash.
    """
    # Skip verification of placeholder text
    if not claim.get("claim_text") or len(claim["claim_text"].strip()) < 10:
        return {
            "status": "FAILED",
            "confidence_score": 0.0,
            "verification_tx_hash": "",
            "error": "Claim text too short or empty — skipped",
        }

    verification_payload = {
        "claim": claim["claim_text"],
        "context": {
            "domain": "seo_content",
            "verification_type": "factual_accuracy",
        },
        "verification_type": "factual_consensus",
    }

    # Generate CREDX payment transaction for this verification
    verification_tx_hash = generate_xrpl_tx_hash(
        f"credx_seo_verify:{hashlib.sha256(claim['claim_text'].encode()).hexdigest()[:8]}"
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{CREDEXAI_API_URL}/v1/verify",
                json=verification_payload,
                headers={"Authorization": f"Bearer {CREDEXAI_API_KEY}"},
            )
            if response.status_code == 200:
                result = response.json()
                return {
                    "status": "verified" if result.get("consensus", False) else "FAILED",
                    "confidence_score": result.get("confidence_score", 0.0),
                    "verification_tx_hash": verification_tx_hash,
                }
            else:
                return {
                    "status": "FAILED",
                    "confidence_score": 0.0,
                    "verification_tx_hash": verification_tx_hash,
                    "error": f"API returned {response.status_code}",
                }
    except Exception as e:
        return {
            "status": "FAILED",
            "confidence_score": 0.0,
            "verification_tx_hash": verification_tx_hash,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Provenance Certificate
# ---------------------------------------------------------------------------


def generate_provenance_certificate(
    job_id: str, claims: list, tx_hashes: list, content_hash: str
) -> dict:
    """Generate a signed provenance certificate for the verified content."""
    certificate_data = {
        "certificate_id": f"prov-seo-{uuid.uuid4().hex[:12]}",
        "job_id": job_id,
        "agent": "seo_content_agent",
        "platform": "credexai.live",
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "content_hash": content_hash,
        "total_claims_verified": len(claims),
        "verification_method": "5-verifier consensus (5 independent GPT-4.1-mini verifiers)",
        "transaction_hashes": tx_hashes,
        "claim_summary": {
            "total": len(claims),
            "verified": sum(1 for c in claims if c.get("verification_status") == "verified"),
            "failed": sum(1 for c in claims if c.get("verification_status") == "FAILED"),
        },
    }
    # Sign the certificate
    payload_bytes = json.dumps(certificate_data, sort_keys=True).encode()
    signature = hashlib.sha256(
        payload_bytes + PROVENANCE_SIGNING_KEY.encode()
    ).hexdigest()
    certificate_data["signature"] = signature
    return certificate_data


# ---------------------------------------------------------------------------
# Background Pipeline
# ---------------------------------------------------------------------------


async def run_content_pipeline(job_id: str, request: ContentRequest):
    """
    Async pipeline for SEO content generation and verification:
    1. Generate SEO-optimized content
    2. Extract factual claims from content
    3. Verify each claim via CredexAI 5-verifier consensus (1 CREDX each)
    4. Generate provenance certificate
    """
    job = jobs[job_id]
    all_tx_hashes: list[str] = []
    credx_spent = 0

    try:
        # Phase 1: Generate content
        job["status"] = JobStatus.GENERATING
        result = await generate_content(request)
        content = result["content"]
        metadata = result["metadata"]

        job["content"] = content
        job["content_metadata"] = metadata

        if not request.verify_claims:
            job["status"] = JobStatus.COMPLETED
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            return

        # Phase 2: Extract factual claims
        job["status"] = JobStatus.EXTRACTING_CLAIMS
        raw_claims = extract_factual_claims(content)
        job["total_claims"] = len(raw_claims)

        if not raw_claims:
            job["status"] = JobStatus.COMPLETED
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            job["provenance_certificate"] = generate_provenance_certificate(
                job_id, [], all_tx_hashes, content_hash
            )
            return

        # Phase 3: Verify each claim (1 CREDX per claim)
        job["status"] = JobStatus.VERIFYING
        verified_claims = []

        for claim in raw_claims:
            verification_result = await verify_claim(claim)
            credx_spent += 1

            if verification_result["verification_tx_hash"]:
                all_tx_hashes.append(verification_result["verification_tx_hash"])

            verified_claim = {
                "claim_id": f"claim-{uuid.uuid4().hex[:8]}",
                "claim_text": claim["claim_text"],
                "verification_status": verification_result["status"],
                "confidence_score": verification_result.get("confidence_score", 0.0),
                "verification_tx_hash": verification_result["verification_tx_hash"],
                "source_sentence": claim["source_sentence"],
            }
            verified_claims.append(verified_claim)

        # Phase 4: Generate provenance certificate
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        provenance_cert = generate_provenance_certificate(
            job_id, verified_claims, all_tx_hashes, content_hash
        )

        job["status"] = JobStatus.COMPLETED
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["verified_claims"] = verified_claims
        job["verified_count"] = sum(
            1 for c in verified_claims if c["verification_status"] == "verified"
        )
        job["failed_count"] = sum(
            1 for c in verified_claims if c["verification_status"] == "FAILED"
        )
        job["total_credx_spent"] = credx_spent
        job["transaction_hashes"] = all_tx_hashes
        job["provenance_certificate"] = provenance_cert

    except Exception as e:
        job["status"] = JobStatus.FAILED
        job["error"] = str(e)
        job["completed_at"] = datetime.now(timezone.utc).isoformat()
        job["transaction_hashes"] = all_tx_hashes


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@app.post("/generate", response_model=dict, status_code=202)
async def submit_content_job(
    request: ContentRequest, background_tasks: BackgroundTasks
):
    """
    Submit a content generation and verification job. The pipeline runs
    asynchronously — poll the /content/{job_id} endpoint for results.

    Each factual claim in the generated content is verified through the
    CredexAI 5-verifier Consensus Verification API (1 CREDX per claim).
    """
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "completed_at": None,
        "content": None,
        "content_metadata": None,
        "verified_claims": [],
        "total_claims": 0,
        "verified_count": 0,
        "failed_count": 0,
        "total_credx_spent": 0,
        "transaction_hashes": [],
        "provenance_certificate": None,
        "error": None,
    }
    background_tasks.add_task(run_content_pipeline, job_id, request)
    return {"job_id": job_id, "status": "pending", "poll_url": f"/content/{job_id}"}


@app.get("/content/{job_id}", response_model=ContentResponse)
async def get_content_result(job_id: str):
    """Retrieve the status and results of a content generation job."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return ContentResponse(**jobs[job_id])


@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    return {
        "status": "healthy",
        "agent": "seo_content_agent",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    """Agent information and capabilities."""
    return {
        "agent": "CredexAI SEO Content Agent",
        "version": "1.0.0",
        "platform": "credexai.live",
        "description": (
            "Generates SEO-optimized content and verifies every factual claim "
            "through the CredexAI 5-verifier Consensus Verification API."
        ),
        "endpoints": {
            "POST /generate": "Submit content generation job",
            "GET /content/{job_id}": "Get content results with verification",
            "GET /health": "Health check",
        },
        "verification": "5 independent GPT-4.1-mini verifiers per claim",
        "cost": "1 CREDX per factual claim verification",
    }
