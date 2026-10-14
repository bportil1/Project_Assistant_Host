# Universal Job Monitor — JM-1 (backend contract)

JM-1 is **read-only observability**, not task scheduling or a process manager.
The standalone `pah_jobs` package has **no Flask, network, PAH catalog, or
module-private database dependency**. A standalone module can install or vendor
this package; importing PAH is not required. Each module owns its registry and
chooses which jobs and streams to report. PAH's `JobMonitorAggregator` reads
explicitly attached sources only. There is no global process discovery.

## Example: parent task and worker process

```python
from pah_jobs import JobRegistry, ProcessStreamCapture
from pah.jobs import JobMonitorAggregator  # PAH-only optional adapter

jobs = JobRegistry("pypique", secrets=[token])  # module owns token/configuration
scrape = jobs.start("logical", "benchmark scrape", run_id="run-42")
worker = jobs.start("process", "cppcheck project 10", parent_id=scrape,
                    pid=popen.pid, checkpoint_id="project-10")
# Caller must have launched subprocess with stdout=PIPE, stderr=PIPE.
# This drains pipes but does NOT call wait(), communicate(), kill(), or spawn().
reader = ProcessStreamCapture(jobs, worker, stdout=popen.stdout, stderr=popen.stderr)
reader.start()
# Existing workflow remains the authority on process completion/status:
exit_code = popen.wait()
reader.join(timeout=3)
jobs.transition(worker, "succeeded" if exit_code == 0 else "failed", exit_code=exit_code)
jobs.heartbeat(scrape, progress=0.25)

agg = JobMonitorAggregator()
agg.attach(jobs.reader())
print(agg.snapshot())
```

JM-1 does not automatically intercept all jobs or stdout. pyPIQUE and EBM/DBN
adapters are planned for JM-3. A future UI should use the read-only reader
(`snapshot`, `job`, `outputs`, `events_since`, `subscribe`) in JM-2.

## Contract and safety

- `logical` jobs need not have a PID; `process` jobs have PID plus Linux `/proc`
  start-time identity when observable. PID reuse is reported, never treated as
  proof of a new job completing. On other OSes the status is `unobservable`.
- Explicit lifecycle: queued → running/paused/completing →
  succeeded/failed/timed_out/interrupted; `unknown` is allowed. No transition
  is inferred from silence or an absent process. A timeout label is a caller
  decision, never a signal to kill the process.
- Each job records parent, optional campaign/run and checkpoint identifiers,
  timestamps, last heartbeat/output, progress, completion reason and exit code.
  CPU seconds/RSS are optional and available for registered Linux PIDs.
- Output and event history use bounded ring buffers; old completed *leaf* jobs
  are evicted before active jobs, and a full active registry fails visibly.
  Subscribers have bounded queues and report dropped event counts. `events_since`
  signals an event-history gap rather than silently claiming completeness.
- Common credential patterns and explicitly configured secrets are masked;
  redaction is best-effort. Do not submit environment variables, raw command
  arguments, credential-bearing paths, or complete secrets as identifiers/logs.
  On-demand output capture requires ownership of the relevant process pipes.
- No shell commands, process killing, cancellation, arbitrary PID probing,
  direct module database access, automatic PAH scheduling, or implicit writes.
- The registry is currently in-memory: restarting the owning Python process
  clears job history. Durable per-module history/reconnection can be introduced
  separately without giving PAH access to module-owned databases.

## JM-2 onward

JM-2: collapsible right-side viewer and per-process output inspector.
JM-3: pyPIQUE/EBM/DBN instrumentation, including artifact dependency lifecycle
and logical workflow steps that are not OS processes; separate dashboard
readiness from background activity. JM-4: other modules.

## JM-2: PAH read-only viewer

Open **Jobs** in the PAH top bar, or **Tools → Job Monitor**, or use
`Ctrl+Alt+J`. Close using the X button or Escape. It is a right-edge drawer
that does not permanently consume workspace columns; its left edge can be
resized with pointer or arrow keys (except on narrow screens). The viewer is
available across PAH modes, refreshes every three seconds **only while open**,
and displays the latest 100 captured output lines of a selected registered job.
Select from Active, All recent, Failed/timed out, and Completed filters.
Parents expand to show child operations and process workers. In-memory history
exists only while the producing module process lives.

The host exposes **read-only** local routes:

- `GET /api/jobs`: the JM-1 aggregate `sources`, `job_count` (no global PID scans).
- `GET /api/jobs/<owner>/<job_id>/output?limit=100`: bounded, redacted output
  from an explicitly attached owner, with 404 for an unknown owner/job.

Trusted runtime adapters attach their `JobRegistry.reader()` to
`app.extensions["pah_job_monitor"]` (via the JM-1 `JobMonitorAggregator`).
The viewer itself does not instrument tasks, obtain raw shell access, or
create a background scheduler. **No sources appearing before JM-3 is expected.**
The displayed liveness and resource metrics are observations already recorded
by the module; a silent process is not presumed to have hung.

No endpoint in JM-2 can stop, pause, launch, or alter jobs. Existing PAH
module routing, experimental datasets, and module-private databases are
unmodified by this sprint. Later JM-3 integration will publish benchmark
scrape, SAT processes, training, and artifact-handoff diagnostics.

## JM-3A: host workflow diagnostics and module-owned readers

JM-3A attaches a PAH-owned `pah` job source. It records host dispatch attempts
(including failures), *verified* PIDs supplied in runtime launch metadata, and
changes in pyPIQUE/HSQA workflow readiness and provider artifact publication.
Refresh events include artifact IDs/kinds/capabilities, **never matrix values**;
unchanged snapshots are deduplicated by module, workspace, and workflow step.
A launch being dispatched successfully **does not** mean an experiment completed.
If a PID vanishes without an exit code its outcome is marked **unknown**, not
succeeded. Output remains bounded and redacted; monitoring errors must not abort
scientific jobs. This does not auto-scan OS processes or attach to foreign PIDs.

A standalone module that implements its own JM-1 `JobRegistry` can voluntarily
publish an adapter `job_reader()` method returning a `pah_jobs.JobReader` with
`owner == adapter.module_id`. On `/api/jobs` the host attaches that reader,
without opening the module's database, filesystem, or PID namespace.
For example, a pyPIQUE adapter can expose a module-owned tree:

```python
from pah_jobs import JobRegistry, ProcessStreamCapture
jobs = JobRegistry('pypique')

# In a runtime adapter, job_reader() returns jobs.reader().
# In the existing subprocess launch path *after* obtaining Popen:
# worker_id = jobs.start('process', 'Cppcheck project_374',
#                        parent_id=scrape_id, pid=child.pid)
# ProcessStreamCapture(jobs, worker_id,
#                      stdout=child.stdout, stderr=child.stderr).start()
# Later, when child.wait() returns: jobs.transition(worker_id, 'succeeded' ...)
```

**Do not** add a second reader to pipes that are already consumed by the
module, call `communicate()` concurrently with `ProcessStreamCapture`, or alter
SAT timeouts/checkpoint mechanics simply to enable diagnostics. Module-level
scrape/training/optimizer/MI instrumentation requires separate changes within
those modules' source trees. JM-3A does **not** yet show individual Cppcheck
workers unless their module has opted into the reader contract.

## JM-3B: pyPIQUE and HSQA_DBN process-level instrumentation

With JM-3B, the PAH launcher explicitly passes a workspace-scoped
`PAH_JOB_MONITOR_DIR` and the installed `pah_jobs` package path to its local
pyPIQUE and HSQA_DBN child runtimes. Standalone module launches do not need
PAH: monitoring is optional and disabled if the package or environment variable
is absent. Each process publishes **bounded, atomic, mode-0600 snapshots**
under `<active-workspace>/.pah/job_monitor/`. These are monitor records, not
scientific checkpoints or module-private databases. The read-only PAH monitor
only loads these opt-in records for the current workspace. Do not share the
monitor directory publicly; diagnostic messages may contain filesystem paths.

Instrumented work includes:

- pyPIQUE's benchmark worker, SAT provider stages, managed SAT subprocesses,
  quality-model loading/evaluation, MI models, validation, and model comparison.
  Cppcheck and other SAT process entries include PID, run state, watchdog
  timing, and stdout/stderr **after `communicate()` completes**. Live output
  cannot be attached safely to that already-owned pipe without redesigning the
  subprocess runner. No additional reader is attached.
- HSQA_DBN's managed UI/experiment processes, already-consumed live stdout,
  per-trial training, deferred analysis/MI, and representation exports.
- Parent-child relationships are preserved within each job publisher process.
  Independent publishers appear as separate roots; remote subprocesses cannot
  safely be assumed to share a parent's in-memory job ID.

Only monitoring records are read by the host. Process IDs are verified using
Linux process-start identity to avoid stale PID reuse. If a publisher disappears
without reporting an outcome, active jobs are displayed as **unknown**, not
successful or failed. Historical records remain local and are capped in each
reader's displayed result. No kill, cancel, execute, or arbitrary attach API is
added. Already-running sessions started *before* JM-3B are not retroactively
instrumented; restart module runtimes to enable future monitoring.

Implementation note: In a checkout where `modules/pypique` and
`modules/hsqa_dbn` are independent Git submodules, a `git apply` from the PAH
root touches their working trees but cannot update the submodule git commits.
Review and commit those module changes independently when integrating upstream.
