# Review 2 presentation

The current [PowerPoint](../../output/pptx/ReCycleGuard_Review_2_Visual.pptx) contains **13 main slides and two hidden backup slides**. It covers the architecture/data flow, adaptive agent graph, selected patterns, worked allocation example, data sources, retrieval/memory, tools, governance and evaluation. Main delivery ends on slide 13. The operating-metrics and source slides remain available for questions.

The [8–10 minute speech](PRESENTATION_SPEECH.md) includes timing, emphasis/pointing cues, a shorter-delivery strategy and likely questions. Its main script has about 1,200 words and a planned 9:20 delivery. The same speech appears in PowerPoint Presenter Notes alongside technical notes and source links. Speak most slowly through architecture, adaptation, the example and evaluation. Mention scope, detailed safeguards and ownership briefly.

Diagrams, the allocation chart, tables and text are native editable objects. Only the conceptual cover illustration is raster artwork. Its [prompt/provenance](assets/README.md) is retained with the project asset. Application behavior and experimental results remain proposed or unmeasured.

The [original deck](../../output/pptx/ReCycleGuard_Review_2.pptx) remains available for comparison.

## Rebuild in Codex

Scripts use bundled `@oai/artifact-tool`, without a project package installation. Obtain the bundled Node.js, Node modules, Python and Presentations skill paths from Codex's workspace dependency tool and export `RUNTIME_NODE`, `RUNTIME_NODE_MODULES`, `RUNTIME_PYTHON` and `PRESENTATIONS_SKILL_DIR`. Run from the repository root:

```sh
mkdir -p tmp/presentations/review2-visual output/pptx
ln -sfn "$RUNTIME_NODE_MODULES" tmp/presentations/review2-visual/node_modules
cp docs/presentation/build_review2_visual.mjs tmp/presentations/review2-visual/build_review2_visual.mjs
"$RUNTIME_NODE" tmp/presentations/review2-visual/build_review2_visual.mjs
PRESENTATION_OUTPUT_PATH="$PWD/output/pptx/REVIEW_2_VISUAL_NEXT.pptx" \
  "$RUNTIME_NODE" docs/presentation/finalize_review2_visual.mjs
```

The builder reads the original deck's technical notes, the project cover asset and `speech_review2.json`, which supplies the timed Presenter Notes. If revising the speech, keep the standalone Markdown script aligned with that JSON. The builder writes its draft/previews under `tmp/presentations/review2-visual`. The finalizer validates package integrity, geometry, fonts, editable tables/chart data, embedded literal-data workbook and artifact-tool import before creating the output. The chart's workbook contains only the explicit synthetic-example quantities, not experimental results.

Use a fresh output filename for each revision, then inspect every rendered slide. Validation reports and intermediate files stay under `tmp/`. Original authoring scripts `build_review2.mjs` and `finalize_review2.mjs` remain for the first deck.
