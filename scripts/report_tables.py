"""Write the report's result tables from the committed run tables, so no number is typed by hand.

    uv run scripts/report_tables.py        # writes docs/report/generated/*.tex and *.csv

MG1 rows come from ``docs/checkpoints/mg1/runs/pc/<run>-tables``; MG2 rows from each T4 queue's
``compare.csv``. The held-out table is written only once ``runs/t4/mg2-t4-heldout`` exists.
The two series are never pooled.
"""

import csv
import hashlib
import json
import textwrap
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
MG1 = REPOSITORY / "docs/checkpoints/mg1/runs/pc"
T4 = REPOSITORY / "docs/checkpoints/mg2/runs/t4"
OUT = REPOSITORY / "docs/report/generated"
PROMPTS = [
    REPOSITORY / "docs/checkpoints/mg1/prompts/u01_non_thinking_v7.json",
    REPOSITORY / "docs/checkpoints/mg2/prompts/mg2_agents_v1.json",
]

# (run, data, what changed), in the order of EXPERIMENT_LOG.md entries 1 to 7.
MG1_RUNS = [
    ("sweep-v11-u01_non_thinking_v7", "tuning-16", "v7 prompt, before the engine fixes"),
    ("sweep-v12-u01_non_thinking_v7", "tuning-16", "v7 prompt, before the engine fixes"),
    ("sweep-v13-u01_non_thinking_v7", "tuning-16", "v7 prompt, before the engine fixes"),
    ("tuning16-v7-det1", "tuning-16", "deterministic checks and contradiction gate"),
    ("tuning16-v7-det2", "tuning-16", "\\texttt{e8b5} fix"),
    ("checking8-v7", "checking-8", "first look at checking-8"),
    ("tuning16-v7-pl1", "tuning-16", "page loss reported as F15"),
    ("checking8-v7-pl1", "checking-8", "page loss reported as F15"),
    ("tuning16-v7-abl1", "ablated", "every deterministic family off"),
    ("tuning16-think-abl1", "ablated", "thinking prompt, families off"),
    ("tuning16-think-pl1", "tuning-16", "thinking prompt, families on"),
]
VARIANTS = {"FIXED_RETRIEVAL": "V1 FIXED", "ADAPTIVE": "V2 ADAPTIVE", "SC": "SC", "V0": "V0"}
# Queue job id -> arm name (PREREGISTRATION.md) and the session's data.
JOBS = {
    "baseline-fixed": "S1 v7 FIXED",
    "baseline-adaptive": "S1 v7 ADAPTIVE",
    "classifier": "M2 Retriever + Classifier",
    "classifier-only": "M2-nr Classifier alone",
    "lookup": "M1 Retriever + lookup",
}
ARM_ORDER = list(JOBS.values())


def rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def ci(row):
    return f"{float(row['ci95_low']):.2f}--{float(row['ci95_high']):.2f}"


def table(caption, label, columns, body, note=None, fit=False):
    """A booktabs table; ``fit`` scales the tabular down to the text width."""
    lines = [
        "\\begin{table}[htbp]",
        "\\centering",
        f"\\caption{{{caption}}}",
        f"\\label{{{label}}}",
        "\\small",
        *(["\\resizebox{\\linewidth}{!}{%"] if fit else []),
        f"\\begin{{tabular}}{{@{{}}{columns}@{{}}}}",
        "\\toprule",
        *body,
        "\\bottomrule",
        "\\end{tabular}" + ("}" if fit else ""),
    ]
    if note:
        lines += ["\\par\\smallskip", f"\\parbox{{\\linewidth}}{{\\footnotesize {note}}}"]
    lines.append("\\end{table}")
    return "\n".join(lines) + "\n"


def mg1():
    body = [
        "\\textbf{Run} & \\textbf{Data} & \\textbf{Change} & \\textbf{Arm} & "
        "\\textbf{Cases} & \\textbf{TP / FP} \\\\",
        "\\midrule",
    ]
    for run, data, change in MG1_RUNS:
        tables = MG1 / f"{run}-tables"
        micro = {row["variant"]: row for row in rows(tables / "t3_findings_micro.csv")}
        first = True
        for row in rows(tables / "t1_primary_success.csv"):
            found = micro[row["variant"]]
            name = run.replace("-u01_non_thinking_v7", "").replace("_", "\\_")
            body.append(
                f"{name if first else ''} & {data if first else ''} & "
                f"{change if first else ''} & {VARIANTS[row['variant']]} & "
                f"{row['successes']} of {row['scored']} & "
                f"{found['true_positives']} / {found['false_positives']} \\\\"
            )
            first = False
        body.append("\\addlinespace")
    body.pop()
    return table(
        "MG1 on the RTX PC (one Docker container per trial): primary success and findings",
        "tab:mg1",
        "l l >{\\raggedright\\arraybackslash}p{3.6cm} l r r",
        body,
        "Cases: trials meeting the primary success rule. TP / FP: true and false positive "
        "findings against the oracle. Source: \\texttt{docs/checkpoints/mg1/runs/pc/<run>-tables}.",
    )


def arm_of(prompt_key):
    job, prompt = prompt_key.split(":")
    for prefix in ("ablated-", "rules-on-", "heldout-"):
        job = job.removeprefix(prefix)
    return JOBS[job], prompt.replace("mg2_agents_", "").replace("u01_non_thinking_", "")


def t4_rows(arena):
    found, controls = [], {}
    for queue in ("mg2-t4-core", "mg2-t4-ablated-rest", "mg2-t4-rules-on-rest"):
        for row in rows(T4 / queue / "compare.csv"):
            if not row["prompt"].startswith(arena):
                continue
            if row["variant"] in {"SC", "V0"}:
                controls.setdefault(row["variant"], []).append(row)
                continue
            arm, prompt = arm_of(row["prompt"])
            found.append((ARM_ORDER.index(arm), prompt, arm, row))
    return sorted(found, key=lambda item: item[:2]), controls


def mg2(arena, title, label):
    found, controls = t4_rows(arena)
    body = [
        "\\textbf{Arm} & \\textbf{Prompt} & \\textbf{Cases} & \\textbf{95\\% CI} & "
        "\\textbf{TP / FP} & \\textbf{Prop.\\ / acc.} & \\textbf{Calls} & \\textbf{s} \\\\",
        "\\midrule",
    ]
    for _, prompt, arm, row in found:
        body.append(
            f"{arm} & {prompt} & {row['successes']} of {row['scored']} & {ci(row)} & "
            f"{row['true_positives']} / {row['false_positives']} & "
            f"{row['proposals_made']} / {row['proposals_accepted']} & "
            f"{float(row['mean_model_calls']):.1f} & {float(row['mean_wall_seconds']):.0f} \\\\"
        )
    body.append("\\midrule")
    for variant, group in sorted(controls.items()):
        outcomes = sorted({(r["successes"], r["scored"], r["false_positives"]) for r in group})
        text = "; ".join(f"{s} of {n}, FP {fp}" for s, n, fp in outcomes)
        sessions = f"{variant} (in each of {len(group)} sessions)"
        body.append(f"{sessions} & -- & \\multicolumn{{6}}{{l}}{{{text}}} \\\\")
    return table(
        title,
        label,
        "l l r r r r r r",
        body,
        "T4 series, cooperative isolation, 3 slots, 2 repeats on tuning-16. Prop.\\ / acc.: model "
        "finding proposals made and accepted by the gate. Calls and s: mean model calls and wall "
        "seconds per trial. Source: \\texttt{docs/checkpoints/mg2/runs/t4/*/compare.csv}.",
    )


def plot_data():
    """Accepted false positives with the rules on, and true positives with them off, per arm."""
    on, _ = t4_rows("rules-on")
    off, _ = t4_rows("ablated")
    ablated = {(arm, prompt): row for _, prompt, arm, row in off}
    lines = ["label,rules_on_fp,ablated_tp"]
    for _, prompt, arm, row in on:
        short = arm.split(" ")[0] + (" " + arm.split(" ")[2] if arm.startswith("S1") else "")
        partner = ablated.get((arm, prompt))
        lines.append(
            f"{short} {prompt},{row['false_positives']},"
            f"{partner['true_positives'] if partner else 'nan'}"
        )
    return "\n".join(lines) + "\n"


def held_out():
    queue = T4 / "mg2-t4-heldout" / "compare.csv"
    if not queue.is_file():
        return None
    body = [
        "\\textbf{Arm} & \\textbf{Prompt} & \\textbf{Cases} & \\textbf{95\\% CI} & "
        "\\textbf{TP / FP / FN} & \\textbf{Prop.\\ / acc.} & \\textbf{Calls} & \\textbf{s} \\\\",
        "\\midrule",
    ]
    order = {"FIXED_RETRIEVAL": 0, "ADAPTIVE": 1}
    sessions = {"heldout-baseline": "S1", "heldout-classifier-only": "M2-nr"}
    for row in sorted(rows(queue), key=lambda r: (r["prompt"], order.get(r["variant"], 2))):
        job, prompt = row["prompt"].split(":")
        if row["variant"] in {"SC", "V0"}:
            arm, prompt = f"{row['variant']} ({sessions[job]} session)", "--"
        elif row["variant"] in VARIANTS:
            arm = f"S1 {VARIANTS[row['variant']]}"
        else:
            arm, _ = arm_of(row["prompt"])
        body.append(
            f"{arm} & {prompt.replace('mg2_agents_', '').replace('u01_non_thinking_', '')} & "
            f"{row['successes']} of {row['scored']} & {ci(row)} & "
            f"{row['true_positives']} / {row['false_positives']} / {row['false_negatives']} & "
            f"{row['proposals_made']} / {row['proposals_accepted']} & "
            f"{float(row['mean_model_calls']):.1f} & {float(row['mean_wall_seconds']):.0f} \\\\"
        )
    return table(
        "Held-out run (24 sealed cases, rules on, 2 repeats, T4)",
        "tab:heldout",
        "l l r r r r r r",
        body,
        "Run once after the freeze (log entry 15). M2-nr is descriptive: it failed the development "
        "gate. Source: \\texttt{docs/checkpoints/mg2/runs/t4/mg2-t4-heldout/compare.csv}.",
        fit=True,
    )


def prompt_lines(value, name=""):
    """Every text field of a prompt file, wrapped for print; the words are unchanged."""
    if isinstance(value, dict):
        return [line for key, item in value.items() for line in prompt_lines(item, f"{name}{key}.")]
    text = json.dumps(value, ensure_ascii=True) if not isinstance(value, str) else value
    return [f"[{name.rstrip('.')}]", *textwrap.wrap(text, 96, break_on_hyphens=False), ""]


def prompts():
    """The prompts that produced the reported results, verbatim, each with its file digest."""
    parts = []
    for path in PROMPTS:
        raw = path.read_bytes()
        name = path.stem.replace("_", "\\_")
        where = path.relative_to(REPOSITORY).as_posix().replace("_", "\\_")
        parts += [
            f"\\section{{\\texttt{{{name}}}}}",
            f"\\noindent File \\texttt{{{where}}}, "
            f"SHA-256 \\texttt{{{hashlib.sha256(raw).hexdigest()[:16]}\\ldots}}",
            "\\begin{lstlisting}[language={},numbers=none,basicstyle=\\ttfamily\\scriptsize]",
            *prompt_lines(json.loads(raw)),
            "\\end{lstlisting}",
        ]
    return "\n".join(parts) + "\n"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {
        "mg1.tex": mg1(),
        "mg2-ablated.tex": mg2(
            "ablated", "MG2 ablated arena (every deterministic family off)", "tab:mg2-ablated"
        ),
        "mg2-rules-on.tex": mg2(
            "rules-on", "MG2 rules-on arena (the no-regression gate)", "tab:mg2-rules-on"
        ),
        "mg2-plot.csv": plot_data(),
        "prompts.tex": prompts(),
    }
    heldout = held_out()
    if heldout is not None:
        outputs["heldout.tex"] = heldout
    for name, text in outputs.items():
        (OUT / name).write_text(text, "utf-8")
        print(f"wrote {OUT.relative_to(REPOSITORY) / name}")


if __name__ == "__main__":
    main()
