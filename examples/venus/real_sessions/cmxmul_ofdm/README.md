# Venus Case Study: CMXMUL vs OFDM Bit-Exact Multiply

This is the first real VibeWiki demo session.

It captures an AI-assisted debugging session about the Venus `VCMXMUL`
instruction, the RTL/VEMU model, and why replacing an OFDM fixed-point complex
multiply chain with the fused `cmxmul` instruction caused large numerical
errors.

## Files

- `raw_session.md`: original exported conversation evidence
- `session.md`: normalized VibeWiki session record
- `diff.patch`: compact illustrative patch summary
- `generated_patches/`: reviewed memory patches extracted from the session

## Key Lesson

`VCMXMUL` is RTL/VEMU-consistent, but it is not a bit-exact replacement for the
explicit `vmul/vssub/vsadd` OFDM path. The fused Gauss-style formula changes
fixed-point quantization and saturation points. In a multi-stage OFDM/FFT chain,
small early errors can be amplified into large final-output error.

The safe default is to keep the explicit multiply path for OFDM and preserve the
logic-correct `cmxmul` version as an experiment.

