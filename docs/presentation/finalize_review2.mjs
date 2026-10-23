import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const ROOT = process.env.RECYCLEGUARD_WORKSPACE ?? process.cwd();
const SKILL = process.env.PRESENTATIONS_SKILL_DIR ?? '/Users/rva/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const BUILD = path.join(ROOT, 'tmp/presentations/review2');
const PYTHON = process.env.RUNTIME_PYTHON ?? '/Users/rva/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const FINAL = process.env.PRESENTATION_OUTPUT_PATH ?? path.join(ROOT, 'output/pptx/ReCycleGuard_Review_2.pptx');
const {finalizePresentation} = await import(pathToFileURL(path.join(SKILL, 'container_tools/artifact_tool_utils.mjs')).href);
const tableSlides = [5,6,7,9,10,11,12,13,14];
const result = await finalizePresentation({
  workspaceDir:ROOT,
  candidatePath:path.join(BUILD,'draft.pptx'),
  finalPath:FINAL,
  pythonExecutable:PYTHON,
  integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),
  layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),
  layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...tableSlides.flatMap(n=>['--require-native-table-slide',String(n)])],
  requiredNativeTableOwnerSlides:tableSlides,
  fontPolicy:JSON.parse(await fs.readFile(path.join(BUILD,'font-policy.json'),'utf8')),
  verifyArtifactToolImport:true,
  receiptPath:path.join(BUILD,`${path.basename(FINAL)}.validation.json`),
});
console.log(JSON.stringify(result,null,2));
