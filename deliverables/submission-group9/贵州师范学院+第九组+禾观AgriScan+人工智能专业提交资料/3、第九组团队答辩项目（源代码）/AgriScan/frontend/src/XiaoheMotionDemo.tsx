import {useState} from 'react'
import {Xiaohe, type XiaoheState} from './Xiaohe'

const states: {key: XiaoheState; name: string; description: string}[] = [
  {key: 'idle', name: '陪你巡田', description: '安静眨眼、轻轻呼吸，日常陪伴不打扰。'},
  {key: 'wave', name: '招手欢迎', description: '打开助手或靠近小禾时，向你打个招呼。'},
  {key: 'scan', name: '观察叶片', description: '检测与图片解读时，拿起放大镜观察叶片细节。'},
  {key: 'think', name: '认真思考', description: '整理对话和建议时，托腮思考。'},
  {key: 'success', name: '整理完成', description: '回答完成时点头示意，表示信息已经准备好。'},
  {key: 'concern', name: '留意异常', description: '发现需要关注的结果时，指出叶片异常，提醒继续核查。'},
]

export function XiaoheMotionDemo() {
  const [selected, setSelected] = useState(states[0])
  return <section className="panel xiaohe-motion-demo">
    <h2>小禾的田间日常</h2><p>小禾会跟随检测与对话切换动作。点击下方动作预览，也可以通过「界面动效」关闭动画。</p>
    <div className="xiaohe-motion-stage"><Xiaohe state={selected.key} crop={null}/><div><strong>{selected.name}</strong><p>{selected.description}</p></div></div>
    <div className="xiaohe-motion-options">{states.map(state => <button key={state.key} aria-pressed={state.key === selected.key} onClick={() => setSelected(state)}>{state.name}</button>)}</div>
  </section>
}
