# Care Cloud Patient Intake API

A take-home demonstration of a phone-based patient registration workflow backed by a REST API and persistent PostgreSQL database. The voice assistant collects and reads back demographics, waits for the caller's confirmation, and saves through the same patient service used by the API.

> **Demo and privacy notice:** Use synthetic data only. This project is not a production clinical system and has not been assessed or certified for HIPAA compliance. The patient read endpoints are currently public, and confirmed registration payloads and call transcripts can contain sensitive information. Do not enter real patient data.

## Live demo

- **API base URL:** <https://voice-ai-agent-patient-registration-navy.vercel.app>
- **Health:** <https://voice-ai-agent-patient-registration-navy.vercel.app/health>
- **Interactive API docs:** <https://voice-ai-agent-patient-registration-navy.vercel.app/docs>
- **Vapi phone number:** **TODO: add the active U.S. number before submission.**
- **Repository:** <https://github.com/jameelkhalidawan/Voice-AI-Agent-Patient-Registration-System>
- **Reviewer write key:** Share a temporary or rotated `API_KEY` privately with the reviewer. Never put a real key in this repository, README, issue, or screenshot.

The deployed URL, number, Vapi credentials, and free-tier availability should be checked again on the review day. Service limits and free-tier terms can change.

## What it does

1. A caller chooses new registration or an existing-record update.
2. The assistant gathers the required fields conversationally, validates fields through the backend, and checks an active phone number for a possible duplicate.
3. It reads back the collected details and waits for a clear caller confirmation before invoking a write tool.
4. The webhook revalidates and persists through `PatientService`; it returns success or a caller-safe failure.
5. Vapi's end-of-call report can save a transcript and summary linked to the call and, when available, patient.

For writes, the webhook requires the `caller_confirmation` tool argument to equal `yes`. The backend does **not** independently prove that the caller said yes from a transcript; the voice model is instructed to set the argument only after hearing confirmation. Updates additionally require backend verification of the existing patient's phone number and date of birth.

## Architecture

```mermaid
flowchart LR
    Caller --> Vapi[ Vapi voice, transcription, and tools ]
    Vapi -->|authenticated webhook| API[FastAPI]
    Reviewer -->|REST / Swagger| API
    API --> Validation[Shared validation]
    API --> Service[Patient service]
    Validation --> Service
    Service --> DB[(Supabase PostgreSQL<br/>patients + call_logs)]
    Vapi -->|end-of-call report| API
```

### Stack and rationale

- **FastAPI + Pydantic settings:** typed request handling, dependency injection, and OpenAPI docs at `/docs`.
- **SQLAlchemy + PostgreSQL:** relational persistence that survives Vercel function restarts and redeployments; SQLite is used for local development and isolated tests.
- **Vapi:** telephony, speech, and tool orchestration configured in its dashboard. The checked-in prompt and tool schemas are in `app/prompts/` and `app/telephony/`.
- **Vercel:** hosts the public API deployment connected to GitHub.
- **Supabase:** hosted PostgreSQL database.

## Repository map

```text
app/
  api/                 REST routes, schemas, auth, middleware, errors
  data/                SQLAlchemy models and database session
  prompts/              Versioned voice-agent system prompt
  services/             Shared validation and patient CRUD service
  telephony/            Vapi webhook handler and tool definitions
scripts/                Schema creation and fake seed data
tests/                  API, validation, service, and webhook tests
.env.example            Safe environment-variable template
```

## Local setup (Windows PowerShell)

Use Python 3.12 (or a compatible Python version satisfying the dependency ranges).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with a local SQLite URL and development-only random secrets. Do not share `.env` or commit it. The example file uses placeholders.

```env
DATABASE_URL=sqlite:///./care_cloud.db
API_KEY=replace-with-a-long-random-secret
VAPI_WEBHOOK_SECRET=replace-with-a-different-long-random-secret
```

Create the local schema, optionally add two fake seed patients, and start the API:

```powershell
python -m scripts.create_schema
python -m scripts.seed
python -m uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs`.

To run the automated suite against its isolated temporary SQLite databases:

```powershell
python -m pytest -q
```

The tests do not use the configured hosted database. **Test status after the latest webhook/prompt changes: not yet rerun.** Update this note with the actual result before submission.

## Environment variables

| Variable | Purpose | Example / notes |
|---|---|---|
| `APP_NAME` | FastAPI title | `Care Cloud Patient Intake API` |
| `APP_ENV` | Environment label | `development` or `production` |
| `LOG_LEVEL` | Logging threshold | `INFO` |
| `HOST` | Local Uvicorn bind host | `127.0.0.1` |
| `PORT` | Local server port | `8000` |
| `DATABASE_URL` | SQLAlchemy database URL | SQLite locally; hosted PostgreSQL in production |
| `API_KEY` | Required `X-API-Key` for write routes | Keep secret; share reviewer key privately |
| `VAPI_WEBHOOK_SECRET` | Shared secret for Vapi webhook authentication | Vapi Authorization Bearer token must match |
| `CORS_ORIGINS` | Optional comma-separated browser origins | Empty by default |
| `MAX_REQUEST_BYTES` | Request-body limit for non-webhook routes | Default `65536` |
| `MAX_WEBHOOK_REQUEST_BYTES` | Webhook request-body limit | Default `1048576` |
| `RATE_LIMIT_PER_MINUTE` | In-process per-client request limit | Default `120`; not shared across serverless instances |

## Database

The `patients` table uses a UUID primary key and stores demographics, contact details, optional insurance/emergency-contact fields, timestamps, and `deleted_at`. Active phone numbers are unique. Deletion is a soft delete; normal list/get/find operations exclude deleted rows. `call_logs` stores call status and may store the transcript, summary, and final collected payload.

The schema is created with SQLAlchemy `create_all` using:

```powershell
python -m scripts.create_schema
```

This project does not currently include Alembic migrations. Run schema creation intentionally against the intended database; do not point seed scripts at production unless you mean to insert the documented fake demo rows.

## REST API

All responses use this envelope:

```json
{"data": {}, "error": null}
```

Errors use `{"data": null, "error": {"code": "...", "message": "...", "fields": {}}}`. Write endpoints require `X-API-Key`; read endpoints currently do not.

| Method | Path | Purpose | Success |
|---|---|---|---|
| `GET` | `/health` | Liveness check | `200` |
| `GET` | `/patients` | List active records; optional exact, case-insensitive `last_name`, normalized `date_of_birth`, and normalized `phone_number` filters | `200` |
| `GET` | `/patients/{patient_id}` | Get one active record | `200`; `404` if missing/deleted |
| `POST` | `/patients` | Create a record | `201`; `409` active phone duplicate |
| `PUT` | `/patients/{patient_id}` | Partial update | `200`; `404` missing/deleted |
| `DELETE` | `/patients/{patient_id}` | Soft delete | `200`; row remains in DB |

Validation failures return `422`; malformed requests (including malformed UUID path values) return `400`; invalid write keys return `401`; oversized requests return `413`; rate-limited requests return `429`; unexpected failures return a generic `500` envelope without a client-facing traceback.

### Create example

Use fake data and replace `YOUR_API_KEY` locally. Do not paste a real key into documentation or chat.

```powershell
$headers = @{ "X-API-Key" = "YOUR_API_KEY" }
$body = @{
  first_name = "Casey"
  last_name = "Demo"
  date_of_birth = "1991-06-15"
  sex = "Other"
  phone_number = "2025550186"
  address_line_1 = "42 Test Avenue"
  city = "Sample City"
  state = "Virginia"
  zip_code = "22030"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "https://voice-ai-agent-patient-registration-navy.vercel.app/patients" `
  -Headers $headers -ContentType "application/json" -Body $body
```

The response includes `data.patient_id`; use that ID for subsequent GET, PUT, or DELETE requests. Swagger UI at `/docs` can also exercise the routes. Do not include real patient information in public calls.

## Voice prompt and tools

- Full system prompt: `app/prompts/registration_system_prompt.md`
- Vapi function schemas: `app/telephony/vapi_tools.json`
- Authenticated webhook route: `POST /webhook/vapi`

The prompt emphasizes a natural one-question-at-a-time flow, accepting out-of-order answers, avoiding repeated questions, validating each field, reading back details, and saving only after a clear affirmative. The backend remains authoritative for validation and persistence. The assistant's live prompt and tool configuration are maintained separately in Vapi; keep them synchronized with the checked-in files.

## Tests

Run all tests locally:

```powershell
python -m pytest -q
```

Fixtures create isolated temporary SQLite databases. They cover API routes, service behavior, validators, and Vapi tool confirmation/identity handling. No tests have been run as part of this README update. Record fresh test output after the latest code changes before submission.

## Known limitations and trade-offs

- **Public reads:** `GET /patients` and `GET /patients/{id}` do not require authentication. Deployment is for fake/demo data only; this needs access control before any real patient information could be considered.
- **Confirmation:** the backend trusts the `caller_confirmation: "yes"` tool argument and does not independently match it to the audio/transcript. The prompt tells the agent to set it only after the caller says yes.
- **Vapi configuration:** prompt, tool schemas, phone-number assignment, speech provider, and webhook credential are dashboard settings and must be checked against the repo and deployment.
- **Migrations:** schema creation uses `create_all`; there is no Alembic history or automated deployment migration.
- **Rate limiting:** the simple middleware keeps counters in process memory, so it is not a global limit across serverless instances.
- **Voice and free-tier availability:** latency, transcription quality, number availability, trial credits, and provider free limits can change; verify balances and current provider terms before review.
- **Call logs:** transcripts may contain personal details; only fake/test calls should be used for this assignment demo.
- **Not implemented:** appointment scheduling and a patient dashboard. Transcript/summary persistence exists in the webhook/model, but a public transcript-view endpoint is not implemented. Spanish responses are prompt-guided and not a fully tested localization feature.
- **Cold starts/availability:** the deployment host may sleep or impose execution limits depending on current plan settings; verify availability shortly before the review call.

## Deployment and review checklist

1. Push the intended commit to the connected GitHub branch and wait for the Vercel production deployment to report **Ready**.
2. Set `DATABASE_URL`, `API_KEY`, `VAPI_WEBHOOK_SECRET`, `APP_ENV`, `LOG_LEVEL`, and request-size settings in the Vercel environment configuration. Never commit those values.
3. Verify the deployed `/health` and `/docs` pages.
4. Confirm the Vapi webhook URL is `https://voice-ai-agent-patient-registration-navy.vercel.app/webhook/vapi` and the saved credential matches `VAPI_WEBHOOK_SECRET`.
5. Confirm Vapi's live prompt and tool schemas match the versions in this repository.
6. Verify the active U.S. phone number, provider credits, and reviewer write key on the day of review. Give the API key to the reviewer privately, not in this file.
7. Test one synthetic registration and a returning-caller lookup, then verify persistence and logs.

### Before submission — fill these in

- [ ] Active Vapi U.S. phone number: **TODO**
- [ ] Confirm reviewer has received a temporary/rotated write API key privately.
- [ ] Replace test-status note above with fresh test output.
- [ ] Confirm production Vapi prompt/tool configuration and webhook secret.
- [ ] Verify available Vapi/provider credits and deployment availability.

## Next steps

1. Add access control to patient read endpoints before any non-demo use.
2. Add Alembic migrations and deployment-safe migration instructions.
3. Add integration tests for webhook event payloads and failure cases.
4. Add authenticated call-log retrieval if transcript review is needed.
5. Consider appointment scheduling, a dashboard, and full Spanish localization only after the core registration flow is stable.

## AI assistance disclosure

AI assistance was used to help design, implement, review, and document parts of this take-home project. The project owner should review the code, run the tests, and be prepared to explain and maintain the implementation.
