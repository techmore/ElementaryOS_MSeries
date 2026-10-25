# UI conventions and decision criteria

These recommendations translate the inspected project into a consistent working
practice; they are not a claim that every existing screen already complies.

## Layout and styling

Use native header bars, navigation, controls and dialogs for the containing app.
Keep primary content and the next useful action easy to find. Group related
settings with a heading and rows: label/optional description at the start,
control at the end. Use a sidebar/detail layout for collections, and a welcome
or placeholder for genuinely empty content.

Match neighboring rows before introducing new dimensions. Observed settings
examples include 12-pixel control gaps, CodexBar row padding of 8 × 12, page
side margins of 18, and Battery row side margins of 14. These are local anchors,
not universal tokens. Avoid converting the whole project to a new spacing scale
as part of a small change. Use logical units and start/end alignment.

Reuse theme typography and hierarchy; keep subordinate copy readable. Scope CSS
to the app or component and prefer theme foreground, background, accent and
semantic colors. Check contrast in both schemes. Follow the app's system color
preference handling; do not force a macOS font, palette or decoration. Keep
intentional palette choices when they communicate a useful identity.

Allow labels to wrap and content to scroll vertically. Check long account names,
provider errors, translated text, enlarged text and narrow windows. Ellipsize
compact summaries only when full information remains available. A width request
does not cap GTK's natural width. Keep header actions usable as space shrinks;
existing crowded headers are not a template to reproduce.

## Controls and navigation

Use a switch for a persistent boolean, a button for an action, and a dropdown or
other suitable selector for mutually exclusive choices. Preserve established
instant-apply settings and display save failures; only show success when the
backend confirms it. Retain an explicit Apply/Save workflow where the target
surface already needs staged changes.

Use clear action labels such as Refresh, Sign In, Cancel, or Retry. Label
icon-only actions accessibly and supply useful tooltips. Preserve keyboard focus,
selection and scroll position after a refresh. Use stable backend identifiers
for rows and accounts, not display text or list positions.

## Asynchronous state and data flow

Keep service, parsing and presentation responsibilities distinct, following
existing model/helper boundaries. Avoid blocking subprocess, network or disk
work on the GTK main loop; marshal worker results onto the UI thread. Cancel or
ignore stale completions when the account changes or a window closes. Avoid
rebuilding the entire widget tree for a value update.

- **Loading:** identify what is being fetched; preserve useful prior data.
- **Empty:** explain why there is no content and offer the relevant next action.
- **Pending:** prevent duplicate operations while retaining cancellation where supported.
- **Stale/offline:** retain last-known data with its age and a useful refresh/retry action.
- **Error:** explain the failed operation and recovery; keep details available without overwhelming the screen.
- **Success:** reflect confirmed backend state. Distinguish measured values, estimates, unavailable values and real zeros.

For sync or account flows, distinguish signed out, verification required,
unlocking, syncing, up to date, expired authentication and failed operations.
Do not invent conflict-resolution controls if the backend is read-only or has
no conflict model. Never expose passwords or tokens in labels, screenshots or logs.

## Accessibility, text and motion

Associate labels and controls; ensure keyboard activation, logical tab order,
visible focus and a way to dismiss dialogs. Communicate state with text or icons
as well as color. Test contrast for dim subtitles and status badges, not only
main headings. Use semantic GTK accessibility properties for custom controls.

Follow the target app's gettext setup for new user-facing text. If it lacks
translation infrastructure, identify that gap and keep strings ready to extract;
do not claim localization is complete. Use locale-aware date/number/unit formatting
and translator context for ambiguous labels. Avoid sentence fragments assembled
around substituted values where grammar changes with translation.

Use restrained feedback and transitions; honor animation preferences where
supported. A continuously pulsing status indicator in existing CSS is something
to assess, not a requirement for every running state.
