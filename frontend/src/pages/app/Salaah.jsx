import { useState } from 'react'
import { Tabs } from '../../components/app/ui'
import BriefCard from '../../components/app/salaah/BriefCard'
import ReorderCards from '../../components/app/salaah/ReorderCards'
import AskTab from '../../components/app/salaah/AskTab'
import WaOrders from '../../components/app/salaah/WaOrders'

const TABS = [
  { id: 'brief', label: 'Aaj' },
  { id: 'reorder', label: 'Order' },
  { id: 'ask', label: 'Puchhein' },
  { id: 'orders', label: 'WhatsApp' },
]

export default function Salaah() {
  const [tab, setTab] = useState('brief')
  return (
    <div className="px-4 pb-16">
      <Tabs items={TABS} value={tab} onChange={setTab} />
      <div className="mt-4">
        {tab === 'brief' && <BriefCard />}
        {tab === 'reorder' && <ReorderCards />}
        {tab === 'ask' && <AskTab />}
        {tab === 'orders' && <WaOrders />}
      </div>
    </div>
  )
}
