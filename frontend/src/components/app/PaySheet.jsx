import { useEffect, useMemo, useState } from 'react'
import { Banknote, Smartphone, BookOpen, SlidersHorizontal } from 'lucide-react'
import { Sheet, Field, inputCls, Chip } from './ui'
import ConfirmCard from './ConfirmCard'
import CustomerSheet from './CustomerSheet'
import { inr } from '../../lib/format'

const MODES = [
  { id: 'upi', icon: Smartphone, hi: 'Paytm', en: 'UPI QR' },
  { id: 'cash', icon: Banknote, hi: 'Cash', en: 'Naqad' },
  { id: 'khata', icon: BookOpen, hi: 'Khata', en: 'Udhaar' },
  { id: 'mix', icon: SlidersHorizontal, hi: 'Mix', en: 'Aadha-aadha' },
]

/** Split-payment sheet: cash / UPI / khata. UPI is always "the rest". onConfirm({ splits?, customer_id? }). */
export default function PaySheet({ open, onClose, total, customer, onConfirm, busy }) {
  const [mode, setMode] = useState('upi')
  const [cash, setCash] = useState('')
  const [khata, setKhata] = useState('')
  const [picked, setPicked] = useState(null)
  const [pickOpen, setPickOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    setMode('upi')
    setCash('')
    setKhata('')
    setPicked(null)
  }, [open])

  const who = picked || customer || null
  const cashN = mode === 'cash' ? total : mode === 'mix' ? Number(cash) || 0 : 0
  const khataN = mode === 'khata' ? total : mode === 'mix' ? Number(khata) || 0 : 0
  const upiN = Math.round((total - cashN - khataN) * 100) / 100
  const invalid = upiN < 0 || (khataN > 0 && !who)

  const summary = useMemo(
    () =>
      [cashN > 0 && `Cash ${inr(cashN)}`, upiN > 0 && `Paytm ${inr(upiN)}`, khataN > 0 && `Khata ${inr(khataN)}`]
        .filter(Boolean)
        .join(', '),
    [cashN, upiN, khataN],
  )

  const go = () => {
    const custId = who?.id ?? who?.customer_id
    const body = {}
    if (custId) body.customer_id = custId
    if (cashN > 0 || khataN > 0) body.splits = { cash: cashN, khata: khataN, upi: null }
    onConfirm(body)
  }

  return (
    <Sheet open={open} onClose={onClose} title="Paisa kaise milega?">
      <div className="text-center mb-3">
        <div className="text-sm text-ink-3">Bill total</div>
        <div className="text-4xl font-bold tabular text-ink">{inr(total)}</div>
      </div>

      <div className="grid grid-cols-4 gap-2 mb-4">
        {MODES.map(({ id, icon: Icon, hi, en }) => (
          <button
            key={id}
            onClick={() => setMode(id)}
            className={`min-h-[72px] rounded-xl flex flex-col items-center justify-center gap-0.5 ${
              mode === id ? 'bg-ink text-white' : 'bg-bg-app text-ink'
            }`}
          >
            <Icon size={20} className={mode === id ? 'text-paytm-blue' : 'text-ink-3'} />
            <span className="font-hindi text-sm font-bold leading-none">{hi}</span>
            <span className={`text-[11px] leading-none ${mode === id ? 'text-white/70' : 'text-ink-3'}`}>{en}</span>
          </button>
        ))}
      </div>

      {mode === 'mix' && (
        <div className="grid grid-cols-2 gap-3 mb-3">
          <Field label="Cash kitna?">
            <input className={inputCls} inputMode="decimal" placeholder="0" value={cash} onChange={(e) => setCash(e.target.value)} />
          </Field>
          <Field label="Khate mein kitna?">
            <input className={inputCls} inputMode="decimal" placeholder="0" value={khata} onChange={(e) => setKhata(e.target.value)} />
          </Field>
        </div>
      )}

      {khataN > 0 && (
        <button
          onClick={() => setPickOpen(true)}
          className="w-full min-h-[52px] mb-3 rounded-xl bg-bg-app px-4 flex items-center justify-between"
        >
          <span className="text-sm text-ink-3">Kiske khate mein</span>
          <span className="font-hindi text-lg font-bold">{who ? who.name || who.customer : 'Customer chuniye'}</span>
        </button>
      )}

      <div className="mb-3 rounded-xl bg-bg-app p-3 text-sm space-y-1 tabular">
        <div className="flex justify-between"><span className="text-ink-3">Cash</span><b>{inr(cashN)}</b></div>
        <div className="flex justify-between"><span className="text-ink-3">Paytm / UPI (QR)</span><b>{inr(Math.max(upiN, 0))}</b></div>
        <div className="flex justify-between"><span className="text-ink-3">Khata</span><b>{inr(khataN)}</b></div>
        {upiN < 0 && <Chip tone="red">Jod bill se zyada hai</Chip>}
        {khataN > 0 && !who && <Chip tone="orange">Pehle customer chuniye</Chip>}
      </div>

      <ConfirmCard
        question={`Bill banaun? ${summary || inr(total)}`}
        busy={busy || invalid}
        onNo={onClose}
        onYes={go}
        yesLabel="Haan"
      />
      <CustomerSheet
        open={pickOpen}
        onClose={() => setPickOpen(false)}
        onPick={(c) => {
          setPicked(c)
          setPickOpen(false)
        }}
        title="Kiske khate mein?"
      />
    </Sheet>
  )
}
