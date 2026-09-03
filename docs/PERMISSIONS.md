# Capability policy (defaults)

ALLOW: read files, web/search APIs, scientific databases, registered
scientific models, run tests.
ASK: write/edit many files, install packages, expensive docking, long GPU
tasks, environment mutation.
ALWAYS ASK: git push, delete important files, external publication/upload,
wet-lab execution instructions, system-wide installation.
Subagents inherit ceilings and never exceed the parent. (Pi `tool_call` gates
hook = slice L.)
