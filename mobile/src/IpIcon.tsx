import './ip-icons.css'

export type IpIconName = 'home' | 'detect' | 'records' | 'profile' | 'camera' | 'video' | 'plots' | 'knowledge' | 'settings'

export function IpIcon({name, className = ''}: {name: IpIconName; className?: string}) {
  return <img
    key={name}
    className={`ip-icon ip-icon--${name} ${className}`.trim()}
    src={`/images/ip-icons/${name}.webp`}
    alt=""
    aria-hidden="true"
    draggable={false}
    decoding="async"
    width={192}
    height={192}
    onError={event => {
      const icon = event.currentTarget
      if (icon.dataset.fallback === 'true') {
        icon.style.visibility = 'hidden'
        return
      }
      icon.dataset.fallback = 'true'
      icon.src = '/images/xiaohe.png'
    }}
  />
}

export default IpIcon
