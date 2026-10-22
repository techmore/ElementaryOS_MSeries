# Scheduler integration provenance

The retained 0002 prototype is byte-identical to the compatibility patch now
selected for package revision 4. Actual M4 driver/Rust core/C scheduler objects
compile and six associated-constant API tests pass on generic ARM64 QEMU.
This replaces the prior pending status in retention-source-preflight.json,
which is preserved as the historical source-preparation record.
Full kernel/package build and hardware qualification remain separate gates.
Allocation-owner and mutable timeout-aliasing reviews remain open.
