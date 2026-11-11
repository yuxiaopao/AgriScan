from pathlib import Path

p=Path('frontend/src/App.tsx');s=p.read_text(encoding='utf-8')
old="<FloatingAssistant key={user?.username || 'guest'}"
assert s.count(old)==1
s=s.replace(old,"<FloatingAssistant key={`${user?.username||'guest'}:${sessionVersion}`}" ,1)
p.write_text(s,encoding='utf-8')

p=Path('frontend/src/FloatingAssistant.tsx');s=p.read_text(encoding='utf-8')
s=s.replace("import {api} from './api'","import {api,getToken} from './api'",1)
old='  const alive = useRef(true)'
assert s.count(old)==1
s=s.replace(old,"  const alive = useRef(true)\n  const mountToken=useRef(getToken())\n  const currentSession=()=>alive.current&&getToken()===mountToken.current",1)
s=s.replace("  useEffect(() => {\n    if (!features.assistant) {", "  useEffect(() => {\n    if(!currentSession())return\n    if (!features.assistant) {",1)
old="    if(!adviceRequest||!user||!features.assistant||loading)return\n    const cached=analysisCache.current.get(adviceRequest.id)"
new="""    if(!adviceRequest||!user||!currentSession()||loading)return
    if(!features.assistant){onAdviceHandled?.();return}
    let cached=analysisCache.current.get(adviceRequest.id)
    if(!cached){
      if(busy||analyzingRecord.current)return
      handled.current.add(adviceRequest.id);onDetectionHandled(adviceRequest.id)
      void analyzeDetection(adviceRequest)
      cached=analysisCache.current.get(adviceRequest.id)
    }"""
assert s.count(old)==1;s=s.replace(old,new,1)
s=s.replace('// The normal detection queue owns the only analysis POST. Viewing a result\n    // opens that queued/cached discussion and never creates another request.', '// Existing queued/cached analyses are reused. If the feature was disabled\n    // when saved, this explicit request starts its first analysis only once.')
s=s.replace("detection?.id,onAdviceHandled])", "detection?.id,onAdviceHandled,onDetectionHandled])",1)
s=s.replace('    if (user) {','    if (user&&currentSession()) {',1)
s=s.replace('if (disposed) return','if (disposed||!currentSession()) return')
s=s.replace('if (!disposed)', 'if (!disposed&&currentSession())')
s=s.replace('return () => {disposed = true; alive.current = false}', 'return () => {disposed = true; alive.current = false;analysisCache.current.clear();handled.current.clear()}',1)
s=s.replace('if (alive.current)', 'if (currentSession())').replace('if (!alive.current)', 'if (!currentSession())')
s=s.replace('  function rememberConversation(detail:Detail){','  function rememberConversation(detail:Detail){\n    if(!currentSession())return',1)
s=s.replace("    if (!features.assistant) return\n    analyzingRecord.current=record.id", "    if (!currentSession()||!features.assistant||analyzingRecord.current) return\n    analyzingRecord.current=record.id",1)
s=s.replace("if (!features.assistant || busy || loading || question.length", "if (!currentSession()||!features.assistant || busy || loading || question.length",1)
old='  async function selectChat(chat: Conversation) {'
if old in s:s=s.replace(old,old+'\n    if(!currentSession())return',1)
old='  async function openChat(chat: Conversation) {'
if old in s:s=s.replace(old,old+'\n    if(!currentSession())return',1)
s=s.replace('if (open && !history && !busy && !loading)', 'if (currentSession()&&open && !history && !busy && !loading)',1)
s=s.replace("  return <div className=\"assistant-widget\"", "  if(!currentSession())return null\n  return <div className=\"assistant-widget\"",1)
p.write_text(s,encoding='utf-8')
print('Assistant cache, queue and async callbacks are bound to exact token scope; explicit cache miss starts once.')
