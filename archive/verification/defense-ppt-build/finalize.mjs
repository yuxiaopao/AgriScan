import path from 'node:path';
import {pathToFileURL} from 'node:url';
const ROOT='E:/AgriScan', BUILD=path.join(ROOT,'.runtime/defense-ppt-build');
const SKILL='C:/Users/18984/.codex/plugins/cache/openai-primary-runtime/presentations/26.1017.22136/skills/presentations';
const {finalizePresentation}=await import(pathToFileURL(path.join(SKILL,'container_tools/artifact_tool_utils.mjs')).href);
const result=await finalizePresentation({workspaceDir:ROOT,candidatePath:path.join(BUILD,'draft.pptx'),finalPath:path.join(ROOT,'deliverables/defense/禾观AgriScan_课程答辩_24页.pptx'),pythonExecutable:'C:/Users/18984/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe',integrityValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit',...[7,9,11,23].flatMap(n=>['--require-native-table-slide',String(n)])],explicitTotalSlideCount:24,requiredNativeTableOwnerSlides:[7,9,11,23],requiredNativeChartOwnerSlides:[6,10],materializeLiteralChartWorkbooks:true,fontPolicy:{basis:'design',families:['Microsoft YaHei']},verifyArtifactToolImport:true,receiptPath:path.join(BUILD,'validation.json')});
console.log(JSON.stringify(result));
