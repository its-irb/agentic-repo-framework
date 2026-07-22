// Tests for the OpenCode plugin .opencode/plugins/agentic-update-check.js.
//
// The plugin only exports `AgenticUpdateCheck`; all logic is internal. These
// tests drive the plugin through its public Hooks.event interface with a fake
// `client` (recording toasts) and a fake `$` (BunShell tag). They cover:
//   - interpretation of all 8 result codes (toast shown only when appropriate),
//   - session.created as the sole trigger,
//   - no duplicate checks for the same session id,
//   - one check per distinct session (covers open + /new),
//   - the event handler is fire-and-forget (does not block on the check).
//
// No network, no bun, no external deps: plain `node --test`.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const PLUGIN_PATH = fileURLToPath(
  new URL("../.opencode/plugins/agentic-update-check.js", import.meta.url),
);

// Import the ESM `.js` plugin via a data: URL so plain node parses it as ESM
// (the project has no "type": "module"); bun (used by opencode) handles it too.
async function loadPlugin() {
  const src = readFileSync(PLUGIN_PATH, "utf8");
  const url = "data:text/javascript," + encodeURIComponent(src);
  const mod = await import(url);
  return mod.AgenticUpdateCheck;
}

const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);

function makeClient() {
  const calls = [];
  return {
    calls,
    tui: {
      async showToast({ body }) { calls.push(body); },
    },
    app: { async log() {} },
  };
}

// Fake BunShell tag: returns a thenable with .quiet()/.nothrow(). `provider`
// is either a static result object or a function(cmd) -> result, or a Promise
// (for the deferred non-blocking test). Also counts invocations.
function makeShell(provider) {
  function shell(strings, ...values) {
    shell.invocations += 1;
    const cmd = strings.reduce(
      (acc, s, i) => acc + s + (i < values.length ? String(values[i]) : ""),
      "",
    );
    shell.lastCmd = cmd;
    const base = typeof provider === "function" ? provider(cmd) : provider;
    const thenable = {
      quiet() { return thenable; },
      nothrow() { return thenable; },
      then(onF, onR) { return Promise.resolve(base).then(onF, onR); },
      catch(onR) { return Promise.resolve(base).catch(onR); },
    };
    return thenable;
  }
  shell.invocations = 0;
  shell.lastCmd = null;
  return shell;
}

function payload(code, extra = {}) {
  return JSON.stringify({ status: "S", code, message: "m", ...extra });
}

function makeSessionCreated(id, directory) {
  return {
    type: "session.created",
    properties: { info: { id, directory, title: "t", version: "1" } },
  };
}

async function flush(n = 2) {
  for (let i = 0; i < n; i++) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

// ---------------------------------------------------------------------------
// Interpretation of the 8 result codes (aviso solo cuando corresponde)
// ---------------------------------------------------------------------------

test("code 0 UP_TO_DATE -> no toast", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 0);
});

test("code 2 SOURCE_REPO_SKIPPED -> no toast", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(2), stderr: "", exitCode: 2 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 0);
});

test("code 1 UPDATE_AVAILABLE -> warning toast with short SHAs and two-step flow", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, {
      installed_commit: SHA_A, remote_commit: SHA_B,
      branch: "main", url: "https://github.com/org/fw.git",
    }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);
  const t = client.calls[0];
  assert.equal(t.variant, "warning");
  assert.equal(t.title, "Actualizacion del framework disponible");
  // Short SHAs (12 chars), not the full 40.
  assert.ok(t.message.includes(SHA_A.slice(0, 12)), "includes short installed commit");
  assert.ok(t.message.includes(SHA_B.slice(0, 12)), "includes short remote commit");
  assert.ok(!t.message.includes(SHA_A), "does NOT include the full installed SHA");
  assert.ok(t.message.includes("main"), "includes branch");
  // Two-step manual flow: pull the local clone first, THEN apply from there.
  assert.ok(t.message.includes("git pull --ff-only"), "includes git pull --ff-only step");
  // The apply command must be the full form run from the framework clone.
  assert.ok(
    t.message.includes("python3 bin/agentic-sync.py --apply"),
    "includes the full apply command",
  );
  assert.ok(
    t.message.includes("desde ese clon"),
    "makes clear the sync runs from the framework clone",
  );
  assert.ok(
    t.message.includes("indicando la ruta de este repositorio"),
    "tells the user to indicate the target repo path",
  );
  // The old, ambiguous bare form must NOT appear on its own.
  assert.ok(
    !t.message.includes("agentic-sync.py --apply sobre este repositorio"),
    "does not use the old ambiguous phrasing",
  );
  // Pull step comes before apply step.
  const applyIdx = t.message.indexOf("python3 bin/agentic-sync.py --apply");
  const pullIdx = t.message.indexOf("git pull --ff-only");
  assert.ok(pullIdx > -1 && applyIdx > -1, "both steps present");
  assert.ok(pullIdx < applyIdx, "pull step comes before apply step");
});

test("code 1 UPDATE_AVAILABLE -> uses framework_source when present", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, {
      installed_commit: SHA_A, remote_commit: SHA_B,
      branch: "main", url: "https://github.com/org/fw.git",
      framework_source: "/home/david/agentic-repo-framework",
    }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);
  const t = client.calls[0];
  assert.ok(
    t.message.includes("/home/david/agentic-repo-framework"),
    "includes the concrete framework_source path",
  );
  assert.ok(t.message.includes("git pull --ff-only"), "still includes the pull step");
  assert.ok(
    t.message.includes("python3 bin/agentic-sync.py --apply"),
    "includes the full apply command",
  );
});

test("code 1 UPDATE_AVAILABLE -> generic pull hint when framework_source absent", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, {
      installed_commit: SHA_A, remote_commit: SHA_B,
      branch: "main", url: "https://github.com/org/fw.git",
    }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  const t = client.calls[0];
  assert.ok(
    t.message.includes("clon local del Agentic Framework") &&
    t.message.includes("git pull --ff-only"),
    "generic hint without a concrete path",
  );
  assert.ok(
    t.message.includes("python3 bin/agentic-sync.py --apply"),
    "includes the full apply command",
  );
});

test("code 3 LOCK_MISSING -> warning toast with two-step flow", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(3), stderr: "", exitCode: 3 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);
  const t = client.calls[0];
  assert.equal(t.variant, "warning");
  assert.ok(t.message.includes(".agentic.lock.json"), "mentions the missing lock");
  assert.ok(t.message.includes("git pull --ff-only"), "includes pull step");
  assert.ok(
    t.message.includes("python3 bin/agentic-sync.py --apply"),
    "includes the full apply command",
  );
  assert.ok(
    t.message.includes("desde ese clon"),
    "makes clear the sync runs from the framework clone",
  );
});

test("code 4 LOCK_INCOMPLETE -> warning toast with two-step flow", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(4), stderr: "", exitCode: 4 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);
  const t = client.calls[0];
  assert.equal(t.variant, "warning");
  assert.ok(t.message.includes("trazabilidad"), "mentions missing traceability");
  assert.ok(t.message.includes("git pull --ff-only"), "includes pull step");
  assert.ok(
    t.message.includes("python3 bin/agentic-sync.py --apply"),
    "includes the full apply command",
  );
  assert.ok(
    t.message.includes("desde ese clon"),
    "makes clear the sync runs from the framework clone",
  );
});

test("code 4 LOCK_INCOMPLETE -> uses framework_source when present", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(4, { framework_source: "/fw/clone" }),
    stderr: "", exitCode: 4,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  const t = client.calls[0];
  assert.ok(t.message.includes("/fw/clone"), "includes the concrete source path");
});

test("code 4 LOCK_INCOMPLETE -> generic hint when framework_source absent (whitespace-only source)", async () => {
  // When the lock's source is whitespace-only, the tool does NOT surface
  // framework_source, so the plugin must fall back to the generic hint and
  // never show a blank/whitespace path.
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    // No framework_source key at all (the tool omits it for whitespace sources).
    stdout: payload(4),
    stderr: "", exitCode: 4,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  const t = client.calls[0];
  assert.ok(
    t.message.includes("clon local del Agentic Framework"),
    "generic hint when no concrete source path is available",
  );
  assert.ok(
    !t.message.includes("en  con"),
    "must not embed an empty/whitespace path",
  );
});

for (const code of [5, 6, 7]) {
  test(`code ${code} -> brief info toast, not a sync warning`, async () => {
    const AgenticUpdateCheck = await loadPlugin();
    const client = makeClient();
    const $ = makeShell({ stdout: payload(code), stderr: "", exitCode: code });
    const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
    await hooks.event({ event: makeSessionCreated("s1", "/repo") });
    await flush();
    assert.equal(client.calls.length, 1);
    assert.equal(client.calls[0].variant, "info");
    assert.ok(client.calls[0].message.includes("No se pudo comprobar"));
  });
}

// ---------------------------------------------------------------------------
// session.created is the sole trigger
// ---------------------------------------------------------------------------

test("non-session.created events do not trigger a check", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(1), stderr: "", exitCode: 1 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  for (const type of ["session.updated", "session.idle", "message.updated", "file.edited"]) {
    await hooks.event({ event: { type, properties: { info: { id: "s1", directory: "/repo" } } } });
  }
  await flush();
  assert.equal($.invocations, 0, "no shell call for non session.created events");
  assert.equal(client.calls.length, 0, "no toast for non session.created events");
});

test("session.created without info.id is ignored", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(1), stderr: "", exitCode: 1 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: { type: "session.created", properties: { info: {} } } });
  await flush();
  assert.equal($.invocations, 0);
});

// ---------------------------------------------------------------------------
// No duplicate checks for the same session; one per distinct session
// ---------------------------------------------------------------------------

test("two session.created for the same id -> one check", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("same", "/repo") });
  await hooks.event({ event: makeSessionCreated("same", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "dedup: same session id checked once");
});

test("distinct sessions (open then /new) -> one check each", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  // Opening OpenCode creates the initial session.
  await hooks.event({ event: makeSessionCreated("open-1", "/repo") });
  await flush();
  // /new creates a new session.
  await hooks.event({ event: makeSessionCreated("new-1", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "one check per distinct session");
});

// ---------------------------------------------------------------------------
// Fire-and-forget: the handler does not block on the (bounded) check
// ---------------------------------------------------------------------------

test("event handler resolves before the check completes (non-blocking)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  // Deferred result: the shell will not resolve until we resolve it.
  const deferred = Promise.withResolvers();
  const $ = makeShell(deferred.promise);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });

  // The handler must return (resolve) immediately even though `$` is pending.
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });

  // No toast yet: the detached check is still waiting on the deferred shell.
  assert.equal(client.calls.length, 0, "handler did not block, toast pending");

  // Complete the check; the toast now appears.
  deferred.resolve({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  await flush();

  assert.equal(client.calls.length, 1);
  assert.equal(client.calls[0].variant, "warning");
});

// ---------------------------------------------------------------------------
// Tool invocation failure (non-JSON / crashed) -> brief warning, no throw
// ---------------------------------------------------------------------------

test("non-JSON tool output -> brief info toast and no throw", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: "python: can't open file\n", stderr: "err", exitCode: 2 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);
  assert.equal(client.calls[0].variant, "info");
  assert.ok(client.calls[0].message.includes("No se pudo comprobar"));
});

// ---------------------------------------------------------------------------
// Wiring: the plugin invokes the tool with the session directory
// ---------------------------------------------------------------------------

test("plugin runs python3 <tool> --root <session dir>", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("s1", "/sessions/sub") });
  await flush();
  assert.equal($.invocations, 1);
  assert.ok($.lastCmd.includes("python3"), "invokes python3");
  assert.ok($.lastCmd.includes("check-framework-updates.py"), "invokes the tool");
  assert.ok($.lastCmd.includes("--root"), "passes --root");
  assert.ok($.lastCmd.includes("/sessions/sub"), "passes the session directory");
});
