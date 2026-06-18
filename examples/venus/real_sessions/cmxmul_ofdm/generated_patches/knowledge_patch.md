# Knowledge Patch

Status: reviewed-example
Session: cmxmul_ofdm

## What Was Solved

The session clarified that Venus `VCMXMUL` RTL and VEMU agree on instruction
semantics, but `VCMXMUL` should not be used as the default replacement for the
OFDM fixed-point complex multiply sequence in `nrPDSCHDag1_v2`.

## Important Facts

- `VCMXMUL` uses `real = C*(A-B) + B*(C-D)` and `imag = D*(A+B) + B*(C-D)`.
- The formula is algebraically equivalent to complex multiply in infinite
  precision, but not bit-exact under fixed-point shift and saturation.
- The EW8 pre-add terms are already widened in RTL; the bigger issue is
  per-product shift/saturate before post-add.
- OFDM/FFT stages amplify early quantization differences, so a small local
  `cmxmul` error can become large final-output error.
- `vd1/vd2` old values are part of the `VCMXMUL` inputs; intrinsic mappings must
  be verified against generated assembly and dumps.

## Evidence

- Full all-`cmxmul` OFDM experiment had around 140% relative RMSE.
- A hybrid stage-0-only `cmxmul` version still had around 87% relative RMSE.
- The restored explicit path matched baseline final stores exactly:
  - mismatch 0 / 7488
  - MAE 0
  - RMSE 0
- DSL build, Emulator build, and full DAG run passed.

## Suggested Wiki Updates

Add this note to Venus known issues and simulation guidance:

`VCMXMUL` is correct for its RTL/VEMU instruction semantics, but it is not a
drop-in bit-exact replacement for explicit `vmul/vssub/vsadd` complex multiply
in long 8-bit OFDM/FFT fixed-point chains.

## Open Questions Before Merge

- Should the corrected `cmxmul` experimental backup become a formal test case?
- Should Venus add a future wide-accumulate complex multiply mode for 8-bit FFT workloads?

