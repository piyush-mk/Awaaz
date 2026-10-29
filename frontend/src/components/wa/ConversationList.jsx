import { Camera, Mic, Store, Truck, User } from 'lucide-react'
import { WA } from './Bubble'
import { hhmm, initials, previewOf } from './waUtils'

function Avatar({ conv }) {
  const Icon = conv.supplier_id ? Truck : conv.customer_id ? null : User
  return (
    <div
      className="grid h-12 w-12 shrink-0 place-items-center rounded-full text-base font-bold"
      style={{ background: conv.supplier_id ? '#FFE3C2' : '#CDEBE4', color: '#0B3B33' }}
      aria-hidden="true"
    >
      {Icon ? <Icon size={22} /> : initials(conv.name)}
    </div>
  )
}

export default function ConversationList({ convs, selectedKey, onSelect }) {
  if (!convs.length) {
    return (
      <div className="p-6 text-center text-base" style={{ color: WA.sub }}>
        Abhi koi chat nahi. &ldquo;Naya chat&rdquo; se customer chuniye ya phone number daaliye.
      </div>
    )
  }
  return (
    <ul>
      {convs.map((c) => {
        const last = c.last_message
        const active = c.key === selectedKey
        const LastIcon = last?.type === 'audio' ? Mic : last?.type === 'image' ? Camera : last?.direction === 'out' ? Store : null
        return (
          <li key={c.key}>
            <button
              type="button"
              onClick={() => onSelect(c.key)}
              aria-current={active ? 'true' : undefined}
              className="flex min-h-[64px] w-full items-center gap-3 border-b px-3 py-2.5 text-left hover:bg-[#F5F6F6]"
              style={{ borderColor: '#EDF0F1', background: active ? '#E9EDEF' : undefined }}
            >
              <Avatar conv={c} />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-base font-semibold" style={{ color: WA.ink }}>{c.name}</span>
                  <span className="shrink-0 text-xs tabular-nums" style={{ color: WA.sub }}>{hhmm(c.last_at)}</span>
                </span>
                <span className="flex items-center gap-1 text-sm" style={{ color: WA.sub }}>
                  {LastIcon && <LastIcon size={14} aria-hidden="true" className="shrink-0" />}
                  <span className="truncate">{previewOf(last) || c.phone}</span>
                </span>
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
