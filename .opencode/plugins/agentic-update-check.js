import path from "node:path";

// OpenCode plugin (local project plugin, auto-discovered in .opencode/plugins/).
//
// It only contains harness glue: it invokes the deterministic, harness-agnostic
// tool at .agentic/tools/check-framework-updates.py, interprets its JSON result
// and shows a toast when appropriate. All lock/git/commit logic lives in the
// tool — none is duplicated here.
//
// Design notes:
//  * The ONLY trigger is the `session.created` event. This covers both opening
//    OpenCode (which creates the initial session) and `/new` (which creates a
//    new session). The plugin body itself performs no check on init, so a single
//    opening cannot produce two notifications (init + session.created).
//  * The event handler is fire-and-forget: it does NOT await the check. It
//    resolves immediately, so even if OpenCode awaits the returned promise the
//    session is not delayed by the (bounded) remote check. The tool itself
//    bounds `git ls-remote` at 10s.
//  * A per-instance dedup guard skips a second `session.created` for the same
//    session id. Different sessions always proceed — this is dedup of a single
//    logical event, not a cache that suppresses per-session checks.
//  * Any failure (tool missing, non-JSON output, network error surfaced by the
//    tool) yields at most a brief informational toast; the session always
//    continues.

const TOOL_REL = path.join(".agentic", "tools", "check-framework-updates.py");

function shortSha(sha) {
  // Show short SHAs in toasts for legibility; the tool still compares full SHAs.
  return typeof sha === "string" && sha.length >= 12 ? sha.slice(0, 12) : String(sha);
}

// Build the manual update instructions. When the tool surfaces framework_source
// (the local path used by the last apply), make the pull step concrete;
// otherwise keep it generic. source is only an informational hint, never a
// trusted origin.
//
// The sync command must be run FROM the framework clone (it resolves the
// framework root as the script's grandparent), not from the target repo. The
// plugin does not have a reliable absolute path for the target, so it instructs
// the user to indicate it rather than fabricating one.
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
  // No trailing period: callers compose further text (a trailing sentence for
  // LOCK_INCOMPLETE, or the closing period for the other states).
  return "Despues, desde ese clon, ejecuta " + APPLY_CMD +
    " indicando la ruta de este repositorio";
}

function buildToast(r) {
  // Returns the toast payload to show, or null when the state must be silent.
  switch (r.code) {
    case 0: // UP_TO_DATE
      return null;
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

async function showToast(client, toast) {
  if (!toast) return;
  try {
    await client.tui.showToast({ body: toast });
  } catch (_e) {
    // Toast display is best-effort; never let it break the session.
  }
}

async function runCheck(client, $, worktree, sessionDirectory) {
  const toolPath = path.join(worktree || "", TOOL_REL);
  const rootDir = sessionDirectory || worktree || "";
  let res;
  try {
    res = await $`python3 ${toolPath} --root ${rootDir}`.quiet().nothrow();
  } catch (_e) {
    await showToast(client, {
      title: "No se pudo comprobar el framework",
      message: "No se pudo comprobar el estado de actualizacion del framework.",
      variant: "info",
      duration: 6000,
    });
    return;
  }

  let parsed = null;
  try {
    parsed = JSON.parse(String(res.stdout).trim());
  } catch (_e) {
    await showToast(client, {
      title: "No se pudo comprobar el framework",
      message: "No se pudo comprobar el estado de actualizacion del framework.",
      variant: "info",
      duration: 6000,
    });
    return;
  }

  await showToast(client, buildToast(parsed));
}

export const AgenticUpdateCheck = async ({ client, $, worktree }) => {
  // Per-instance dedup state: a single logical session.created must not trigger
  // two checks. A different session id always proceeds.
  let lastCheckedSessionId = null;

  return {
    event: async ({ event }) => {
      if (!event || event.type !== "session.created") return;
      const info = event.properties && event.properties.info;
      if (!info || !info.id) return;

      if (lastCheckedSessionId === info.id) return;
      lastCheckedSessionId = info.id;

      // Fire-and-forget: do not await. The handler resolves immediately so the
      // session is not delayed by the remote check, regardless of whether
      // OpenCode awaits the returned promise.
      void runCheck(client, $, worktree, info.directory).catch(() => {});
    },
  };
};
