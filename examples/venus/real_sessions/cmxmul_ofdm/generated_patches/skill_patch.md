# Skill Patch

Status: reviewed-example
Session: cmxmul_ofdm
Confidence: high

## Skill Name

Evaluate Fixed-Point CMXMUL Replacement In Venus OFDM

## When To Use

- Use this when replacing an explicit fixed-point complex multiply sequence with
  a fused Venus instruction.
- Use this especially inside OFDM, FFT, or other multi-stage signal-processing
  chains where local fixed-point errors can propagate.

## When Not To Use

- Do not use all-`cmxmul` as the default OFDM path for `nrPDSCHDag1_v2`.
- Do not accept a local first-stage match unless final task outputs are also
  compared.
- Do not treat algebraic equivalence as fixed-point numerical equivalence.

## Environment Requirements

- Know the target DAG and Venus row/lane settings.
- Have a baseline output produced by the original explicit instruction sequence.
- Preserve a backup of the experimental instruction-mapping version.

## Steps

- Confirm the RTL and VEMU instruction formula and operand mapping.
- Generate DSL output and inspect assembly for the expected instruction, such as `vns_cmxmul.ivv`.
- Run the full Emulator DAG, not only a local instruction test.
- Compare final task outputs as signed int8 when the dumps are byte-valued.
- Compute mismatch count, MAE, RMSE, signal RMS, relative RMSE, and simple swap/sign checks.
- If errors are large, inspect the first fused multiply point and verify operand order against intermediate dumps.
- Keep the explicit fixed-point sequence as the default if final-output error is not acceptable.

## Probes

- name: dsl_build
  command: `make -C /home/shenyihao/Project/MultiVemu/VEMU/dsl all`
  success: DSL generation and resource check pass.
- name: emulator_build
  command: `make -C /home/shenyihao/Project/MultiVemu/VEMU Emulator`
  success: Emulator builds without new errors.
- name: emulator_run
  command: `Debug/Emulator test.hex -w -j../dsl/final_output/dag1.json -b../dsl/bin/dag1.bin`
  success: Full DAG exits with code 0.
- name: final_vstore_compare
  command: Compare final VSTORE dumps as signed int8.
  success: Mismatch, MAE, and RMSE meet the project threshold.
- name: assembly_marker
  command: Search generated assembly for `vns_cmxmul.ivv`.
  success: Marker presence matches the intended implementation path.

## Common Failures

- Treating algebraic equivalence as fixed-point equivalence.
- Ignoring that old `vd1/vd2` values are inputs to `VCMXMUL`.
- Comparing only the first local multiply and missing later OFDM/FFT error amplification.
- Comparing byte dumps as unsigned values instead of signed int8.

## Verification

- `make -C /home/shenyihao/Project/MultiVemu/VEMU/dsl all`
- `make -C /home/shenyihao/Project/MultiVemu/VEMU Emulator`
- `Debug/Emulator test.hex -w -j../dsl/final_output/dag1.json -b../dsl/bin/dag1.bin`
- Confirm default generated assembly has no `vns_cmxmul` when the explicit path is required.
- Confirm final VSTORE mismatch, MAE, and RMSE against baseline.

## Evidence

- All-`cmxmul` OFDM relative RMSE was about 140%.
- Stage-0-only `cmxmul` relative RMSE was about 87%.
- Restored explicit OFDM path matched baseline final stores exactly.

## Confidence

High for the recommendation to keep explicit OFDM fixed-point multiply as the
default. Medium for future RTL design conclusions because RTL changes were not
implemented in this session.

## Related Files

- `/home/shenyihao/Project/MultiVemu/VEMU/source/venus_ext.cpp`
- `/home/shenyihao/Project/RTL/venus_soc421/hardware/venus_extension/venus_cau.sv`
- `/home/shenyihao/Project/RTL/venus_soc421/hardware/venus_extension/venus_multiply.sv`
- `/home/shenyihao/Project/RTL/venus_soc421/hardware/venus_extension/venus_addsub.sv`
- `/home/shenyihao/Project/MultiVemu/VEMU/5g_lite/tasks/nrPDSCHDag1_v2/Task_nrOFDMDemodulation.c`

## Related Wiki Pages

- `docs/wiki/development_notes.md`
- `docs/wiki/known_issues.md`
- `docs/wiki/venus_architecture.md`

## Evolution Log

- v0.1: all-`cmxmul` experiment rejected after final-output error comparison.
- v0.2: operand mapping corrected, but final OFDM error remained too large.
- v0.3: default path restored to explicit `vmul/vssub/vsadd`; corrected
  `cmxmul` mapping kept only as an experimental backup.
