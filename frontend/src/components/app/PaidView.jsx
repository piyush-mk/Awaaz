import { Check, FileText, Plus } from 'lucide-react'
import { Btn } from './ui'
import { inr, num, toPath } from '../../lib/format'

/** Success screen after payment_received (or a cash/khata-only bill). */
export default function PaidView({ data, onNew }) {
  const amount = data.amount ?? data.total
  const low = data.low_stock || []
  const receipt = data.receipt_url || data.invoice?.receipt_url
  return (
    <div className="bg-white rounded-2xl p-5 text-center">
      <div className="mx-auto w-20 h-20 rounded-full bg-green-700 flex items-center justify-center animate-checkmark" role="img" aria-label="Payment mil gaya">
        <Check size={44} className="text-white" strokeWidth={3} />
      </div>
      <div className="mt-3 text-[44px] leading-none font-semibold tabular text-ink">{inr(amount)}</div>

      {low.length > 0 && (
        <ul className="mt-4 text-left divide-y divide-line">
          {low.map((l) => (
            <li key={l.product_id} className="flex items-center justify-between py-2">
              <span className="font-hindi text-base font-semibold">{l.name}</span>
              <span className={`text-sm font-semibold tabular ${l.level === 'low' ? 'text-red-700' : 'text-orange-800'}`}>{num(l.quantity)} {l.unit} bacha</span>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-5 flex gap-2">
        {receipt && (
          <a href={toPath(receipt)} target="_blank" rel="noreferrer" aria-label="Receipt" className="w-14 min-h-[56px] flex-shrink-0 flex items-center justify-center rounded-xl bg-bg-app">
            <FileText size={22} />
          </a>
        )}
        <Btn size="lg" variant="navy" icon={Plus} className="flex-1" onClick={onNew}>Naya bill</Btn>
      </div>
    </div>
  )
}
