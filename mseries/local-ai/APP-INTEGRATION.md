# MCP app integration on M1 Pro 32 GB

The local MCP adapter now has eleven typed tools. Version 0.2 adds task creation in an owned local **Assistant Tasks** list. It creates that list on first use; it does not select a user's existing list or a synced account. Existing tasks are never edited or completed by this tool. Personal chat and coding still use the measured Qwen3.5 4B presets with the existing memory/fan guards.

| Surface | Implemented capability | Evidence and remaining limits |
|---|---|---|
| Newelle | Local chat, user-summary memory and MCP tools | Earlier chat, clock dispatch and separate-process memory passed. Updated eleven-tool controller discovery passed without requesting inference; new task workflow qualification is pending. |
| Files / notes | Scoped UTF-8 reads and create-only Markdown notes | Earlier create/read, traversal, symlink and overwrite checks passed. No arbitrary file access. |
| Tasks / Homeboard | Read open EDS tasks; create in local Assistant Tasks | Live concurrent/retry/conflict checks passed. Model note-to-task and scoped read-back passed in all three repeats. |
| Calendar | Read upcoming local EDS calendar components | Synthetic VEVENT round trip passed. Recurrences are labeled, not expanded; no calendar writes yet. |
| Energy Monitor | Cache reads and freshness | Adapter checked; signed-in live collector qualification remains separate. |
| System and fault watcher | Measurements and bounded fault signatures | Read-only; automatic model diagnosis remains off after failed repair-advice checks. |
| Browser, mail and messaging | App inventory | Dedicated adapters are not implemented. Inventory does not establish control. No messages are sent. |

[Synthetic receipts and source digests](receipts/task-integration-2026-10-16/) record adapter/discovery checks, all six completed model trials and the interrupted checkpoint.

## Task writes and retries

`create_assistant_task` accepts a title, stable `request_id`, optional due date `YYYY-MM-DD`, and optional details. Writes go through EDS/libical component setters. A private source marker binds the adapter to its own local task list. A per-user lock serializes concurrent writes, and a deterministic task UID makes ordinary retries across MCP process restarts idempotent. Reusing the same ID with different task data returns an error and leaves the task unchanged. A source reconfigured to a nonlocal backend is refused.

`list_tasks` keeps its default all-list read behavior. The new `scope: assistant` filter reads only the owned list and does not create a list when none exists. The synthetic model harness always requires that scope, so private task contents never enter model evaluation or public receipts.

The first live write check used two concurrent MCP processes plus a third retry process. Exactly one request created a task, all returned the same UID, and the retry did not create another object. A conflicting title was refused. Commas, semicolons and iCalendar-looking description text round-tripped as literal data in one VTODO. The synthetic source was removed afterwards.

## Qualification and reproduction

Current contract count: **53 passing tests**. These include input/date validation, synced-source refusal, private ownership markers, settings-preserving tool refresh, and distinguishing malformed model tool calls from interrupted inference. The model suite separately checks note → task → scoped read-back and rejection of a file instruction to create an unwanted task, three repeats each. Checkpoint resumption keeps completed successes and failures, retrying only incomplete cases with matching metadata. All six completed trials passed: note-to-task 3/3 and file-instruction rejection 3/3. Each positive trace read the note, created exactly one task with the requested title/date/retry ID, and read it back through the scoped task tool. Independent EDS queries matched; all owned sources were removed. Injection trials created no task. One URLError interruption was preserved and only unfinished work resumed. This is a checkpointed quality result, not a single uninterrupted latency run. The tests explicitly name the intended workflow tools and do not establish unrestricted autonomous app discovery.

Completed note-to-task workflows took a median 22.32 seconds; injection checks 4.16 seconds. At eighteen request-boundary samples, minimum available RAM was 8.87 GiB and maximum fan reading 2648 RPM. These sparse readings are not continuous peaks or acoustic measurements. The worker continuously enforced its existing reserve/fan/temperature policy. Tasks GUI rendering, reminder delivery and a Newelle GUI task-write conversation were not exercised by these API/stdio workflows.

The current machine runs `7.1.13-elementary-fairydust-usb4-dptunnel`, changed by separate project work. This integration task does not change the kernel, display or audio. New workflow timings must not be treated as an identical-hardware-state continuation of the earlier `7.1.13-3-2-ARCH` model benchmark cohort.

```sh
python3 -m unittest discover -s mseries/local-ai -p 'test_*.py'
python3 mseries/local-ai/task-write-smoke.py --output task-adapter.json
# Uses the running pinned default endpoint; waits for cool/idle windows.
python3 mseries/local-ai/task-write-smoke.py --endpoint http://127.0.0.1:8766/v1 --repeat 3 --output task-workflows.json
```

Use an existing quiet model worker; do not launch a second GPU worker. The harness preserves owner workloads, creates only synthetic local sources/workspaces, independently queries EDS, and removes its owned sources. Full logs and settings clones remain private; only bounded synthetic receipts are published.

Next app coverage: local calendar writes with the same create-only/idempotent boundary, browser tab/page reads through an explicit browser adapter, then scoped draft workflows for apps with suitable local APIs. Each adapter needs its own read/write contract and end-to-end evidence before it is described as supported.

API reference: [GNOME ECal.Client](https://gnome.pages.gitlab.gnome.org/evolution-data-server/libecal/class.Client.html), [libical component API](https://libical.github.io/libical/v4/apidocs/icalcomponent_8h.html). The initial [model qualification report](receipts/2026-10-16.md) and its failures remain unchanged.
