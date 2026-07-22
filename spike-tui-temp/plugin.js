const SERVICE = "agentic-update-check-tui-spike";
const TOOL_REL = ".agentic/tools/check-framework-updates.py";

function shortSha(sha) {
  return typeof sha === "string" && sha.length >= 12 ? sha.slice(0, 12) : String(sha);
}

function buildToast(r) {
  const prefix = "[TUI SPIKE] ";
  switch (r.code) {
    case 0: case 2: return null;
    case 1: return { title: prefix + "Actualizacion disponible", message: "Instalado: " + shortSha(r.installed_commit) + "\nDisponible: " + shortSha(r.remote_commit) + "\nRama: " + r.branch, variant: "warning", duration: 12000 };
    case 3: return { title: prefix + "Framework incompleto", message: "Falta .agentic.lock.json", variant: "warning", duration: 10000 };
    case 4: return { title: prefix + "Framework incompleto", message: "El lock no contiene trazabilidad", variant: "warning", duration: 10000 };
    default: return { title: prefix + "No se pudo comprobar", message: "No se pudo comprobar el estado de actualizacion", variant: "info", duration: 6000 };
  }
}

async function waitForPath(api) {
  const start = Date.now();
  while (Date.now() - start < 10000) {
    const dir = api.state?.path?.worktree || api.state?.path?.directory;
    if (dir) return dir;
    await new Promise((r) => setTimeout(r, 100));
  }
  return null;
}

async function runTool(worktree) {
  const toolPath = worktree + "/" + TOOL_REL;
  const proc = Bun.spawn(["python3", toolPath, "--root", worktree], { stdout: "pipe", stderr: "pipe" });
  const stdout = await new Response(proc.stdout).text();
  const exitCode = await proc.exited;
  return { stdout, exitCode };
}

export default {
  id: SERVICE,
  tui: async (api) => {
    const log = (level, message, extra) => {
      try { const p = api.client?.app?.log?.({ body: { service: SERVICE, level, message: String(message), extra: extra || {} } }); if (p && typeof p.catch === "function") p.catch(() => {}); } catch (_e) {}
      console.error("[" + SERVICE + "] " + message);
    };
    log("info", "tui spike plugin initialized");
    const worktree = await waitForPath(api);
    if (!worktree) { log("warn", "could not resolve worktree path"); return; }
    log("info", "worktree resolved", { worktree });
    try {
      const { stdout, exitCode } = await runTool(worktree);
      log("info", "tool executed", { exitCode });
      const parsed = JSON.parse(stdout.trim());
      log("info", "tool result", { code: parsed.code, status: parsed.status });
      const toast = buildToast(parsed);
      if (toast) { api.ui.toast(toast); log("info", "toast shown", { variant: toast.variant }); }
      else { log("info", "no toast needed", { code: parsed.code }); }
    } catch (e) {
      log("error", "check failed", { error: String(e) });
      api.ui.toast({ title: "[TUI SPIKE] Error", message: "Fallo: " + String(e), variant: "error", duration: 6000 });
    }
  },
};
