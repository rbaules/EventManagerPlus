(() => {
  "use strict";

  const KEYS = Object.freeze({
    outage: "evp_network_outage",
    cycle: "evp_recovery_cycle",
    reloadDone: "evp_rescue_reload_done",
    lastOfflineAt: "evp_last_offline_at",
    recoveryId: "evp_client_recovery_id",
  });
  const HEALTH_TIMEOUT_MS = 1800;
  const HEALTH_RETRY_MS = 1000;
  const MAX_HEALTH_PROBES = 8;
  const NATIVE_RECONNECT_GRACE_MS = 2500;
  let recoveryPromise = null;

  const sleep = (milliseconds) =>
    new Promise((resolve) => window.setTimeout(resolve, milliseconds));

  function isProtectedPath() {
    const path = window.location.pathname;
    return path === "/auth/callback" || path === "/auth/callback/" ||
      !(path === "/app" || path === "/app/" || path.startsWith("/app/"));
  }

  function currentRecoveryId() {
    let value = sessionStorage.getItem(KEYS.recoveryId);
    if (!value) {
      value = window.crypto && typeof window.crypto.randomUUID === "function"
        ? window.crypto.randomUUID().replaceAll("-", "")
        : `${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
      sessionStorage.setItem(KEYS.recoveryId, value);
    }
    return value;
  }

  function elapsedSeconds() {
    const offlineAt = Number(sessionStorage.getItem(KEYS.lastOfflineAt));
    return Number.isFinite(offlineAt) && offlineAt > 0
      ? Math.max(0, (Date.now() - offlineAt) / 1000)
      : 0;
  }

  function telemetry(eventName) {
    if (isProtectedPath()) return Promise.resolve();
    const payload = {
      event: eventName,
      client_recovery_id: currentRecoveryId(),
      timestamp: new Date().toISOString(),
      path: window.location.pathname,
      elapsed_seconds: elapsedSeconds(),
    };
    return fetch("/diagnostics/web-recovery", {
      method: "POST",
      cache: "no-store",
      credentials: "omit",
      keepalive: true,
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    }).catch(() => undefined);
  }

  function markOffline() {
    if (isProtectedPath()) return;
    if (sessionStorage.getItem(KEYS.outage) !== "1") {
      const cycle = Number(sessionStorage.getItem(KEYS.cycle) || "0") + 1;
      sessionStorage.setItem(KEYS.cycle, String(cycle));
      sessionStorage.setItem(KEYS.recoveryId, "");
      sessionStorage.setItem(KEYS.lastOfflineAt, String(Date.now()));
      sessionStorage.setItem(KEYS.reloadDone, "0");
    }
    sessionStorage.setItem(KEYS.outage, "1");
    void telemetry("OFFLINE");
  }

  async function healthProbe() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), HEALTH_TIMEOUT_MS);
    try {
      const response = await fetch("/health", {
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      return response.status === 200;
    } catch (_error) {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function recover(trigger) {
    if (isProtectedPath() || sessionStorage.getItem(KEYS.outage) !== "1" ||
        sessionStorage.getItem(KEYS.reloadDone) === "1" || !navigator.onLine) {
      return;
    }

    if (trigger === "online") void telemetry("ONLINE");
    if (trigger === "foreground") void telemetry("FOREGROUND");
    void telemetry("RECOVERY_START");

    let healthy = false;
    for (let attempt = 0; attempt < MAX_HEALTH_PROBES; attempt += 1) {
      if (!navigator.onLine || isProtectedPath()) return;
      healthy = await healthProbe();
      void telemetry(healthy ? "HEALTH_OK" : "HEALTH_FAILED");
      if (healthy) break;
      if (attempt + 1 < MAX_HEALTH_PROBES) await sleep(HEALTH_RETRY_MS);
    }
    if (!healthy) return;

    await sleep(NATIVE_RECONNECT_GRACE_MS);
    if (!navigator.onLine || isProtectedPath() ||
        sessionStorage.getItem(KEYS.outage) !== "1" ||
        sessionStorage.getItem(KEYS.reloadDone) === "1") {
      return;
    }

    sessionStorage.setItem(KEYS.reloadDone, "1");
    void telemetry("RESCUE_RELOAD");
    window.location.reload();
  }

  function startRecovery(trigger) {
    if (recoveryPromise) return;
    recoveryPromise = recover(trigger).finally(() => {
      recoveryPromise = null;
    });
  }

  function completeReloadedCycle() {
    if (sessionStorage.getItem(KEYS.outage) === "1" &&
        sessionStorage.getItem(KEYS.reloadDone) === "1") {
      sessionStorage.setItem(KEYS.outage, "0");
    }
  }

  window.addEventListener("offline", markOffline);
  window.addEventListener("online", () => startRecovery("online"));
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" &&
        sessionStorage.getItem(KEYS.outage) === "1") {
      startRecovery("foreground");
    }
  });
  window.addEventListener("pageshow", () => {
    completeReloadedCycle();
    if (sessionStorage.getItem(KEYS.outage) === "1" && navigator.onLine) {
      startRecovery("pageshow");
    }
  });

  completeReloadedCycle();
})();
