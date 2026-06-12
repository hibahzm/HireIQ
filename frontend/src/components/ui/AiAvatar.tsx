// Robot recruiter avatar for the AI interviewer. Deliberately non-human so
// candidates always know they're talking to an AI — but dressed for the job:
// headset with mic boom, collar and tie, ID badge, and a clipboard it takes
// notes on while thinking.

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";

interface Props {
  state?: AvatarState;
  size?: number;
  className?: string;
}

const RING_COLORS: Partial<Record<AvatarState, string>> = {
  listening: "border-emerald-400/60",
  speaking: "border-brand-400/60",
};

const fillBox = { transformBox: "fill-box" as const };

function Mouth({ state, cx }: { state: AvatarState; cx: number }) {
  if (state === "speaking") {
    // Waveform mouth: five bars dancing at staggered phases
    return (
      <g fill="#38bdf8">
        {[-14, -8, -2, 4, 10].map((dx, i) => (
          <rect
            key={dx}
            x={cx + dx}
            y={60}
            width="4"
            height="12"
            rx="2"
            className="animate-sound-bar"
            style={{ ...fillBox, transformOrigin: "center bottom", animationDelay: `${i * 120}ms` }}
          />
        ))}
      </g>
    );
  }
  if (state === "thinking") {
    return (
      <g fill="#7dd3fc">
        {[-8, 0, 8].map((dx, i) => (
          <circle
            key={dx}
            cx={cx + dx}
            cy={66}
            r="2.5"
            className="animate-dot-bounce"
            style={{ ...fillBox, transformOrigin: "center", animationDelay: `${i * 150}ms` }}
          />
        ))}
      </g>
    );
  }
  // idle / listening: calm smile
  return (
    <path
      d={`M${cx - 10} 64 Q${cx} 70 ${cx + 10} 64`}
      stroke="#38bdf8"
      strokeWidth="3"
      strokeLinecap="round"
      fill="none"
    />
  );
}

function Eyes({ cx }: { cx: number }) {
  return (
    <>
      {[cx - 14, cx + 6].map((x) => (
        <rect
          key={x}
          x={x}
          y={41}
          width="8"
          height="14"
          rx="4"
          fill="#38bdf8"
          className="animate-blink"
          style={{ ...fillBox, transformOrigin: "center" }}
        />
      ))}
    </>
  );
}

/** Compact head-only version for tiny placements (chat message chips). */
function CompactRobot({ state, size }: { state: AvatarState; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 120 120" fill="none" role="img" aria-label={`Sila, the AI interviewer (${state})`}>
      <defs>
        <linearGradient id="ai-head-sm" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
      </defs>
      <line x1="60" y1="22" x2="60" y2="12" stroke="#0ea5e9" strokeWidth="4" strokeLinecap="round" />
      <circle cx="60" cy="9" r="4.5" fill="#38bdf8" />
      {/* Headset ear cups */}
      <rect x="12" y="44" width="11" height="24" rx="5" fill="#0284c7" />
      <rect x="97" y="44" width="11" height="24" rx="5" fill="#0284c7" />
      <rect x="20" y="22" width="80" height="68" rx="20" fill="url(#ai-head-sm)" stroke="#0ea5e9" strokeWidth="3" />
      <rect x="31" y="32" width="58" height="48" rx="13" fill="#020617" />
      <g transform="translate(0,4)">
        <Eyes cx={60} />
        <Mouth state={state} cx={60} />
      </g>
    </svg>
  );
}

/** Full robot-recruiter: headset + mic boom, collar and tie, ID badge, clipboard. */
function RecruiterRobot({ state, size }: { state: AvatarState; size: number }) {
  const speaking = state === "speaking";
  const listening = state === "listening";
  const thinking = state === "thinking";
  return (
    <svg
      width={size}
      height={size * (150 / 140)}
      viewBox="0 0 140 150"
      fill="none"
      role="img"
      aria-label={`Sila, the AI recruiter (${state})`}
      className={state === "idle" ? "animate-float" : ""}
    >
      <defs>
        <linearGradient id="ai-head" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#1e293b" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="ai-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#334155" />
          <stop offset="100%" stopColor="#0f172a" />
        </linearGradient>
        <linearGradient id="ai-tie" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
      </defs>

      {/* Antenna */}
      <line x1="70" y1="24" x2="70" y2="12" stroke="#0ea5e9" strokeWidth="3.5" strokeLinecap="round" />
      <circle cx="70" cy="9" r="4" fill="#38bdf8" className={speaking || thinking ? "animate-pulse" : ""} />

      {/* Headset band (drawn first so the head overlaps its base) */}
      <path d="M30 52 C30 24, 110 24, 110 52" stroke="#0284c7" strokeWidth="5" fill="none" strokeLinecap="round" />

      {/* Torso */}
      <path
        d="M40 150 V122 C40 107 51 98 62 98 H78 C89 98 100 107 100 122 V150 Z"
        fill="url(#ai-body)"
        stroke="#0ea5e9"
        strokeWidth="2"
      />
      {/* Neck */}
      <rect x="63" y="84" width="14" height="14" rx="3" fill="#0f172a" />
      {/* Collar */}
      <path d="M58 99 L70 112 L82 99 L77 96 L70 104 L63 96 Z" fill="#e2e8f0" />
      {/* Tie */}
      <rect x="66" y="110" width="8" height="6" rx="1.5" fill="url(#ai-tie)" />
      <path d="M70 116 L77 127 L70 144 L63 127 Z" fill="url(#ai-tie)" />
      {/* ID badge */}
      <rect x="85" y="116" width="12" height="15" rx="2" fill="#e2e8f0" />
      <circle cx="91" cy="121" r="2.2" fill="#0284c7" />
      <rect x="87.5" y="125.5" width="7" height="1.6" rx="0.8" fill="#94a3b8" />
      <rect x="87.5" y="128.2" width="5" height="1.6" rx="0.8" fill="#cbd5e1" />

      {/* Headset ear cups — glow green while listening */}
      <rect x="22" y="44" width="12" height="24" rx="5" fill={listening ? "#34d399" : "#0284c7"} className={listening ? "animate-pulse" : ""} />
      <rect x="106" y="44" width="12" height="24" rx="5" fill={listening ? "#34d399" : "#0284c7"} className={listening ? "animate-pulse" : ""} />

      {/* Head */}
      <rect x="34" y="24" width="72" height="62" rx="18" fill="url(#ai-head)" stroke="#0ea5e9" strokeWidth="2.5" />
      {/* Face screen */}
      <rect x="43" y="33" width="54" height="44" rx="12" fill="#020617" />

      <Eyes cx={70} />
      <Mouth state={state} cx={70} />

      {/* Mic boom from the left ear cup toward the mouth */}
      <path d="M28 68 C28 82, 40 88, 50 88" stroke="#0284c7" strokeWidth="3.5" fill="none" strokeLinecap="round" />
      <circle cx="53" cy="88" r="4" fill={speaking ? "#38bdf8" : "#0ea5e9"} className={speaking ? "animate-pulse" : ""} />

      {/* Clipboard — appears while the recruiter "takes notes" */}
      {thinking && (
        // Outer group holds the SVG transform; inner group animates (CSS
        // animations would otherwise override the transform attribute).
        <g transform="translate(106 100) rotate(8)">
          <g className="animate-scale-in" style={{ ...fillBox, transformOrigin: "center" }}>
          <rect width="26" height="32" rx="3" fill="#f1f5f9" stroke="#94a3b8" strokeWidth="1.5" />
          <rect x="8" y="-3" width="10" height="6" rx="2" fill="#64748b" />
          <rect x="4" y="9" width="18" height="2.2" rx="1.1" fill="#cbd5e1" />
          <rect x="4" y="15" width="18" height="2.2" rx="1.1" fill="#cbd5e1" />
          <rect x="4" y="21" width="11" height="2.2" rx="1.1" fill="#cbd5e1" />
          {/* Pen tip bobbing along the unfinished line */}
          <circle
            cx="19"
            cy="22"
            r="2.4"
            fill="#0284c7"
            className="animate-dot-bounce"
            style={{ ...fillBox, transformOrigin: "center" }}
          />
          </g>
        </g>
      )}
    </svg>
  );
}

export default function AiAvatar({ state = "idle", size = 120, className = "" }: Props) {
  const ring = RING_COLORS[state];
  const compact = size < 64;
  const height = compact ? size : size * (150 / 140);

  return (
    <div className={`relative inline-flex items-center justify-center ${className}`} style={{ width: size, height }}>
      {/* Pulse rings while listening / speaking */}
      {ring && !compact && (
        <>
          <span className={`absolute inset-1 rounded-full border-2 ${ring} animate-pulse-ring`} aria-hidden="true" />
          <span
            className={`absolute inset-1 rounded-full border-2 ${ring} animate-pulse-ring`}
            style={{ animationDelay: "600ms" }}
            aria-hidden="true"
          />
        </>
      )}
      {compact ? <CompactRobot state={state} size={size} /> : <RecruiterRobot state={state} size={size} />}
    </div>
  );
}
