import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { inr } from '../../../lib/format'
import { tr } from '../../../lib/i18n'

const AXIS = { fontSize: 11, fill: '#46546B' }

/** Sales by hour today. Peak hour in navy, others in Paytm blue. */
export function HourlyChart({ data }) {
  const rows = (data || []).filter((h) => h.hour >= 7 && h.hour <= 22)
  const peak = Math.max(...rows.map((r) => r.total), 0)
  return (
    <div className="h-28">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
          <XAxis dataKey="hour" tick={AXIS} tickLine={false} axisLine={false} interval={1} tickFormatter={(h) => `${h}`} />
          <YAxis hide domain={[0, 'dataMax']} />
          <Tooltip
            cursor={{ fill: 'rgba(14,27,51,0.06)' }}
            formatter={(v) => [inr(v), tr('Sale')]}
            labelFormatter={(h) => `${h}:00`}
            contentStyle={{ borderRadius: 12, border: '1px solid #DDE3EA', fontSize: 12 }}
          />
          <Bar dataKey="total" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.hour} fill={r.total === peak && peak > 0 ? '#0E1B33' : '#00B9F5'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

/** 14 day sales. Today (partial) is drawn lighter; the best day is navy. */
export function SeriesChart({ data }) {
  const rows = data || []
  const best = Math.max(...rows.map((r) => r.total), 0)
  return (
    <div className="h-28">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
          <XAxis dataKey="weekday" tick={AXIS} tickLine={false} axisLine={false} interval={0} tickFormatter={(d) => d.slice(0, 1)} />
          <YAxis hide domain={[0, 'dataMax']} />
          <Tooltip
            cursor={{ fill: 'rgba(14,27,51,0.06)' }}
            formatter={(v, _n, p) => [inr(v), p.payload.partial ? tr('Aaj (abhi tak)') : tr('Sale')]}
            labelFormatter={(_l, p) => p?.[0]?.payload?.date || ''}
            contentStyle={{ borderRadius: 12, border: '1px solid #DDE3EA', fontSize: 12 }}
          />
          <Bar dataKey="total" radius={[4, 4, 0, 0]} isAnimationActive={false}>
            {rows.map((r) => (
              <Cell key={r.date} fill={r.partial ? '#8FDCF8' : r.total === best ? '#0E1B33' : '#00B9F5'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
