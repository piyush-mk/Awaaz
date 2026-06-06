import { useEffect, useState } from 'react'
import { InventoryCard } from '../components/ItemCard'
import { getDashboard, getInventory } from '../api/client'
import { AlertTriangle, TrendingUp, Package, IndianRupee } from 'lucide-react'

// feat/inventory branch: build out this page fully with charts (recharts), transactions list, alerts

export default function Dashboard() {
  const [stats, setStats] = useState(null)
  const [inventory, setInventory] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([getDashboard(), getInventory()])
      .then(([s, inv]) => {
        setStats(s)
        setInventory(inv)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="p-4 space-y-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="card h-16 animate-pulse bg-gray-100" />
        ))}
      </div>
    )
  }

  const lowStock = inventory.filter((i) => i.status === 'low')

  return (
    <div className="p-4 space-y-4">
      {/* Low stock alert banner */}
      {lowStock.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3 flex items-center gap-2">
          <AlertTriangle size={18} className="text-stock-red flex-shrink-0" />
          <span className="text-sm font-medium text-red-700">
            {lowStock.length} items कम स्टॉक में: {lowStock.map((i) => i.name_hi).join(', ')}
          </span>
        </div>
      )}

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3">
        <div className="card">
          <div className="flex items-center gap-2 text-gray-500 mb-1">
            <IndianRupee size={14} />
            <span className="text-xs">Stock Value</span>
          </div>
          <div className="text-xl font-bold text-gray-900">₹{stats?.total_stock_value?.toLocaleString('en-IN') ?? 0}</div>
        </div>
        <div className="card">
          <div className="flex items-center gap-2 text-gray-500 mb-1">
            <TrendingUp size={14} />
            <span className="text-xs">Today's Sales</span>
          </div>
          <div className="text-xl font-bold text-stock-green">₹{stats?.today_sales?.toLocaleString('en-IN') ?? 0}</div>
        </div>
      </div>

      {/* Top selling */}
      {stats?.top_selling?.length > 0 && (
        <div className="card space-y-2">
          <h3 className="font-semibold text-gray-700 flex items-center gap-2">
            <TrendingUp size={16} className="text-paytm-blue" /> Top Selling (7 days)
          </h3>
          {stats.top_selling.map((item) => (
            <div key={item.product_id} className="flex justify-between items-center">
              <div>
                <div className="text-sm font-medium">{item.name_hi}</div>
                <div className="text-xs text-gray-400">{item.name}</div>
              </div>
              <div className="text-right">
                <div className="text-sm font-bold text-paytm-blue">{item.total_qty} units</div>
                <div className="text-xs text-gray-400">₹{item.total_amount}</div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Inventory list */}
      <div>
        <h3 className="font-semibold text-gray-700 mb-2 flex items-center gap-2">
          <Package size={16} className="text-paytm-blue" /> सभी स्टॉक
        </h3>
        <div className="space-y-2">
          {inventory.map((item) => (
            <InventoryCard key={item.product_id} item={item} />
          ))}
        </div>
      </div>
    </div>
  )
}
