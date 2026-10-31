import { Check, ExternalLink, Plus } from 'lucide-react'
import { Btn } from './ui'
import { inr, toPath } from '../../lib/format'

/** Success screen after payment_received (or a cash/khata-only bill). */
export default function PaidView({ data, onNew }) {
  const amount = data.amount ?? data.total
  const low = data.low_stock || []
  const receipt = data.receipt_url || data.invoice?.receipt_url
  return (
    <div className="bg-white rounded-2xl p-5 text-center">
      <div className="mx-auto w-20 h-20 rounded-full bg-green-700 flex items-center justify-center animate-checkmark">
        <Check size={44} className="text-white" strokeWidth={3} />
      </div>
      <div className="mt-3 font-hindi text-2xl font-semibold text-ink">Payment mil gaya</div>
      <div className="text-[44px] leading-none font-semibold tabular text-ink mt-2">{inr(amount)}</div>
      {(data.number || data.invoice?.number) && (
        <div className="mt-2 text-sm text-ink-3">{data.number || data.invoice?.number}</div>
      )}
      {data.spoken_text && <p className="mt-3 font-hindi text-lg text-ink">{data.spoken_text}</p>}

      {low.length > 0 && (
        <div className="mt-4 text-left">
          <div className="text-sm font-semibold text-ink-3 mb-1.5">Stock kam ho raha hai</div>
          <ul className="divide-y divide-line">
            {low.map((l) => (
              <li key={l.product_id} className="flex items-center justify-between py-2">
                <span className="font-hindi text-base font-semibold">{l.name}</span>
                <span className={`text-sm font-semibold tabular ${l.level === 'low' ? 'text-red-700' : 'text-orange-800'}`}>
                  {l.quantity} {l.unit} bacha
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 gap-2">
        {receipt && (
          <a
            href={toPath(receipt)}
            target="_blank"
            rel="noreferrer"
            className="min-h-[48px] inline-flex items-center justify-center gap-2 rounded-xl bg-bg-app font-semibold"
          >
            <ExternalLink size={18} /> Receipt dekhein
          </a>
        )}
        <Btn size="lg" variant="navy" icon={Plus} onClick={onNew}>
          Naya bill
        </Btn>
      </div>
    </div>
  )
}
