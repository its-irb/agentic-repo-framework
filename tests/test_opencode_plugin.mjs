// Tests for the OpenCode plugin .opencode/plugins/agentic-update-check.js.
//
// The plugin body launches the update check ONCE at load time (init check),
// fire-and-forget. session.created is kept as a TEMPORARY single-shot fallback.
// These tests cover:
//   - interpretation of all 8 result codes (toast shown only when appropriate),
//   - the init check fires once on load (before any session.created),
//   - a successful init toast means session.created does nothing,
//   - if the init toast fails, session.created retries the SAME toast (no new
//     tool call),
//   - if the init check produces no result, session.created retries the tool
//     exactly once,
//   - a second /new does not trigger another check,
//   - sessions with parentID (subagents) do not trigger the fallback,
//   - no double execution if session.created arrives while init is running,
//   - UP_TO_DATE and SOURCE_REPO_SKIPPED complete silently and disable fallback,
//   - non-blocking init (Hooks resolve before the check completes),
//   - wiring: tool invoked with python3 <tool> --root <dir>.
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
// A unique nonce comment is prepended to bust Node's module cache, so each
// load re-evaluates the module and env-var flags (e.g.
// AGENTIC_UPDATE_CHECK_DEFER_INIT_TOAST) are read fresh per load.
async function loadPlugin() {
  const src = readFileSync(PLUGIN_PATH, "utf8");
  const nonce = `// nonce-${Date.now()}-${Math.random()}\n`;
  const url = "data:text/javascript," + encodeURIComponent(nonce + src);
  const mod = await import(url);
  return mod.AgenticUpdateCheck;
}

const SHA_A = "a".repeat(40);
const SHA_B = "b".repeat(40);

// Fake client. showToastSucceeds controls whether the TUI is "ready".
// calls records every toast body passed to showToast. logs records app.log
// bodies.
function makeClient({ showToastSucceeds = true } = {}) {
  const calls = [];
  const logs = [];
  return {
    calls,
    logs,
    tui: {
      async showToast({ body }) {
        calls.push(body);
        if (showToastSucceeds) {
          return { data: true, error: undefined };
        }
        return { data: undefined, error: { message: "TUI not ready" } };
      },
    },
    app: {
      async log({ body }) { logs.push(body); return { data: true }; },
    },
  };
}

// Fake BunShell tag: returns a thenable with .quiet()/.nothrow(). `provider`
// is either a static result object or a function(cmd) -> result, or a Promise
// (for deferred/non-blocking tests). Also counts invocations.
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

function makeSessionCreated(id, directory, extra = {}) {
  return {
    type: "session.created",
    properties: { info: { id, directory, title: "t", version: "1", ...extra } },
  };
}

// Flush the microtask queue + a couple of macrotasks so detached async work
// (init check, fallback) settles.
async function flush(n = 5) {
  for (let i = 0; i < n; i++) {
    await new Promise((r) => setTimeout(r, 0));
  }
}

// ---------------------------------------------------------------------------
// Interpretation of the 8 result codes (aviso solo cuando corresponde)
// The init check fires on load; no session.created is needed.
// ---------------------------------------------------------------------------

test("code 0 UP_TO_DATE -> no toast, silent completion", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 0);
  assert.equal($.invocations, 1, "init check ran once");
});

test("code 2 SOURCE_REPO_SKIPPED -> no toast, silent completion", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(2), stderr: "", exitCode: 2 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 0);
  assert.equal($.invocations, 1, "init check ran once");
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
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 1, "toast shown during init");
  const t = client.calls[0];
  assert.equal(t.variant, "warning");
  assert.equal(t.title, "Actualizacion del framework disponible");
  assert.ok(t.message.includes(SHA_A.slice(0, 12)), "includes short installed commit");
  assert.ok(t.message.includes(SHA_B.slice(0, 12)), "includes short remote commit");
  assert.ok(!t.message.includes(SHA_A), "does NOT include the full installed SHA");
  assert.ok(t.message.includes("main"), "includes branch");
  assert.ok(t.message.includes("git pull --ff-only"), "includes git pull --ff-only step");
  assert.ok(
    t.message.includes("python3 bin/agentic-sync.py --apply"),
    "includes the full apply command",
  );
  assert.ok(t.message.includes("desde ese clon"), "makes clear the sync runs from the framework clone");
  assert.ok(t.message.includes("indicando la ruta de este repositorio"), "tells the user to indicate the target repo path");
  assert.ok(!t.message.includes("agentic-sync.py --apply sobre este repositorio"), "does not use the old ambiguous phrasing");
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
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const t = client.calls[0];
  assert.ok(t.message.includes("/home/david/agentic-repo-framework"), "includes the concrete framework_source path");
  assert.ok(t.message.includes("git pull --ff-only"), "still includes the pull step");
  assert.ok(t.message.includes("python3 bin/agentic-sync.py --apply"), "includes the full apply command");
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
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const t = client.calls[0];
  assert.ok(
    t.message.includes("clon local del Agentic Framework") &&
    t.message.includes("git pull --ff-only"),
    "generic hint without a concrete path",
  );
  assert.ok(t.message.includes("python3 bin/agentic-sync.py --apply"), "includes the full apply command");
});

test("code 3 LOCK_MISSING -> warning toast with two-step flow", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(3), stderr: "", exitCode: 3 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const t = client.calls[0];
  assert.equal(t.variant, "warning");
  assert.ok(t.message.includes(".agentic.lock.json"), "mentions the missing lock");
  assert.ok(t.message.includes("git pull --ff-only"), "includes pull step");
  assert.ok(t.message.includes("python3 bin/agentic-sync.py --apply"), "includes the full apply command");
  assert.ok(t.message.includes("desde ese clon"), "makes clear the sync runs from the framework clone");
});

test("code 4 LOCK_INCOMPLETE -> warning toast with two-step flow", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(4), stderr: "", exitCode: 4 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const t = client.calls[0];
  assert.equal(t.variant, "warning");
  assert.ok(t.message.includes("trazabilidad"), "mentions missing traceability");
  assert.ok(t.message.includes("git pull --ff-only"), "includes pull step");
  assert.ok(t.message.includes("python3 bin/agentic-sync.py --apply"), "includes the full apply command");
  assert.ok(t.message.includes("desde ese clon"), "makes clear the sync runs from the framework clone");
});

test("code 4 LOCK_INCOMPLETE -> uses framework_source when present", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(4, { framework_source: "/fw/clone" }),
    stderr: "", exitCode: 4,
  });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const t = client.calls[0];
  assert.ok(t.message.includes("/fw/clone"), "includes the concrete source path");
});

test("code 4 LOCK_INCOMPLETE -> generic hint when framework_source absent (whitespace-only source)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(4), stderr: "", exitCode: 4 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const t = client.calls[0];
  assert.ok(t.message.includes("clon local del Agentic Framework"), "generic hint when no concrete source path is available");
  assert.ok(!t.message.includes("en  con"), "must not embed an empty/whitespace path");
});

for (const code of [5, 6, 7]) {
  test(`code ${code} -> brief info toast, not a sync warning`, async () => {
    const AgenticUpdateCheck = await loadPlugin();
    const client = makeClient();
    const $ = makeShell({ stdout: payload(code), stderr: "", exitCode: code });
    await AgenticUpdateCheck({ client, $, worktree: "/repo" });
    await flush();
    assert.equal(client.calls.length, 1);
    assert.equal(client.calls[0].variant, "info");
    assert.ok(client.calls[0].message.includes("No se pudo comprobar"));
  });
}

// ---------------------------------------------------------------------------
// 1. Init check fires once on load, before any session.created
// ---------------------------------------------------------------------------

test("init check fires exactly once on plugin load (no session.created)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal($.invocations, 1, "exactly one tool call on load");
  // No session.created was sent.
  assert.equal(client.calls.length, 0, "no toast for UP_TO_DATE");
});

// ---------------------------------------------------------------------------
// 2. UPDATE_AVAILABLE tries to show the toast before any session.created
// ---------------------------------------------------------------------------

test("UPDATE_AVAILABLE toast shown during init, before any session.created", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  // Toast shown without any session.created.
  assert.equal(client.calls.length, 1, "toast shown during init");
  assert.equal($.invocations, 1, "tool called once");
});

// ---------------------------------------------------------------------------
// 3. If init toast succeeds, later session.created does nothing
// ---------------------------------------------------------------------------

test("successful init toast -> session.created does nothing", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 1, "init toast shown");
  assert.equal($.invocations, 1);

  // Send several session.created events.
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();

  assert.equal($.invocations, 1, "no new tool call");
  assert.equal(client.calls.length, 1, "no new toast");
});

// ---------------------------------------------------------------------------
// 4. If init toast fails, first session.created retries SAME toast (no tool)
// ---------------------------------------------------------------------------

test("init toast fails -> session.created retries same toast without re-running tool", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  // TUI not ready during init.
  const client = makeClient({ showToastSucceeds: false });
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  // Init attempted to show toast but failed.
  assert.equal(client.calls.length, 1, "init toast attempt recorded");
  assert.equal($.invocations, 1, "tool called once during init");

  // Now make the TUI ready and send session.created.
  client.tui.showToast = async ({ body }) => {
    client.calls.push(body);
    return { data: true, error: undefined };
  };
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();

  assert.equal($.invocations, 1, "tool NOT called again (same toast reused)");
  assert.equal(client.calls.length, 2, "fallback retried the same toast");
  // Same toast content.
  assert.deepEqual(client.calls[1], client.calls[0]);
});

// ---------------------------------------------------------------------------
// 5. If init check fails before result, first session.created retries tool once
// ---------------------------------------------------------------------------

test("init produces no result -> session.created retries tool exactly once", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  // First call (init): non-JSON. Second call (fallback): valid JSON.
  let callCount = 0;
  const $ = makeShell(() => {
    callCount++;
    if (callCount === 1) return { stdout: "not json\n", stderr: "", exitCode: 2 };
    return {
      stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                            branch: "main", url: "https://github.com/org/fw.git" }),
      stderr: "", exitCode: 1,
    };
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal($.invocations, 1, "init ran");
  assert.equal(client.calls.length, 0, "no toast during init (no result)");

  // session.created triggers a single retry.
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "fallback ran the tool once");
  assert.equal(client.calls.length, 1, "fallback showed the toast");

  // A second session.created must not trigger another check.
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "no third tool call");
  assert.equal(client.calls.length, 1, "no extra toast");
});

// ---------------------------------------------------------------------------
// 6. A second /new does not trigger another check
// ---------------------------------------------------------------------------

test("second /new does not trigger another check (init succeeded)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "only the init check");
  assert.equal(client.calls.length, 1, "only the init toast");
});

test("second /new does not trigger another check (after fallback consumed)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  let callCount = 0;
  const $ = makeShell(() => {
    callCount++;
    if (callCount === 1) return { stdout: "not json\n", stderr: "", exitCode: 2 };
    return { stdout: payload(0), stderr: "", exitCode: 0 };
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  // Init failed (no result). Fallback retries.
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "init + fallback retry");
  // Second /new: no more checks.
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "no third check after fallback consumed");
});

// ---------------------------------------------------------------------------
// 7. Sessions with parentID (subagents) do not trigger the fallback
// ---------------------------------------------------------------------------

test("subagent session (parentID) does not trigger fallback", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  // Init toast fails -> TOAST_PENDING. A subagent session.created must NOT
  // consume the fallback. A later top-level session.created must succeed.
  const client = makeClient({ showToastSucceeds: false });
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 1, "init toast attempt");

  // Subagent session: has parentID.
  await hooks.event({ event: makeSessionCreated("sub-1", "/repo", { parentID: "parent-session" }) });
  await flush();
  assert.equal($.invocations, 1, "no tool call for subagent");
  assert.equal(client.calls.length, 1, "no toast retry for subagent");

  // Now a top-level session (no parentID) triggers the fallback.
  client.tui.showToast = async ({ body }) => {
    client.calls.push(body);
    return { data: true, error: undefined };
  };
  await hooks.event({ event: makeSessionCreated("top-1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 2, "fallback retried toast for top-level session");
  assert.equal($.invocations, 1, "still no new tool call (reused result)");
});

// ---------------------------------------------------------------------------
// 8. No double execution if session.created arrives while init is running
// ---------------------------------------------------------------------------

test("session.created during init check -> waits, no second tool call", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  // Deferred shell: init check will not complete until we resolve it.
  const deferred = Promise.withResolvers();
  const $ = makeShell(deferred.promise);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  // Init check is pending on the deferred shell. $.invocations is already 1
  // (the tag was called synchronously).
  assert.equal($.invocations, 1, "init check started");

  // Send session.created while init is still running.
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  // The fallback handler is now awaiting initPromise.

  // Complete the init check.
  deferred.resolve({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  await flush();

  assert.equal($.invocations, 1, "no second tool call — init check was reused");
  assert.equal(client.calls.length, 1, "init toast shown once");
});

// ---------------------------------------------------------------------------
// 9. UP_TO_DATE and SOURCE_REPO_SKIPPED complete silently, disable fallback
// ---------------------------------------------------------------------------

test("UP_TO_DATE completes silently and disables fallback", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 0, "no toast");
  assert.equal($.invocations, 1, "init check ran");

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "fallback did not re-run the tool");
  assert.equal(client.calls.length, 0, "fallback did not show a toast");
});

test("SOURCE_REPO_SKIPPED completes silently and disables fallback", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(2), stderr: "", exitCode: 2 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal(client.calls.length, 0, "no toast");
  assert.equal($.invocations, 1, "init check ran");

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "fallback did not re-run the tool");
  assert.equal(client.calls.length, 0, "fallback did not show a toast");
});

// ---------------------------------------------------------------------------
// Non-blocking: Hooks resolve before the check completes
// ---------------------------------------------------------------------------

test("plugin body resolves before the init check completes (non-blocking)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const deferred = Promise.withResolvers();
  const $ = makeShell(deferred.promise);
  // The plugin body must resolve even though $ is pending.
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });

  // Hooks returned; init check still pending.
  assert.ok(hooks && typeof hooks.event === "function", "Hooks returned");
  assert.equal(client.calls.length, 0, "no toast yet — check still pending");

  // Complete the check.
  deferred.resolve({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "https://github.com/org/fw.git" }),
    stderr: "", exitCode: 1,
  });
  await flush();
  assert.equal(client.calls.length, 1, "toast shown after check completes");
});

// ---------------------------------------------------------------------------
// Non-session.created events do not trigger additional checks
// ---------------------------------------------------------------------------

test("non-session.created events do not trigger additional checks", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  assert.equal($.invocations, 1, "init check ran");
  for (const type of ["session.updated", "session.idle", "message.updated", "file.edited"]) {
    await hooks.event({ event: { type, properties: { info: { id: "s1", directory: "/repo" } } } });
  }
  await flush();
  assert.equal($.invocations, 1, "no extra tool call for non-session.created events");
  assert.equal(client.calls.length, 0, "no toast");
});

test("session.created without info.id is ignored", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(1), stderr: "", exitCode: 1 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const before = client.calls.length;
  await hooks.event({ event: { type: "session.created", properties: { info: {} } } });
  await flush();
  assert.equal(client.calls.length, before, "no toast for session without info.id");
});

// ---------------------------------------------------------------------------
// Wiring: the init check invokes the tool with python3 <tool> --root <worktree>
// ---------------------------------------------------------------------------

test("init check runs python3 <tool> --root <worktree>", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  await AgenticUpdateCheck({ client, $, worktree: "/my-repo" });
  await flush();
  assert.equal($.invocations, 1);
  assert.ok($.lastCmd.includes("python3"), "invokes python3");
  assert.ok($.lastCmd.includes("check-framework-updates.py"), "invokes the tool");
  assert.ok($.lastCmd.includes("--root"), "passes --root");
  assert.ok($.lastCmd.includes("/my-repo"), "uses the worktree as root");
});

// ---------------------------------------------------------------------------
// Wiring: the fallback (when triggered) uses the session directory
// ---------------------------------------------------------------------------

test("fallback retry uses the session directory as --root", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  // Init: non-JSON -> NO_RESULT. Fallback: valid JSON.
  let callCount = 0;
  const $ = makeShell(() => {
    callCount++;
    if (callCount === 1) return { stdout: "garbage\n", stderr: "", exitCode: 2 };
    return { stdout: payload(0), stderr: "", exitCode: 0 };
  });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  // The init check used worktree as root.
  assert.ok($.lastCmd.includes("--root") && $.lastCmd.includes("/repo"), "init used worktree");

  // Trigger the fallback with a session directory.
  await hooks.event({ event: makeSessionCreated("s1", "/sessions/sub") });
  await flush();
  assert.equal($.invocations, 2, "fallback ran the tool");
  assert.ok($.lastCmd.includes("/sessions/sub"), "fallback used the session directory");
});

// ---------------------------------------------------------------------------
// Diagnostic flag: AGENTIC_UPDATE_CHECK_DEFER_INIT_TOAST forces TOAST_PENDING
// ---------------------------------------------------------------------------

test("diagnostic flag defers init toast and fallback shows it", async () => {
  process.env.AGENTIC_UPDATE_CHECK_DEFER_INIT_TOAST = "1";
  try {
    const AgenticUpdateCheck = await loadPlugin();
    // TUI reports success, but the flag forces deferral.
    const client = makeClient({ showToastSucceeds: true });
    const $ = makeShell({
      stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                           branch: "main", url: "https://github.com/org/fw.git" }),
      stderr: "", exitCode: 1,
    });
    const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
    await flush();
    // No toast during init (forced deferral).
    assert.equal(client.calls.length, 0, "init toast deferred by flag");

    // session.created triggers the fallback and shows the toast.
    await hooks.event({ event: makeSessionCreated("s1", "/repo") });
    await flush();
    assert.equal(client.calls.length, 1, "fallback showed the deferred toast");
    assert.equal($.invocations, 1, "tool NOT called again");
  } finally {
    delete process.env.AGENTIC_UPDATE_CHECK_DEFER_INIT_TOAST;
  }
});

// ---------------------------------------------------------------------------
// Logging: structured logs are emitted via app.log
// ---------------------------------------------------------------------------

test("structured logs are emitted for init and fallback", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await flush();
  const messages = client.logs.map((l) => l.message);
  assert.ok(messages.includes("plugin initialized"), "logs plugin initialized");
  assert.ok(messages.includes("init check launched"), "logs init check launched");
  assert.ok(messages.some((m) => m === "tool result"), "logs tool result");
  // All logs use the stable service id.
  for (const l of client.logs) {
    assert.equal(l.service, "agentic-update-check");
  }
});
