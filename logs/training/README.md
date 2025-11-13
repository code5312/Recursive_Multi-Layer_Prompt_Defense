Training Log Directory
=======================

`logs/training/` is meant to store verbose training traces (checkpoints, scalar
metrics, and debug JSONL files). The repository keeps the folder but omits the
heavy artifacts to prevent bloating the Git history.

Recommended usage:

- Add an entry to `.gitignore` (or a local exclude) for any large files you
  place here, especially checkpoint binaries.
- If you export logs to an external experiment tracker, you can leave this
  directory empty.

