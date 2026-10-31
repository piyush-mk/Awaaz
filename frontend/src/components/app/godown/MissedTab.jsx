import { useState } from 'react'
import { Plus, SearchX } from 'lucide-react'
import { Btn, Empty, ErrorBox, Rows, SkeletonList, inputCls } from '../ui'
import { useApp, useStoreEvent } from '../AppContext'
import useLoad from '../../../lib/useLoad'
import { addMissedSale, getMissedSales } from '../../../api/client'

/** What customers asked for and the shop did not have. */
export default function MissedTab() {
  const { showToast, showError } = useApp()
  const { data, loading, error, reload } = useLoad(() => getMissedSales(7), [])
  useStoreEvent('demo_reset', () => reload({ quiet: true }))
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const add = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    try {
      await addMissedSale(name.trim())
      showToast('Note ho gaya')
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
      <form onSubmit={add} className="flex gap-2">
        <input className={inputCls} aria-label="Kya nahi mila" placeholder="Kya nahi mila? jaise kurkure" value={name} onChange={(e) => setName(e.target.value)} />
        <Btn type="submit" busy={busy} disabled={!name.trim()} icon={Plus} variant="navy" aria-label="Note" className="flex-shrink-0 !px-3" />
      </form>
      {loading && !data && <SkeletonList rows={3} />}
      <ErrorBox error={error} onRetry={reload} />
      {data && data.items.length === 0 && <Empty icon={SearchX} hi="Is hafte kuch nahi" />}
      {data?.items.length > 0 && (
        <Rows>
          {data.items.map((r) => (
            <li key={r.product_name} className="min-h-[56px] px-4 py-2 flex items-center justify-between gap-3">
              <span className="font-hindi text-lg font-semibold truncate">{r.product_name}</span>
              <span className="text-[15px] text-ink-3 tabular whitespace-nowrap">{r.count} baar</span>
            </li>
          ))}
        </Rows>
      )}
    </div>
  )
}
