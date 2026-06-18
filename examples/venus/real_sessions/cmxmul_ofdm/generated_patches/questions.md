# Clarifying Questions

Status: reviewed-example
Session: cmxmul_ofdm

## Questions

- Should the `cmxmul_logic_correct_20260617` backup be promoted into a regression
  fixture, or should it remain only as a developer reference?
- What relative RMSE threshold should Venus use for approximate DSP replacements?
- Should future RTL work add a wide-accumulate `VCMXMUL` variant, or preserve the
  current instruction and rely on explicit sequences for high-accuracy 8-bit OFDM?

