interface Props {
  size?: number
  withWordmark?: boolean
}

/** Shield (guard) + eye (watching) + falling amber line (cost going down). */
export function LogoMark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="CostWarden logo">
      <defs>
        <linearGradient id="cw-grad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5eead4" />
          <stop offset="1" stopColor="#0ea5a4" />
        </linearGradient>
      </defs>
      <path
        d="M32 4 56 12v18c0 15-10 25-24 30C18 55 8 45 8 30V12Z"
        fill="#0a1020"
        stroke="url(#cw-grad)"
        strokeWidth="3"
        strokeLinejoin="round"
      />
      <path d="M17 27q15-13 30 0-15 13-30 0Z" fill="none" stroke="url(#cw-grad)" strokeWidth="2.6" strokeLinejoin="round" />
      <circle cx="32" cy="27" r="5" fill="url(#cw-grad)" />
      <polyline
        points="20,41 27,42 33,47 39,46 43,50"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Logo({ size = 40, withWordmark = true }: Props) {
  return (
    <div className="logo">
      <LogoMark size={size} />
      {withWordmark && (
        <div className="logo-text">
          <span className="logo-name">
            Cost<span>Warden</span>
          </span>
          <span className="logo-tag">Guard the cloud. Keep the savings.</span>
        </div>
      )}
    </div>
  )
}
