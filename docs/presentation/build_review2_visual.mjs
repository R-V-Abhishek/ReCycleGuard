import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile, FileBlob } from '@oai/artifact-tool';

const ROOT=process.env.RECYCLEGUARD_WORKSPACE??process.cwd();
const BUILD=path.join(ROOT,'tmp/presentations/review2-visual');
const SKILL=process.env.PRESENTATIONS_SKILL_DIR??'/Users/rva/.codex/plugins/cache/openai-primary-runtime/presentations/26.1020.11127/skills/presentations';
const {resolvePresentationFont,applyPresentationChartFont}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const FONT=resolvePresentationFont();
const C={navy:'#10283F',blue:'#23466B',teal:'#00858B',tealLight:'#43C3BF',amber:'#E7AF53',ink:'#182B3B',gray:'#607180',paper:'#FAFCFE',line:'#C7D5DF',light:'#EDF5F8',white:'#FFFFFF'};
const P=Presentation.create({slideSize:{width:1280,height:720}});
const speeches=JSON.parse(await fs.readFile(path.join(ROOT,'docs/presentation/speech_review2.json'),'utf8'));
const original=await PresentationFile.importPptx(await FileBlob.load(path.join(ROOT,'output/pptx/ReCycleGuard_Review_2.pptx')));
const noteMap=[0,1,2,3,4,5,6,7,8,9,10,11,13,12,14];
let seq=0;
function txt(s,value,x,y,w,h,size=26,o={}){
 const z=s.shapes.add({geometry:'textbox',name:o.name??`text-${++seq}`,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 z.text=value;z.text.style={typeface:FONT,fontSize:size,color:o.color??C.ink,bold:o.bold??false,alignment:o.align??'left',verticalAlignment:'top',autoFit:'none',wrap:'square',insets:0};return z;
}
function rect(s,x,y,w,h,fill='none',stroke=C.line,dash=false){return s.shapes.add({geometry:'rect',name:`diagram-${++seq}`,position:{left:x,top:y,width:w,height:h},fill,line:{fill:stroke,width:1.2,style:dash?'dashed':'solid'}});}
function node(s,heading,body,x,y,w,h,dark=false,size=24){
 const a=rect(s,x,y,w,h,dark?C.navy:C.white,dark?C.navy:C.line);
 const lines=heading.split('\n').length;
 txt(s,heading,x+16,y+12,w-32,lines*30,size,{bold:true,color:dark?C.white:C.blue});
 if(body)txt(s,body,x+16,y+18+lines*30,w-32,h-30-lines*30,size-2,{color:dark?'#DBEDF5':C.gray});
 return a;
}
function link(s,a,b,from='right',to='left',both=false){return s.shapes.connect(a,b,{kind:'straight',fromSide:from,toSide:to,line:{fill:C.teal,width:2},head:{type:both?'triangle':'none',width:'sm',length:'sm'},tail:{type:'triangle',width:'sm',length:'sm'}});}
function vArrow(s,x,y,h){return s.shapes.add({geometry:'connector',name:`connector-${++seq}`,kind:'straight',position:{left:x,top:y,width:0,height:h},line:{fill:C.teal,width:2},tail:{type:'triangle',width:'sm',length:'sm'}});}
function rule(s,x,y,w,color=C.line){return s.shapes.add({geometry:'line',position:{left:x,top:y,width:w,height:0},fill:'none',line:{fill:color,width:1}});}
function page(n,title,dark=false){
 const s=P.slides.add();s.background.fill=dark?C.navy:C.paper;
 txt(s,title,58,43,1162,65,44,{bold:true,color:dark?C.white:C.navy,name:`slide-${n}-title`});
 txt(s,'ReCycleGuard',60,686,900,20,15,{color:dark?'#BCD4E3':C.gray});
 txt(s,String(n).padStart(2,'0'),1160,684,60,24,17,{align:'right',color:dark?C.tealLight:C.teal});
 const a=speeches[n-1];s.speakerNotes.text=`${a.priority}\nSuggested time: ${a.seconds?`${a.seconds} seconds`:'backup only'}\nPresenter cue: ${a.cue}\n\nSPEECH\n${a.speech}\n\nTECHNICAL NOTES AND SOURCES\n${original.slides.items[noteMap[n-1]].speakerNotes.text}`;
 if(n>=14)s.hidden=true;
 return s;
}
function para(s,title,body,x,y,w,h=114,opts={}){
 txt(s,title,x,y,w,39,29,{bold:true,color:opts.dark?C.white:C.blue});
 txt(s,body,x,y+46,w,h-46,26,{color:opts.dark?'#DCEAF1':C.gray});
}
function table(s,values,widths,x,y,heights,size=24){
 const t=s.tables.add({rows:values.length,columns:widths.length,left:x,top:y,width:widths.reduce((a,b)=>a+b,0),height:heights.reduce((a,b)=>a+b,0),columnWidths:widths,values});
 t.borders.assign({fill:C.white,width:.6,style:'solid'});
 for(let r=0;r<values.length;r++){t.rows[r].height=heights[r];for(let c=0;c<widths.length;c++){
  const q=t.getCell(r,c);q.fill=r===0?C.blue:(r%2===0?C.light:C.white);
  q.text.style={typeface:FONT,fontSize:size,bold:r===0||c===0,color:r===0?C.white:(c===0?C.blue:C.ink),verticalAlignment:'middle',autoFit:'none',insets:{left:14,right:14,top:10,bottom:10}};
 }}return t;
}
// 1. The cover uses one conceptual image. All type stays editable.
{
 const s=page(1,'');
 const b=await fs.readFile(path.join(ROOT,'docs/presentation/assets/review2-cover.png'));
 s.images.add({blob:b,contentType:'image/png',alt:'Conceptual AI-generated still life of discarded circuit boards, recovered metals and documents',fit:'cover',position:{left:0,top:0,width:1280,height:720}});
 txt(s,'ReCycleGuard',62,110,680,100,74,{bold:true,color:C.white,name:'cover-title'});
 txt(s,'Agentic AI for e-waste\nEPR reconciliation',66,236,625,110,38,{color:C.white});
 txt(s,'System design and evaluation plan',66,394,610,42,28,{color:C.tealLight});
 txt(s,'R V Abhishek, H Sampreeth Bhat,\nSushanth S and Vedantha Vinay Vernekar',66,553,620,68,22,{color:'#E4EDF4'});
 txt(s,'Agentic AI (26CD7PEAAI), BMSCE\nDr. Kalyan Nagaraj',66,642,620,53,19,{color:'#BDD3E0'});
 s.speakerNotes.text+='\nCover asset: conceptual illustration generated with the built-in ImageGen tool. It does not depict an actual case or company. Prompt and local asset provenance are retained in docs/presentation/assets/README.md.';
}
// 2. One focal question followed by a concise scope comparison.
{
 const s=page(2,'Decision and scope');
 txt(s,'Which discrepancy needs investigation?',60,166,1130,64,48,{bold:true,color:C.blue});
 txt(s,'What action does the evidence support?',60,245,1130,64,44,{color:C.teal});
 rule(s,60,350,1158);
 para(s,'Bounded scope','One producer, one closed year\nSupplied metal-wise obligations\nSeparate historical liabilities',60,398,545,175);
 para(s,'Human-reviewed output','Exact calculations and evidence\nOpen questions and next actions\nA traceable working paper',680,398,540,175);
 txt(s,'Design proposal. Live filing, trading, legal certification and compensation calculations are excluded.',60,620,1160,43,23,{color:C.gray});
}
// 3. Native architecture with vertical intake links and horizontal tool/retrieval traffic.
{
 const s=page(3,'Architecture and data flow');
 txt(s,'Official regulatory sources',77,145,500,36,25,{bold:true,color:C.blue});
 txt(s,'Producer dossier',775,145,430,36,25,{bold:true,color:C.blue});
 rect(s,48,200,1182,401,'none',C.line,true);
 const f=node(s,'Evidence foundation','C01 Intake, C02 Originals, C03 Extraction, C04 Normalization, C05 Frozen snapshots',76,222,1128,88,false,24);
 vArrow(s,322,184,38);vArrow(s,965,184,38);
 const a=node(s,'C06 Index, C07 Retrieval','Clauses and amendments\nEvidence grading',76,359,330,107);
 const b=node(s,'C09 Investigator','C10 model gateway\nBounded plan, act, observe',476,359,330,107,true);
 const c=node(s,'C08 Domain tools','Exact lifecycle, allocation\nand quantity checks',876,359,328,107);
 link(s,f,b,'bottom','top');link(s,a,b,'right','left',true);link(s,b,c,'right','left',true);
 txt(s,'preflight',654,324,120,24,17,{color:C.gray});txt(s,'retrieve',412,378,64,22,16,{color:C.gray});txt(s,'check',812,378,64,22,16,{color:C.gray});
 const r=node(s,'C12 Verified report, C13 Human review, C14 Export and replay','Findings, calculations, citations and explicit uncertainty',76,515,1128,77,true,24);
 link(s,b,r,'bottom','top');
 txt(s,'C00 CLI / review interface     C11 Audit capture across every component',76,613,1128,27,21,{color:C.gray});
 txt(s,'C15 Generator, C16 Evaluator: visible dossiers and isolated trials',76,651,788,26,20,{bold:true,color:C.blue});
 txt(s,'Hidden oracle: evaluator only',881,651,333,25,20,{bold:true,color:'#92611C'});
}
// 4. The graph is the core adaptive behavior, not decorative artwork.
{
 const s=page(4,'Agent graph and adaptation');
 const a=node(s,'1. Preflight','Freeze inputs and compute\nprovisional findings',60,158,340,112);
 const b=node(s,'2. Plan investigation','State hypotheses and\nrequired evidence',470,158,340,112);
 const c=node(s,'3. Execute a tool','Validate arguments,\npermission and budget',880,158,340,112);
 const d=node(s,'4. Assess observations','Support, refutation,\nweak evidence or no progress',880,359,340,112);
 const e=node(s,'5. Revise investigation','Reformulate retrieval or\nchoose a different check',470,359,340,112,true);
 const f=node(s,'6. Resolve or stop','Resolve supported findings\nor abstain within limits',60,359,340,112);
 link(s,a,b);link(s,b,c);link(s,c,d,'bottom','top');link(s,d,e,'left','right');link(s,e,f,'left','right');link(s,e,b,'top','bottom');
 txt(s,'continue',653,307,140,24,21,{color:C.teal});
 node(s,'7. Verify report and obtain a human decision','Render referenced calculations, check claims and citations, then request authenticated review',60,557,1160,89,true,25);
 vArrow(s,230,471,86);
}
// 5. Flat editorial layout replaces the dense pattern table.
{
 const s=page(5,'Why these agentic patterns');
 para(s,'Deterministic tools','Exact joins, lifecycle checks\nand conserved credit allocations',60,168,548,138);
 para(s,'Planning and reflection','Persist hypotheses, observations\nand reasons for changing direction',687,168,533,138);
 rule(s,60,343,1160);
 para(s,'Agentic RAG','Choose queries, assess support\nand re-query inadequate evidence',60,384,548,144);
 para(s,'Optional multi-agent','Measure whether collector/auditor roles\njustify extra cost and complexity',687,384,533,144);
 txt(s,'Human review controls the decision. Checkpoints support recovery.',60,606,1160,47,28,{bold:true,color:C.teal});
}
// 6. Native chart, using only the supplied synthetic arithmetic.
{
 const s=page(6,'Worked investigation: a pending allocation',true);
 txt(s,'100 kg',60,145,390,88,70,{bold:true,color:C.white});
 txt(s,'Supplied target for one metal',60,237,580,34,26,{color:'#BED5E2'});
 txt(s,'25 kg remains pending until\nallocation evidence supports it',711,164,510,95,31,{bold:true,color:C.amber});
 const ch=s.charts.add('bar',{
  position:{left:58,top:299,width:1162,height:259},categories:['Supported update','Initial evidence'],
  series:[{name:'Supported allocation',values:[80,55],fill:C.tealLight,line:{fill:'none',width:0},dataLabels:{showValue:true,position:'center',numberFormatCode:'0" kg"',textStyle:{typeface:FONT,fontSize:28,bold:true,fill:C.navy}}},
          {name:'Apparent gap',values:[20,45],fill:C.amber,line:{fill:'none',width:0},dataLabels:{showValue:true,position:'center',numberFormatCode:'0" kg"',textStyle:{typeface:FONT,fontSize:28,bold:true,fill:C.navy}}}],
  barOptions:{direction:'bar',grouping:'stacked',gapWidth:70,overlap:100},hasLegend:true,legend:{position:'bottom',overlay:false,textStyle:{typeface:FONT,fontSize:20,fill:C.white}},
  xAxis:{visible:true,textStyle:{typeface:FONT,fontSize:23,fill:C.white},line:{fill:'none',width:0},majorGridlines:null},
  yAxis:{visible:false,min:0,max:100,line:{fill:'none',width:0},majorGridlines:null},
  chartFill:C.navy,chartLine:{fill:'none',width:0},plotAreaFill:C.navy,plotAreaLine:{fill:'none',width:0}
 });
 applyPresentationChartFont(ch,{fontFamily:FONT});
 txt(s,'Trace the certificate and allocation history',60,591,1150,37,29,{bold:true,color:C.white});
 txt(s,'Payment or a newer account snapshot alone cannot support the extra 25 kg.',60,641,1155,33,24,{color:'#D0E3ED'});
}
// 7. Source roles appear as lanes rather than a dense grid.
{
 const s=page(7,'Data sources and evidence intake');
 para(s,'Regulatory authority','Official Gazette instruments, amendments and CPCB guidance',60,159,1158,100);
 txt(s,'Reviewed clause applicability and exact source locators',60,257,1158,36,25,{color:C.teal});
 rule(s,60,316,1158);
 para(s,'Operational evidence','Synthetic obligations, certificate events, allocations and account snapshots',60,345,1158,100);
 txt(s,'Original files and row/page provenance remain available',60,443,1158,36,25,{color:C.teal});
 rule(s,60,502,1158);
 para(s,'Public context','Aggregate statistics provide context outside the producer transaction ledger',60,531,1158,102);
 txt(s,'Every submitted asset and discovered page/row receives an explicit disposition.',60,641,1158,32,23,{bold:true,color:C.blue});
}
// 8. Retrieval flow with a short memory comparison.
{
 const s=page(8,'Retrieval and memory');
 const a=node(s,'Eligible corpus','Access, role, regime\nand applicable period',60,165,245,121);
 const b=node(s,'Lexical retrieval','FTS5 / BM25\nFrozen clauses',365,165,245,121);
 const c=node(s,'Clause expansion','Headers, footnotes\nand amendments',670,165,245,121);
 const d=node(s,'Evidence grading','Assess support and\nre-query weak results',975,165,245,121);
 link(s,a,b);link(s,b,c);link(s,c,d);
 txt(s,'Authority, temporal applicability, direct support, completeness and contradiction',60,338,1158,76,31,{bold:true,color:C.teal});
 para(s,'Working memory','Plans, observations, checkpoints\nand remaining budgets',60,460,540,124);
 para(s,'Persistent case history','SQLite records and immutable artifacts.\nEarlier interpretations require support.',681,460,539,124);
 txt(s,'Dense retrieval remains an experiment. Original evidence outlives the model context.',60,631,1158,39,23,{color:C.gray});
}
// 9. Detailed interfaces remain an editable native table.
{
 const s=page(9,'Deterministic tool plan');
 table(s,[['Tool','Representative input','Structured output'],['inspect_evidence','Artifact, observation or record references','Values, locators and issues'],['resolve_locator','Source revision, legal path and applicability','Exact provision or explicit uncertainty'],['trace_certificate','Certificate and event references','Lifecycle, equivalence and allocation history'],['compute_reconciliation','Case, profile and liability buckets','Required, supported, pending, gap and provenance'],['compare_return_draft','Draft, calculations and section dispositions','Bucket deltas and scoped readiness']],[300,420,440],60,155,[50,77,77,77,77,77],23);
 txt(s,'Typed calls, exact decimals and complete snapshot membership',60,636,1155,40,27,{bold:true,color:C.teal});
}
// 10. Large budget figures and a concise review path.
{
 const s=page(10,'Bounded autonomy and human authority');
 txt(s,'8',60,161,230,120,102,{bold:true,color:C.teal});
 txt(s,'tool actions\nper finding',60,291,255,77,29,{color:C.blue});
 txt(s,'2',342,161,230,120,102,{bold:true,color:C.teal});
 txt(s,'query\nreformulations',342,291,260,77,29,{color:C.blue});
 txt(s,'Bounded retries, report repair, time and cost',60,420,545,89,27,{bold:true,color:C.blue});
 txt(s,'Audit failure blocks progress.\nThe model cannot approve its report.',60,538,545,92,26,{color:C.gray});
 txt(s,'Authenticated review',685,169,535,43,31,{bold:true,color:C.blue});
 const rows=[['Approve','Complete with approved report'],['Reject','Block output'],['Request changes','Block output, then\nstart authorized correction'],['Escalate','Await external review']];
 for(const [i,r] of rows.entries()){const y=247+i*77;txt(s,r[0],685,y,214,70,26,{bold:true,color:C.teal});txt(s,r[1],909,y,310,68,24,{color:C.gray});}
 txt(s,'Decisions bind to exact report and input hashes.',685,598,535,62,25,{bold:true,color:C.blue});
}
// 11. The benchmark and controlled variants form an editable comparison diagram.
{
 const s=page(11,'Evaluation design');
 txt(s,'48',60,135,300,143,116,{bold:true,color:C.blue});
 txt(s,'planned synthetic dossiers',67,285,400,37,27,{color:C.gray});
 txt(s,'24',529,161,240,92,70,{bold:true,color:C.teal});txt(s,'development',533,258,260,42,29,{color:C.gray});
 txt(s,'24',942,161,240,92,70,{bold:true,color:C.teal});txt(s,'held-out',946,258,260,42,29,{color:C.gray});
 txt(s,'Same visible inputs across every variant',60,368,1158,42,30,{bold:true,color:C.blue});
 node(s,'Deterministic','Exact reconciliation\nwithout an LLM',60,435,266,122);
 node(s,'Fixed retrieval','A fixed evidence plan\nplus domain tools',358,435,266,122);
 node(s,'Investigator','Adaptive investigation\nwithin a fixed budget',656,435,266,122,true);
 node(s,'Collector/auditor','Optional collaboration\nunder the same rules',954,435,266,122,false,23);
 txt(s,'16 fault families. Independent reference calculations. Oracle access only after run closure.',60,616,1158,57,25,{bold:true,color:C.teal});
}
// 12. Quality criteria plus the operating metrics that will be mentioned briefly.
{
 const s=page(12,'How we will judge quality');
 table(s,[['Quality dimension','Planned measurement'],['Arithmetic','Exact decimal matches against independent bucket references'],['Discrepancy detection','Precision and recall over reference findings'],['Resolution or abstention','Correct outcome for the evidence actually visible'],['Citation correctness','Direct support and correct role, regime and date'],['Unsupported/prohibited claims','Claim rates, blocked verdicts and forbidden action attempts']],[390,770],60,155,[50,76,76,76,76,90],25);
 txt(s,'Also track steps, latency, cost and repeated-run reliability',60,626,1160,38,27,{bold:true,color:C.teal});
 txt(s,'Planned measures. Quality and performance remain unmeasured.',60,115,1160,28,21,{color:C.gray});
}
// 13. The closing slide keeps ownership secondary to acceptance.
{
 const s=page(13,'Acceptance and team ownership',true);
 txt(s,'Proposed acceptance gates',60,158,500,40,29,{color:C.tealLight,bold:true});
 txt(s,'Exact calculations\n\nComplete evidence\n\nNo prohibited verdicts',60,223,530,337,38,{bold:true,color:C.white});
 txt(s,'Human review remains the final authority',60,599,530,69,28,{color:C.amber});
 const people=[
  ['R V Abhishek, 1BM23CD047','Team lead. Orchestration and correctness'],
  ['Sushanth S, 1BM23CD063','Data generation and RAG'],
  ['Vedantha Vinay Vernekar, 1BM23CD069','Build and test agent tools'],
  ['H Sampreeth Bhat, 1BM23CD020','Evidence, audit, review and evaluation']
 ];
 for(const [i,p] of people.entries()){const y=158+i*118;txt(s,p[0],681,y,538,30,21,{bold:true,color:C.tealLight});txt(s,p[1],681,y+40,538,66,26,{color:C.white});}
}
// 14-15. Backup slides stay in the file but do not interrupt the main talk.
{
 const s=page(14,'Operating metrics and audit coverage');
 table(s,[['Metric','Assessment'],['Steps, latency and cost','Mean investigative actions, latency p50/p95 and provider cost per task'],['Repeated-run reliability','Trials passing correctness and safety gates / repeated trials'],['Evidence and audit coverage','Accounted assets and complete interaction records / expected totals']],[400,760],60,167,[50,100,100,110],25);
 para(s,'Reporting rules','Include failures and unknown coverage. Preserve all permitted tool/model records.\nPerformance results remain unmeasured.',60,550,1160,118);
}
{
 const s=page(15,'Sources and remaining limits');
 para(s,'Official regulatory material','MoEFCC E-Waste Rules and applicable amendments\nCPCB certificate-generation framework and FAQ',60,162,1160,132);
 para(s,'Technical references','SQLite FTS5 and LangGraph persistence documentation',60,342,1160,103);
 para(s,'Remaining limits','Synthetic pilot. Reviewed source/profile activation required.\nModel choice, OCR and dense retrieval await evaluation.',60,505,1160,132);
}
await fs.mkdir(BUILD,{recursive:true});
await fs.writeFile(path.join(BUILD,'font-policy.json'),JSON.stringify({basis:'design',families:[FONT]},null,2));
await (await PresentationFile.exportPptx(P)).save(path.join(BUILD,'draft.pptx'));
console.log(`Exported ${P.slides.items.length} slides in ${FONT}`);
for(const [i,s] of P.slides.items.entries()){
 const png=await P.export({slide:s,format:'png',scale:1.25});
 await fs.writeFile(path.join(BUILD,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 console.log(`Rendered ${i+1}`);
}
await fs.writeFile(path.join(BUILD,'presentation.json'),JSON.stringify(P.toProto()));
