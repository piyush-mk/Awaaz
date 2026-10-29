// Side screens (/soundbox, /wa, /status, /test) are full-width, outside the 430px phone frame.
// Pinning the page to the viewport keeps them independent of #root's width in index.css.
export const FONT = "'IBM Plex Sans', 'Noto Sans Devanagari', system-ui, -apple-system, 'Segoe UI', sans-serif"

export const INK = '#0E1B33'
export const INK2 = '#1B2330'
export const CYAN = '#00B9F5'
export const ORANGE = '#FF8A1F'
export const SOFT = '#ECF0F4'

export default function FullPage({ children, background = SOFT, color = INK, className = '' }) {
  return (
    <div
      className={`fixed inset-0 overflow-auto ${className}`}
      style={{ background, color, fontFamily: FONT, zIndex: 40 }}
    >
      {children}
    </div>
  )
}
