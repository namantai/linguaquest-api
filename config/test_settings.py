"""Isolated tests: no .env secrets, network calls, or external broker required."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-deployment-secret")

from .settings import *  # noqa: E402,F403

test_database_backend = os.getenv("TEST_DATABASE", "sqlite")
if test_database_backend == "sqlite":
    DATABASES = {
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
    }
elif test_database_backend == "postgres":
    # pytest-django creates/destroys this database, never the application database.
    # Do not expose an override that could accidentally name the development DB.
    development_database = DATABASES["default"]["NAME"]  # noqa: F405
    test_database_name = f"test_{development_database}"
    # PostgreSQL truncates identifiers to 63 bytes. Reject names that could collide.
    if len(test_database_name.encode("utf-8")) > 63:
        raise ValueError("POSTGRES_DB is too long to derive a safe test database name.")
    DATABASES["default"]["TEST"] = {"NAME": test_database_name}  # noqa: F405
else:
    raise ValueError("TEST_DATABASE must be sqlite or postgres.")

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AI_FEEDBACK_PROVIDER = "mock"
OPENAI_API_KEY = ""
CELERY_BROKER_URL = "memory://"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": []}  # noqa: F405
