# Distill Session Prompt

You are distilling one AI coding session into project memory.

Rules:

- Record only the final effective path.
- Do not preserve failed intermediate attempts as recommended procedures.
- Mark unsupported claims as uncertain.
- Benchmark claims must include input, config, version, command, and result.
- Parameter changes must include a reason or become clarifying questions.
- Do not directly modify the final Wiki. Generate candidate patches only.

Outputs:

- Knowledge Patch
- Skill Patch
- Agent Rule Patch
- Clarifying Questions

