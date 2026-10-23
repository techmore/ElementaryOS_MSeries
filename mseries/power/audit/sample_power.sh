#!/bin/bash
# usage: sample_power.sh N  -> median/p10/p90 of whole-system power (W) and CPU busy % at 1 Hz for N seconds.
# The SMC rail is found by label in ../sensors.py (it is not always hwmon2).
exec python3 -I "$(dirname "$(readlink -f "$0")")/../sensors.py" "${1:-60}"
