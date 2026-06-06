import { Plus, Minus } from 'lucide-react'

const STATUS_COLORS = {
  high: 'text-stock-green bg-green-50',
  medium: 'text-yellow-600 bg-yellow-50',
  low: 'text-stock-red bg-red-50',
}

export function InventoryCard({ item }) {
  return (
    <div className="card flex items-center gap-3">
      <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center text-xl flex-shrink-0">
        📦
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-base font-bold text-gray-900">{item.name_hi}</div>
        <div className="text-xs text-gray-500">{item.name} · ₹{item.price}/{item.unit}</div>
      </div>
      <div className="text-right flex-shrink-0">
        <div className={`text-sm font-bold px-2 py-0.5 rounded-full ${STATUS_COLORS[item.status]}`}>
          {item.quantity} {item.unit}
        </div>
        {item.status === 'low' && (
          <div className="text-[10px] text-stock-red mt-0.5">⚠ कम स्टॉक</div>
        )}
      </div>
    </div>
  )
}

export function ParsedItemCard({ item, onQtyChange }) {
  return (
    <div className="card flex items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="text-base font-bold text-gray-900">{item.name_hi}</div>
        <div className="text-xs text-gray-500">{item.name} · ₹{item.price}/{item.unit}</div>
      </div>
      {onQtyChange ? (
        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={() => onQtyChange(item.product_id, Math.max(1, item.quantity - 1))}
            className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center active:bg-gray-200"
          >
            <Minus size={14} />
          </button>
          <span className="text-base font-bold w-6 text-center">{item.quantity}</span>
          <button
            onClick={() => onQtyChange(item.product_id, item.quantity + 1)}
            className="w-8 h-8 rounded-full bg-paytm-blue text-white flex items-center justify-center active:bg-paytm-blue-dark"
          >
            <Plus size={14} />
          </button>
        </div>
      ) : (
        <div className="text-right flex-shrink-0">
          <div className="text-sm font-bold text-gray-800">{item.quantity} {item.unit}</div>
        </div>
      )}
    </div>
  )
}
