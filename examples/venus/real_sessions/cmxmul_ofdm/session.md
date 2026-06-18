# Session Record

## Goal

Investigate whether Venus `VCMXMUL` RTL behavior matches the VEMU model, then
try using `vcmxmul` in `nrPDSCHDag1_v2` OFDM complex multiplication and decide
whether the numerical error is acceptable.

## Final Outcome

The RTL and VEMU `VCMXMUL` algorithms were confirmed to match at the instruction
semantic level, but `VCMXMUL` was not acceptable as a default replacement for
the OFDM fixed-point complex multiply chain. The default VEMU task was restored
to the explicit `vmul/vssub/vsadd` implementation, and a logic-correct
`cmxmul` experimental backup was kept for future investigation.

## Key Commands

- make -C /home/shenyihao/Project/MultiVemu/VEMU/dsl all
- make -C /home/shenyihao/Project/MultiVemu/VEMU Emulator
- Debug/Emulator test.hex -w -j../dsl/final_output/dag1.json -b../dsl/bin/dag1.bin
- Compare baseline explicit OFDM VSTORE dumps against cmxmul OFDM VSTORE dumps as signed int8.
- Search generated assembly for `vns_cmxmul.ivv`.

## Tests / Verification

- DSL build passed with `TARGET_DAG=nrPDSCHDag1_v2`, `VENUSROW=128`, and `VENUSLANE=16`.
- Emulator build passed.
- Full DAG Emulator run exited successfully.
- Default restored path generated no `vns_cmxmul` in the final assembly.
- Default restored OFDM final stores matched the baseline exactly:
  - `OFDM final_store0`: mismatch 0 / 7488, MAE 0, RMSE 0
  - `OFDM final_store1`: mismatch 0 / 7488, MAE 0, RMSE 0

## Benchmark Results

For the all-`cmxmul` OFDM experiment, signed int8 final VSTORE comparison showed
large error:

- OFDM real: mismatch 6992 / 7488 = 93.38%, MAE 14.54, RMSE 21.59, signal RMS 15.10, relative RMSE 142.96%
- OFDM imag: mismatch 6981 / 7488 = 93.23%, MAE 14.24, RMSE 21.09, signal RMS 14.98, relative RMSE 140.79%
- Downstream phase-decomp outputs had similar relative RMSE around 140%.

After fixing the `cmxmul` operand mapping, the first local error point improved
from a large formula-level mismatch to about 1 LSB, but the multi-stage OFDM
chain still amplified the error. A hybrid version with only stage 0 using
`cmxmul` still had relative RMSE around 87%, so it was not accepted as the
default path.

## Important Facts

- `VCMXMUL` in RTL and VEMU uses a Gauss-style three-multiply formula:
  - `real = C * (A - B) + B * (C - D)`
  - `imag = D * (A + B) + B * (C - D)`
- The formula is algebraically equivalent to complex multiply in infinite
  precision, but not bit-exact under Venus fixed-point shift and saturation.
- In RTL, the pre-add terms such as `A-B` are already kept wider for EW8, so the
  main error source is not an 8-bit pre-add truncation.
- The larger error source is that each multiply term is shifted/saturated before
  the post-add, instead of accumulating raw products and quantizing once.
- `vd1/vd2` are not pure outputs for `VCMXMUL`; their old values participate as
  inputs, so the intrinsic operand mapping must be handled carefully.

## Files Changed

- /home/shenyihao/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c
- /home/shenyihao/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c.cmxmul_logic_correct_20260617

## User Notes

Default OFDM behavior should stay functionally correct. RTL is not being changed
in this session. Keep the corrected `cmxmul` mapping as an experimental backup,
not as the default VEMU implementation.

## AI Conversation Summary

The session first located `VCMXMUL` in the Venus RTL and compared it with the
VEMU implementation. It then tried a `cmxmul` OFDM replacement, measured large
final-output errors, traced one large error back to operand mapping, corrected
the mapping, and finally showed that even corrected `cmxmul` errors can be
amplified through the OFDM/FFT chain. The final decision was to restore the
explicit multiply path and preserve the corrected `cmxmul` version as an
experiment.

## Things Not To Record

Do not record the initial broken operand mapping as a recommended workflow. Do
not describe all intermediate `cmxmul` attempts as successful replacements.

