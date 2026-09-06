# Web recovery supervisor prototype

This prototype supplements, but does not replace, the reconnect behavior in
Flet Web 0.85.3. It is loaded from EventPlus-owned `assets/index.html`; the
installed Flet bundle and `main.dart.js` remain unchanged.

## Recovery cycle

1. `offline` records one outage cycle in `sessionStorage`. It never reloads.
2. `online`, `pageshow`, or return to foreground may start recovery only when
   an outage is pending and the current path is an authenticated `/app` route.
3. Same-origin `/health` is probed with `cache: no-store`, no credentials, and
   an `AbortController` timeout of 1.8 seconds.
4. A failed probe is retried every second, at most eight times per recovery
   invocation. There is no permanent polling.
5. After HTTP 200, the native Flet reconnect receives a 2.5-second grace
   period. The prototype cannot observe Flet's private connection state, so it
   then performs one rescue reload for that outage.
6. The reload marker survives the reload and closes the outage cycle on the
   next page load, preventing a loop.

The supervisor is disabled outside `/app`, including `/`, login and
`/auth/callback`. This deliberately favors OAuth safety over rescuing an
unauthenticated login screen.

## Stored data and telemetry

Only technical state is stored: outage flag, cycle number, rescue-reload flag,
offline timestamp, and a random recovery ID. No EventPlus or authentication
data is stored by the script.

Telemetry is best-effort and same-origin. The endpoint accepts only a closed
event list and constrained technical fields. Requests omit credentials. No
database or Supabase writes occur.

## State across a rescue reload

The following transient UI state can be lost: unsubmitted text, local checkbox
selection, open dialogs, filters/results not persisted by the application, and
operations whose response has not yet reached the browser.

EventPlus restores its server session, authenticated user, selected account,
selected event, and route using the existing 3A mechanisms. Arrival writes that
already completed in Supabase remain persisted and are read again. A reload
does not click a button, reopen a confirmation dialog, or auto-submit an
arrival. An in-flight request has an inherently ambiguous outcome; the operator
must verify the refreshed persisted state before retrying.

## Manual test

Run with the project interpreter:

```powershell
env\Scripts\python.exe -m uvicorn asgi:app --host 0.0.0.0 --port 8560 --timeout-graceful-shutdown 5
```

1. Sign in and navigate to an `/app/...` route.
2. In Chrome DevTools Network, select **Offline**.
3. Confirm no reload occurs while offline.
4. Restore **No throttling**.
5. Confirm `/health` returns 200, then exactly one reload occurs after about
   2.5 seconds.
6. Confirm no reload loop and that route/account/event/session are restored.
7. Repeat after returning from background and after a screen lock.
8. Start OAuth from `/`; confirm the supervisor does not probe or reload.

Expected Render correlation:

```text
[WEBCLIENT][ONLINE]
[WEBCLIENT][RECOVERY_START]
[WEBCLIENT][HEALTH_OK]
[WEBCLIENT][RESCUE_RELOAD]
[WEB][PAGE_CREATED] or [WEB][CONNECT]
[SESSION][RESTORE_OK]
[WEB][READY]
```
