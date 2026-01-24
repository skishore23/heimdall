# Bifröst Quickstart - 5 Minute Setup

## TL;DR

1. **Bifröst needs API key** (in its `.env`)
2. **Client doesn't need API key** (Bifröst is trusted proxy)
3. **Client auth**: `x-policy-id` header
4. **Upstream**: Set `UPSTREAM_BASE_URL` to proxy anywhere

## Setup Steps

### 1. Configure Bifröst (.env file)

```bash
# Create .env in project root
cat > .env << EOF
# Required: API key for upstream LLM
OPENAI_API_KEY=sk-your-key-here

# Optional: Proxy to different endpoint
# UPSTREAM_BASE_URL=http://localhost:11434/v1  # Ollama
# UPSTREAM_API_KEY=dummy

# Optional: Redis for caching
REDIS_URL=redis://localhost:6379

# Required: Default policy
DEFAULT_POLICY_ID=enterprise_default_v1
EOF
```

### 2. Start Bifröst

```bash
python -m bifrost.main

# Should see:
# INFO: Guardrails Gateway started successfully
# INFO: Uvicorn running on http://0.0.0.0:8000
```

### 3. Use from Client

```python
from openai import AsyncOpenAI

# Point to Bifröst
client = AsyncOpenAI(
    base_url="http://localhost:8000/v1",  # ← Bifröst
    api_key="any-value"  # ← Not validated
)

# Make request
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_headers={"x-policy-id": "enterprise_default_v1"}  # ← Required
)

print(response.choices[0].message.content)
```

That's it!

## FAQ

### Q: Do I need an API key to connect to Bifröst?

**No.** Client sends any value in `api_key` (OpenAI SDK requires it), but Bifröst doesn't validate it.

### Q: Where is authentication configured?

**In Bifröst's `.env` file**, not in client code:

```bash
# .env (for Bifröst server)
OPENAI_API_KEY=sk-...      # For OpenAI upstream
# OR
UPSTREAM_BASE_URL=...      # For other providers
UPSTREAM_API_KEY=...
```

### Q: How does Bifröst authenticate clients?

Via **policy header**:

```python
extra_headers={"x-policy-id": "enterprise_default_v1"}
```

This is the "auth" - which policy to enforce. Optional `x-tenant-id` for multi-tenancy.

### Q: Can I add real client authentication?

Yes, two ways:

**Option 1: Add reverse proxy in front**
```
Client → nginx (with auth) → Bifröst → Upstream
```

**Option 2: Add middleware to Bifröst**
```python
# bifrost/main.py
@app.middleware("http")
async def authenticate(request: Request, call_next):
    api_key = request.headers.get("authorization", "").replace("Bearer ", "")
    if api_key not in VALID_KEYS:
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return await call_next(request)
```

### Q: What if I'm using Bedrock/Azure/Ollama?

Just set `UPSTREAM_BASE_URL`:

```bash
# For Bedrock
UPSTREAM_BASE_URL=https://bedrock-runtime.us-east-1.amazonaws.com/v1
UPSTREAM_API_KEY=your-aws-key

# For Ollama
UPSTREAM_BASE_URL=http://localhost:11434/v1
UPSTREAM_API_KEY=dummy

# For Azure
UPSTREAM_BASE_URL=https://your-resource.openai.azure.com/...
UPSTREAM_API_KEY=your-azure-key
```

Client code stays identical.

## Request Flow

```
┌─────────────────────────────────────────────────────────┐
│  1. Client sends request                                │
│     - base_url: http://localhost:8000/v1                │
│     - api_key: "any-value" (not used)                   │
│     - headers: x-policy-id=enterprise_default_v1        │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  2. Bifröst receives request                            │
│     - Extracts policy_id from header                    │
│     - Loads policy from cache                           │
│     - Runs input guards                                 │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  3. Bifröst forwards to upstream                        │
│     - Uses UPSTREAM_BASE_URL (from .env)                │
│     - Uses UPSTREAM_API_KEY (from .env)                 │
│     - Calls: AsyncOpenAI(base_url=...).create()         │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  4. Upstream (OpenAI/Bedrock/etc) responds              │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  5. Bifröst runs output guards                          │
│     - Checks response content                           │
│     - Adds guardrails metadata                          │
└─────────────────┬───────────────────────────────────────┘
                  ▼
┌─────────────────────────────────────────────────────────┐
│  6. Returns to client                                   │
│     - Original response + guardrails info               │
└─────────────────────────────────────────────────────────┘
```

## Environment Variables Summary

### Bifröst Server (.env)

```bash
# Required
OPENAI_API_KEY=sk-...              # Default upstream
DEFAULT_POLICY_ID=enterprise_v1    # Default policy

# Or use custom upstream
UPSTREAM_BASE_URL=http://your-llm/v1
UPSTREAM_API_KEY=your-key

# Optional
PORT=8000
REDIS_URL=redis://localhost:6379
LOG_LEVEL=INFO
```

### Client (none needed!)

Client just points to Bifröst:

```python
AsyncOpenAI(base_url="http://bifrost:8000/v1", api_key="any")
```

## Testing

```bash
# Terminal 1: Start Bifröst
export OPENAI_API_KEY=sk-...
python -m bifrost.main

# Terminal 2: Test with curl
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "x-policy-id: enterprise_default_v1" \
  -H "Authorization: Bearer any-value" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Summary

**Authentication architecture:**
- Client → Bifröst: **No API key** (trusted proxy)
- Client → Bifröst: **Policy ID** (via header)
- Bifröst → Upstream: **API key** (from .env)

**Configuration:**
- All keys in Bifröst's `.env` file
- Client code needs no secrets
- Works with any OpenAI-compatible upstream

**Simple principle:**
```
Client Request → Guards → Forward to UPSTREAM_BASE_URL → Response
```

No complexity, no abstractions, just proxy + guards.

