import { useState } from 'react'
import { Tabs } from '../../components/app/ui'
import BriefCard from '../../components/app/salaah/BriefCard'
import ReorderCards from '../../components/app/salaah/ReorderCards'
import AskTab from '../../components/app/salaah/AskTab'
import WaOrders from '../../components/app/salaah/WaOrders'
import { tr } from '../../lib/i18n'

const TABS = [
  { id: 'brief', label: tr('Aaj') },
  { id: 'reorder', label: tr('Order') },
  { id: 'ask', label: tr('Puchhein') },
  { id: 'orders', label: tr('WhatsApp') },
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
