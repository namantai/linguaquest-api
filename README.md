# LinguaQuest

An English learning application built with Django REST Framework and a small
HTML, CSS and vanilla JavaScript frontend. Learners complete exercises, earn XP
and receive background feedback on written English. This student portfolio project
focuses on readable backend code, API integration and automated tests.

The [screenshot guide](docs/screenshots/README.md) describes how to capture the
dashboard and practice views using safe demonstration data.

## Implemented features

- Registration, JWT login and refresh, profile and logout in the browser.
- Published courses and lessons, managed through Django Admin.
- Multiple-choice, normalized text-answer and writing exercises.
- Private submissions; correct answers excluded from public API responses.
- XP awarded once per user and exercise, including concurrent correct submissions.
- Completed exercises and lessons, with progress bars and XP indicators.
- Celery feedback processing, persisted status/results, retries and manual recovery.
- Explicit mock, real OpenAI and disabled feedback modes.
- Responsive interface, paginated API lists, loading states and error messages.

## Technology stack

Python 3.12 · Django 5.2 LTS · Django REST Framework · PostgreSQL 17 · Redis 7.4 ·
Celery · Simple JWT · drf-spectacular · OpenAI Python SDK · Pydantic · pytest ·
pytest-django · Ruff · Docker Compose.

The frontend uses HTML5, CSS3, vanilla JavaScript and Fetch. It has no framework,
package dependencies, separate server or build step. Node is optional for JavaScript
tests. `requirements.in` records dependency ranges; `requirements.txt` pins the
resolved Python environment, including test tools.

## Architecture and background AI workflow

| Directory | Responsibility |
| --- | --- |
| `accounts/` | Registration, JWT views and profile; Django's built-in User. |
| `learning/` | Courses, lessons, exercises, submissions, grading and seed command. |
| `progress/` | UserProgress, XP awards and completion tracking. |
| `ai_feedback/` | Feedback providers, structured validation, Celery task and recovery command. |
| `config/` | Django settings, URLs, WSGI and Celery configuration. |
| `templates/` | Homepage and interface structure in `index.html`. |
| `static/frontend/` | `style.css`, Fetch/token handling in `api.js`, UI behavior in `app.js`. |
| `tests/` | Python API/integration tests and dependency-free JavaScript tests. |
| `docs/screenshots/` | Demo screenshots and capture instructions. |

The domain models are User, Course, Lesson, Exercise, Submission and UserProgress.
Views validate requests through serializers; services handle grading and XP.
PostgreSQL transactions lock the user row before awarding XP. Lesson completion is
derived from completed exercises in the current lesson content.

Writing submissions are committed before `transaction.on_commit` publishes a task.
Redis carries task messages; a separate Celery worker calls the feedback provider
and saves the result in PostgreSQL. There is no Celery result backend. The browser
polls the submission API, never OpenAI directly.

### AI feedback workflow

1. The API validates a writing answer and stores a submission.
2. After commit, the task is queued through Redis.
3. Celery claims the submission, calls the configured provider and saves feedback.
4. The client polls `/api/v1/submissions/{id}/` until a terminal status.
5. A score of at least 70 completes the exercise and awards XP once.

Statuses are `pending`, `processing`, `retrying`, `completed`, `failed` and
`unavailable`. Feedback contains `score` (integer 0–100), `corrections` (strings) and
`explanation` (simple English). The browser polls every two seconds, pauses after
about two minutes and offers **Check status again**. Leaving the page stops polling,
not the saved task.

| Provider | Behavior |
| --- | --- |
| `disabled` | Writing is stored as `unavailable` / `ai_not_configured`; other exercises work. |
| `mock` | Runs through Celery, returns fixed score 80 and explicitly labeled demo feedback; awards demo XP. No OpenAI calls. |
| `openai` | Uses the OpenAI SDK Responses API and Pydantic structured output. Requires credentials and may incur charges. Missing configuration returns `unavailable`. |

Real mode sends the prompt and answer to OpenAI with `store=False`. Credentials
stay on the server. Automated tests clear the API key and replace the provider/SDK.
Mock feedback does not evaluate grammar.

Transient connection failures, HTTP 429 and provider 5xx responses retry up to three
times after 10, 20 and 40 seconds. Invalid output, refusals and authentication
failures terminate safely without exposing raw provider errors. SDK timeout is 30
seconds; task soft/hard limits are 60/90 seconds. Queue publication failure records
`queue_unavailable`.

A processing lease and token guard duplicate task deliveries. Completed submissions
are not re-evaluated. If a worker crashes or publication fails, fix the service,
then requeue failed work or a submission stale for at least five minutes:

```bash
docker compose exec api python manage.py retry_feedback SUBMISSION_ID
docker compose logs --tail=100 worker
```

Recovery preserves the original provider and rejects completed work or active
leases. A submission created with `disabled` cannot become a real AI call; submit
again after enabling the provider. There is no scheduled recovery service.

## Docker quick start

Install Docker Engine and Docker Compose, with access to the Docker daemon. From
the repository root, copy the example environment **only if you do not already have
an `.env` file**:

```bash
cp .env.example .env
```

Edit `.env`: supply your own `DJANGO_SECRET_KEY` (at least 50 unpredictable
characters) and `POSTGRES_PASSWORD`. For the full free demo, set
`AI_FEEDBACK_PROVIDER=mock` and leave `OPENAI_API_KEY` empty. Keep
`DJANGO_DEBUG=true` for local static file serving. Do not commit `.env`.

```bash
docker compose up --build -d
docker compose exec api python manage.py seed_lessons
docker compose ps
```

Open **<http://localhost:8000/>** and create an account. Select a course and lesson,
submit an answer, then check your progress. Try the writing lesson to see background
mock feedback. Its result is labeled **“Demo feedback — not real AI evaluation.”**

Optional: create a content administrator with
`docker compose exec api python manage.py createsuperuser`, then open
<http://localhost:8000/admin/>.

Compose starts PostgreSQL and Redis, waits for health checks, applies migrations,
starts the API and then the worker. The seed command is safe to rerun and preserves
existing content. Only port 8000 is exposed, bound to localhost. Data uses named
volumes. Rebuild/recreate the containers after code or environment changes.

```bash
docker compose logs -f api worker
docker compose exec api python manage.py migrate
docker compose down
```

`down` preserves data; adding `-v` deletes the database and queue volumes. Compose
uses Django's development server. The Dockerfile also has a default Gunicorn
command, but production deployment and static file serving are outside this setup.

### Environment configuration

| Variable | Purpose / default |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required Django/JWT signing secret; no application fallback. |
| `DJANGO_DEBUG` | Defaults to `false`; example enables it for local development. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts; `localhost,127.0.0.1`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional Admin origins, including scheme and port. |
| `POSTGRES_DB`, `POSTGRES_USER` | Both default to `linguaquest`. |
| `POSTGRES_PASSWORD` | Your database password; required by Compose. |
| `POSTGRES_HOST`, `POSTGRES_PORT` | Default `localhost`, `5432`; Compose overrides with `db`, `5432`. |
| `CELERY_BROKER_URL` | Redis broker URL; Compose uses `redis://redis:6379/0`. |
| `AI_FEEDBACK_PROVIDER` | `disabled` (default), `mock`, or `openai`. |
| `OPENAI_API_KEY` | Required only for real OpenAI feedback. |
| `OPENAI_MODEL` | Default `gpt-4o-mini`; must support structured Responses output. |
| `TEST_DATABASE` | Test-only: local default `sqlite`; Compose sets `postgres`. |

Environment variables override `.env`. API and worker must use the same provider
configuration; recreate both after changing it.

### Local Python development

Install Python 3.12 and run PostgreSQL and Redis locally. Create the database and
role matching `.env`, set `POSTGRES_HOST=localhost` and
`CELERY_BROKER_URL=redis://localhost:6379/0`. Compose does not publish these ports.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_lessons
python manage.py runserver 0.0.0.0:8000
```

In another terminal with the same environment, run
`celery -A config worker --loglevel=INFO`.

## Website and documentation

After starting the containers:

| Page | URL |
| --- | --- |
| Website | <http://localhost:8000/> |
| Swagger UI | <http://localhost:8000/api/docs/> |
| OpenAPI schema | <http://localhost:8000/api/schema/> |
| Django Admin | <http://localhost:8000/admin/> |

Swagger assets are bundled locally. Create a superuser to manage educational
content through Admin.

## API overview

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

Lists return DRF pagination (`count`, `next`, `previous`, `results`); single objects
are plain JSON. Send JSON request bodies. Validation errors use field names;
authentication and lookup errors use `detail`.

### Example API workflow

Register and obtain tokens using your own password:

```bash
curl -X POST http://localhost:8000/api/v1/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"student","email":"student@example.com","password":"YOUR_STRONG_PASSWORD"}'

curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"student","password":"YOUR_STRONG_PASSWORD"}'
```

Use the returned access token in `Authorization: Bearer <access token>` or Swagger's
**Authorize** dialog. Access tokens last 30 minutes and refresh tokens last one day.
Do not publish tokens or include them in screenshots. Replace the IDs below with
values returned by the list endpoints:

```bash
export ACCESS_TOKEN='PASTE_ACCESS_TOKEN_HERE'
curl http://localhost:8000/api/v1/courses/
curl http://localhost:8000/api/v1/courses/COURSE_ID/lessons/
curl http://localhost:8000/api/v1/lessons/LESSON_ID/exercises/

curl -X POST http://localhost:8000/api/v1/exercises/EXERCISE_ID/submit/ \
  -H "Authorization: Bearer $ACCESS_TOKEN" -H 'Content-Type: application/json' \
  -d '{"answer":"b"}'

curl http://localhost:8000/api/v1/me/progress/ \
  -H "Authorization: Bearer $ACCESS_TOKEN"

curl -X POST http://localhost:8000/api/v1/auth/token/refresh/ \
  -H 'Content-Type: application/json' -d '{"refresh":"PASTE_REFRESH_TOKEN_HERE"}'
```

For a choice exercise, submit an option key. For text and writing, submit the answer
string (maximum 2,000 characters). Text grading normalizes case, Unicode and
whitespace; it does not accept paraphrases. Repeating a correct answer returns
`is_correct: true` with `xp_awarded: 0`.

A terminal submission returns `201 Created`; queued feedback returns `202 Accepted`
with a polling URL in `Location`. Invalid input returns 400, missing/invalid JWTs
401, and missing or other users' submissions 404. Unsupported methods return 405.

## Tests and verification

The latest local release checks completed with **71 Python tests passed, 1 skipped**
and **17 JavaScript tests passed**, with no failures or Python warnings. The skip is
`test_concurrent_correct_answers_award_once`, which requires PostgreSQL. Django
checks, Ruff lint/formatting, OpenAPI validation and migration consistency passed.
Docker daemon access was denied during this review, so PostgreSQL and live worker
checks were not repeated. These results do not verify production deployment or real
OpenAI calls.

Run integration tests against a **separate PostgreSQL test database** in Compose:

```bash
docker compose up --build -d
docker compose exec api pytest -q -W error::pytest.PytestWarning
docker compose exec api python manage.py check
docker compose exec api python manage.py makemigrations --check --dry-run
docker compose exec api python manage.py spectacular --validate --fail-on-warn --file /tmp/schema.yaml
docker compose exec api ruff check .
docker compose exec api ruff format --check .
```

pytest loads `config.test_settings`; the running API/worker load `config.settings`.
Compose sets `TEST_DATABASE=postgres`. pytest-django creates and drops
`test_<POSTGRES_DB>` (`test_linguaquest` by default); it does not flush or write test
data to the development database. The database user needs permission to create test
databases. Do not bypass this setup or use an existing database as the test database.
Container caches use `/tmp/linguaquest-pytest-cache`, writable by the non-root app user.

Without PostgreSQL, activate the local virtual environment and run:

```bash
pytest -q -W error::pytest.PytestWarning
ruff check .
ruff format --check .
python manage.py check --settings=config.test_settings
python manage.py makemigrations --check --dry-run --settings=config.test_settings
python manage.py spectacular --settings=config.test_settings --validate --fail-on-warn --file /tmp/linguaquest-schema.yaml
```

Local tests default to in-memory SQLite. **The PostgreSQL row-locking test skips on
SQLite.** Both configurations use an in-memory broker and eager tasks, so passing
pytest does not verify a separate worker or Redis. Check those independently:

```bash
docker compose exec redis redis-cli ping
docker compose exec worker celery -A config inspect ping --timeout=10
docker compose exec worker celery -A config inspect registered --timeout=10
```

Expect `PONG`, a worker `pong`, and `ai_feedback.tasks.process_feedback` respectively.
For a complete background check, submit a writing answer in mock mode and retrieve
its completed feedback through the API or browser.

Optional JavaScript checks require Node with built-in `node:test` support, no npm:

```bash
node tests/frontend.test.cjs
node --check static/frontend/api.js
node --check static/frontend/app.js
git diff --check
```

Python tests cover authentication, visibility, validation, ownership, XP, progress,
concurrent submissions, provider mocks, task retries/recovery, schema and homepage
assets. JavaScript tests cover pagination, refresh/session races, errors and UI
state using small DOM doubles. They do not verify browser layout or interactions.

## Current limitations

- Local portfolio application; no production deployment is included. Production
  needs HTTPS, static asset serving, secret management, backups and monitoring.
- Tokens live in `sessionStorage`, accessible to JavaScript and therefore vulnerable
  to XSS. Passwords are never stored. Logout clears this tab's tokens but does not
  revoke issued JWTs or sign out other tabs; browser restoration may restore storage.
- No email verification, password reset, refresh rotation or submission-history UI.
- DRF throttles (30 auth requests/hour, 60 submissions/hour) use process-local cache;
  they are not shared abuse protection or a billing limit.
- Repeated writing submissions can make additional paid calls. A crash after a call
  but before saving can also repeat it during recovery. XP is protected; external
  calls are not exactly once. A public service would need per-user budgets.
- LLM scores may vary or be affected by prompt injection; they are not authoritative
  exam grades. Real paid OpenAI calls have not been verified for this demo.
- Adding lesson exercises can make a previously completed lesson incomplete again.
- No transactional outbox or scheduled recovery; operators inspect Admin and use
  `retry_feedback` after queue/worker failures.

## Interview study guide

Trace a submission from `config/urls.py` through the learning view, serializer and
service into `progress/services.py`. Then follow writing feedback into
`ai_feedback/tasks.py`. Be ready to explain:

- Django ORM models/migrations, serializers versus views, and password hashing.
- JWT authentication versus permissions and owner-filtered querysets.
- Transactions, `select_for_update` and why checking XP without a lock races.
- Redis versus Celery, `on_commit`, retries, duplicate delivery and the queue gap.
- Pagination, 201 versus 202, polling and safe rendering with `textContent`.
- Mock/eager tests versus PostgreSQL concurrency and live worker verification.
