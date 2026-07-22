import path from "node:path";

// OpenCode plugin (local project plugin, auto-discovered in .opencode/plugins/).
//
// Harness glue: it invokes the deterministic, harness-agnostic tool at
// .agentic/tools/check-framework-updates.py, interprets its JSON result and
// shows a toast when appropriate. All lock/git/commit logic lives in the
// tool — none is duplicated here.
//
// Lifecycle (current):
//   * The plugin body is invoked ONCE by OpenCode at load time. It launches a
//     single update check immediately (fire-and-forget), without waiting for
//     any session to be created and without blocking the Hooks resolution.
//   * session.created is kept TEMPORARILY as a fallback, used at most once per
//     plugin instance, only if the init check did not produce a visible toast.
//     It is NOT a per-session check anymore: /new and subagent sessions do not
//     trigger a new remote query.
//
// State machine (per plugin instance, no persistent cache):
//   IDLE              init check not launched yet
//   RUNNING           init check in progress
//   DONE              result obtained AND toast handled (shown or null)
//   TOAST_PENDING     result obtained, toast could not be shown
//   NO_RESULT         ran but no interpretable result (non-JSON / exception)
//   FALLBACK_RUNNING  fallback in progress (prevents concurrent fallback)
//   FALLBACK_CONSUMED terminal: fallback already used
//
// Anti-race: if session.created arrives while RUNNING, the handler awaits the
// init promise and then re-evaluates the state — it never launches a second
// concurrent check.
//
// Diagnostic escape hatch: AGENTIC_UPDATE_CHECK_DEFER_INIT_TOAST=1 forces the
// init toast to be treated as deferred (TOAST_PENDING) so the fallback path
// can be exercised without altering productive behavior when the flag is off.

const TOOL_REL = path.join(".agentic", "tools", "check-framework-updates.py");
const SERVICE = "agentic-update-check";

const STATE = {
  IDLE: "IDLE",
  RUNNING: "RUNNING",
  DONE: "DONE",
  TOAST_PENDING: "TOAST_PENDING",
  NO_RESULT: "NO_RESULT",
  FALLBACK_RUNNING: "FALLBACK_RUNNING",
  FALLBACK_CONSUMED: "FALLBACK_CONSUMED",
};

// Diagnostic flag (see header). Off in production.
const DEFER_INIT_TOAST =
  process.env.AGENTIC_UPDATE_CHECK_DEFER_INIT_TOAST === "1";

function shortSha(sha) {
  return typeof sha === "string" && sha.length >= 12 ? sha.slice(0, 12) : String(sha);
}

const APPLY_CMD = "python3 bin/agentic-sync.py --apply";

function pullStep(frameworkSource) {
  if (frameworkSource) {
    return "Actualiza el clon local del framework en " + frameworkSource +
      " con git pull --ff-only.";
  }
  return "Actualiza primero tu clon local del Agentic Framework con " +
    "git pull --ff-only.";
}

function applyStep() {
  return "Despues, desde ese clon, ejecuta " + APPLY_CMD +
    " indicando la ruta de este repositorio";
}

function buildToast(r) {
  switch (r.code) {
    case 0: // UP_TO_DATE
    case 2: // SOURCE_REPO_SKIPPED
      return null;
    case 1: // UPDATE_AVAILABLE
      return {
        title: "Actualizacion del framework disponible",
        message:
          "Instalado: " + shortSha(r.installed_commit) + "\n" +
          "Disponible: " + shortSha(r.remote_commit) + "\n" +
          "Rama: " + r.branch + "\n\n" +
          pullStep(r.framework_source) + " " + applyStep() + ".",
        variant: "warning",
        duration: 12000,
      };
    case 3: // LOCK_MISSING
      return {
        title: "Framework incompleto",
        message:
          "Falta .agentic.lock.json; la instalacion o sincronizacion esta " +
          "incompleta. " + pullStep(r.framework_source) + " " + applyStep() + ".",
        variant: "warning",
        duration: 10000,
      };
    case 4: // LOCK_INCOMPLETE
      return {
        title: "Framework incompleto",
        message:
          "El lock no contiene todavia la trazabilidad necesaria. " +
          pullStep(r.framework_source) + " " + applyStep() +
          " para regenerar el lock.",
        variant: "warning",
        duration: 10000,
      };
    case 5: // LOCK_INVALID
    case 6: // REMOTE_BRANCH_MISSING
    case 7: // GIT_OR_NETWORK_ERROR
      return {
        title: "No se pudo comprobar el framework",
        message: "No se pudo comprobar el estado de actualizacion del framework.",
        variant: "info",
        duration: 6000,
      };
    default:
      return null;
  }
}

// Best-effort structured logging via OpenCode's official app.log API.
// Never throws, never blocks: it is fire-and-forget. Errors are swallowed —
// logging must not break the plugin.
function makeLogger(client) {
  const fn = client && client.app && typeof client.app.log === "function"
    ? client.app.log.bind(client.app)
    : null;
  return function emit(level, message, extra) {
    if (!fn) return;
    const lvl = (level === "debug" || level === "info" ||
                 level === "warn" || level === "error") ? level : "info";
    try {
      const p = fn({
        body: {
          service: SERVICE,
          level: lvl,
          message: String(message),
          extra: extra || {},
        },
      });
      if (p && typeof p.catch === "function") p.catch(() => {});
    } catch (_e) {
      // Swallow: logging is best-effort.
    }
  };
}

// Try to show a toast. Returns true on success, false on failure (TUI not
// ready, API error, etc). Never throws.
async function tryShowToast(client, toast) {
  if (!toast) return true;
  try {
    const res = await client.tui.showToast({ body: toast });
    if (res && res.error) return false;
    return true;
  } catch (_e) {
    return false;
  }
}

// Run the tool once and return a parsed result object, or null when no
// interpretable result could be obtained (tool missing, non-JSON, exception).
async function runToolOnce($, worktree, rootDir) {
  const toolPath = path.join(worktree || "", TOOL_REL);
  const root = rootDir || worktree || "";
  let res;
  try {
    res = await $`python3 ${toolPath} --root ${root}`.quiet().nothrow();
  } catch (_e) {
    return null;
  }
  if (!res) return null;
  try {
    return JSON.parse(String(res.stdout).trim());
  } catch (_e) {
    return null;
  }
}

const TOOL_FAILURE_TOAST = {
  title: "No se pudo comprobar el framework",
  message: "No se pudo comprobar el estado de actualizacion del framework.",
  variant: "info",
  duration: 6000,
};

export const AgenticUpdateCheck = async ({ client, $, worktree }) => {
  const log = makeLogger(client);

  // Per-instance state (no persistent cache).
  let state = STATE.IDLE;
  let pendingToast = null;
  let initPromise = null;

  log("info", "plugin initialized", { worktree: worktree || null });

  // ---- Init check -------------------------------------------------------
  // Runs detached; does NOT block Hooks resolution.
  const runInitCheck = async () => {
    state = STATE.RUNNING;
    log("info", "init check launched");
    const parsed = await runToolOnce($, worktree, worktree);
    if (!parsed) {
      log("warn", "init check produced no interpretable result");
      state = STATE.NO_RESULT;
      return;
    }
    log("info", "tool result", { code: parsed.code, status: parsed.status });
    const toast = buildToast(parsed);
    if (!toast) {
      state = STATE.DONE;
      return;
    }
    if (DEFER_INIT_TOAST) {
      log("info", "init toast deferred (diagnostic flag)");
      pendingToast = toast;
      state = STATE.TOAST_PENDING;
      return;
    }
    const shown = await tryShowToast(client, toast);
    if (shown) {
      log("info", "init toast shown");
      state = STATE.DONE;
    } else {
      log("warn", "init toast could not be shown; deferred to fallback");
      pendingToast = toast;
      state = STATE.TOAST_PENDING;
    }
  };

  initPromise = runInitCheck().catch(() => {
    if (state === STATE.RUNNING) {
      log("error", "init check threw unexpectedly");
      state = STATE.NO_RESULT;
    }
  });

  // ---- session.created fallback ----------------------------------------
  const handleSessionCreated = async (info) => {
    if (!info || !info.id) return;

    // Subagent / child sessions never trigger the fallback. The Session type
    // exposes parentID (optional); a truthy parentID means a subagent.
    if (info.parentID) {
      log("debug", "subagent session ignored", {
        sessionId: info.id,
        parentID: info.parentID,
      });
      return;
    }

    // If the init check is still in progress, wait for it so we never launch
    // a second concurrent check. After awaiting, re-evaluate the state.
    if (state === STATE.RUNNING && initPromise) {
      log("info", "session.created arrived during init check; waiting");
      try { await initPromise; } catch (_e) {}
    }

    switch (state) {
      case STATE.DONE:
      case STATE.FALLBACK_CONSUMED:
        log("info", "fallback skipped (init check already completed)");
        return;
      case STATE.FALLBACK_RUNNING:
        log("info", "fallback skipped (already in progress)");
        return;
      case STATE.TOAST_PENDING: {
        // Result obtained earlier; retry the SAME toast (no git ls-remote).
        state = STATE.FALLBACK_RUNNING;
        log("info", "fallback activated: retrying deferred toast");
        const shown = await tryShowToast(client, pendingToast);
        if (shown) log("info", "fallback toast shown");
        else log("warn", "fallback toast could not be shown");
        state = STATE.FALLBACK_CONSUMED;
        return;
      }
      case STATE.NO_RESULT:
      case STATE.IDLE: {
        // Single new attempt of the tool.
        state = STATE.FALLBACK_RUNNING;
        log("info", "fallback activated: single retry of the tool", { from: state });
        const parsed = await runToolOnce($, worktree, info.directory || worktree);
        if (!parsed) {
          log("warn", "fallback retry produced no interpretable result");
          state = STATE.FALLBACK_CONSUMED;
          return;
        }
        log("info", "tool result (fallback)", { code: parsed.code, status: parsed.status });
        const toast = buildToast(parsed);
        if (toast) {
          const shown = await tryShowToast(client, toast);
          if (shown) log("info", "fallback toast shown");
          else log("warn", "fallback toast could not be shown");
        }
        state = STATE.FALLBACK_CONSUMED;
        return;
      }
      default:
        state = STATE.FALLBACK_CONSUMED;
        return;
    }
  };

  return {
    event: async ({ event }) => {
      if (!event || event.type !== "session.created") return;
      const info = event.properties && event.properties.info;
      if (!info || !info.id) return;
      // Fire-and-forget: do not await. The handler resolves immediately so
      // the session is not delayed, regardless of whether OpenCode awaits
      // the returned promise.
      void handleSessionCreated(info).catch(() => {});
    },
  };
};
