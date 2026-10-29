import { useEffect, useRef, useState } from 'react'
import { AudioLines, ImagePlus, Mic, Send, X } from 'lucide-react'
import useMic from '../sb/useMic'
import { WA } from './Bubble'

const PHRASES = [
  ['', 'Voice STT: auto'],
  ['1', '1 do maggi ek surf excel chaar colgate'],
  ['2', '2 das packet maggi paanch kilo chawal'],
  ['3', '3 aashirvaad atta teen bag'],
  ['4', '4 paanch dettol sabun teen vim bar'],
  ['5', '5 ek patanjali shahad do colgate'],
  ['6', '6 do maggi ek surf bees rupaye ki cheeni'],
  ['7', '7 verma ji ke khate mein paanch sau'],
  ['8', '8 teen sau cash do sau paytm'],
  ['9', '9 kurkure nahi hai'],
  ['10', '10 bas kitna hua'],
]

function QuickButton({ children, onClick, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="min-h-[44px] rounded-full border bg-white px-4 text-sm font-semibold hover:bg-[#F0F2F5] disabled:opacity-50"
      style={{ borderColor: '#C5CED3', color: WA.ink }}
    >
      {children}
    </button>
  )
}

/**
 * Composer. mode 'customer' plays the customer (text / voice note / photo to the shop number);
 * mode 'shop' sends a manual merchant message.
 */
export default function Composer({ mode, disabled, busy, onText, onVoiceBlob, onVoiceText, onImage, phrase, onPhrase }) {
  const [text, setText] = useState('')
  const [photo, setPhoto] = useState(null) // {file, url}
  const fileRef = useRef(null)
  const customer = mode === 'customer'

  const mic = useMic({ onRecorded: (blob, filename) => onVoiceBlob(blob, filename) })

  useEffect(() => () => photo && URL.revokeObjectURL(photo.url), [photo])

  const submit = (e) => {
    e?.preventDefault()
    const t = text.trim()
    if (photo) {
      onImage(photo.file, t)
      setPhoto(null)
      setText('')
      return
    }
    if (!t) return
    onText(t)
    setText('')
  }

  const pick = (e) => {
    const f = e.target.files?.[0]
    e.target.value = ''
    if (f) setPhoto({ file: f, url: URL.createObjectURL(f) })
  }

  return (
    <div className="border-t px-2 pb-2 pt-2" style={{ background: '#F0F2F5', borderColor: '#D5DADD' }}>
      {customer && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <QuickButton disabled={disabled || busy} onClick={() => onText('sahi hai')}>Reply sahi</QuickButton>
          <QuickButton disabled={disabled || busy} onClick={() => onText('galat hai')}>Reply galat</QuickButton>
          <QuickButton disabled={disabled || busy} onClick={() => onText('hi')}>Hi</QuickButton>
          <label className="ml-auto sr-only" htmlFor="wa-phrase">Fixture STT phrase</label>
          <select
            id="wa-phrase"
            value={phrase}
            onChange={(e) => onPhrase(e.target.value)}
            className="min-h-[44px] max-w-[190px] rounded-lg border bg-white px-2 text-xs"
            style={{ borderColor: '#C5CED3' }}
            title="Used by the fixture speech-to-text when no Sarvam key is set (DEMO_MODE)"
          >
            {PHRASES.map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </div>
      )}

      {photo && (
        <div className="mb-2 flex items-center gap-2 rounded-lg bg-white p-2">
          <img src={photo.url} alt="Chuni gayi photo" className="h-14 w-14 rounded object-cover" />
          <div className="min-w-0 flex-1 truncate text-sm">{photo.file.name} (caption likh sakte hain)</div>
          <button
            type="button"
            onClick={() => setPhoto(null)}
            className="grid h-11 w-11 place-items-center rounded-full hover:bg-black/5"
            aria-label="Photo hatayein"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
      )}

      {mic.recording && (
        <div className="mb-2 flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-sm font-semibold" role="status">
          <span className="inline-block h-3 w-3 animate-pulse rounded-full" style={{ background: '#D93025' }} aria-hidden="true" />
          Voice note record ho raha hai {mic.seconds}s. Chhodein ya dobara tap karein.
        </div>
      )}
      {mic.error && <div className="mb-2 text-sm font-semibold" style={{ color: '#B3261E' }} role="alert">{mic.error}</div>}

      <form onSubmit={submit} className="flex items-center gap-1.5">
        {customer && (
          <>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={pick} aria-label="Photo chunein" />
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              disabled={disabled || busy}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full hover:bg-black/5 disabled:opacity-50"
              aria-label="Photo attach karein (parchi)"
              title="Photo attach karein (parchi)"
              style={{ color: WA.sub }}
            >
              <ImagePlus size={22} aria-hidden="true" />
            </button>
          </>
        )}
        <label htmlFor="wa-text" className="sr-only">Message</label>
        <input
          id="wa-text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={customer ? 'Customer ki taraf se likhein...' : 'Dukaan ki taraf se message...'}
          className="min-h-[44px] min-w-0 flex-1 rounded-full border-0 bg-white px-4 text-[15px] outline-none focus:ring-2 focus:ring-[#00A884]"
          autoComplete="off"
          disabled={disabled}
        />
        {customer && (
          <>
            <button
              type="button"
              onClick={() => {
                const t = text.trim()
                if (t) {
                  onVoiceText(t)
                  setText('')
                }
              }}
              disabled={disabled || busy || !text.trim()}
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full hover:bg-black/5 disabled:opacity-40"
              aria-label="Likha hua text voice note ki tarah bhejein"
              title="Likha hua text voice note ki tarah bhejein (transcript)"
              style={{ color: WA.sub }}
            >
              <AudioLines size={22} aria-hidden="true" />
            </button>
            <button
              type="button"
              onPointerDown={mic.pressStart}
              onPointerUp={mic.pressEnd}
              onPointerCancel={mic.pressEnd}
              onPointerLeave={mic.pressEnd}
              onClick={mic.keyboardToggle}
              disabled={disabled || busy}
              aria-pressed={mic.recording}
              aria-label={mic.recording ? 'Voice note bhejein' : 'Voice note record karein'}
              className="grid h-11 w-11 shrink-0 select-none place-items-center rounded-full disabled:opacity-50"
              style={{ background: mic.recording ? '#D93025' : '#E3E8EB', color: mic.recording ? '#fff' : WA.ink, touchAction: 'none' }}
            >
              <Mic size={22} aria-hidden="true" />
            </button>
          </>
        )}
        <button
          type="submit"
          disabled={disabled || busy || (!text.trim() && !photo)}
          className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-white disabled:opacity-50"
          style={{ background: WA.header }}
          aria-label="Bhejein"
        >
          <Send size={20} aria-hidden="true" />
        </button>
      </form>
    </div>
  )
}
