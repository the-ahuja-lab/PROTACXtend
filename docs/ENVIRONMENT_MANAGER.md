# Environment manager (slice L)

Policy: never silently mutate host env; prefer project-local/isolated env.
check_dependency(name) → install_dependency(name, environment) →
verify_dependency(name). Classify safe vs approval-required; explicit approval
for system mutation; log every install (installation_log.jsonl); verify
version/executable after install; never trust exit code alone. Files:
environment.lock, installation_log.jsonl, registered_capabilities.json.
