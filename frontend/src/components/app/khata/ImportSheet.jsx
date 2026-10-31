import { useEffect, useState } from 'react'
import { Sheet, Chip, Btn, inputCls } from '../ui'
import ConfirmCard from '../ConfirmCard'
import SourceChip from '../SourceChip'
import { confirmKhataImport } from '../../../api/client'
import { useApp } from '../AppContext'
import { inr } from '../../../lib/format'

/** Review rows read from a khata notebook photo, edit them, then confirm. */
export default function ImportSheet({ proposal, onClose, onDone }) {
  const { showError } = useApp()
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setRows((proposal?.rows || []).map((r) => ({ ...r })))
  }, [proposal])

  const update = (i, patch) => setRows((rs) => rs.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  const included = rows.filter((r) => r.include)
  const total = included.reduce((s, r) => s + (Number(r.amount) || 0), 0)

  const confirm = async () => {
    setBusy(true)
    try {
      const res = await confirmKhataImport(
        proposal.action_id,
        rows.map((r, index) => ({ index, include: r.include, name: r.name, amount: Number(r.amount) || 0 })),
      )
      onDone(res)
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet open={!!proposal} onClose={onClose} title="Notebook se padha">
      {proposal && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-ink-3">{rows.length} entry mili</span>
            <SourceChip source={proposal.source} latency={proposal.latency_ms} demo={proposal.source === 'fixture'} />
          </div>
          <ul className="space-y-2">
            {rows.map((r, i) => (
              <li key={i} className={`rounded-2xl bg-bg-app p-3 ${r.include ? '' : 'opacity-50'}`}>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={!!r.include}
                    onChange={(e) => update(i, { include: e.target.checked })}
                    className="w-6 h-6 accent-[#00B9F5] flex-shrink-0"
                    aria-label="shamil karein"
                  />
                  <input className={`${inputCls} font-hindi font-bold`} value={r.name} onChange={(e) => update(i, { name: e.target.value })} />
                  <input
                    className={`${inputCls} w-28 text-right tabular font-bold`}
                    inputMode="decimal"
                    value={r.amount}
                    onChange={(e) => update(i, { amount: e.target.value })}
                  />
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1.5 pl-8">
                  <Chip tone={r.action === 'create' ? 'blue' : 'green'}>{r.action === 'create' ? 'naya customer' : `${r.match?.name || 'purane'} mein jodo`}</Chip>
                  {r.date && <Chip>{r.date}</Chip>}
                  {r.note && <Chip>{r.note}</Chip>}
                </div>
              </li>
            ))}
          </ul>
          <ConfirmCard
            question={`${included.length} entry jodun? Kul ${inr(total)}`}
            busy={busy || included.length === 0}
            onYes={confirm}
            onNo={onClose}
            yesLabel="Haan, jodo"
            tone="orange"
          />
        </div>
      )}
    </Sheet>
  )
}
