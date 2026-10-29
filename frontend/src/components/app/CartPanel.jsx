import { useState } from 'react'
import { Scale, Trash2, ChevronDown } from 'lucide-react'
import { inr, qtyLabel } from '../../lib/format'
import { Stepper } from './ui'

/** The live cart. Loose lines show the weigh instruction ("450 gram tolo") in an orange band. */
export default function CartPanel({ cart, onQty, onRemove, disabled }) {
  const [showTax, setShowTax] = useState(false)
  const lines = cart?.lines || []
  if (!lines.length) return null

  return (
    <div className="bg-white rounded-2xl border border-line overflow-hidden">
      <ul className="divide-y divide-line">
        {lines.map((ln) => {
          const loose = ln.sell_mode === 'loose'
          return (
            <li key={`${ln.product_id}-${ln.unit}`} className="p-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-hindi text-xl font-bold leading-tight text-ink truncate">{ln.name_hi || ln.name}</div>
                  <div className="text-sm text-ink-3">
                    {ln.name_hi ? `${ln.name} . ` : ''}
                    {inr(ln.unit_price)}/{loose ? ln.base_unit || ln.unit : ln.unit}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-lg font-bold tabular text-ink">{inr(ln.line_total)}</div>
                  <div className="text-xs text-ink-3 tabular">{qtyLabel(ln.qty, ln.unit)}</div>
                </div>
              </div>
              {ln.weigh_instruction && (
                <div className="mt-2 flex items-center gap-2 rounded-xl bg-accent px-3 py-2 text-ink">
                  <Scale size={22} className="flex-shrink-0" />
                  <span className="font-hindi text-xl font-bold leading-tight">{ln.weigh_instruction}</span>
                </div>
              )}
              <div className="mt-2 flex items-center justify-between">
                <Stepper
                  value={Number(ln.qty)}
                  step={loose ? 0.25 : 1}
                  onChange={(q) => !disabled && onQty(ln, q)}
                  unit={ln.unit}
                />
                <button
                  onClick={() => !disabled && onRemove(ln)}
                  aria-label={`${ln.name} hatayein`}
                  className="w-11 h-11 flex items-center justify-center rounded-xl text-stock-red active:bg-red-50"
                >
                  <Trash2 size={20} />
                </button>
              </div>
            </li>
          )
        })}
      </ul>
      <div className="bg-ink text-white px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="font-hindi text-lg font-bold">Kul</div>
          <div className="text-2xl font-bold tabular">{inr(cart.total)}</div>
        </div>
        <button
          onClick={() => setShowTax((v) => !v)}
          className="mt-1 flex items-center gap-1 text-xs text-white/60 min-h-[28px]"
        >
          GST included <ChevronDown size={14} className={showTax ? 'rotate-180' : ''} />
        </button>
        {showTax && (
          <div className="text-xs text-white/70 tabular grid grid-cols-3 gap-2 pb-1">
            <div>Taxable<br />{inr(cart.taxable_total, 2)}</div>
            <div>CGST<br />{inr(cart.cgst_total, 2)}</div>
            <div>SGST<br />{inr(cart.sgst_total, 2)}</div>
          </div>
        )}
      </div>
    </div>
  )
}
