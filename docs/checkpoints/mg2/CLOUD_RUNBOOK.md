# MG2 cloud runbook: run the experiment on a free T4 (Kaggle or Colab)

Use this while the PC is unavailable. Follow the parts in order. Every step says what you should
see and what to do if you do not. You need a browser, this laptop (with `benchmarks/hidden`) and
your own Kaggle and Google accounts. Nothing else.

**Status.** The host-mode queue, the persist copy, the scoring helper and the local export were
run on the laptop against the fixture model (not evidence). The bootstrap has not yet run on Kaggle
or Colab, so Part 2 is where a surprise can still happen. If a step does not behave as written,
stop, copy the cell's output into the log, and do not improvise.

## How this differs from the PC runbook

| | PC (`RUNBOOK.md`) | Cloud (this file) |
| --- | --- | --- |
| GPU | 24 GB, 6 slots | T4 16 GB, **3 slots** for every cloud shard |
| Trial isolation | one Docker container per trial | `--isolation-disclosed` (cooperative): one process per trial on the notebook VM |
| Evaluator answers | in a Docker volume | **never uploaded**; scoring runs on the laptop |
| Queue | `run_queue.py` | `run_queue.py --host`: same queue code, HTTP health check, refuses final/held-out jobs unless `--final-disclosed` (Part 5) |
| llama.cpp | image `LLAMA_IMAGE_DIGEST` | the same image's binary, extracted; a source build of `b12033` only if that fails, recorded in `llama-provenance.txt` |
| Queue names | `mg2-baseline`, `mg2-agents` | `mg2-t4-core`, `mg2-t4-ablated-rest`, `mg2-t4-rules-on-rest`, `mg2-t4-heldout` |

The T4 runs are a **separate series**. Compare arms only within it. Never pool them with PC runs.
The held-out run was first planned for the PC only (RUNBOOK.md Part 9). On 2026-11-11 it moved here,
once, as Part 5 (log entry 15, PREREGISTRATION deviations).

## What you will run

| Queue file (in `docs/checkpoints/mg2/queue/t4/`) | Sessions | Trials | Where | Order |
| --- | --- | --- | --- | --- |
| `queue-t4-core.json` | 4: ablated and rules-on, v7 ADAPTIVE and Retriever+Classifier v1 | 224 | Kaggle | first |
| `queue-t4-rules-on-rest.json` | 7: the other rules-on sessions | 448 | Colab | at the same time as core |
| `queue-t4-ablated-rest.json` | 7: the other ablated sessions | 336 | Kaggle | after core |
| `queue-t4-heldout.json` | 2: held-out, rules on (Part 5) | 240 | Kaggle | once, last |

The three files hold exactly the 18 sessions of the two PC queues, with the same protocols and
prompts. Every session has its own SC controls. Core alone answers the main question: does the
Retriever+Classifier beat v7 and SC in the ablated arena, without a regression with the rules on?

Rough time: on the PC a v7 trial took about 47 s. Expect 2 to 4 times that on a T4. Core should take
3 to 6 hours; the status ETA gives the real figure after the first hour.

## Part 0. Accounts (once)

1. **Kaggle.** Sign in and verify your phone number (*Settings → Phone verification*), otherwise
   the notebook has no internet. *Settings* also shows the GPU quota left this week (about 30 h,
   reset every Saturday 00:00 UTC).
2. **Colab.** Sign in with your own Google account. Open *Settings → Subscription*. If it lists
   compute units (the Jio Google AI Pro plan may or may not include them), still choose a **T4** so
   every shard runs on the same hardware.
3. Use **one account per platform**. Colab's FAQ disallows using several accounts to get around
   its limits, and Kaggle allows one account per person.

## Part 1. On the laptop, before any cloud run

1. The branch `codex/mg2-cloud-t4` must be pushed: the notebook clones it from GitHub. The notebook
   prints `git rev-parse HEAD`; write it down, as every shard must show the same revision.
2. Do not edit any file under `docs/checkpoints/mg2/queue/t4/` once a shard has started.

## Part 2. Kaggle: the core queue

1. *Create → New Notebook*. *File → Import Notebook* → GitHub → `R-V-Abhishek/ReCycleGuard`, branch
   `codex/mg2-cloud-t4`, file `deploy/cloud/mg2_t4.ipynb` (or download that file from GitHub
   and use *Import Notebook → File*).
2. Right panel, *Session options*: **Accelerator: GPU T4 x2** (the notebook uses GPU 0 only, like
   a Colab T4; never P100), **Internet: on**.
3. In the first code cell, keep `QUEUE = "docs/checkpoints/mg2/queue/t4/queue-t4-core.json"` and
   `HOURS = 10.5`.
4. *Save Version* → **Save & Run All (Commit)**. This runs without the browser and stops at 12 h.
   Close the tab whenever you like.
5. To watch it: open the notebook → *Versions* → the running version → *Logs*. Expect, in order:
   - `platform: kaggle`, then the revision.
   - `== 1/7 GPU` showing `Tesla T4`.
   - `== 3/7 llama-server b12033`, a version line containing `12033`, and a `CUDA0` device.
   - `== 4/7` (about 10 GB download, a few minutes).
   - `== 6/7 probe and VRAM` passing.
   - `queue mg2-t4-core: 4 sessions, 224 trials, 3 slots`.
   - Every 5 minutes, a status block (`Trials: n of 224 ... ETA ...`).

   Write the ETA into the log after the first hour.
6. When it ends (finished, or stopped by `HOURS`), the version's *Output* holds `work/`.
7. **If core did not finish**, or to start `queue-t4-ablated-rest`: open the notebook → *Add Input*
   → *Notebook Output Files* → this notebook's latest version. Set `QUEUE` (the same file to
   resume, or the next one), then *Save & Run All* again. Cell 2 restores `/work` from that input.
   Nothing finished runs twice. When moving on to the next queue, keep the previous output attached
   so its records stay in the new output too.

## Part 3. Colab: the rules-on queue, at the same time

1. colab.research.google.com → *File → Open notebook → GitHub* → `R-V-Abhishek/ReCycleGuard`,
   branch `codex/mg2-cloud-t4` → `deploy/cloud/mg2_t4.ipynb`.
2. *Runtime → Change runtime type* → **T4 GPU**.
3. Set `QUEUE = "docs/checkpoints/mg2/queue/t4/queue-t4-rules-on-rest.json"`.
4. *Runtime → Run all*, then allow the Google Drive access it asks for. The records go to
   `MyDrive/recycleguard-work` every 10 minutes.
5. **Keep the tab open.** The free tier disconnects an idle or long session (about 12 h at most,
   often less). If it disconnects, *Runtime → Run all* again with the same `QUEUE`: it restores from
   Drive and continues. Trials that were running at the cut are recorded as `INFRA_FAILED`; list
   them in the report.
6. Expect the same log as Part 2, step 5, with `platform: colab` and
   `queue mg2-t4-rules-on-rest: 7 sessions, 448 trials, 3 slots`.

## Part 4. Bring the results back and score them on the laptop

1. Download the work folder into a new, empty folder, for example `~/mg2-t4/kaggle-1/work`:
   - From Kaggle: the version's *Output* → download (one zip). The output is about 65,000 small
     files; `kaggle kernels output` fetches them one at a time and takes hours.
   - From Colab: `MyDrive/recycleguard-work/work` in Google Drive → download. The one Colab run
     (2026-11-10) left nothing in Drive: the copy loop died on rsync exit 24 (a vanished SQLite
     `-wal` file), fixed since in `persist.sh`. Check that the folder appears after the first 10
     minutes.
2. Score each queue, from the repository root (the oracle is only here):

   ```sh
   RECYCLEGUARD_WORK=~/mg2-t4/kaggle-1/work uv run scripts/cloud/score.py docs/checkpoints/mg2/queue/t4/queue-t4-core.json
   ```

   Expect `scored N sessions; compare.csv in .../work/mg2-t4-core`. The `-scores` and `-tables`
   folders that came back from the notebook were made without the oracle (all unscored); this
   command scores every whole session again and replaces them. Unfinished sessions are
   listed as `not whole, not scored`.
3. Export what may be committed, by the same rule as the PC, plus the machine record:

   ```sh
   RECYCLEGUARD_WORK=~/mg2-t4/kaggle-1/work sh scripts/docker/export-results.sh mg2-t4-core docs/checkpoints/mg2/runs/t4
   mkdir -p docs/checkpoints/mg2/runs/t4/mg2-t4-core/machine-kaggle-1
   command cp -f ~/mg2-t4/kaggle-1/work/_model/*.txt docs/checkpoints/mg2/runs/t4/mg2-t4-core/machine-kaggle-1/
   ```

4. Read `compare.csv` and the tables as in RUNBOOK.md Part 7. Add the next numbered entry to
   `EXPERIMENT_LOG.md`, with the label **T4, cooperative isolation, s3**. Commit only the exported
   files and the log. Bundles and `benchmarks/hidden` stay out of Git.

## Part 5. The held-out run (once)

The 24 sealed held-out dossiers run once, rules on: v7 FIXED and ADAPTIVE, the Classifier alone
(v3, descriptive), with V0 and SC. What runs and why is in log entry 15. The result stands whatever
it is; nothing is tuned after the freeze.

1. **Laptop: freeze.** Commit and push everything; `git status --short` must list no tracked change.
   Build one freeze per protocol from that commit, from the specs in `freeze-spec/`:

   ```sh
   mkdir -p benchmarks/heldout/freeze
   for name in heldout-baseline heldout-classifier-only; do
       PYTHONPATH=. uv run scripts/make_freeze.py docs/checkpoints/mg2/freeze-spec/$name.json \
           benchmarks/heldout/freeze/$name.json
       PYTHONPATH=. uv run scripts/verify_freeze.py benchmarks/heldout/freeze/$name.json --strict-commit
   done
   ```

   Each freeze pins the commit, the protocol, prompt and queue files, and `benchmarks/heldout/visible`
   as a tree digest, with `held_out_visible_root` set to that checkout-relative path. The folder
   `benchmarks/heldout/` is gitignored, so the freezes do not dirty the tree. Record both freeze
   digests in `HELDOUT_APPROVAL.md`.
2. **Laptop: private dataset.** Upload `benchmarks/heldout/` (only `visible/` and `freeze/`; never
   `benchmarks/hidden`) as the private Kaggle dataset `recycleguard-heldout`, then confirm it is
   private (`kaggle datasets metadata`, `isPrivate: true`). Do not share it.
3. **Kaggle.** Import the notebook as in Part 2 and keep the notebook private. *Add Input* →
   *Your Datasets* → `recycleguard-heldout`. Do **not** attach an earlier notebook output (this is a
   fresh queue). In the first cell set
   `QUEUE = "docs/checkpoints/mg2/queue/t4/queue-t4-heldout.json"` and `FINAL = True`, then
   *Save & Run All (Commit)*.
4. **Expect** in the log, beyond Part 2's lines: `git checkout --detach <freeze commit>`, two
   `verify_freeze.py` outputs with `"ok": true`, then
   `queue mg2-t4-heldout: 2 sessions, 240 trials, 3 slots`. If a freeze does not verify, the cell
   stops before any trial; do not edit the freeze, find out why.
5. **Laptop: score and export** as in Part 4, with `queue-t4-heldout.json` and the name
   `mg2-t4-heldout`. `score.py` scores the final sessions against `benchmarks/heldout/visible`; the
   export holds ledgers, results and tables, never the dossiers. Write the next log entry.

The notebook's output holds trial folders with copies of the held-out dossiers, so keep the notebook
private, like the dataset.

## Something went wrong

| What you see | Cause | What to do |
| --- | --- | --- |
| `STOP: no NVIDIA GPU` | no GPU runtime | Kaggle: Accelerator T4. Colab: runtime type T4 |
| `STOP: not a T4` | a P100 or another GPU was assigned | do not run a T4 shard on it; try again later, or on the other platform |
| `git clone` or `curl` fails | Kaggle internet is off or the phone is not verified | Part 0, step 1 |
| `STOP: the image has no ld-linux` or `sees no CUDA device` | the extracted image binary does not run here | run `!rm -rf /opt/llama`, set `os.environ["LLAMA_FROM"] = "source"` in the first cell, run all again (adds about 15 min). Record it: `llama-provenance.txt` then says `source` |
| `llama-server is not build b12033` | wrong binary | as above |
| `server not healthy after 15 minutes` | out of memory or a bad binary | read `/work/_model/server.log` (`!tail -50 /work/_model/server.log`) |
| `only N MiB free with 3 slots` | the T4 has less free memory than expected | **only before any shard has started**: set `"slots": 2` in all three t4 queue files, commit, push, add a deviation row, rerun. Never change it once a shard has run |
| `the model server runs with ..., the sweep needs ...` | the server started with another slot count | rerun cell 3 |
| `this queue name was used with another model or slot count` | `slots` changed after a shard began | restore the value |
| `--host runs final or held-out jobs only with --final-disclosed` | a final job in a development queue, or Part 5 run without `FINAL = True` | development: remove it. Held-out: Part 5 |
| A session shows `FAILED` | 3 attempts used | read `/work/<queue>/<job>-<prompt>.log`; report it; do not rerun it under the same name |
| `score.py`: `no evaluator data` | run on a machine without `benchmarks/hidden` | score on the laptop |

## Known limits

- Cooperative isolation: a trial process could in principle read other files on the VM. Nothing
  there holds evaluator answers or held-out dossiers, but the isolation is weaker than one container
  per trial. Report it as such.
- Throughput, VRAM headroom at 3 slots and the extracted binary are unmeasured until the first
  Kaggle run.
- The time limits were set on the PC: 180 s per model call and 1200 s per trial. A T4 serving 3
  slots is slower. In the first hour, check the ledgers for `INFRA_FAILED` with `child exit` or
  calls that end in timeouts. If they are common, KILL the queue, write down what you saw and decide
  before going on. Do not change the limits silently.
- Kaggle's quota and free T4s on Colab are not guaranteed. If only core finishes, that is the
  result to report, alongside a note of what did not run.
- The fixture model only answers v7-shaped prompts, so the laptop dry run could not exercise the
  Retriever+Classifier arm beyond the harness: those trials ended in `PROVIDER_FAILURE` there, as
  expected for the fixture.
