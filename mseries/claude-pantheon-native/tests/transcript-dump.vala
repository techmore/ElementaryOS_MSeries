/* Loads a transcript and prints what the chat view would render.
 * Usage: transcript-dump <file.jsonl> */
int main (string[] args) {
    if (args.length < 2) { stderr.printf ("usage: %s <file.jsonl>\n", args[0]); return 2; }
    var start = get_monotonic_time ();
    var transcript = Transcript.load (args[1]);
    var elapsed = (get_monotonic_time () - start) / 1000.0;
    stdout.printf ("session=%s cwd=%s title=%s messages=%u parse_ms=%.1f\n", transcript.session_id, transcript.cwd, transcript.title, transcript.messages.length (), elapsed);
    foreach (var message in transcript.messages) {
        foreach (var block in message.blocks) {
            if (block.kind == BlockKind.TEXT) stdout.printf ("[%s] %s\n", message.role, Transcript.first_line (block.text, 100));
            else stdout.printf ("[%s] <tool> %s%s\n", message.role, block.summary, block.result != "" ? " (result %d bytes)".printf (block.result.length) : "");
        }
    }
    return 0;
}
