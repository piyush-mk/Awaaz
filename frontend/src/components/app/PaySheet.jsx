import { useEffect, useState } from 'react'
import { Banknote, Smartphone, BookOpen, SlidersHorizontal } from 'lucide-react'
import { Sheet, Btn, inputCls } from './ui'
import CustomerSheet from './CustomerSheet'
import { inr } from '../../lib/format'
import { tr } from '../../lib/i18n'

const MODES = [
  { id: 'upi', icon: Smartphone, label: tr('Paytm') },
  { id: 'cash', icon: Banknote, label: tr('Cash') },
  { id: 'khata', icon: BookOpen, label: tr('Khata') },
  { id: 'mix', icon: SlidersHorizontal, label: tr('Mix') },
]

/** Tap how the money came: that tap is the confirmation. Khata asks whose first; Mix asks how much of each. */
export default function PaySheet({ open, onClose, total, customer, onConfirm, busy }) {
  const [mix, setMix] = useState(false)
  const [cash, setCash] = useState('')
  const [khata, setKhata] = useState('')
  const [pending, setPending] = useState(null) // splits waiting for a khata customer

  useEffect(() => {
    if (!open) return
    setMix(false)
    setCash('')
    setKhata('')
    setPending(null)
  }, [open])

  const custId = customer?.id ?? customer?.customer_id
  const send = (splits, id = custId) => {
    const body = {}
    if (id) body.customer_id = id
    if (splits) body.splits = { ...splits, upi: null }
    onConfirm(body)
  }
  const withKhata = (splits) => (custId ? send(splits) : setPending(splits))

  const tap = (id) => {
    if (id === 'upi') send(null)
    else if (id === 'cash') send({ cash: total, khata: 0 })
    else if (id === 'khata') withKhata({ cash: 0, khata: total })
    else setMix(true)
  }

  const cashN = Number(cash) || 0
  const khataN = Number(khata) || 0
  const upiN = Math.round((total - cashN - khataN) * 100) / 100

  return (
    <Sheet open={open} onClose={onClose} title={<span className="text-3xl tabular">{inr(total)}</span>}>
      {!mix ? (
        <div className="grid grid-cols-2 gap-3">
          {MODES.map(({ id, icon: Icon, label }) => (
            <button
              key={id}
              onClick={() => tap(id)}
              disabled={busy}
              className="min-h-[96px] rounded-2xl bg-bg-app flex flex-col items-center justify-center gap-2 text-lg font-semibold active:bg-line disabled:opacity-50"
            >
              <Icon size={28} className="text-paytm-blue-dark" />
              {tr(label)}
            </button>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <input className={`${inputCls} text-center text-lg`} inputMode="decimal" aria-label={tr('Cash')} placeholder={tr('Cash')} value={cash} onChange={(e) => setCash(e.target.value)} autoFocus />
            <input className={`${inputCls} text-center text-lg`} inputMode="decimal" aria-label={tr('Khata')} placeholder={tr('Khata')} value={khata} onChange={(e) => setKhata(e.target.value)} />
          </div>
          <Btn
            size="lg"
            variant="navy"
            className="w-full"
            busy={busy}
            disabled={upiN < 0 || (cashN <= 0 && khataN <= 0)}
            onClick={() => (khataN > 0 ? withKhata({ cash: cashN, khata: khataN }) : send({ cash: cashN, khata: 0 }))}
          >
            {upiN < 0 ? tr('Bill se zyada') : upiN > 0 ? tr('Paytm {amt} ka QR', { amt: inr(upiN) }) : tr('Ho gaya')}
          </Btn>
        </div>
      )}
      <CustomerSheet
        open={!!pending}
        onClose={() => setPending(null)}
        onPick={(c) => {
          const splits = pending
          setPending(null)
          send(splits, c.id)
        }}
        title={tr('Kiske khate mein?')}
      />
    </Sheet>
  )
}
