# Demo screenshots

Use this guide to capture or refresh real application screenshots with safe demo
data. Do not use mockups or change displayed values in developer tools.

## Prepare safe demonstration data

1. Follow the main [README](../../README.md#docker-quick-start) to start and seed the app.
2. Set `AI_FEEDBACK_PROVIDER=mock` and leave `OPENAI_API_KEY` empty in `.env`.
   Recreate the API and worker with `docker compose up --build -d`.
3. Open <http://localhost:8000/>. Create a demonstration account with a name such as
   `portfolio_demo` and an address at `example.com`. Use a new password, not a real
   account's password. Do not include the registration or login form in the images.
4. Complete a few seeded exercises so progress comes from actual submissions.

## Capture the views

Use the same desktop window size (around 1440 × 1000) and 100% browser zoom. Capture
only the application area using your browser or operating system's screenshot tool.
Wait until loading indicators disappear.

| File | View to capture |
| --- | --- |
| `dashboard.png` | **Overview**, showing the demo username, earned XP and available courses. |
| `practice.png` | A multiple-choice or text exercise, showing its prompt and answer controls. |
| `ai-feedback.png` (optional) | A completed writing submission, showing its score, explanation and **Demo feedback — not real AI evaluation.** label. |

For writing feedback, submit a short English answer and wait for the Celery worker
to complete it. An unavailable or failed result is not a completed feedback example.

Close developer tools, network/storage panels and terminals before capturing.
Inspect each image for passwords, JWTs, API keys, personal email addresses and other
private information. Save the PNGs in this directory, then add their relative
image links to the main README. Do not commit empty placeholders.
