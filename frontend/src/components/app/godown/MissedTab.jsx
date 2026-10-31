import { useState } from 'react'
import { Plus, SearchX } from 'lucide-react'
import { Btn, Card, Chip, Empty, ErrorBox, SkeletonList, inputCls } from '../ui'
import { useApp } from '../AppContext'
import useLoad from '../../../lib/useLoad'
import { addMissedSale, getMissedSales } from '../../../api/client'
import { shortDate } from '../../../lib/format'

/** What customers asked for and the shop did not have. */
export default function MissedTab() {
  const { showToast, showError } = useApp()
  const { data, loading, error, reload } = useLoad(() => getMissedSales(7), [])
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const add = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    try {
      const r = await addMissedSale(name.trim())
      showToast(`${r.product_name}: is hafte ${r.asked_this_week} baar maanga gaya`)
      setName('')
      reload({ quiet: true })
    } catch (err) {
      showError(err)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-3">
      <Card>
        <div className="font-hindi text-lg font-bold mb-2">Kisi ne kuch maanga jo nahi tha?</div>
        <form onSubmit={add} className="flex gap-2">
          <input className={inputCls} placeholder="jaise: kurkure" value={name} onChange={(e) => setName(e.target.value)} />
          <Btn type="submit" busy={busy} disabled={!name.trim()} icon={Plus} className="flex-shrink-0">Note</Btn>
        </form>
      </Card>
      {loading && !data && <SkeletonList rows={3} />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={SearchX} hi="Is hafte koi nahi laut kar gaya" />}
      {data && data.items.length > 0 && (
        <>
          <div className="px-1 text-sm text-ink-3">Is hafte {data.total_asks} baar maanga gaya</div>
          <ul className="divide-y divide-line">
            {data.items.map((r) => (
              <li key={r.product_name} className="py-3 flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-bg-app text-ink flex items-center justify-center text-xl font-bold tabular flex-shrink-0">{r.count}</div>
                <div className="min-w-0 flex-1">
                  <div className="font-hindi text-lg font-bold">{r.product_name}</div>
                  <div className="text-sm text-ink-3">{r.suggestion}</div>
                  <div className="text-xs text-ink-3">aakhri baar {shortDate(r.last_asked)}</div>
                </div>
                {!r.in_catalog && <Chip tone="orange">catalog mein nahi</Chip>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
