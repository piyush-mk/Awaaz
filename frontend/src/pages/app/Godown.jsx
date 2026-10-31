import { useState } from 'react'
import { Tabs } from '../../components/app/ui'
import StockTab from '../../components/app/godown/StockTab'
import BillScanTab from '../../components/app/godown/BillScanTab'
import ShelfTab from '../../components/app/godown/ShelfTab'
import ExpiryTab from '../../components/app/godown/ExpiryTab'
import MissedTab from '../../components/app/godown/MissedTab'
import { tr } from '../../lib/i18n'

const TABS = [
  { id: 'stock', label: tr('Stock') },
  { id: 'bill', label: tr('Bill scan') },
  { id: 'shelf', label: tr('Shelf') },
  { id: 'expiry', label: tr('Expiry') },
  { id: 'missed', label: tr('Nahi mila') },
]

export default function Godown() {
  const [tab, setTab] = useState('stock')
  return (
    <div className="px-4 pb-16">
      <Tabs items={TABS} value={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === 'stock' && <StockTab />}
        {tab === 'bill' && <BillScanTab />}
        {tab === 'shelf' && <ShelfTab />}
        {tab === 'expiry' && <ExpiryTab />}
        {tab === 'missed' && <MissedTab />}
      </div>
    </div>
  )
}
