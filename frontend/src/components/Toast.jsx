import { useEffect } from 'react'
import { CheckCircle, AlertTriangle, X } from 'lucide-react'

export default function Toast({ message, type = 'success', onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500)
    return () => clearTimeout(t)
  }, [onClose])

  const styles = {
    success: 'bg-stock-green text-white',
    error: 'bg-stock-red text-white',
    warning: 'bg-stock-yellow text-gray-900',
  }

  const Icon = type === 'success' ? CheckCircle : AlertTriangle

  return (
    <div className={`fixed bottom-24 left-1/2 -translate-x-1/2 w-[90%] max-w-[380px] z-50 animate-slide-up rounded-xl px-4 py-3 flex items-center gap-3 shadow-lg ${styles[type]}`}>
      <Icon size={20} className="flex-shrink-0" />
      <span className="text-sm font-medium flex-1">{message}</span>
      <button onClick={onClose} className="flex-shrink-0 opacity-75">
        <X size={16} />
      </button>
    </div>
  )
}
