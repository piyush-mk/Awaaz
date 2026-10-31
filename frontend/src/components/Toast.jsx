import { useEffect } from 'react'
import { CheckCircle, AlertTriangle, X } from 'lucide-react'
import { tr } from '../lib/i18n'

export default function Toast({ message, type = 'success', onClose }) {
  useEffect(() => {
    const t = setTimeout(onClose, 3500)
    return () => clearTimeout(t)
  }, [onClose])

  const styles = {
    success: 'bg-ink text-white',
    error: 'bg-red-700 text-white',
    warning: 'bg-accent text-ink',
  }

  const Icon = type === 'success' ? CheckCircle : AlertTriangle

  return (
    <div className="fixed bottom-28 inset-x-0 z-50 flex justify-center px-4 pointer-events-none">
      <div role="status" className={`pointer-events-auto w-full max-w-[380px] animate-slide-up rounded-xl px-4 py-3 flex items-center gap-3 shadow-lg ${styles[type]}`}>
        <Icon size={20} className="flex-shrink-0" />
        <span className="text-sm font-medium flex-1">{message}</span>
        <button onClick={onClose} aria-label={tr('Sandesh hatayein')} className="flex-shrink-0 opacity-75">
          <X size={16} />
        </button>
      </div>
    </div>
  )
}
