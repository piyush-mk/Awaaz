import { useState } from 'react'
import { SectionTitle, Tabs } from '../../components/app/ui'
import BriefCard from '../../components/app/salaah/BriefCard'
import ReorderCards from '../../components/app/salaah/ReorderCards'
import MunimAsk from '../../components/app/salaah/MunimAsk'
import WaOrders from '../../components/app/salaah/WaOrders'

const TABS = [
  { id: 'brief', hi: 'सुबह की सलाह', en: 'Brief' },
  { id: 'reorder', hi: 'ऑर्डर', en: 'Reorder' },
  { id: 'munim', hi: 'मुनीम से पूछो', en: 'Ask' },
  { id: 'orders', hi: 'WhatsApp ऑर्डर', en: 'Orders' },
]

export default function Salaah() {
  const [tab, setTab] = useState('brief')
  return (
    <div className="px-4 pt-3 pb-6">
      <SectionTitle hi="सलाह" en="Salaah: munim ki raay" />
      <Tabs items={TABS} value={tab} onChange={setTab} />
      <div className="mt-2">
        {tab === 'brief' && <BriefCard />}
        {tab === 'reorder' && <ReorderCards />}
        {tab === 'munim' && <MunimAsk />}
        {tab === 'orders' && <WaOrders />}
      </div>
    </div>
  )
}
