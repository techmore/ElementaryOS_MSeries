/* Program entry point, kept apart from the Orchard class so the UI smoke test can build the whole window. */
int main (string[] args) {
    // On Asahi Mesa the GL/Vulkan renderers cost ~180 MB of shader heap for a mostly static
    // window; cairo draws the same UI in a third of the memory. ORCHARD_RENDERER=gl|ngl|vulkan overrides.
    var renderer = Environment.get_variable ("ORCHARD_RENDERER");
    Environment.set_variable ("GSK_RENDERER", renderer ?? "cairo", true);
    return new Orchard ().run (args);
}
