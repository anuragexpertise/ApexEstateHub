# Post-deploy smoke test (Render + Aiven)

Run after every production deploy. `$URL` = your `https://…onrender.com` (or custom domain).

1. **Health / DB** — `curl -si $URL/healthz` → `200 {"status":"ok","db":"connected"}`.
   Check Render's service health shows *Healthy*. A 503 means the Aiven database is unreachable
   (check `DATABASE_URL`, `PGSSLMODE`, the Aiven IP allow-list, and the connection limit).
2. **HTTPS and cookies** — log in via the browser; in DevTools → Application → Cookies the session
   cookie must show `Secure`, `HttpOnly`, `SameSite=Lax`. `curl -sI http://…` must redirect to https.
3. **Proxy headers** — the audit/login log should show your real client IP, not a Render internal IP.
4. **No debug** — `curl -si $URL/does-not-exist` returns a plain 404 page, never a Werkzeug traceback;
   force an error and confirm the response contains no exception text.
5. **CORS** — `curl -si -H "Origin: https://evil.example" $URL/healthz` must NOT contain
   `Access-Control-Allow-Origin` (unless that origin is listed in `CORS_ORIGINS`).
6. **RBAC / tenancy** — as a resident of society A, open a society-B record URL → denied/empty. As a
   non-admin, open an admin-only page → denied.
7. **Rate limits** — as a logged-in user, POST `/api/push/send-test` 6 times in a minute → the 6th
   returns `429`.
8. **Web Push on live HTTPS** (VAPID)
   - Open the app in Chrome on Android or desktop; accept the notification prompt.
   - Confirm `GET /api/push/vapid-public-key` (or the page's configured key) equals `VAPID_PUBLIC`, and that
     `VAPID_PRIVATE` appears nowhere in served JS/HTML: `curl -s $URL | grep -c "$VAPID_PRIVATE"` → `0`.
   - Trigger a test push (`/api/push/send-test`); the notification must appear, and clicking it opens `/dashboard/`.
   - **Dead-subscription purge:** unsubscribe/clear site data in the browser, send another test push, then
     confirm the row is gone: `SELECT count(*) FROM push_subscriptions WHERE user_id = <id>;` → `0`.
   - iOS: push works only for a PWA added to the Home Screen (iOS 16.4+) and served over HTTPS.
9. **Realtime** — open two tabs as one user and a third; the third `/api/sse/events` must return `429`
   (limit is `SSE_MAX_PER_USER`, default 2).
10. **Gate scan** — scan one QR from a phone on mobile data; confirm one `gate_access` row per scan, and a
    repeated scan within a few seconds does not create duplicates.
11. **Persistence** — upload a document/photo, trigger a redeploy, and confirm it is still there
    (see `docs/DEPLOYMENT_STORAGE.md`; local-disk uploads will NOT survive).
12. **Jobs** - trigger each of the five Render Cron Jobs once (**Trigger Run**) and confirm exit 0 and a fresh row for
    each in `job_runs`: `SELECT job_name, status, finished_at FROM job_runs ORDER BY started_at DESC LIMIT 10;`.
    Then set a wrong `SECRET_VAULT_KEY` on the `estatehub-jobs` group, run `anchors`, and confirm the master receives
    "Scheduled job failed: anchors"; restore the key. See `docs/SCHEDULER.md`.
