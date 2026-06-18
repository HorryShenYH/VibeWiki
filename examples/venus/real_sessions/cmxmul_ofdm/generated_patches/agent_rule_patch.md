# Agent Rule Patch

Status: reviewed-example
Session: cmxmul_ofdm

## New Rules

- For Venus fixed-point DSP kernels, do not assume algebraically equivalent
  formulas are numerically equivalent.
- Before replacing explicit `vmul/vssub/vsadd` complex multiply with `VCMXMUL`,
  compare full task outputs, not only local instruction outputs.
- Verify `VCMXMUL` operand mapping through generated assembly and intermediate
  dumps because `vd1/vd2` old values participate as inputs.
- For OFDM/FFT chains, measure relative RMSE against signal RMS before accepting
  an approximate instruction replacement.

## Do Not Do

- Do not use all-`cmxmul` OFDM as the default path for `nrPDSCHDag1_v2`.
- Do not record the initial broken operand mapping as a valid implementation.
- Do not ignore final-output amplification when a local first-stage error looks small.

## Verification Required

- DSL build passes.
- Emulator build passes.
- Full DAG run passes.
- Final VSTORE outputs are compared against baseline as signed int8.
- Generated assembly is checked for intended instruction use.

