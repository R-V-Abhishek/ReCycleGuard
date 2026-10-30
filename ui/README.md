# ReCycleGuard investigation UI

A local browser UI for the API in `src/recycleguard/api/`. It takes a synthetic dossier through readiness, investigation, the verified report and human review. All decisions and calculations stay in the backend.

**Status:** typecheck, unit tests and the production build pass on Windows. It has not yet been run against a real API or opened in a browser, so the checklist below is its first real test, and some fixes are likely.

Response types in `src/api/types.ts` are hand-written from the backend contracts, because `docs/api/openapi.json` declares empty response schemas. If the UI shows a wrong or missing field on the first run, check there first.

## Run

The API and model run on the Mac. The UI can run on the Mac or on another laptop on the same network.

1. Start the model server and the API, as described in `docs/api/README.md`. Add the UI's exact origin:

   ```sh
   uv run recycleguard serve --host 0.0.0.0 --port 8000 \
     --model-config .recycleguard/local-model.json \
     --cors-origin http://<ui-host>:5173
   ```

2. Start the UI. This needs Node 22 or later:

   ```sh
   cd ui
   npm ci
   npm run dev -- --host
   ```

3. Open `http://<ui-host>:5173`, then enter the API address (`http://<mac-address>:8000`) and the API token.

The token stays in page memory, so you re-enter it after a reload. The page then returns to the same dossier or run. Tokens and passwords travel unencrypted over plain HTTP, so use this only on a private network.

## Checks

```sh
npm run typecheck
npm test
npm run build
```

## First-run checklist (on the Mac)

**Main flow**

- [ ] Connect with the token.
- [ ] Select `case_001`, then prepare it. Counts and issues appear.
- [ ] Enroll a reviewer, then approve the foundation.
- [ ] Open an original file from the list. Try one PDF and one CSV or JSON.
- [ ] Start a `MODEL_BACKED` run. The timeline fills in live and the header shows the mode.
- [ ] Reload mid-run and re-enter the token. There are no missing or duplicated rows, and no second run starts.
- [ ] On a model call, compare the Sent, Prepared and Template layers. On a tool proposal, check the reason and arguments.
- [ ] Open the report and audit. Click through a finding's evidence and calculation links.
- [ ] Open the review packet and submit a decision. Workflow state and review outcome update.

**Failure cases**

- [ ] Wrong token: shows a 401 and offers to re-enter it.
- [ ] Malformed ZIP: shows the backend's error, and no dossier opens.
- [ ] Second run while one is active: shows the `409`.
- [ ] Wrong reviewer password: shows an error, and the password field is cleared.
- [ ] Stale digest: review a packet, then submit against it again from a second tab. It's rejected.
- [ ] Cancel during a run: shows "cancellation requested" until the state becomes `CANCELLED`.

**Cross-check**

- [ ] Compare the displayed values with `GET /runs/{id}/trace` and `GET /runs/{id}/report`.
