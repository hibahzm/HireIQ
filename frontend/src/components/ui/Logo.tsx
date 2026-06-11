// Vector remake of docs/logo.png: a magnifying glass over a person, with
// circuit traces — "AI-powered talent search". Crisp at any size and
// animatable, unlike the raster original.

interface MarkProps {
  size?: number;
  animated?: boolean;
  className?: string;
}

const NODE_DELAYS = [350, 500, 650];

export function LogoMark({ size = 36, animated = false, className = "" }: MarkProps) {
  return (
    <svg
      width={size}
      height={size * (56 / 64)}
      viewBox="0 0 64 56"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      {/* Circuit traces */}
      <g stroke="#0284c7" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M25 20 H16 L11 14" className={animated ? "animate-logo-draw [stroke-dasharray:300]" : ""} />
        <path d="M23 28 H7" className={animated ? "animate-logo-draw [stroke-dasharray:300]" : ""} />
        <path d="M25 36 H16 L11 42" className={animated ? "animate-logo-draw [stroke-dasharray:300]" : ""} />
      </g>
      {/* Circuit nodes */}
      {[
        { cx: 8.5, cy: 11 },
        { cx: 4.5, cy: 28 },
        { cx: 8.5, cy: 45 },
      ].map((n, i) => (
        <circle
          key={i}
          cx={n.cx}
          cy={n.cy}
          r="2.6"
          fill="#0ea5e9"
          className={animated ? "animate-node-pop" : ""}
          style={animated ? { animationDelay: `${NODE_DELAYS[i]}ms`, transformOrigin: `${n.cx}px ${n.cy}px` } : undefined}
        />
      ))}
      {/* Lens */}
      <circle
        cx="40"
        cy="28"
        r="13.5"
        stroke="#0284c7"
        strokeWidth="4.5"
        className={animated ? "animate-logo-draw [stroke-dasharray:300]" : ""}
      />
      {/* Handle */}
      <path
        d="M50 38.5 L57 46"
        stroke="#0284c7"
        strokeWidth="5.5"
        strokeLinecap="round"
        className={animated ? "animate-logo-draw [stroke-dasharray:300]" : ""}
      />
      {/* Person inside the lens */}
      <g fill="#0ea5e9" className={animated ? "animate-scale-in" : ""} style={animated ? { animationDelay: "550ms", transformOrigin: "40px 28px" } : undefined}>
        <circle cx="40" cy="24" r="4.4" />
        <path d="M32.8 36.5 a7.2 6.4 0 0 1 14.4 0 Z" />
      </g>
    </svg>
  );
}

interface LogoProps extends MarkProps {
  /** Wordmark color scheme — set true on dark surfaces like the sidebar. */
  onDark?: boolean;
  withWordmark?: boolean;
}

export default function Logo({
  size = 36,
  animated = false,
  onDark = false,
  withWordmark = true,
  className = "",
}: LogoProps) {
  const wordmarkSize = size * 0.62;
  return (
    <span className={`inline-flex items-center gap-2 ${className}`}>
      <LogoMark size={size} animated={animated} />
      {withWordmark && (
        <span
          className={`font-extrabold tracking-tight ${animated ? "animate-fade-in" : ""}`}
          style={{ fontSize: wordmarkSize, ...(animated ? { animationDelay: "700ms" } : {}) }}
        >
          <span className={onDark ? "text-white" : "text-primary-800"}>Hire</span>
          <span className="text-brand-500">IQ</span>
        </span>
      )}
    </span>
  );
}
