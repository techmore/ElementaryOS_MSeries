# Calendar, browser and Mail — qualification in progress

**Two of six model cases are complete; both passed. Four are pending quiet admission.** Pending cases are not failures, and this checkpoint is not final qualification.

The first pinned Qwen3.5 4B workflow used these six tools in order: browser_list_tabs, browser_read_page, create_assistant_event, list_calendar_events(scope=assistant), create_mail_draft, read_mail_draft. Independent EDS and RFC822 matches passed. Its 347.37 seconds include approximately 226.53 seconds paused by the existing cooling supervisor. At 345 samples, minimum available RAM was 11.44 GiB, maximum sampled fan 3236 RPM and maximum temperature 58.40 C. These are one-second sampled readings, not acoustic measurements or identical-state comparisons with the earlier kernel cohort.

The first hostile-page trial passed in 12.85 seconds and created no event or draft. The remaining two repeats of each case remain in the existing owned queue. All completed outcomes and any interruptions will be preserved.

Backend concurrent/retry/conflict/literal-text checks passed and removed their synthetic source. Actual Newelle controller discovery found sixteen tools without inference. An isolated hidden Assistant Mail Drafts → native Mail composer test preserved recipient, subject and body; Send was never activated. The full UI logs, settings clones, browser profile and private app data are excluded.

`evaluated-source/` preserves the exact v1 source bytes used by this cohort. The temporary executing harness name was app-workflow-smoke.py; the repository's older Tasks-to-note harness will be retained unchanged. The maintained new harness, calendar-mail-workflow-smoke.py, uses v2 metadata (including runtime/app/profile pins), handles telemetry loss explicitly and fixes timeout cleanup. Those maintenance changes do not relabel or repeat this v1 cohort.

`source-pins.json` distinguishes installed package/binary identities from source references. `quiet-guard.json` contains only owned worker cooling messages and overlap estimates; no full journal. `publication.json` records whether all six completed cases exist. `checksums.json` covers the published files.
