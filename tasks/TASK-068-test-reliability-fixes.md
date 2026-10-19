# TASK-068 Test Reliability Fixes

## Source Plan

Developer-approved plan (2026-10-19) covering small test-only fixes:

1. The backend test `test_stopping_during_a_prophet_fit_leaves_no_cmdstan_process`
   in `backend/tests/test_prediction_worker.py` passes locally but sometimes
   fails in CI with `CmdStan did not write into the private temporary
   directory` (`tests/test_prediction_worker.py:311`).
2. TASK-067 review round 2, finding F-002 (`missing_test`, `info`, left open):
   the `console.error` spy in the workspace fallback failure test is restored
   only when the test passes
   (`docs/ai-reviews/TASK-067/review-002.json`).
3. Developer-approved extension during implementation (2026-10-19): when an
   assertion in the Prophet stop test fails before the test stops the child,
   the child and CmdStan keep sampling, and pytest hangs at exit waiting for the
   non-daemon child. The child's private temporary directory is also left
   behind. Reproduced with the slow font-cache check below on the original
   test.

## Goal

The Prophet stop test waits for the actual CmdStan process before checking the
private temporary directory, so it passes regardless of runner speed. If any of
its assertions fails, it still stops the child, so pytest reports the failure
and exits instead of hanging, with no CmdStan process or private temporary
directory left behind. Frontend
tests that silence `console.error` with a spy always restore it, even when an
assertion fails.

### Cause Of The Backend Flake

The test waits until the child's process group has any member other than the
child, treats that as "CmdStan started", and then requires the private
temporary directory to be non-empty. Other short-lived processes join the group
first:

- `from prophet import Prophet` imports `prophet.plot`, which imports
  matplotlib. The child's `MPLCONFIGDIR` is a new, empty directory, so
  matplotlib has no font cache and rebuilds it by running `fc-list --help` and
  `fc-list --format=...`. A `uname -p` subprocess also runs during the import.
- These processes start after `os.setsid()`, so they are in the child's group,
  and they run while the private directory is still empty.
- `cmdstanpy` is imported lazily when Prophet builds its model. Its
  import-time `tempfile.mkdtemp()` is the first entry in the private directory.

Traced during planning with `TMPDIR` and `MPLCONFIGDIR` pointing at an empty
directory: `uname -p` and both `fc-list` calls ran while the directory had no
entries. The matplotlib font cache appeared only after the import, and
`cmdstanpy`'s directory appeared when the model was built. On a slow CI runner
the 50 ms poll catches `fc-list` while it runs, so the wait returns before
CmdStan starts. Locally those processes usually finish between polls.

## Requirements

### Backend: Prophet Stop Test

`backend/tests/test_prediction_worker.py`,
`test_stopping_during_a_prophet_fit_leaves_no_cmdstan_process`:

- Replace the "any other group member" wait with a wait for a group member
  whose executable is Prophet's CmdStan model binary, `prophet_model.bin`.
  Keep the existing 60-second wait timeout and the "CmdStan did not start"
  message.
- Identify the process by its executable path or the first `cmdline` argument,
  not `/proc/<pid>/comm`, because `comm` is truncated to 15 characters
  (`prophet_model.b`).
- Keep the private temporary directory assertion and its message unchanged. It
  must run after the new wait, when `cmdstanpy` has already created its
  directory in the private directory.
- Keep the rest of the test's checks unchanged: stopping within 5 seconds, no
  group members left within 5 seconds and the private directory removed.
- Wrap the assertions before and including the timed stop in `try/finally`, and
  call `worker._stop_child()` in `finally`. `_stop_child()` returns immediately
  once the child has been released, so the call is a no-op after the timed
  stop. Do not change `_stop_child()` or other worker code.
- If a helper is added, keep it next to `_group_members` and use the same
  `/proc` style, ignoring processes that exit while they are read.

### Frontend: Console Error Spy Restore (TASK-067 F-002)

- `frontend/src/App.workspace-fallback.test.tsx`: restore the `console.error`
  spy in "shows the session bar and allows sign out when the workspace fails
  to load" even when an assertion fails. Add `vi.restoreAllMocks()` to the
  existing `afterEach` and remove the manual `consoleError.mockRestore()`.
- `frontend/src/components/DeferredRoute.test.tsx`: the review notes the same
  pattern in "shows a non-sensitive error and reload action for a rejected
  lazy import". Apply the same fix: add an `afterEach` with
  `vi.restoreAllMocks()` and remove the manual `mockRestore()`.
- If a test no longer uses the spy variable after the change, call
  `vi.spyOn(...)` without assigning it.
- Do not change any other assertion in these tests.

### General

- Test-only changes. No application code changes.
- No tests removed, skipped or weakened. No longer timeouts or retries used to
  hide a race.
- No new dependencies, test tooling, scripts or configuration changes.

## Acceptance Criteria

- [ ] The Prophet stop test waits for a group member running
      `prophet_model.bin` before checking the private temporary directory.
- [ ] The Prophet stop test passes when the matplotlib font cache rebuild is
      slowed down, using the temporary verification below, and fails with the
      reported message on the current test under the same check.
- [ ] When an assertion in the Prophet stop test fails before the timed stop,
      the test stops the child in `finally`: pytest exits promptly with the
      failure, and no `prophet_model.bin` process or private temporary
      directory is left.
- [ ] Both frontend tests restore the `console.error` spy in `afterEach`, and
      neither restores it manually inside the test.
- [ ] The backend and frontend suites, lint, typecheck, format check and build
      pass.
- [ ] No application code, dependency, tooling or configuration is changed,
      and no test is removed, skipped or weakened.

## Out Of Scope

- Changing the worker's private temporary directory or `MPLCONFIGDIR` setup.
  Every calculation child currently rebuilds the matplotlib font cache and
  runs `fc-list`, which wastes time on each prediction even though plotting is
  never used. Changing that touches the ADR-014 child isolation design and
  needs a separate developer decision and task.
- Other worker tests in `test_prediction_worker.py`. They do not rely on the
  group-member wait.
- Enabling `restoreMocks` globally in the Vitest configuration, or changing
  other tests that use spies.
- TASK-067 review round 2 F-001 (task line estimate) and the round 1 F-003
  Customers overlap.

## Implementation Notes

Read before implementation:

```text
AGENTS.md
ARCHITECTURE.md
docs/TESTING.md
docs/decisions/ADR-014-prophet-and-model-selection.md
```

- Prophet loads its model from
  `prophet/stan_model/prophet_model.bin` (`prophet/models.py`,
  `CmdStanModel(exe_file=...)`). `CmdStanModel` may run the binary briefly to
  read model information before sampling. That happens after `cmdstanpy` is
  imported, so the private directory is already non-empty.
- `use_private_temporary_directory` in
  `backend/app/api/v1/predictions/worker.py` sets `TMPDIR` and `MPLCONFIGDIR`
  to the same directory. Do not change it.
- The project uses Vitest 4. `vi.restoreAllMocks()` restores only spies
  created with `vi.spyOn`. It does not reset `vi.fn()` module mocks such as
  `navigateBrowser`, so the existing `beforeEach` `mockReset()` stays
  unchanged.

### Temporary Slow Font-Cache Verification

Use this only to verify the backend fix, and delete it before committing:

1. Create a temporary directory outside the repository with an executable
   `fc-list` script that sleeps for about 2 seconds and then runs the real
   `fc-list` with the same arguments.
2. Run the Prophet stop test with that directory first in `PATH`, for example
   `PATH=<temporary dir>:$PATH uv run pytest
   tests/test_prediction_worker.py::test_stopping_during_a_prophet_fit_leaves_no_cmdstan_process`.
3. Before the fix it fails with "CmdStan did not write into the private
   temporary directory", and pytest then hangs until the child's process group
   is killed by hand. After the fix it passes.
4. To check the `finally` cleanup, temporarily restore the old "any other group
   member" wait in the fixed test and run step 2 again. The test must fail with
   the same message, pytest must exit promptly, and no `prophet_model.bin`
   process (check `/proc/<pid>/exe`) or `/tmp/schatten-prediction-*` directory
   may remain. Restore the fixed wait afterwards.
5. Delete the temporary directory and confirm `git status` shows no leftovers.

## Testing

Required:

- [ ] Backend tests: the Prophet stop test passes normally and under the
      temporary slow font-cache check.
- [ ] Frontend tests
- [ ] Format check
- [ ] Lint
- [ ] Typecheck
- [ ] Build

Not applicable:

- [ ] Integration tests and manual verification. Reason: test-only change; no
      application behaviour changes.

Commands:

```bash
cd frontend
pnpm format:check
pnpm lint
pnpm test
pnpm build

cd ../backend
uv run ruff check .
uv run pytest
uv run pyright

cd ..
python3 scripts/ai_review_records.py validate
```

## Documentation

- `docs/TESTING.md`, "Prophet And Model Selection": state that the Prophet stop
  test waits for the CmdStan model binary in the child's group, because
  matplotlib's font cache rebuild runs `fc-list` in the same group first, and
  that the test stops the child in `finally` so a failed assertion does not
  leave CmdStan running or pytest hanging.
- `docs/TESTING.md`: add a short rule for frontend tests: restore spies such as
  a silenced `console.error` in `afterEach` with `vi.restoreAllMocks()`, not at
  the end of the test.

## Notes For AI Agent

- Use the branch `fix/TASK-068-test-reliability-fixes`.
- Save the redacted Step 13 review record under `docs/ai-reviews/TASK-068/`.
  Record the TASK-067 review-002 F-002 disposition there.
- Report all changed files, every verification command run, and the result of
  the temporary slow font-cache check before and after the fix, including the
  `finally` cleanup check.
