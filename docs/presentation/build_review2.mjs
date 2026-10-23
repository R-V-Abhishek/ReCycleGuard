import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile } from '@oai/artifact-tool';

// Run a copy of this file from a build directory linked to the bundled runtime.
const ROOT = process.env.RECYCLEGUARD_WORKSPACE ?? process.cwd();
const BUILD = path.join(ROOT, 'tmp/presentations/review2');
const SKILL = process.env.PRESENTATIONS_SKILL_DIR ?? '/Users/rva/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const { resolvePresentationFont } = await import(pathToFileURL(path.join(SKILL, 'container_tools/artifact_tool_utils.mjs')).href);
const FONT = resolvePresentationFont();
const C = { navy:'#23466B', ink:'#20252B', gray:'#606A75', light:'#F3F5F7', border:'#ADB8C4', white:'#FFFFFF', amber:'#8A5C12' };
const P = Presentation.create({ slideSize:{width:1280,height:720} });
let serial = 0;
const sources = {
  rules:'https://eprewaste.cpcb.gov.in/assets/PDF/e-waste_rules_2022.pdf',
  amendment:'https://eprewaste.cpcb.gov.in/assets/PDF/Amendment-Rules-2024.pdf',
  framework:'https://eprewaste.cpcb.gov.in/assets/PDF/Framework.pdf',
  faq:'https://eprewaste.cpcb.gov.in/assets/PDF/faqewaste.pdf',
  sqlite:'https://www.sqlite.org/fts5.html',
  graph:'https://docs.langchain.com/oss/python/langgraph/persistence',
};
function text(slide, value, x,y,w,h, size=26, opts={}) {
  const sh = slide.shapes.add({geometry:'textbox',name:opts.name ?? `text-${++serial}`,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  sh.text=value;
  sh.text.style={typeface:FONT,fontSize:size,color:opts.color??C.ink,bold:opts.bold??false,alignment:opts.align??'left',verticalAlignment:'top',autoFit:'none',wrap:'square',insets:0};
  return sh;
}
function rect(slide,x,y,w,h,fill=C.light,line=C.border,dashed=false) {
  return slide.shapes.add({geometry:'rect',name:`diagram-${++serial}`,position:{left:x,top:y,width:w,height:h},fill,line:{style:dashed?'dashed':'solid',fill:line,width:1.25}});
}
function node(slide, title, description, x,y,w,h, dark=false, size=23) {
  const sh=rect(slide,x,y,w,h,dark?C.navy:C.light,dark?C.navy:C.border);
  text(slide,title,x+14,y+10,w-28,31,size,{bold:true,color:dark?C.white:C.navy});
  if(description) text(slide,description,x+14,y+44,w-28,h-48,size-2,{color:dark?C.white:C.ink});
  return sh;
}
function arrow(slide,a,b,from='right',to='left',bidir=false,dashed=false) {
  return slide.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{style:dashed?'dashed':'solid',fill:C.navy,width:1.7},head:{type:bidir?'triangle':'none',width:'sm',length:'sm'},tail:{type:'triangle',width:'sm',length:'sm'}});
}
function slide(title, notes, subtitle='') {
  const s=P.slides.add(); s.background.fill=C.white;
  text(s,title,56,40,1165,61,44,{bold:true,color:C.navy,name:`slide-${P.slides.items.length}-title`});
  if(subtitle) text(s,subtitle,58,108,1155,30,23,{color:C.gray});
  text(s,'ReCycleGuard / Proposed system',58,684,900,20,15,{color:C.gray});
  text(s,String(P.slides.items.length).padStart(2,'0'),1166,682,58,24,17,{color:C.navy,align:'right'});
  s.speakerNotes.text=notes;
  return s;
}
function table(s, values, widths, x,y,heights, size=23) {
  const t=s.tables.add({rows:values.length,columns:widths.length,left:x,top:y,width:widths.reduce((a,b)=>a+b,0),height:heights.reduce((a,b)=>a+b,0),columnWidths:widths,values});
  t.borders.assign({style:'solid',fill:C.border,width:.6});
  for(let r=0;r<values.length;r++) {
    t.rows[r].height=heights[r];
    for(let c=0;c<widths.length;c++) {
      const cell=t.getCell(r,c);
      cell.fill=r===0?C.navy:(r%2===0?C.light:C.white);
      cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?C.white:C.ink,verticalAlignment:'middle',autoFit:'none',insets:{left:12,right:12,top:8,bottom:8}};
    }
  }
  return t;
}
function paragraph(s,heading,body,x,y,w,h=100) {
  text(s,heading,x,y,w,34,27,{bold:true,color:C.navy});
  text(s,body,x,y+42,w,h-42,26);
}

// 1. Title
{
  const s=P.slides.add();s.background.fill=C.navy;
  text(s,'ReCycleGuard',64,96,1150,100,78,{bold:true,color:C.white,name:'cover-title'});
  text(s,'Agentic AI for e-waste EPR\ncompliance reconciliation',68,224,1120,110,38,{color:C.white});
  text(s,'System design and evaluation plan',68,382,1110,44,29,{color:'#DAE5F1'});
  text(s,'R V Abhishek, 1BM23CD047     H Sampreeth Bhat, 1BM23CD020\nSushanth S, 1BM23CD063         Vedantha Vinay Vernekar, 1BM23CD069',68,530,1130,74,23,{color:C.white});
  text(s,'Agentic AI (26CD7PEAAI), BMSCE\nInstructor: Dr. Kalyan Nagaraj',68,634,1100,52,20,{color:'#DAE5F1'});
  s.speakerNotes.text='Introduce the project as a proposed system for the compliance officer. EPR means Extended Producer Responsibility. The system investigates discrepancies in a supplied dossier and produces an evidence-backed working paper. Components, datasets and experiments are planned. This presentation contains no measured implementation results. Suggested opening: a payment record, a certificate event and a supported liability allocation each establish different facts.';
}
// 2. Decision and scope
{
 const s=slide('Decision and scope','The compliance officer decides which discrepancy to investigate next and which verification or correction the evidence supports. The initial scope contains one synthetic producer in closed FY 2024-25, up to two specific reviewed EEE codes, supplied metal-wise obligations and separately dated historical liabilities. Gold is a supplied fixed bucket. The system does not derive statutory targets from sales. Live filing, trading, OTP interaction, autonomous legal certification and compensation calculations are excluded. Explain that a numerical gap requires investigation and is not an automatic legal verdict.');
 text(s,'Which discrepancy needs investigation, and what action does the evidence support?',60,147,1140,100,36,{bold:true});
 paragraph(s,'Initial scope','One synthetic producer in FY 2024-25\nSupplied Au, Cu, Al and Fe obligations\nSeparate historical liability buckets\nUp to two reviewed EEE codes',60,294,552,215);
 paragraph(s,'Officer’s working paper','Apparent gaps with exact calculations\nEvidence locators and applicable clauses\nUnresolved questions and next actions\nAuthenticated human review',670,294,552,215);
 text(s,'Excluded: live filing, certificate trading, legal certification and compensation calculations',60,581,1155,64,25,{color:C.gray});
}
// 3. System architecture
{
 const s=slide('Architecture and data flow','The diagram groups C00-C16 as logical modules of one local application plus an offline benchmark. Regulatory-source and producer-dossier paths both preserve originals. C01 acquisition, C02 artifact catalog, C03 extraction, C04 normalization and C05 snapshots supply the runtime. C06 index and C07 retrieval support C09 investigation. C08 performs deterministic checks. C10 is the sole provider gateway. C12 builds/verifies reports, C13 handles human decisions and C14 exports/replays. C00 supplies commands and review access. C11 captures all transformations and interactions. C15 generates only visible evidence for intake. C16 launches an isolated runtime and accesses protected truth only after its run artifacts close. No oracle path exists into retrieval, prompts or the human review interface. Relationships show principal data/control flow and abbreviate invocation traffic.','Logical modules in one local Python application');
 text(s,'Official Gazette and CPCB sources',76,148,520,29,23,{bold:true});
 text(s,'Producer dossier with synthetic originals',690,148,515,29,23,{bold:true});
 rect(s,52,202,1174,378,'none',C.border,true);
 const f=node(s,'C01 Intake, C02 Originals, C03 Extraction, C04 Normalization, C05 Snapshots','Immutable evidence, page/row accounting, typed records and frozen inputs',76,224,1125,80,false,23);
 const a=node(s,'C06 Index, C07 Retrieval','Clauses, amendments\nand graded evidence',76,356,330,108,false,23);
 const b=node(s,'C09 Investigator','C10 model gateway\nBounded plan, act, observe',476,356,330,108,true,23);
 const c=node(s,'C08 Deterministic tools','Lifecycle, allocations\nand exact balances',876,356,325,108,false,23);
 const out=node(s,'C12 Verified report, C13 Human review, C14 Export and replay','Findings, calculations, citations, uncertainty and version-bound decisions',76,501,1125,70,false,23);
 arrow(s,f,b,'bottom','top');
 arrow(s,a,b,'right','left',true);arrow(s,b,c,'right','left',true);
 arrow(s,b,out,'bottom','top');
 text(s,'retrieve',410,379,66,23,16,{color:C.gray});
 text(s,'check',812,379,60,23,16,{color:C.gray});
 text(s,'preflight',650,324,130,24,17,{color:C.gray});
 text(s,'C00 CLI / review interface     C11 Audit capture across every component',76,591,1125,30,22,{color:C.gray});
 text(s,'C15 Generator and C16 Evaluator: visible dossiers and isolated trials',76,631,780,28,21,{color:C.navy,bold:true});
 text(s,'Hidden oracle: evaluator only',885,631,333,28,20,{bold:true,color:C.amber});
 // Native connectors from the external source labels into the evidence foundation.
 for(const x of [330,946]) s.shapes.add({geometry:'connector',name:'source-intake-'+x,kind:'straight',position:{left:x,top:184,width:0,height:40},line:{fill:C.navy,width:1.7},tail:{type:'triangle',width:'sm',length:'sm'}});
}
// 4. Agent graph
{
 const s=slide('Agent graph and adaptation','The preflight runs before the first model call. It inventories all assets, checks entity, period and units, freezes approved inputs and computes provisional findings. Each investigative action persists a concise plan and hypothesis, then the dispatcher validates the typed proposal and budget. The observation assessment records support, refutation, weak evidence, mistakes or no progress. A linked plan revision explains the next check without storing private chain-of-thought. Stop with a scoped resolution, abstention or budget stop. Verification checks quantities, provenance, citations and scope before human review. Missing critical inputs block the run. One report repair is allowed before blocked output. Persistent checkpoints cannot reset consumed budgets.');
 const p1=node(s,'1. Preflight','Freeze inputs and calculate\nprovisional balances',60,154,340,115);
 const p2=node(s,'2. Plan investigation','State hypotheses, required\nevidence and stop criteria',470,154,340,115);
 const p3=node(s,'3. Execute a tool','Validate permission,\narguments and budget',880,154,340,115);
 const p4=node(s,'4. Assess observation','Record support, refutation,\nweakness or no progress',880,354,340,115);
 const p5=node(s,'5. Revise investigation','Reformulate retrieval or\nselect a different check',470,354,340,115);
 const p6=node(s,'6. Resolve or stop','Resolve supported findings\nor abstain within limits',60,354,340,115);
 const p7=node(s,'7. Verify report and obtain human decision','Render referenced calculations and claims, verify evidence, then request authenticated review',60,552,1160,90,true,24);
 arrow(s,p1,p2);arrow(s,p2,p3);arrow(s,p3,p4,'bottom','top');
 arrow(s,p4,p5,'left','right');arrow(s,p5,p6,'left','right');
 arrow(s,p5,p2,'top','bottom');text(s,'continue',650,301,130,26,20,{color:C.gray});
 s.shapes.add({geometry:'connector',name:'resolution-to-review',kind:'straight',position:{left:230,top:469,width:0,height:83},line:{fill:C.navy,width:1.7},tail:{type:'triangle',width:'sm',length:'sm'}});
}
// 5. Patterns
{
 const s=slide('Selected agentic patterns','Tool use preserves deterministic checks for exact joins, dimensions, lifecycle and allocation conservation. Agentic RAG gives the investigator control over query formulation and evidence adequacy. Planning and reflection persist visible objectives, observations and revisions. Human review is a trusted external event bound to the exact report. Durable workflow uses checkpoints for recovery but retains the application audit ledger as authority. The optional collector/auditor variant uses the same authorized snapshots and controlled dispatcher. Its value must be measured against the single investigator. There is no selected model provider or automatic fallback. Source for checkpoint capability: '+sources.graph);
 table(s,[['Pattern','Choice and reason'],['Tool use','Exact joins, lifecycle checks and allocation arithmetic stay deterministic.'],['Agentic RAG','The investigator chooses queries and re-queries weak evidence.'],['Planning and reflection','Persist hypotheses, observations, mistakes and linked plan revisions.'],['Human review','Bind approval, rejection, requested changes and escalation to exact inputs.'],['Durable workflow','Recover from checkpoints while the application audit ledger stays authoritative.'],['Optional multi-agent','Compare collector/auditor roles with one bounded investigator.']], [284,876],60,150,[48,68,68,68,68,68,68],25);
}
// 6. Example
{
 const s=slide('Worked investigation: a pending allocation','This is a synthetic single-metal example, not a statutory target or certificate denomination rule. A supplied 100 kg target has one supported 55 kg credit-lot allocation observed twice. Those observations refer to one supported allocation, so the result is 55 kg, not 110 kg. A paid 25 kg item has pending transfer/allocation evidence. The initial apparent gap remains 45 kg and 25 kg remains pending. The investigator traces certificate history and seeks supported allocation evidence. Only a later evidenced and reviewed 25 kg allocation, in a new authorized input/run revision, supports 80 kg and a 20 kg gap. Payment or a newer account balance alone cannot produce that update. If evidence remains insufficient, abstain on the unresolved scope and name the evidence required.');
 text(s,'100 kg',60,145,380,89,64,{bold:true,color:C.navy});
 text(s,'Supplied target for one metal',60,236,540,35,25,{color:C.gray});
 table(s,[['Evidence state','Supported','Pending','Apparent gap'],['Initial dossier','55 kg','25 kg','45 kg'],['After supported allocation','80 kg','0 kg','20 kg']], [476,220,220,244],60,310,[54,70,70],25);
 text(s,'Investigation',60,542,260,34,27,{bold:true,color:C.navy});
 text(s,'Trace the certificate and allocation history.\nRequest missing evidence or abstain on the unresolved amount.',60,588,1140,70,28);
 text(s,'A payment or account snapshot alone cannot support the extra 25 kg.',660,167,550,104,28,{bold:true});
}
// 7. Sources
{
 const s=slide('Data sources and evidence intake','Normative sources include the E-Waste (Management) Rules, applicable Gazette amendments, CPCB framework, SOPs, FAQs and instructions. Retain source class, exact instrument/provision revision, commencement, applicability, locators and per-asset rights-review status. Public URL availability does not automatically permit model use or redistribution. Aggregate statistics provide context only, never transaction evidence. Planned synthetic dossiers contain obligations, events, allocations, account snapshots and commercial records, with original PDF/CSV/JSONL artifacts. Every submitted file, including corrupt, duplicate or never-retrieved material, gets an intake receipt. Every page/row gets a parsed, quarantined, excluded or unavailable disposition. Source links: '+sources.rules+'\n'+sources.amendment+'\n'+sources.framework+'\n'+sources.faq);
 table(s,[['Source class','Planned material','Use'],['Normative authority','Official Gazette instruments, amendments and CPCB guidance','Review clause applicability and preserve exact source locators'],['Operational evidence','Original synthetic dossiers, events, allocations and account snapshots','Reconstruct case facts with explicit provenance'],['Public context','Aggregate e-waste statistics','Context only, outside the producer transaction ledger']], [255,515,390],60,154,[50,104,104,90],24);
 paragraph(s,'Intake and preservation','Keep original bytes and hashes. Preserve clauses, tables, headers and footnotes during extraction.',60,552,1145,90);
}
// 8. RAG + memory
{
 const s=slide('Retrieval, evidence checks and memory','Start with SQLite FTS5 lexical retrieval and BM25. Check FTS5 at startup. Filter frozen corpus membership by access, regime, role and reviewed temporal applicability. Retrieve clauses, then expand parent headers, footnotes and relevant amendment counterparts under a bounded expansion policy. Grade authority, temporal applicability, direct support, completeness and contradiction separately. A missing signed authority is a lead, not a definitive citation. At most two query reformulations fit within the investigative action budget. Optional dense retrieval requires measured benefit and the same access/provenance contract. Working memory uses run state and LangGraph checkpoints. Persistent case history uses SQLite and immutable artifacts. Previous interpretations never become legal truth automatically. Keep all original evidence independently of what the model sees. Sources: '+sources.sqlite+'\n'+sources.graph);
 const n1=node(s,'Eligible corpus','Access, role, regime\nand applicable period',60,169,245,108);
 const n2=node(s,'Lexical retrieval','FTS5 / BM25 over\nfrozen source clauses',365,169,245,108);
 const n3=node(s,'Clause expansion','Headers, footnotes\nand amendment links',670,169,245,108);
 const n4=node(s,'Evidence grading','Assess support and\nre-query weak results',975,169,245,108);
 arrow(s,n1,n2);arrow(s,n2,n3);arrow(s,n3,n4);
 text(s,'Authority   /   Temporal applicability   /   Direct support   /   Completeness   /   Contradiction',60,326,1165,72,26,{bold:true,color:C.navy});
 paragraph(s,'Working memory','Run state, plans, observations,\ncheckpoints and remaining budgets',60,446,555,133);
 paragraph(s,'Persistent case history','SQLite records and immutable artifacts.\nPast interpretations require fresh support.',670,446,555,133);
 text(s,'Dense retrieval remains an experiment. Originals remain available even when the model never sees them.',60,613,1155,53,23,{color:C.gray});
}
// 9. Tools
{
 const s=slide('Deterministic tool plan','All calls share a capability-scoped command context, pinned snapshots, operation/attempt IDs, audit references and a structured service result. Typed errors preserve missing evidence, ambiguity, dimension mismatch, unsupported profile and applicability uncertainty. Decimal strings and Decimal arithmetic prevent binary-float compliance totals. The complete relevant input universe comes from the frozen snapshot, including historical allocations and conflicts. Caller-selected record lists cannot hide liabilities. Domain tools create new derivations and results but cannot edit source records, human review state or portal state. An account snapshot is a comparison-only observation and cannot become an invented allocation.');
 table(s,[['Tool','Representative input','Structured output'],['inspect_evidence','Artifact, observation or record references','Permitted values, locators and issues'],['resolve_locator','Source revision, legal path and applicability basis','Exact provision or unresolved applicability'],['trace_certificate','Certificate and event references','Equivalence, lifecycle and allocation history'],['compute_reconciliation','Case, profile and liability buckets','Required, supported, pending, gaps and provenance'],['compare_return_draft','Draft, calculations and section dispositions','Bucket deltas and scoped readiness']], [290,425,445],60,155,[48,76,76,76,76,76],23);
 text(s,'Typed arguments, exact decimals, complete input membership and explicit errors',60,618,1160,50,25,{bold:true,color:C.navy});
}
// 10. Governance
{
 const s=slide('Execution limits and human review','The model may propose allowlisted read/check operations and findings. It cannot modify originals, source quantities, profiles or portal state, run arbitrary SQL/shell/dynamic code, authenticate a reviewer or approve its own report. Untrusted document text cannot change capabilities or control state. Redact model inputs according to rights/access policy and preserve permitted originals. Budget defaults are eight investigative tool actions per finding, two query reformulations, one report repair and one retry per retryable attempt. Required case-wide action/token/cost/wall-time ceilings bound total work and retries consume those budgets. These are configuration, not measured runtime results. Approval ends the run with APPROVED. Rejection and requested changes block output. Escalation waits for an external reviewer event. Manual closure may end without a decision, never with fabricated approval. Corrections start a new authorized parent-linked run. Stop dispatch if audit storage fails.');
 paragraph(s,'Model permissions','Read and check authorized evidence.\nCreate new findings and report drafts.\nPreserve source records and portal state.',60,155,556,162);
 paragraph(s,'Investigation budgets','8 tool actions per finding\n2 query reformulations\n1 report repair and 1 retry per retryable attempt',60,359,556,183);
 text(s,'Case-wide token, cost and time ceilings also apply.\nAudit failure blocks progress.',60,585,556,69,23,{color:C.gray});
 table(s,[['Human decision','Run outcome'],['Approve','Complete with approved report'],['Reject','Block output'],['Request changes','Block output, start authorized correction'],['Escalate','Wait for external review']], [232,344],644,155,[50,75,75,90,75],23);
 text(s,'Decisions bind to exact report/input hashes.\nChanged inputs require fresh review.',644,565,576,78,25,{bold:true,color:C.navy});
}
// 11. Evaluation setup
{
 const s=slide('Evaluation design and comparison variants','The planned pilot contains 48 independently loadable synthetic dossiers, with 24 development and 24 held-out. Split by entity, template and fault combination rather than random rows. Cover all sixteen shared families: F01 clean control, F02 overlapping exports, F03 legitimate multistage certificate-ID reuse, F04 unit/dimension mix, F05 entity alias, F06 stale snapshot, F07 paid without completed transfer/allocation, F08 prior arrears, F09 expired/cancelled, F10 recycler capability mismatch, F11 wrong-period rule, F12 unseen signed notice, F13 weight-basis conflict, F14 unsupported regime, F15 extraction/page loss and F16 prompt injection. F02 repeated observations and F03 distinct legitimate stages must remain separate. The oracle distinguishes hidden world facts from what visible evidence justifies. Independent reviewed fixtures/calculations supply expected results. Run each variant on the same visible case/corpus/profile, record all trials and freeze configuration before held-out scoring. The investigator sees no oracle mount, seeds, labels or answer-bearing filenames. Score only after run artifacts close.');
 text(s,'48 dossiers',60,144,355,77,58,{bold:true,color:C.navy});
 text(s,'24 development / 24 held-out',472,165,740,47,35,{bold:true});
 text(s,'All 16 fault families, including clean controls, lifecycle ambiguity, missing evidence and injection',60,244,1155,68,27);
 table(s,[['Variant','Question it answers'],['Deterministic reconciliation','What do exact rules and calculations establish alone?'],['Fixed retrieval plus tools','What does a fixed evidence-retrieval plan add?'],['Bounded single investigator','Does adaptive investigation improve supported resolution?'],['Optional collector/auditor','Does collaboration improve quality enough to justify its cost?']], [410,750],60,324,[47,58,58,58,58],24);
 text(s,'Independent references and isolated truth. Same visible inputs for every variant.',60,646,1155,30,23,{color:C.gray});
}
// 12. Quality metrics
{
 const s=slide('Quality metrics','Report numerators, denominators and trial counts. Exact balance agreement compares each eligible metal/liability bucket with independent decimal reference results. Discrepancy precision is correct predicted findings divided by all predicted findings. Recall is detected reference discrepancies divided by all reference discrepancies. Resolution and abstention use the visible-evidence oracle rather than inaccessible hidden-world facts. Citation and temporal correctness assess direct support and role/regime/date applicability. Count unsupported claims and prohibited verdict candidates even if verification rejects them. Require zero prohibited verdicts in released reports and record forbidden tool attempts separately. All quality results remain unmeasured.');
 table(s,[['Metric','Planned assessment'],['Exact balance agreement','Exact decimal matches / eligible metal-liability buckets'],['Discrepancy precision and recall','Correct / predicted findings, and detected / reference discrepancies'],['Resolutions and abstentions','Correct resolutions and abstentions against the visible-evidence oracle'],['Citation applicability','Direct support and correct role, regime and date applicability'],['Unsupported/prohibited claims','Claim rates, blocked verdicts and forbidden action attempts']], [400,760],60,155,[50,80,80,80,80,80],24);
 text(s,'Reference answers follow visible evidence. Report counts beside rates.',60,639,1160,29,24,{color:C.gray});
}
// 13. Operating metrics
{
 const s=slide('Reliability, cost and audit coverage','Compare measured average investigative steps, latency p50/p95 including failures, provider cost per task and repeated-run gate-pass rates. Unknown provider cost is null, never zero. Report all trials and configuration rather than selecting successful examples. Evidence coverage includes received originals, discovered pages/rows and explicit missing/quarantined/excluded/unavailable dispositions. Audit coverage includes complete tool/model requests, full results/errors, contexts and turn records. Original evidence remains available even when never sent to the model. Audit storage failure blocks dispatch and reporting. Coverage and exact arithmetic are hard gates, not optional score bonuses. All runtime performance remains unmeasured.');
 table(s,[['Metric','Planned assessment'],['Steps, latency and cost','Mean investigative actions, latency p50/p95 and provider cost per task'],['Repeated-run reliability','Trials meeting correctness and safety gates / repeated trials'],['Evidence and audit coverage','Accounted assets and complete interaction records / expected totals']], [400,760],60,164,[50,94,94,108],25);
 paragraph(s,'Reporting rules','Record failed trials and unknown coverage. Preserve complete tool/model records.\nPerformance results remain unmeasured.',60,568,1160,99);
}
// 13. Ownership and gates
{
 const s=slide('Ownership and acceptance gates','Abhishek is the team lead and owns overall orchestration, correctness, workflow, model gateway and integration. Sushanth owns data generation and RAG, including the isolated oracle, corpus preparation, indexing and retrieval. Vedanth owns building and testing deterministic agent tools. Sampreeth owns remaining evidence ingestion/storage, audit, human review, report/export and evaluation integration. All members review shared interfaces, and independent cross-review protects reference calculations. Build interfaces/audit first, then data foundation and synthetic fixtures, deterministic baseline, lexical RAG, bounded investigator and review/evaluation. Hard gates require exact supported arithmetic, complete evidence accounting and audit coverage, and zero prohibited verdicts in released reports. A fluent report or generic qualification cannot bypass these gates.');
 table(s,[['Member','Primary responsibility'],['Abhishek, Team lead','Overall orchestration, correctness, model gateway and integration'],['Sushanth','Data generation and RAG, including isolated oracle and retrieval'],['Vedanth','Build and test the agent’s deterministic tools'],['Sampreeth','Evidence storage, audit, human review, reports/export and evaluation integration']], [310,850],60,151,[47,62,62,62,75],24);
 text(s,'Hard acceptance gates',60,505,1155,40,31,{bold:true,color:C.navy});
 text(s,'Exact supported arithmetic against independent references\nComplete evidence accounting and interaction audit coverage\nZero prohibited generated verdicts in released reports',60,565,1155,101,26);
}
// 14. Primary sources and limits
{
 const s=slide('Primary sources and remaining limits','Primary source URLs:\n'+Object.values(sources).join('\n')+'\nThe legal sources inform the planned source corpus and reviewed rule profiles. This is not a claim that these references constitute a complete current consolidated corpus. The pilot is synthetic-only. Exact equipment codes, source rights and reviewed profile activation remain decisions. Model/provider/context limits, OCR and dense retrieval require evaluation. Numerical agreement and valid locators do not prove semantic legal correctness. Local audit hashes rely on retained anchors. Publication exports require explicit rights/redaction decisions.');
 text(s,'Official regulatory material',60,153,1160,38,29,{bold:true,color:C.navy});
 text(s,'MoEFCC E-Waste (Management) Rules, 2022, G.S.R. 801(E)\nMoEFCC Amendment Rules, 2024, G.S.R. 164(E)\nCPCB certificate-generation framework and FAQ',60,204,1155,124,27);
 text(s,'Technical references',60,363,1160,38,29,{bold:true,color:C.navy});
 text(s,'SQLite FTS5 documentation\nLangGraph persistence documentation',60,413,1155,82,27);
 text(s,'Remaining limits',60,530,1160,38,29,{bold:true,color:C.navy});
 text(s,'Synthetic pilot. Reviewed source/profile activation required.\nModel choice, OCR and dense retrieval await measured evaluation.',60,581,1155,77,26);
}

await fs.mkdir(BUILD,{recursive:true});
await fs.writeFile(path.join(BUILD,'font-policy.json'),JSON.stringify({basis:'design',families:[FONT]},null,2));
await (await PresentationFile.exportPptx(P)).save(path.join(BUILD,'draft.pptx'));
console.log(`Exported ${P.slides.items.length} slides using ${FONT}`);
for(const [i,s] of P.slides.items.entries()) {
 const blob=await P.export({slide:s,format:'png',scale:1.25});
 await fs.writeFile(path.join(BUILD,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));
 console.log(`Rendered ${i+1}`);
}
await fs.writeFile(path.join(BUILD,'presentation.json'),JSON.stringify(P.toProto()));
