// Tests for the OpenCode plugin .opencode/plugins/agentic-update-check.js.
//
// The plugin only exports `AgenticUpdateCheck`; all logic is internal. These
// tests drive the plugin through its public Hooks.event interface with a fake
// `client` (recording toasts), a fake `$` (BunShell tag) and an injectable
// clock (`now`) so the 1h and 24h throttles are deterministic and fast (no
// real waits).
//
// Coverage (all offline — no network, no bun, no external deps; plain
// `node --test`):
//   - interpretation of all 8 result codes (toast shown only when appropriate),
//   - session.created as the sole trigger,
//   - child/subagent sessions (parentID) are ignored,
//   - hourly throttle: several sessions in an hour -> one check; after 1h a new
//     check is allowed,
//   - concurrency: two simultaneous events -> one tool; checkInFlight cleared
//     even on exception,
//   - UP_TO_DATE / SOURCE_REPO_SKIPPED silent,
//   - update: new commit notifies; same commit not re-notified within 24h;
//     same commit re-notified after 24h; a different remote commit notifies on
//     the next allowed check even if <24h,
//   - diagnostics: same diagnostic not repeated for 24h (per-key Map so
//     alternating diagnostics keep independent clocks); different diagnostic
//     can notify; the GIT_OR_NETWORK_ERROR -> LOCK_INVALID -> GIT_OR_NETWORK_ERROR
//     sequence does not re-notify the third,
//   - reinitializing the plugin creates fresh in-memory state (no persistence),
//   - no TUI plugin / server.connected / filesystem-write logic in the source.
//
// Distribution of the plugin via agentic-sync.py is covered by the Python
// suite (tests/test_check_framework_updates.py), which asserts the plugin is
// installed and tracked in the lockfile.
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
const SHA_C = "c".repeat(40);

const HOUR = 60 * 60 * 1000;
const DAY = 24 * HOUR;

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

// A client whose showToast rejects — used to verify checkInFlight is cleared
// even when an exception escapes the inner try.
function makeRejectingClient() {
  return {
    calls: [],
    tui: {
      async showToast() { throw new Error("toast boom"); },
    },
    app: { async log() {} },
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
  const status = extra.status || (
    code === 0 ? "UP_TO_DATE" :
    code === 1 ? "UPDATE_AVAILABLE" :
    code === 2 ? "SOURCE_REPO_SKIPPED" :
    code === 3 ? "LOCK_MISSING" :
    code === 4 ? "LOCK_INCOMPLETE" :
    code === 5 ? "LOCK_INVALID" :
    code === 6 ? "REMOTE_BRANCH_MISSING" :
    code === 7 ? "GIT_OR_NETWORK_ERROR" : "UNKNOWN"
  );
  return JSON.stringify({ status, code, message: "m", ...extra });
}

function makeSessionCreated(id, directory, extra = {}) {
  return {
    type: "session.created",
    properties: { info: { id, directory, title: "t", version: "1", ...extra } },
  };
}

// Injectable deterministic clock. Tests advance time explicitly; no real waits.
function makeClock(start = 0) {
  let t = start;
  return {
    now() { return t; },
    advance(ms) { t += ms; },
    set(ms) { t = ms; },
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
  for (const type of ["session.updated", "session.idle", "message.updated", "file.edited", "server.connected"]) {
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
// Child / subagent sessions (parentID) are ignored
// ---------------------------------------------------------------------------

test("a session with parentID (child/subagent) does not trigger a check", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(1), stderr: "", exitCode: 1 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({
    event: makeSessionCreated("child-1", "/repo", { parentID: "parent-session" }),
  });
  await flush();
  assert.equal($.invocations, 0, "child session does not run the tool");
  assert.equal(client.calls.length, 0, "child session produces no toast");
});

test("a primary session (no parentID) does trigger a check", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({ event: makeSessionCreated("primary-1", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "primary session runs the tool");
});

test("a session with an empty-string parentID is treated as primary", async () => {
  // An empty parentID is the SDK's "no parent" form; it must not be ignored.
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo" });
  await hooks.event({
    event: makeSessionCreated("primary-2", "/repo", { parentID: "" }),
  });
  await flush();
  assert.equal($.invocations, 1, "empty parentID is a primary session");
});

// ---------------------------------------------------------------------------
// Hourly throttle: several sessions in an hour -> one check; after 1h -> new
// ---------------------------------------------------------------------------

test("several primary sessions within an hour produce only one check", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  clock.advance(5 * 60 * 1000); // 5 min
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  clock.advance(30 * 60 * 1000); // 35 min total
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();
  clock.advance(10 * 60 * 1000); // 45 min total
  await hooks.event({ event: makeSessionCreated("s4", "/repo") });
  await flush();

  assert.equal($.invocations, 1, "only one remote check within the hour");
});

test("after one hour a new check is allowed", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(0), stderr: "", exitCode: 0 });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 1);

  // Just under 1h: still throttled.
  clock.advance(HOUR - 1);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "throttled just under 1h");

  // At/after 1h: a new check is allowed.
  clock.advance(2); // now >= 1h since lastCheckAt
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "new check allowed after 1h");
});

test("a failed check still counts as a check for the hourly throttle", async () => {
  // lastCheckAt records the START of the attempt, so a network failure must
  // not cause a retry on every subsequent session within the hour.
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(7), stderr: "", exitCode: 7 }); // GIT_OR_NETWORK_ERROR
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 1);

  clock.advance(10 * 60 * 1000); // 10 min
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  clock.advance(20 * 60 * 1000); // 30 min
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();

  assert.equal($.invocations, 1, "failure does not retry within the hour");
});

// ---------------------------------------------------------------------------
// Concurrency: two simultaneous events -> one tool; checkInFlight cleared
// ---------------------------------------------------------------------------

test("two simultaneous session.created events start only one tool", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  // Deferred shell: the first check stays in-flight while the second event
  // arrives, so checkInFlight is deterministically true for the second.
  const deferred = Promise.withResolvers();
  const $ = makeShell(deferred.promise);
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  // Second event while the first check is still pending (not yet flushed).
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  assert.equal($.invocations, 1, "second event did not start a second tool");

  deferred.resolve({ stdout: payload(0), stderr: "", exitCode: 0 });
  await flush();
  assert.equal($.invocations, 1);
});

test("a primary session and a subagent created during the same check start one tool", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const deferred = Promise.withResolvers();
  const $ = makeShell(deferred.promise);
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("primary", "/repo") });
  // Subagent arrives while the primary's check is in-flight.
  await hooks.event({
    event: makeSessionCreated("sub", "/repo", { parentID: "primary" }),
  });
  assert.equal($.invocations, 1, "subagent did not start a second tool");

  deferred.resolve({ stdout: payload(0), stderr: "", exitCode: 0 });
  await flush();
  assert.equal($.invocations, 1);
});

test("checkInFlight is cleared even when an exception escapes", async () => {
  // A rejecting showToast makes runCheck reject after the inner try. The
  // outer `finally` must still clear checkInFlight so the next (post-throttle)
  // event can run a check.
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeRejectingClient();
  const $ = makeShell({
    stdout: payload(1, {
      installed_commit: SHA_A, remote_commit: SHA_B,
      branch: "main", url: "https://github.com/org/fw.git",
    }),
    stderr: "", exitCode: 1,
  });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal($.invocations, 1, "first check ran");

  // After the rejected toast, checkInFlight must be false. Advance past the
  // hourly throttle and fire again: if checkInFlight were stuck, this second
  // event would be skipped (invocations stays 1).
  clock.advance(HOUR + 1);
  // Switch to a normal client for the second check so it can complete.
  const client2 = makeClient();
  const hooks2 = await AgenticUpdateCheck({
    client: client2, $, worktree: "/repo", now: clock.now,
  });
  await hooks2.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal($.invocations, 2, "checkInFlight was cleared; a new check ran");
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
// Update notification policy (daily dedup keyed by remote_commit)
// ---------------------------------------------------------------------------

test("a new update shows a toast (first time)", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "u" }),
    stderr: "", exitCode: 1,
  });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);
});

test("the same commit does not re-notify before 24 hours", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "u" }),
    stderr: "", exitCode: 1,
  });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1, "notified once at t=0");

  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();
  // still < 24h since first notification
  assert.equal(client.calls.length, 1, "same commit not re-notified within 24h");
  assert.equal($.invocations, 3, "checks still ran (hourly throttle respected)");
});

test("the same commit re-notifies after 24 hours", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "u" }),
    stderr: "", exitCode: 1,
  });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);

  // Cross the 24h threshold (each check is also >1h apart so it runs).
  clock.advance(DAY + HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal(client.calls.length, 2, "same commit re-notified after 24h");
});

test("a different remote commit notifies on the next allowed check even if <24h", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  let remote = SHA_B;
  const $ = makeShell(() => ({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: remote,
                         branch: "main", url: "u" }),
    stderr: "", exitCode: 1,
  }));
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1, "notified of commit B");

  // Only 1h later (well within 24h of the first notice), but remote changed.
  remote = SHA_C;
  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal(client.calls.length, 2, "a new commit notifies despite <24h");
});

// ---------------------------------------------------------------------------
// Diagnostic throttling: per-key Map (independent 24h clocks)
// ---------------------------------------------------------------------------

test("the same diagnostic is not shown repeatedly within 24 hours", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: payload(7), stderr: "", exitCode: 7 }); // GIT_OR_NETWORK_ERROR
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1, "diagnostic notified once");

  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1, "same diagnostic throttled for 24h");
  assert.equal($.invocations, 3, "checks still ran");
});

test("a different diagnostic can notify within the same 24h window", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  let code = 7; // GIT_OR_NETWORK_ERROR
  let $code = 7;
  const $ = makeShell(() => ({
    stdout: payload(code), stderr: "", exitCode: $code,
  }));
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1, "GIT_OR_NETWORK_ERROR notified");

  // Switch to a different diagnostic 1h later.
  code = 5; $code = 5; // LOCK_INVALID
  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal(client.calls.length, 2, "a different diagnostic notifies");
});

test("alternating diagnostics keep independent clocks: GIT_OR_NETWORK_ERROR -> LOCK_INVALID -> GIT_OR_NETWORK_ERROR does not re-notify the third", async () => {
  // Verifies the per-key Map: the intermediate LOCK_INVALID must NOT reset the
  // GIT_OR_NETWORK_ERROR 24h clock, so the third (again GIT_OR_NETWORK_ERROR,
  // within 24h of the first) is suppressed.
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  let code = 7; let $code = 7;
  const $ = makeShell(() => ({
    stdout: payload(code), stderr: "", exitCode: $code,
  }));
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  // 1. GIT_OR_NETWORK_ERROR -> notify.
  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);

  // 2. LOCK_INVALID (1h later) -> notify (different key).
  code = 5; $code = 5;
  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal(client.calls.length, 2);

  // 3. GIT_OR_NETWORK_ERROR again (1h later, 2h after the first) -> NOT notified.
  code = 7; $code = 7;
  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s3", "/repo") });
  await flush();
  assert.equal(client.calls.length, 2, "third (same as first) not re-notified within 24h");
  assert.equal($.invocations, 3, "all three checks ran");
});

test("TOOL_EXECUTION_ERROR (non-JSON / crash) is throttled like a diagnostic", async () => {
  const AgenticUpdateCheck = await loadPlugin();
  const client = makeClient();
  const $ = makeShell({ stdout: "garbage", stderr: "", exitCode: 2 });
  const clock = makeClock(0);
  const hooks = await AgenticUpdateCheck({ client, $, worktree: "/repo", now: clock.now });

  await hooks.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1);

  clock.advance(HOUR);
  await hooks.event({ event: makeSessionCreated("s2", "/repo") });
  await flush();
  assert.equal(client.calls.length, 1, "TOOL_EXECUTION_ERROR throttled for 24h");
});

// ---------------------------------------------------------------------------
// No persistence: reinitializing the plugin creates fresh in-memory state
// ---------------------------------------------------------------------------

test("reinitializing the plugin creates fresh state (no persistence)", async () => {
  // First instance notifies of an update.
  const $ = makeShell({
    stdout: payload(1, { installed_commit: SHA_A, remote_commit: SHA_B,
                         branch: "main", url: "u" }),
    stderr: "", exitCode: 1,
  });
  const clock = makeClock(0);
  const clientA = makeClient();
  const hooksA = await AgenticUpdateCheckA(clientA, $, clock.now);
  await hooksA.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(clientA.calls.length, 1);

  // A fresh instance (simulating an OpenCode restart) has independent state:
  // the same update notifies again because nothing is persisted.
  const clientB = makeClient();
  const hooksB = await AgenticUpdateCheckA(clientB, $, clock.now);
  await hooksB.event({ event: makeSessionCreated("s1", "/repo") });
  await flush();
  assert.equal(clientB.calls.length, 1, "fresh instance notifies again; no persistence");

  async function AgenticUpdateCheckA(c, shell, now) {
    const fn = await loadPlugin();
    return fn({ client: c, $: shell, worktree: "/repo", now });
  }
});

test("the plugin source contains no on-disk persistence logic", () => {
  const src = readFileSync(PLUGIN_PATH, "utf8");
  assert.ok(!src.includes("writeFile"), "no filesystem writes");
  assert.ok(!src.includes("mkdir"), "no directory creation");
  assert.ok(!/from\s+["']node:fs["']/.test(src), "no fs import");
  assert.ok(!/from\s+["']fs["']/.test(src), "no fs import");
});

// ---------------------------------------------------------------------------
// No TUI plugin / server.connected logic (architectural decision)
// ---------------------------------------------------------------------------

test("the plugin source has no TUI plugin, tui.json or server.connected logic", () => {
  const src = readFileSync(PLUGIN_PATH, "utf8");
  // Check for actual string-literal usage (a handler/comparison), not mere
  // mentions in comments. This catches `event.type === "server.connected"`
  // while allowing informative comments that explain the decision.
  assert.ok(!/["'`]tui\.json["'`]/.test(src), "no tui.json string literal");
  assert.ok(!/["'`]server\.connected["'`]/.test(src), "no server.connected handler");
  // The only event type handled is session.created. Collect dotted string
  // literals used in === / !== comparisons (excludes typeof checks against
  // "string"/"number"/"function", which have no dot).
  const eventTypes = [...src.matchAll(/[=!]==\s*["'`]([a-z_.]*\.[a-z_.]+)["'`]/g)]
    .map((m) => m[1]);
  assert.deepEqual(eventTypes, ["session.created"], "session.created is the sole trigger");
  // The only export is AgenticUpdateCheck (no second TUI plugin export).
  assert.ok(/export const AgenticUpdateCheck/.test(src), "exports AgenticUpdateCheck");
  assert.ok(!/export const \w*Tui\w*/i.test(src), "no TUI plugin export");
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
