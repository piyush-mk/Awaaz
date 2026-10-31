import { useState } from 'react'
import { Camera } from 'lucide-react'
import PhotoButton from '../PhotoButton'
import ConfirmCard from '../ConfirmCard'
import SourceChip from '../SourceChip'
import { Btn, Card, Chip, Empty } from '../ui'
import { useApp } from '../AppContext'
import { cancelShelfAudit, confirmShelfAudit, shelfAudit } from '../../../api/client'
import { speak } from '../../../lib/audio'
import { inr, num } from '../../../lib/format'

/** Shelf photos -> expected (book) vs counted, loss value, then adjust stock. */
export default function ShelfTab() {
  const { showError, showToast } = useApp()
  const [busy, setBusy] = useState(false)
  const [audit, setAudit] = useState(null)
  const [counts, setCounts] = useState({})
  const [confirming, setConfirming] = useState(false)
  const [done, setDone] = useState(null)

  const reset = () => {
    setAudit(null)
    setDone(null)
    setCounts({})
  }

  const run = async (files) => {
    setBusy(true)
    reset()
    try {
      const res = await shelfAudit(files)
      setAudit(res)
      speak({ spoken_text: res.message_hi })
    } catch (e) {
      showError(e)
    } finally {
      setBusy(false)
    }
  }

  const rows = (audit?.rows || []).map((r) => {
    const counted = counts[r.product_id] ?? r.counted
    const variance = counted - r.expected
    return { ...r, counted, variance, variance_value: Math.round(variance * r.cost_price * 100) / 100 }
  })
  const loss = rows.reduce((s, r) => s + Math.min(r.variance_value, 0), 0)

  const confirm = async () => {
    setConfirming(true)
    try {
      const edited = {}
      Object.entries(counts).forEach(([k, v]) => (edited[k] = v))
      const res = await confirmShelfAudit(audit.action_id, { counts: edited })
      setDone(res)
      speak({ spoken_text: res.message_hi })
    } catch (e) {
      showError(e)
    } finally {
      setConfirming(false)
    }
  }

  const cancel = async () => {
    try {
      await cancelShelfAudit(audit.action_id)
      showToast('Audit chhod diya', 'warning')
    } catch (e) {
      showError(e)
    }
    reset()
  }

  if (done) {
    return (
      <Card className="text-center">
        <div className="font-hindi text-2xl font-bold">{done.message_hi}</div>
        <div className="text-ink-3 mt-1">Kul fark {inr(done.total_adjustment_value)}</div>
        <Btn className="w-full mt-4" variant="navy" onClick={reset}>Naya audit</Btn>
      </Card>
    )
  }

  if (!audit) {
    return (
      <div className="pt-16 flex justify-center">
        <PhotoButton variant="blue" multiple busy={busy} label="Shelf ki photo" onFiles={run} className="min-h-[64px] !px-8 text-lg" />
      </div>
    )
  }

  if (!rows.length) {
    return (
      <Empty icon={Camera} hi="Gin nahi paya">
        <PhotoButton variant="blue" multiple busy={busy} label="Doosri photo" onFiles={run} />
      </Empty>
    )
  }

  return (
    <div className="space-y-3">
      <Card>
        <div className="flex items-start gap-2">
          <div className="flex-1">
            <div className="text-sm text-ink-3">Nuksaan (cost par)</div>
            <div className={`text-3xl font-bold tabular ${loss < 0 ? 'text-stock-red' : 'text-ink'}`}>{inr(Math.abs(loss))}</div>
          </div>
          <SourceChip source={audit.source} latency={audit.latency_ms} demo={audit.demo_mode} />
        </div>
      </Card>

      <div className="overflow-hidden">
        <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 px-3 py-2 text-xs font-medium text-ink-3">
          <span></span><span className="text-right">Book</span><span className="text-right">Mila</span><span className="text-right">Fark</span>
        </div>
        {rows.map((r) => (
          <div key={r.product_id} className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 items-center px-3 py-2 border-t border-line">
            <div className="min-w-0">
              <div className="font-hindi text-base font-bold truncate">{r.name_hi || r.name}</div>
            </div>
            <div className="text-right tabular">{num(r.expected)}</div>
            <input
              inputMode="decimal"
              value={counts[r.product_id] ?? r.counted}
              onChange={(e) => setCounts((c) => ({ ...c, [r.product_id]: e.target.value === '' ? 0 : Number(e.target.value) }))}
              className="w-16 min-h-[44px] rounded-lg border border-line text-right px-2 tabular font-semibold"
            />
            <div className="text-right tabular">
              <Chip tone={r.variance < 0 ? 'red' : r.variance > 0 ? 'green' : 'gray'}>{r.variance > 0 ? '+' : ''}{num(r.variance)}</Chip>
            </div>
          </div>
        ))}
      </div>

      <ConfirmCard
        question="Stock sahi karun?"
        busy={confirming}
        onYes={confirm}
        onNo={cancel}
        yesLabel="Haan"
        tone="orange"
      />
    </div>
  )
}
