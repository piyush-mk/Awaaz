import { useState } from 'react'
import { Scale, Trash2 } from 'lucide-react'
import { inr, qtyLabel } from '../../lib/format'
import { Stepper } from './ui'

/** The bill as a paper receipt that fills while you speak. Tap a line to change it. The total is on the button below. */
export default function CartPanel({ cart, onQty, onRemove, disabled }) {
  const [editing, setEditing] = useState(null)
  const lines = cart?.lines || []
  if (!lines.length) return null

  return (
    <ul className="bg-white rounded px-4 py-1 divide-y divide-line">
      {lines.map((ln) => {
        const key = `${ln.product_id}-${ln.unit}`
        const loose = ln.sell_mode === 'loose'
        const open = editing === key
        return (
          <li key={key} className="py-2">
            <button onClick={() => setEditing(open ? null : key)} aria-expanded={open} className="w-full min-h-[44px] flex items-center gap-3 text-left">
              <span className="min-w-0 flex-1 font-hindi text-lg font-semibold leading-tight truncate">{ln.name_hi || ln.name}</span>
              <span className="text-sm text-ink-3 tabular whitespace-nowrap">{qtyLabel(ln.qty, ln.unit)}</span>
              <span className="w-16 text-right text-lg font-semibold tabular">{inr(ln.line_total)}</span>
            </button>
            {ln.weigh_instruction && (
              <div className="mt-1 flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-ink">
                <Scale size={22} className="flex-shrink-0" />
                <span className="font-hindi text-xl font-bold leading-tight">{ln.weigh_instruction}</span>
              </div>
            )}
            {open && (
              <div className="mt-1 flex items-center justify-between">
                <Stepper value={Number(ln.qty)} step={loose ? 0.25 : 1} onChange={(q) => !disabled && onQty(ln, q)} unit={ln.unit} />
                <button
                  onClick={() => !disabled && onRemove(ln)}
                  aria-label={`${ln.name} hatayein`}
                  className="w-11 h-11 flex items-center justify-center rounded-xl text-red-700 active:bg-red-50"
                >
                  <Trash2 size={20} />
                </button>
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
