import { useVoice } from '../VoiceContext'
import useLoad from '../../../lib/useLoad'
import { getAskExamples } from '../../../api/client'

/** Questions about the shop: tap one, or just ask the mic. The answer opens in a sheet. */
export default function AskTab() {
  const { submit, busy } = useVoice()
  const { data: ex } = useLoad(() => getAskExamples(), [])
  return (
    <ul className="divide-y divide-line">
      {(ex?.examples || []).slice(0, 4).map((q) => (
        <li key={q}>
          <button onClick={() => submit({ text: q })} disabled={busy} className="w-full min-h-[52px] text-left font-hindi text-lg text-ink">
            {q}
          </button>
        </li>
      ))}
    </ul>
  )
}
