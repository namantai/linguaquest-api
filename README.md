# LinguaQuest API

Backend for a gamified English learning mobile application. This portfolio project
implements registration, English lessons, exercise grading, XP, progress and
background feedback on written English. There is no frontend.

The code is intended to be readable by a developer learning Django. PostgreSQL is
the application database; a separate SQLite configuration supports fast tests when
PostgreSQL is unavailable.

## Features

- Django users, password validation, JWT login and refresh, current-user profile.
- Public published courses, lessons and exercises; Django Admin content editing.
- Multiple choice, normalized exact text answers and AI writing exercises.
- Private submission history by ID, with answer keys excluded from API responses.
- XP once per user/exercise and derived lesson completion.
- Celery processing, persisted feedback/status, bounded retries and manual recovery.
- OpenAI structured feedback, explicitly labeled mock mode and disabled mode.
- OpenAPI schema, Swagger UI and automated tests without paid AI calls.

## Stack

Python 3.12, Django 5.2 LTS, Django REST Framework, PostgreSQL 17, Redis 7.4,
Celery, Simple JWT, drf-spectacular, the OpenAI Python SDK, Pydantic, pytest,
pytest-django, Ruff, Docker and Docker Compose.

`requirements.in` records compatible dependency ranges. `requirements.txt` pins
the complete resolved environment, including test tools. Review updates regularly.

## Architecture

| App | Responsibility |
| --- | --- |
| `accounts` | Registration serializers, JWT views, current user. Uses Django's built-in User. |
| `learning` | Course, Lesson, Exercise, Submission, public content APIs, answer submission, seed command. |
| `progress` | UserProgress, XP awards and completed exercises/lessons. |
| `ai_feedback` | OpenAI/mock services, feedback schema, Celery task and recovery command. |
| `config` | Settings, URLs, WSGI and Celery application. |

The six domain models are User, Course, Lesson, Exercise, Submission and
UserProgress. Django creates a join table for completed exercises. There are no
repositories or dependency injection frameworks.

```text
accounts/       Registration, JWT and user profile
learning/       Courses, lessons, exercises, submissions and seed command
progress/       XP awards and completion tracking
ai_feedback/    Feedback providers, Celery task and recovery command
config/         Django settings, URL routing and Celery configuration
tests/          API, permissions, progress, concurrency and feedback tests
manage.py
Dockerfile
compose.yaml
requirements.in
requirements.txt
.env.example
```

Requests go through URLs → views → serializers → services → models. Views validate
input and return HTTP responses. Services handle grading and XP. A writing submission
is committed before its task is published using `transaction.on_commit`. The worker
calls the AI service and writes feedback into the same submission row.

## Start with Docker

Requirements: Git, Docker Engine and Docker Compose, with permission to access the
Docker daemon. Run these commands from the repository root:

```bash
cp .env.example .env
```

Edit `.env`: set your own `DJANGO_SECRET_KEY` (at least 50 unpredictable characters)
and `POSTGRES_PASSWORD`. Keep `AI_FEEDBACK_PROVIDER=disabled` to start without an
OpenAI account. Do not commit `.env`.

```bash
docker compose up --build -d
docker compose exec api python manage.py seed_lessons
docker compose exec api python manage.py createsuperuser
docker compose ps
```

The API runs at <http://localhost:8000>. Swagger is at
<http://localhost:8000/api/docs/>, the schema at
<http://localhost:8000/api/schema/>, and Django Admin at
<http://localhost:8000/admin/>. Swagger assets are bundled locally.

Compose starts PostgreSQL and Redis, waits for their health checks, applies
migrations, starts the API, then starts the worker. The seed command is explicit
and safe to rerun; it preserves existing content. Database and Redis data use named
volumes. Only the API port is exposed, bound to localhost.

```bash
docker compose logs -f api worker
docker compose exec api python manage.py migrate
docker compose exec api python manage.py makemigrations --check --dry-run
docker compose down
```

`down` preserves data. `down -v` deletes the development database and queue volumes.
Compose uses Django's development server so Admin and Swagger assets work with
`DJANGO_DEBUG=true`. The Dockerfile's default Gunicorn command is available for
other environments; production static file serving and deployment are outside scope.
After code or dependency changes, rebuild with `docker compose up --build -d`.

## Local Python development

Install Python 3.12 and run PostgreSQL and Redis locally. Create the PostgreSQL role
and database matching `.env`, then set `POSTGRES_HOST=localhost` and
`CELERY_BROKER_URL=redis://localhost:6379/0`. Compose does not publish their ports.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_lessons
python manage.py runserver 0.0.0.0:8000
```

In another terminal, with the same environment activated:

```bash
celery -A config worker --loglevel=INFO
```

## Environment variables

| Variable | Meaning / default |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required; Django and JWT signing secret. No application fallback. |
| `DJANGO_DEBUG` | `false` by default; `.env.example` enables it for local development. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts; `localhost,127.0.0.1`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional origins for Admin, including scheme and port. |
| `POSTGRES_DB`, `POSTGRES_USER` | Both default to `linguaquest`. |
| `POSTGRES_PASSWORD` | Your database password; required by Compose. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Application defaults: `localhost`, `5432`; Compose sets `db`, `5432`. |
| `CELERY_BROKER_URL` | Redis URL; Compose sets `redis://redis:6379/0`. |
| `AI_FEEDBACK_PROVIDER` | `disabled` (default), `openai`, or `mock`. |
| `OPENAI_API_KEY` | Required only for real AI feedback. |
| `OPENAI_MODEL` | `gpt-4o-mini`; choose a model supporting structured Responses output. |
| `TEST_DATABASE` | Test-only: `sqlite` locally by default; Compose sets `postgres`. |

Environment variables take precedence over `.env`. The API and worker must have
the same provider configuration. Restart/recreate both after changing it.

## API and demonstration

All application endpoints use `/api/v1/`. Lists use DRF pagination:
`{"count": 1, "next": null, "previous": null, "results": [...]}`.
Single objects are plain JSON. Validation errors use field names; authentication
and lookup errors use `detail`. JSON is required for request bodies.

| Method | Path | Access |
| --- | --- | --- |
| POST | `/api/v1/auth/register/` | Public |
| POST | `/api/v1/auth/token/` | Public |
| POST | `/api/v1/auth/token/refresh/` | Public |
| GET | `/api/v1/me/` | JWT |
| GET | `/api/v1/courses/` | Public |
| GET | `/api/v1/courses/{id}/` | Public |
| GET | `/api/v1/courses/{id}/lessons/` | Public |
| GET | `/api/v1/lessons/{id}/` | Public |
| GET | `/api/v1/lessons/{id}/exercises/` | Public |
| POST | `/api/v1/exercises/{id}/submit/` | JWT |
| GET | `/api/v1/submissions/{id}/` | Owner's JWT |
| GET | `/api/v1/me/progress/` | JWT |

Register, then obtain tokens (replace the example password with your own):

```bash
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"student","email":"student@example.com","password":"YOUR_STRONG_PASSWORD"}'

curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"student","password":"YOUR_STRONG_PASSWORD"}'
```

Copy the returned access token into `ACCESS_TOKEN` in your shell. Access tokens
last 30 minutes; refresh tokens last one day. Swagger's **Authorize** accepts the
access token. Tokens grant access as the user; do not publish them.

```bash
export ACCESS_TOKEN='PASTE_ACCESS_TOKEN_HERE'
curl http://localhost:8000/api/v1/me/ -H "Authorization: Bearer $ACCESS_TOKEN"
curl http://localhost:8000/api/v1/courses/
curl http://localhost:8000/api/v1/courses/1/lessons/
curl http://localhost:8000/api/v1/lessons/1/exercises/

curl -X POST http://localhost:8000/api/v1/exercises/1/submit/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"answer":"b"}'

curl http://localhost:8000/api/v1/me/progress/ \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -X POST http://localhost:8000/api/v1/auth/token/refresh/ \
  -H 'Content-Type: application/json' -d '{"refresh":"PASTE_REFRESH_TOKEN_HERE"}'
```

IDs above match a fresh seeded database; otherwise use IDs from list responses.
The first correct seeded choice earns 10 XP. Repeating it returns `is_correct: true`
with `xp_awarded: 0`. Submit `{"answer":"am"}` to the seeded text exercise to finish
the first lesson and reach 20 XP. Text grading ignores case, Unicode presentation
differences and repeated whitespace; it does not accept paraphrases.

`201 Created` means a submission was stored and is already graded or terminal.
`202 Accepted` means AI work is pending. The `Location` response header is the polling
URL. Invalid answers return 400, missing/invalid JWTs return 401, and missing or
other users' submissions return 404. Unsupported methods return 405.

## AI, Celery and Redis

Redis carries task messages. Celery runs a separate worker process so OpenAI calls
do not block a Django view. PostgreSQL holds all submissions, statuses and feedback;
there is no Celery result backend. A short broker publication can still delay the
request, with connection timeouts configured.

For a free background-task demonstration, set `AI_FEEDBACK_PROVIDER=mock` in
`.env`, then recreate both the API and worker. Leave `OPENAI_API_KEY` empty.
The mock still runs through Redis and the Celery worker:

```bash
docker compose up -d --force-recreate api worker
curl -X POST http://localhost:8000/api/v1/exercises/3/submit/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"answer":"I wake up at seven. I goes to university every day."}'
curl http://localhost:8000/api/v1/submissions/RETURNED_ID/ \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

Replace `RETURNED_ID` with the submission ID from the POST response. In mock mode,
a completed submission contains:

```json
{
  "status": "completed",
  "provider": "mock",
  "feedback": {
    "score": 80,
    "corrections": [],
    "explanation": "Mock feedback. No AI evaluation was performed."
  },
  "xp_awarded": 20
}
```

The XP above assumes the seeded writing exercise and a first successful answer.
Request the submission again to read the stored feedback. Check worker activity with
`docker compose logs --tail=100 worker`.

For real feedback, set `AI_FEEDBACK_PROVIDER=openai`, supply `OPENAI_API_KEY` and
choose `OPENAI_MODEL`, then recreate both services with the same command. Real
feedback requires API access and may incur charges; mock mode never calls OpenAI.

Poll every few seconds until `completed`, `failed` or `unavailable`. Feedback has
`score` (integer 0–100), `corrections` (list of strings) and `explanation` (simple
English). Scores of at least 70 complete the exercise and award XP once. The SDK
uses the Responses API with Pydantic structured output, following the
[official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
Inputs are limited to 2,000 characters. Student writing and the exercise prompt are
sent to OpenAI only in real mode; the request uses `store=False`.

Provider behavior is explicit:

- `disabled`: writing submissions are stored as `unavailable`, with
  `error_code: ai_not_configured`. Other features work normally.
- `openai` without credentials: also `unavailable`; no simulated response.
- `mock`: fixed score 80 and an explanation stating no AI evaluation occurred.
  Responses include `provider: mock`. This mode awards demo XP and requires the
  worker in normal operation. It does not assess grammar.
- `openai` with credentials: real calls that may incur API charges. Tests always
  replace the provider/SDK and clear the real key.

Transient connection errors, HTTP 429 and provider 5xx errors retry up to three
times, after 10, 20 and 40 seconds. Authentication failures, invalid structured
output and refusals terminate as failures. Raw provider exceptions are never returned.
Tasks use a 30-second SDK timeout, 60-second soft limit and 90-second hard limit.

The state flow is `pending → processing → completed`, with `retrying`, `failed`
and `unavailable` alternatives. Queue publication failures set `queue_unavailable`.
A processing lease and token prevent duplicate deliveries from overwriting a newer
result; completed submissions do not call the provider again. XP and completion
are committed together under a PostgreSQL row lock on the user.

If the worker is killed or the process exits between the database commit and queue
publication, a submission may remain pending/processing. After fixing the worker or
broker, requeue a failed submission, or one stale for at least five minutes:

```bash
docker compose exec api python manage.py retry_feedback SUBMISSION_ID
```

This operator command preserves the original provider and rejects completed work
or active leases. A submission created with `disabled` cannot be converted into a
real AI call; submit a new answer after enabling the provider. There is no automatic
periodic recovery service in this version.

## Tests and checks

Fast isolated tests use SQLite, an in-memory Celery broker and eager tasks:

```bash
pytest -q
ruff check .
ruff format --check .
python manage.py check --settings=config.test_settings
python manage.py spectacular --settings=config.test_settings --validate --fail-on-warn --file /tmp/linguaquest-schema.yaml
```

Compose sets `TEST_DATABASE=postgres`, so its default pytest command verifies actual
row locking and simultaneous submissions. Rebuild/recreate existing containers to
pick up the test settings and writable cache configuration:

```bash
docker compose up --build -d
docker compose exec api pytest -q -W error::pytest.PytestWarning
docker compose exec api python manage.py check
docker compose exec api python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yaml
```

pytest loads `config.test_settings`; normal API and worker processes load
`config.settings`. PostgreSQL tests use an explicitly named `test_<POSTGRES_DB>`
database (`test_linguaquest` with the example configuration). pytest-django creates
it, applies migrations, runs tests, and drops it afterward. The development database
is not flushed or used for test writes. Do not bypass pytest-django's database setup
or point a test database at existing data. Overlong database names and invalid
`TEST_DATABASE` values are rejected rather than silently selecting another backend.

Container pytest caches go to `/tmp/linguaquest-pytest-cache` via `PYTEST_ADDOPTS`.
The application still runs as the unprivileged `app` user; `/app` permissions do not
need to change. To deliberately run the SQLite suite in Compose, use
`docker compose exec -e TEST_DATABASE=sqlite api pytest -q`; its row-locking test skips.

Check the live broker and worker separately from the eager task tests:

```bash
docker compose exec redis redis-cli ping
docker compose exec worker celery -A config inspect ping --timeout=10
docker compose exec worker celery -A config inspect registered --timeout=10
```

Expect Redis `PONG`, a worker `pong`, and `ai_feedback.tasks.process_feedback` in the
registered task list. These checks do not enqueue AI work or change learner data.

The PostgreSQL test user needs permission to create a test database (the Compose
development user has it). Tests cover auth, course visibility, input validation,
ownership, repeated XP, lesson completion, provider mocks, task retries, task
deduplication, recovery and schema generation. The concurrency test explicitly skips
on SQLite because SQLite does not implement PostgreSQL row locks. Eager task tests
do not verify a live Redis broker or a separate worker process.

The verified Docker/PostgreSQL suite has **71 passing tests, no skipped tests and
no warnings**. SQLite runs skip the PostgreSQL concurrency test. A live mock-provider
workflow has also been checked through the API: registration, JWT login, writing
submission (`202 pending`), background completion, feedback retrieval and XP.
Real OpenAI calls have not been verified with paid API credentials.

## Limitations and future improvements

- This is a local portfolio implementation, not a production deployment.
- PostgreSQL concurrency checks and real broker/worker tests need those services.
- No email verification, password reset, logout/revocation or refresh rotation.
- DRF throttles provide a basic local guard (30 auth requests/hour, 60 submissions/hour).
  They use process-local cache and are not a shared abuse or billing limit.
- Repeated writing submissions may incur new calls even after XP was earned. A
  real public release needs per-user budgets and stronger rate limiting.
- A crash after an external call but before saving can cause a repeated paid call
  on recovery. Database results/XP are guarded; external calls are not exactly once.
- LLM scores can be inconsistent or manipulated by prompt injection. Do not treat
  them as authoritative exam scores. Mock mode must not be used for real assessment.
- Lesson completion is derived from current content. Adding exercises can make a
  lesson incomplete again; content versioning is a future improvement.
- There is no task dashboard, scheduled recovery or transactional outbox. An
  operator can inspect submissions in Admin and run `retry_feedback`.
- Production work would include HTTPS, static asset serving, shared throttling,
  secret management, monitoring, backups and a deployment-specific security review.

## Interview study guide

Start with `config/urls.py` and trace a choice submission through
`learning/views.py`, `learning/serializers.py`, `learning/services.py` and
`progress/services.py`. Then follow the writing path into `ai_feedback/tasks.py`.

- **Django vs Spring:** URL patterns map requests; DRF views resemble controllers;
  serializers validate/represent data; services hold business rules; Django ORM
  models describe persistence. Migrations are versioned schema changes.
- **Authentication:** `create_user` hashes passwords; JWT authenticates requests;
  permissions and owner-filtered querysets enforce access independently.
- **Transactions:** explain `atomic`, PostgreSQL `select_for_update`, why the user
  row exists before UserProgress, and why checking XP without a lock races.
- **Background work:** explain Redis as broker, Celery as worker, `on_commit`,
  retries, duplicate delivery, leases and the database/queue publication gap.
- **API contracts:** distinguish 201/202/400/401/404, pagination and polling;
  explain why answer keys are absent from response serializer fields.
- **AI integration:** input limits, structured validation, mock isolation, safe
  failures, model configuration, costs and the limits of LLM grading.
- **Testing:** explain the difference between mocked unit/integration tests,
  PostgreSQL concurrency tests and a real end-to-end broker/worker demonstration.
