public class GenerationGate : Object {
    public const uint64 DESKTOP_RESERVE_BYTES = 6UL * 1024UL * 1024UL * 1024UL;

    // A run is admitted only after a specific engine/model/size tuple has been
    // calibrated and its measured peak footprint is known.
    public static bool can_run (bool qualified, uint64 available_bytes, uint64 measured_peak_bytes) {
        if (!qualified || measured_peak_bytes == 0) return false;
        if (available_bytes < DESKTOP_RESERVE_BYTES) return false;
        return available_bytes - DESKTOP_RESERVE_BYTES >= measured_peak_bytes;
    }

    public static string explain (bool qualified, uint64 available_bytes, uint64 measured_peak_bytes) {
        if (!qualified) return "Image engine not qualified on this M-Series system.";
        if (available_bytes < DESKTOP_RESERVE_BYTES) return "Waiting for the 6 GiB desktop memory reserve.";
        if (measured_peak_bytes == 0) return "A measured memory budget is required before generation.";
        if (available_bytes - DESKTOP_RESERVE_BYTES < measured_peak_bytes) {
            return "This run would use the protected desktop memory reserve.";
        }
        return "Ready for the calibrated model and image size.";
    }
}
