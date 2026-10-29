import { useState } from 'react'
import { SectionTitle, Tabs } from '../../components/app/ui'
import StockTab from '../../components/app/godown/StockTab'
import BillScanTab from '../../components/app/godown/BillScanTab'
import ShelfTab from '../../components/app/godown/ShelfTab'
import VoiceStockTab from '../../components/app/godown/VoiceStockTab'
import ExpiryTab from '../../components/app/godown/ExpiryTab'
import MissedTab from '../../components/app/godown/MissedTab'

const TABS = [
  { id: 'stock', hi: 'स्टॉक', en: 'Stock' },
  { id: 'bill', hi: 'बिल स्कैन', en: 'Bill scan' },
  { id: 'shelf', hi: 'शेल्फ', en: 'Shelf' },
  { id: 'voice', hi: 'बोलकर', en: 'Voice' },
  { id: 'expiry', hi: 'एक्सपायरी', en: 'Expiry' },
  { id: 'missed', hi: 'छूटी बिक्री', en: 'Missed' },
]

export default function Godown() {
  const [tab, setTab] = useState('stock')
  return (
    <div className="px-4 pt-3 pb-6">
      <SectionTitle hi="गोदाम" en="Godown: maal ka hisaab" />
      <Tabs items={TABS} value={tab} onChange={setTab} />
      <div className="mt-2">
        {tab === 'stock' && <StockTab />}
        {tab === 'bill' && <BillScanTab />}
        {tab === 'shelf' && <ShelfTab />}
        {tab === 'voice' && <VoiceStockTab />}
        {tab === 'expiry' && <ExpiryTab />}
        {tab === 'missed' && <MissedTab />}
      </div>
    </div>
  )
}
