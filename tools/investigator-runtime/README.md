# Restricted scripted investigator

Build the application wheel with `uv build --wheel`. Use
`recycleguard.isolated_runtime.prepare_build_context(repository, wheel, new_directory)`
to create a minimal build context, then `docker build -t recycleguard-isolated CONTEXT`.
It contains locked metadata and one wheel, never the repository/evaluator tree.

Run the actual installed investigation with dedicated directories:

```sh
uv run recycleguard isolated-investigation --image recycleguard-isolated \
  --visible-root VISIBLE_DIRECTORY --runtime-root RUNTIME_DIRECTORY \
  --user-id NONROOT_UID -- investigation start /visible/request.json
uv run recycleguard isolated-investigation --image recycleguard-isolated \
  --visible-root VISIBLE_DIRECTORY --runtime-root RUNTIME_DIRECTORY \
  --user-id NONROOT_UID -- investigation run RUN_ID
```

The runtime directory contains approved input snapshots and audit storage. Match
its writable owner with a nonzero container UID. On Colima use an existing shared
workspace path. New Linux indexes must be built inside that runtime; retain a
copied host index cache separately instead of overwriting its frozen bytes.

The launcher fixes mounts, nonroot identity, read-only root, network none,
capability drop, no-new-privileges and resource ceilings. It forwards no host
secrets. Actual OS probes must pass and be fsynced before dispatch. Image identity,
source pins and closed evidence must be retained with acceptance records.
This is a trusted Docker-host boundary for the explicit scripted command; it
is not automatic sandboxing of ordinary API runs or local MLX transport.
