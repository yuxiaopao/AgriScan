import {Fragment, type ReactNode} from 'react'

type Block = {kind:'paragraph';text:string} | {kind:'heading';text:string;number?:string} | {kind:'list';ordered:boolean;items:string[];start:number}

// These are text tokens rendered by React, never model-generated HTML.
function inline(text:string):ReactNode {
  return text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part,index)=>part.startsWith('**')&&part.endsWith('**')
    ? <strong key={index}>{part.slice(2,-2)}</strong>
    : part.startsWith('`')&&part.endsWith('`') ? <code key={index}>{part.slice(1,-1)}</code> : <Fragment key={index}>{part}</Fragment>)
}

function blocksFor(content:string):Block[] {
  const blocks:Block[]=[]
  let paragraph:string[]=[]
  const flush=()=>{if(paragraph.length){blocks.push({kind:'paragraph',text:paragraph.join('\n')});paragraph=[]}}
  for(const raw of content.replace(/\r\n?/g,'\n').split('\n')) {
    const line=raw.trim()
    if(!line){flush();continue}
    const numbered=line.match(/^(\d{1,2}|[一二三四五六七八九十]+)[.、．)）]\s*(.+)$/)
    const markdown=line.match(/^#{1,4}\s+(.+)$/)
    const title=(markdown?.[1]??numbered?.[2]??line).replace(/^\*\*(.*?)\*\*[:：]?$/,'$1')
    const [rawLabel,...rest]=title.split(/[:：]/)
    const label=rawLabel.replace(/^\*\*(.*?)\*\*$/,'$1').trim()
    const section=/^(检测结果解读|叶片可见异常|虫害线索|现在可以做什么|复拍与复检建议|何时联系农技人员|观察结论|处理建议|复检建议|注意事项)$/.test(label)
    if(markdown||(section&&(numbered||title.length<36))) {
      flush();blocks.push({kind:'heading',text:section?label:title,number:numbered?.[1]})
      if(section&&rest.join('：').trim()) paragraph.push(rest.join('：').trim())
      continue
    }
    const bullet=line.match(/^(?:[-*•]\s+|\d{1,2}[.、)）]\s+)(.+)$/)
    if(bullet) {
      flush()
      const ordered=/^\d/.test(line), last=blocks[blocks.length-1]
      if(last?.kind==='list'&&last.ordered===ordered)last.items.push(bullet[1])
      else blocks.push({kind:'list',ordered,items:[bullet[1]],start:ordered?Number.parseInt(line,10):1})
      continue
    }
    paragraph.push(raw.trimEnd())
  }
  flush()
  return blocks
}

export default function AssistantMessageBody({content}:{content:string}) {
  return <div className="assistant-message-body">{blocksFor(content).map((block,index)=>block.kind==='heading'
    ? <h4 key={index}>{block.number&&<span aria-hidden="true">{/^\d+$/.test(block.number)?block.number.padStart(2,'0'):block.number}</span>}{inline(block.text)}</h4>
    : block.kind==='list' ? block.ordered
      ? <ol key={index} start={block.start}>{block.items.map((text,item)=><li key={item}>{inline(text)}</li>)}</ol>
      : <ul key={index}>{block.items.map((text,item)=><li key={item}>{inline(text)}</li>)}</ul>
    : <p key={index}>{inline(block.text)}</p>)}</div>
}
