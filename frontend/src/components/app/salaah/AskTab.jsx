import { Card, Spinner } from '../ui'
import { VoiceHint, useVoice } from '../VoiceContext'
import useLoad from '../../../lib/useLoad'
import { getAskExamples } from '../../../api/client'

/** Questions about the shop. The mic in the nav answers here too; answers open in a sheet. */
export default function AskTab() {
  const { submit, busy } = useVoice()
  const { data: ex } = useLoad(() => getAskExamples(), [])
  return (
    <div className="space-y-3">
      <VoiceHint />
      <ul className="divide-y divide-line">
        {(ex?.examples || []).slice(0, 6).map((q) => (
          <li key={q}>
            <button onClick={() => submit({ text: q })} disabled={busy} className="w-full min-h-[52px] text-left font-hindi text-base text-ink">
              {q}
            </button>
          </li>
        ))}
      </ul>
      {busy && <Card className="flex items-center gap-2 text-ink-3"><Spinner size={16} /> Dekh raha hoon</Card>}
    </div>
  )
}
