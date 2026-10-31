import { useState } from 'react'
import { Scale, Trash2, ChevronDown } from 'lucide-react'
import { inr, qtyLabel } from '../../lib/format'
import { Stepper } from './ui'

/** The bill as a paper receipt that fills while you speak. Tap a line to change it. */
export default function CartPanel({ cart, onQty, onRemove, disabled }) {
  const [showTax, setShowTax] = useState(false)
  const [editing, setEditing] = useState(null)
  const lines = cart?.lines || []
  if (!lines.length) return null

  return (
    <div className="bg-white rounded px-4 pt-2 pb-3">
      <ul className="divide-y divide-line">
        {lines.map((ln) => {
          const key = `${ln.product_id}-${ln.unit}`
          const loose = ln.sell_mode === 'loose'
          const open = editing === key
          return (
            <li key={key} className="py-2.5">
              <button onClick={() => setEditing(open ? null : key)} aria-expanded={open} className="w-full min-h-[44px] flex items-center gap-3 text-left">
                <span className="min-w-0 flex-1">
                  <span className="block font-hindi text-lg font-semibold leading-tight truncate">{ln.name_hi || ln.name}</span>
                  <span className="block text-sm text-ink-3 tabular">
                    {qtyLabel(ln.qty, ln.unit)}, {inr(ln.unit_price)}/{loose ? ln.base_unit || ln.unit : ln.unit}
                  </span>
                </span>
                <span className="text-lg font-semibold tabular">{inr(ln.line_total)}</span>
              </button>
              {ln.weigh_instruction && (
                <div className="mt-1.5 flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-ink">
                  <Scale size={22} className="flex-shrink-0" />
                  <span className="font-hindi text-xl font-bold leading-tight">{ln.weigh_instruction}</span>
                </div>
              )}
              {open && (
                <div className="mt-2 flex items-center justify-between">
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
      <div className="border-t-2 border-dashed border-line mt-1 pt-2.5">
        <div className="flex items-baseline justify-between">
          <div className="font-hindi text-lg font-semibold">Kul</div>
          <div className="text-[34px] leading-none font-semibold tabular tracking-tight">{inr(cart.total)}</div>
        </div>
        <button onClick={() => setShowTax((v) => !v)} aria-expanded={showTax} className="mt-1 flex items-center gap-1 text-sm text-ink-3 min-h-[32px]">
          GST shaamil <ChevronDown size={14} className={showTax ? 'rotate-180' : ''} />
        </button>
        {showTax && (
          <div className="text-sm text-ink-3 tabular grid grid-cols-3 gap-2 pb-1">
            <div>Taxable<br />{inr(cart.taxable_total, 2)}</div>
            <div>CGST<br />{inr(cart.cgst_total, 2)}</div>
            <div>SGST<br />{inr(cart.sgst_total, 2)}</div>
          </div>
        )}
      </div>
    </div>
  )
}
