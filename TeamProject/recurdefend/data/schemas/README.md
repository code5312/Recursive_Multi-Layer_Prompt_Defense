# schemas/

- `sample.schema.json`: JSON Schema used to validate raw records before promotion
  to `data/processed/`. Update this when you add new fields to your dataset.

**Validation tips**
- Use `jsonschema` in Python to validate every record.
- Required fields: `id`, `prompt`, `attack_label`, `expected_action`.
- `attack_label` taxonomy:
  - `none`: Benign
  - `ipi`: Indirect Prompt Injection (instruction override / hidden intent)
  - `jailbreak`: Jailbreak & safety bypass phrasing
  - `target_deviation`: Attempts to skew objective / goal misalignment
  - `tool_call_manipulation`: Function-calling misuse (bad API name/args)
  - `other`: Anything else
