import { useState } from 'react'
import { Tabs } from '../../components/app/ui'
import StockTab from '../../components/app/godown/StockTab'
import BillScanTab from '../../components/app/godown/BillScanTab'
import ShelfTab from '../../components/app/godown/ShelfTab'
import ExpiryTab from '../../components/app/godown/ExpiryTab'
import MissedTab from '../../components/app/godown/MissedTab'

const TABS = [
  { id: 'stock', label: 'Stock' },
  { id: 'bill', label: 'Bill scan' },
  { id: 'shelf', label: 'Shelf' },
  { id: 'expiry', label: 'Expiry' },
  { id: 'missed', label: 'Nahi mila' },
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
