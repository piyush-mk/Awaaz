import QRCode from 'react-qr-code'
import { AlertTriangle, CheckCircle2, Mic, Scale, ExternalLink, X, Info, Package, Check } from 'lucide-react'
import { inr, localUrl } from '../../api/sideClient'
import { CYAN, INK, ORANGE } from './FullPage'
import SourceChip from '../app/SourceChip'

// Text colours that keep >= 4.5:1 on white (cyan/orange are fills only).
export const CYAN_TEXT = '#00678C'
export const ORANGE_TEXT = '#A84F00'

const qty = (n) => {
  const v = Number(n)
  return Number.isFinite(v) ? String(+v.toFixed(3)) : ''
}

/** Animated "listening" bars. Static when reduced motion is requested (see the page <style>). */
export function Bars({ active = true, count = 9, color = CYAN, height = 56, className = '' }) {
  return (
    <div className={`flex items-center justify-center gap-1.5 ${className}`} style={{ height }} aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <span
          key={i}
          className={active ? 'sb-bar' : ''}
          style={{
            width: 7,
            height: active ? height : 10,
            borderRadius: 4,
            background: color,
            opacity: active ? 1 : 0.35,
            animationDelay: `${(i % 5) * 0.13 + (i % 3) * 0.05}s`,
            animationDuration: `${0.7 + (i % 4) * 0.12}s`,
          }}
        />
      ))}
    </div>
  )
}

export function HeardBubble({ heard }) {
  if (!heard || (!heard.transcript && !heard.reply)) return null
  return (
    <div className="mb-3 rounded-2xl px-4 py-3" style={{ background: '#E6F7FD' }} aria-live="polite">
      {heard.transcript && (
        <div className="flex items-start gap-2">
          <Mic size={18} className="mt-1 shrink-0" style={{ color: CYAN_TEXT }} aria-hidden="true" />
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide" style={{ color: CYAN_TEXT }}>
              Suna / Heard
            </div>
            <div className="text-xl font-semibold leading-snug">&ldquo;{heard.transcript}&rdquo;</div>
          </div>
        </div>
      )}
      {heard.reply && <div className="mt-1.5 pl-7 text-base" style={{ color: '#33415C' }}>{heard.reply}</div>}
      {(heard.source || heard.timings) && (
        <div className="mt-1.5 pl-7">
          <SourceChip source={heard.source} latency={heard.latency} timings={heard.timings} demo={heard.demo} />
        </div>
      )}
    </div>
  )
}

export function IdleView({ store, connected, tally, listening, processing, heard }) {
  return (
    <div className="flex h-full flex-col">
      <HeardBubble heard={heard} />
      <div className="flex flex-1 flex-col items-center justify-center text-center">
        <div className="text-sm font-semibold uppercase tracking-[0.18em]" style={{ color: '#4A5873' }}>
          {store}
        </div>
        <Bars active={connected && !processing} height={64} className="my-5" />
        <div className="text-5xl font-bold" lang="hi">
          {processing ? 'समझ रहा है…' : listening ? 'रिकॉर्ड हो रहा है…' : 'सुन रहा है'}
        </div>
        <div className="mt-1 text-2xl font-medium" style={{ color: CYAN_TEXT }}>
          {processing ? 'Samajh raha hai' : listening ? 'Recording' : connected ? 'Sun raha hai · Listening' : 'Offline · reconnecting'}
        </div>
        <div className="mt-8 max-w-md text-lg" style={{ color: '#4A5873' }} lang="hi">
          बोलिए: &ldquo;दो मैगी, एक सर्फ एक्सेल, चार कोलगेट&rdquo;
        </div>
        {tally != null && (
          <div className="mt-6 rounded-full px-5 py-2 text-lg font-semibold" style={{ background: '#ECF0F4' }}>
            आज की बिक्री / Today <span className="ml-1 font-bold">₹{inr(tally)}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export function BillView({ cart, heard }) {
  const lines = cart?.lines || []
  const weigh = lines.filter((l) => l.weigh_instruction)
  return (
    <div className="flex h-full flex-col">
      <HeardBubble heard={heard} />
      <div className="mb-2 flex items-baseline justify-between">
        <div className="text-3xl font-bold" lang="hi">
          बिल <span className="text-xl font-semibold" style={{ color: '#4A5873' }}>Bill</span>
        </div>
        <div className="text-base font-medium" style={{ color: '#4A5873' }}>
          {lines.length} item{lines.length === 1 ? '' : 's'}
          {cart?.customer?.name ? ` · ${cart.customer.name}` : ''}
        </div>
      </div>

      {weigh.length > 0 && (
        <div
          className="mb-3 flex items-center gap-3 rounded-2xl px-4 py-3 font-bold"
          style={{ background: '#FFE9D1', color: '#7A3A00' }}
          role="status"
        >
          <Scale size={30} aria-hidden="true" />
          <div className="text-3xl leading-tight" lang="hi">
            {weigh.map((l) => `${l.name}: ${l.weigh_instruction}`).join(' · ')}
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="text-xs font-semibold uppercase tracking-wide" style={{ color: '#4A5873' }}>
              <th className="pb-1 font-semibold">Item</th>
              <th className="pb-1 text-right font-semibold">Qty</th>
              <th className="pb-1 text-right font-semibold">Rate</th>
              <th className="pb-1 text-right font-semibold">Total</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((l) => (
              <tr key={`${l.product_id}-${l.unit}`} className="border-t" style={{ borderColor: '#E3E8EF' }}>
                <td className="py-2 pr-2">
                  <div className="text-2xl font-bold leading-tight">{l.name}</div>
                  {l.name_hi && (
                    <div className="text-base" style={{ color: '#4A5873' }} lang="hi">
                      {l.name_hi}
                    </div>
                  )}
                </td>
                <td className="whitespace-nowrap py-2 text-right text-2xl font-semibold">
                  {qty(l.qty)}
                  <span className="ml-1 text-base font-medium" style={{ color: '#4A5873' }}>
                    {l.unit}
                  </span>
                </td>
                <td className="whitespace-nowrap py-2 text-right text-lg" style={{ color: '#4A5873' }}>
                  ₹{inr(l.unit_price)}
                </td>
                <td className="whitespace-nowrap py-2 pl-3 text-right text-2xl font-bold">₹{inr(l.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 flex items-end justify-between border-t-2 pt-3" style={{ borderColor: INK }}>
        <div>
          <div className="text-2xl font-bold" lang="hi">
            कुल <span className="text-lg font-semibold" style={{ color: '#4A5873' }}>Total</span>
          </div>
          {cart?.cgst_total != null && (
            <div className="text-sm" style={{ color: '#4A5873' }}>
              GST shaamil: CGST ₹{inr(cart.cgst_total)} + SGST ₹{inr(cart.sgst_total)}
            </div>
          )}
        </div>
        <div className="text-6xl font-bold leading-none">₹{inr(cart?.total)}</div>
      </div>
    </div>
  )
}

export function QrView({ checkout, heard }) {
  const value = checkout.upi_string || checkout.qr_payload
  const due = checkout.amount_due ?? checkout.total
  const split = checkout.total != null && Math.abs(Number(checkout.total) - Number(due)) > 0.009
  const items = checkout.items || []
  return (
    <div className="flex h-full flex-col">
      <HeardBubble heard={heard} />
      <div className="grid min-h-0 flex-1 grid-cols-1 items-center gap-6 md:grid-cols-[auto_1fr]">
        <div className="mx-auto">
          {value ? (
            <div className="rounded-3xl border-4 bg-white p-4" style={{ borderColor: INK }}>
              <QRCode value={value} size={248} fgColor={INK} bgColor="#FFFFFF" level="M" aria-label={`UPI QR for rupees ${due}`} />
            </div>
          ) : (
            <div className="grid h-64 w-64 place-items-center rounded-3xl text-center" style={{ background: '#ECF0F4' }}>
              QR available nahi
            </div>
          )}
          <div className="mt-2 text-center text-sm font-medium" style={{ color: '#4A5873' }}>
            Order {checkout.order_id}
          </div>
        </div>
        <div className="min-w-0">
          <div className="text-xl font-semibold" lang="hi" style={{ color: CYAN_TEXT }}>
            स्कैन करके भरें · Scan to pay
          </div>
          <div className="text-[88px] font-bold leading-none tracking-tight">₹{inr(due)}</div>
          {split && (
            <div className="mt-1 text-lg font-medium" style={{ color: ORANGE_TEXT }}>
              Kul ₹{inr(checkout.total)}; baaki cash / khata mein
            </div>
          )}
          {checkout.customer?.name && <div className="mt-1 text-lg font-semibold">{checkout.customer.name}</div>}
          <ul className="mt-4 max-h-36 space-y-0.5 overflow-y-auto pr-1 text-lg">
            {items.map((it, i) => (
              <li key={i} className="flex justify-between gap-3">
                <span className="truncate">
                  {qty(it.qty)} {it.unit} {it.name}
                </span>
                <span className="font-semibold">₹{inr(it.total)}</span>
              </li>
            ))}
          </ul>
          {checkout.khata_warning && (
            <div className="mt-3 flex items-start gap-2 rounded-xl px-3 py-2 text-base font-medium" style={{ background: '#FFE9D1', color: '#7A3A00' }}>
              <AlertTriangle size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
              {checkout.khata_warning}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function PaidView({ paid }) {
  const low = paid.low_stock || []
  const receipt = localUrl(paid.receipt_url)
  return (
    <div className="flex h-full flex-col items-center justify-center text-center">
      <CheckCircle2 size={84} style={{ color: '#1E8E3E' }} aria-hidden="true" className="sb-pop" />
      <div className="mt-2 text-xl font-semibold" lang="hi" style={{ color: '#1E7A38' }}>
        पेमेंट मिल गया · Payment received
      </div>
      <div className="text-[110px] font-bold leading-none tracking-tight">₹{inr(paid.amount)}</div>
      <div className="mt-1 text-3xl font-semibold" lang="hi">
        ₹{inr(paid.amount)} प्राप्त हुए
        <span className="ml-3 text-2xl font-medium" style={{ color: '#4A5873' }}>
          {paid.mode ? paid.mode.toUpperCase() : ''}
          {paid.customer?.name ? ` · ${paid.customer.name}` : ''}
        </span>
      </div>
      {paid.spoken_text && <div className="mt-2 max-w-2xl text-lg" style={{ color: '#4A5873' }}>{paid.spoken_text}</div>}
      {low.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {low.slice(0, 3).map((l) => (
            <li
              key={l.product_id}
              className="flex items-center justify-center gap-2 rounded-full px-5 py-2 text-xl font-semibold"
              style={{ background: l.level === 'low' || l.level === 'out' ? '#FFE0DE' : '#FFF1CC', color: l.level === 'low' || l.level === 'out' ? '#8C1A12' : '#6B4E00' }}
            >
              <Package size={22} aria-hidden="true" />
              {l.text}
            </li>
          ))}
        </ul>
      )}
      {receipt && (
        <a
          href={receipt}
          target="_blank"
          rel="noreferrer"
          className="mt-5 inline-flex min-h-[44px] items-center gap-2 rounded-full border-2 px-5 text-base font-semibold hover:bg-slate-50"
          style={{ borderColor: INK }}
        >
          <ExternalLink size={18} aria-hidden="true" /> Receipt dekhein · {paid.number}
        </a>
      )}
    </div>
  )
}

export function BriefView({ brief, onClose }) {
  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-start justify-between gap-4">
        <div>
          <div className="text-sm font-semibold uppercase tracking-[0.18em]" style={{ color: CYAN_TEXT }}>
            Subah ka brief · Morning brief
          </div>
          <div className="text-3xl font-bold" lang="hi">नमस्ते रमेश जी</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full border-2 hover:bg-slate-50"
          style={{ borderColor: '#B8C2D1' }}
          aria-label="Brief band karein"
        >
          <X size={22} aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pr-1 text-2xl leading-relaxed" lang="hi">
        {brief.text}
      </div>
      {brief.yesterday_total != null && (
        <div className="mt-3 inline-flex self-start rounded-full px-4 py-2 text-lg font-semibold" style={{ background: '#ECF0F4' }}>
          Kal ki sale ₹{inr(brief.yesterday_total)}
        </div>
      )}
    </div>
  )
}

const TONES = {
  info: { bg: '#E6F7FD', fg: '#0B3C52', icon: Info },
  ok: { bg: '#E3F6E8', fg: '#14532D', icon: Check },
  warn: { bg: '#FFF1CC', fg: '#5C4300', icon: AlertTriangle },
  error: { bg: '#FFE0DE', fg: '#7A150E', icon: AlertTriangle },
}

export function Banners({ banners }) {
  return (
    <div className="pointer-events-none flex flex-col gap-1.5" aria-live="polite">
      {banners.map((b) => {
        const t = TONES[b.tone] || TONES.info
        const Icon = t.icon
        return (
          <div
            key={b.id}
            className="sb-slide flex items-center gap-2 truncate rounded-xl px-4 py-2 text-base font-semibold"
            style={{ background: t.bg, color: t.fg }}
          >
            <Icon size={18} className="shrink-0" aria-hidden="true" />
            <span className="truncate">{b.text}</span>
          </div>
        )
      })}
    </div>
  )
}

export function ProposalCard({ proposal, onConfirm, onCancel, busy }) {
  const p = proposal.payload || {}
  return (
    <div
      className="sb-slide mb-2 flex flex-wrap items-center gap-3 rounded-2xl border-2 px-4 py-3"
      style={{ borderColor: ORANGE, background: '#FFF6EA' }}
      role="alertdialog"
      aria-label="Confirm karein"
    >
      <div className="min-w-[220px] flex-1">
        <div className="text-sm font-semibold uppercase tracking-wide" style={{ color: ORANGE_TEXT }}>
          Confirm karein · {String(proposal.kind || '').replace(/_/g, ' ')}
        </div>
        <div className="text-xl font-bold leading-snug">{p.summary || proposal.spoken_text}</div>
      </div>
      <button
        type="button"
        disabled={busy}
        onClick={onConfirm}
        className="min-h-[48px] rounded-xl px-6 text-xl font-bold disabled:opacity-50"
        style={{ background: INK, color: '#fff' }}
      >
        हाँ · Haan
      </button>
      <button
        type="button"
        disabled={busy}
        onClick={onCancel}
        className="min-h-[48px] rounded-xl border-2 px-6 text-xl font-bold disabled:opacity-50"
        style={{ borderColor: INK }}
      >
        नहीं · Nahi
      </button>
    </div>
  )
}
