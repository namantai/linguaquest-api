# LinguaQuest API project rules

- Use Python 3.12, Django 5.2 LTS, Django REST Framework and PostgreSQL.
- Keep apps focused: accounts, learning, progress, ai_feedback and config.
- Use Django's built-in User model and authentication. Use JWT for the API.
- Keep views thin; put submission, XP and AI logic in services and tasks.
- Write readable PEP 8 Python with four spaces. Avoid unnecessary abstractions.
- Never expose answer keys, other users' submissions, credentials or raw provider errors.
- Award XP once per user and exercise, including under concurrent submissions.
- Call external AI services only from Celery tasks. Persist processing states.
- Label mock feedback explicitly. Missing AI credentials must produce a clear status.
- Use mocks in automated tests; never make paid API calls in tests.
- Include migrations for model changes and verify the OpenAPI schema.
- Keep README setup instructions and environment examples accurate.
- Run relevant tests and report actual results and verification limits.
- Do not push, deploy or commit credentials.
