import * as React from "react"
import { addPropertyControls, ControlType, RenderTarget } from "framer"

/**
 * GEEIQ brand check hero. The four-state checker flow:
 * 1 input -> 2 discovering (theatre, no network) -> 3 email gate -> 4 confirmation.
 *
 * No secret or signing key lives in this component. Signature verification,
 * domain re-validation and rate limiting all happen server-side in n8n.
 */

const FREE_EMAIL_DOMAINS = [
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "msn.com", "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com", "proton.me",
    "protonmail.com", "aol.com", "gmx.com", "gmx.co.uk", "mail.com",
    "yandex.com", "zoho.com",
]

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

const COLORS = {
    purple: "#7C68FB",
    amethyst: "#2E204D",
    offWhite: "#FAF7F2",
    coral: "#FC4F3F",
    white: "#FFFFFF",
    tint: "#EEEDFE",
    muted: "#5B5170",
    border: "#E6E1D8",
}

const FONT_HEAD = '"Plus Jakarta Sans", system-ui, sans-serif'
const FONT_BODY = '"Figtree", system-ui, sans-serif'

const DISCOVERY_STEPS = [
    "Scanning official activations",
    "Scanning creator-made content",
    "Checking branded items",
    "Reviewing category activity",
]

export default function BrandCheckHero(props) {
    const { webhookUrl, avatar, reportUrl, pageBackground } = props

    const [state, setState] = React.useState(1)
    const [brand, setBrand] = React.useState("")
    const [brandField, setBrandField] = React.useState("")
    const [brandError, setBrandError] = React.useState("")
    const [firstName, setFirstName] = React.useState("")
    const [lastName, setLastName] = React.useState("")
    const [jobTitle, setJobTitle] = React.useState("")
    const [emailField, setEmailField] = React.useState("")
    const [emailError, setEmailError] = React.useState("")
    const [sending, setSending] = React.useState(false)
    const [progress, setProgress] = React.useState(0)
    // 0 pending, 1 active (spinner), 2 done (tick)
    const [steps, setSteps] = React.useState([0, 0, 0, 0])

    const hpRef = React.useRef(null)
    const loadedAt = React.useRef(Date.now())
    const uid = React.useId().replace(/[^a-zA-Z0-9]/g, "")
    const isCanvas = RenderTarget.current() === RenderTarget.canvas

    // ---- State 2: discovery theatre. Timers only, no network. ----
    React.useEffect(() => {
        if (state !== 2 || isCanvas) return
        setProgress(0)
        setSteps([0, 0, 0, 0])
        const timers = []
        const at = (ms, fn) => timers.push(setTimeout(fn, ms))
        // Progress: fast start, brief pause near 70 percent, then complete
        at(40, () => setProgress(45))
        at(900, () => setProgress(68))
        at(1700, () => setProgress(70))
        at(2600, () => setProgress(88))
        at(3900, () => setProgress(100))
        const stepStart = [200, 1200, 2200, 3200]
        const stepDone = [1100, 2100, 3100, 3900]
        for (let i = 0; i < 4; i++) {
            at(stepStart[i], () =>
                setSteps((s) => s.map((v, j) => (j === i ? 1 : v)))
            )
            at(stepDone[i], () =>
                setSteps((s) => s.map((v, j) => (j === i ? 2 : v)))
            )
        }
        at(4200, () => setState(3))
        return () => timers.forEach(clearTimeout)
    }, [state, isCanvas])

    // ---- Spinning ball seams: longitude lines on a sphere, drawn per frame ----
    const merRef = React.useRef(null)
    React.useEffect(() => {
        if (state !== 2 || isCanvas) return
        const group = merRef.current
        if (!group) return
        const NS = "http://www.w3.org/2000/svg"
        const CX = 60, R = 54, TOP = 6, BOT = 114, SEAMS = 8, PERIOD = 1800
        const paths = []
        for (let i = 0; i < SEAMS; i++) {
            const p = document.createElementNS(NS, "path")
            group.appendChild(p)
            paths.push(p)
        }
        const reduce = window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        ).matches
        const frame = (angle) => {
            for (let i = 0; i < SEAMS; i++) {
                const theta = angle + (i * 2 * Math.PI) / SEAMS
                const cos = Math.cos(theta)
                const o = Math.min(1, Math.max(0, cos * 2.2))
                const p = paths[i]
                if (o <= 0.01) {
                    p.setAttribute("opacity", "0")
                    continue
                }
                const rx = Math.abs(R * Math.sin(theta)).toFixed(1)
                const sweep = Math.sin(theta) >= 0 ? 1 : 0
                p.setAttribute(
                    "d",
                    `M ${CX} ${TOP} A ${rx} ${R} 0 0 ${sweep} ${CX} ${BOT}`
                )
                p.setAttribute("opacity", o.toFixed(2))
                p.setAttribute("stroke-width", (1.7 + 1.2 * cos).toFixed(2))
            }
        }
        if (reduce) {
            frame(0.6)
            return () => paths.forEach((p) => p.remove())
        }
        let raf, start = null
        const tick = (now) => {
            if (start === null) start = now
            frame(((now - start) / PERIOD) * 2 * Math.PI)
            raf = requestAnimationFrame(tick)
        }
        raf = requestAnimationFrame(tick)
        return () => {
            cancelAnimationFrame(raf)
            paths.forEach((p) => p.remove())
        }
    }, [state, isCanvas])

    // ---- Handlers ----
    const submitBrand = (e) => {
        e.preventDefault()
        const value = brandField.trim()
        if (!value) {
            setBrandError("Enter a brand name to check.")
            return
        }
        setBrandError("")
        setBrand(value)
        setState(2)
    }

    const submitEmail = async (e) => {
        e.preventDefault()
        const first = firstName.trim()
        const last = lastName.trim()
        const job = jobTitle.trim()
        const email = emailField.trim().toLowerCase()
        if (!first || !last || !job) {
            setEmailError(
                "Fill in every field so we know who to build the report for."
            )
            return
        }
        if (!EMAIL_RE.test(email)) {
            setEmailError("Enter a valid email address.")
            return
        }
        const domain = email.split("@")[1]
        if (FREE_EMAIL_DOMAINS.includes(domain)) {
            setEmailError(
                "That looks like a personal email. Enter your work email so we know who to build the report for."
            )
            return
        }
        setEmailError("")
        setSending(true)
        const payload = {
            brand,
            email,
            firstName: first,
            lastName: last,
            jobTitle: job,
            submittedAt: new Date().toISOString(),
            pageUrl: window.location.href,
            elapsedMs: Date.now() - loadedAt.current,
            hp: hpRef.current ? hpRef.current.value : "",
        }
        try {
            const res = await fetch(webhookUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            })
            if (!res.ok) throw new Error("Bad response " + res.status)
            setState(4)
        } catch (err) {
            setEmailError(
                "Something went wrong on our end. Try again, or email us and we'll sort it manually."
            )
        } finally {
            setSending(false)
        }
    }

    // ---- Shared styles ----
    const headingStyle = {
        fontFamily: FONT_HEAD,
        fontWeight: 600,
        color: COLORS.amethyst,
        lineHeight: 1.15,
        margin: 0,
    }
    const bodyStyle = {
        fontFamily: FONT_BODY,
        fontSize: 18,
        color: COLORS.muted,
        lineHeight: 1.55,
        margin: "0 auto",
        maxWidth: 540,
    }
    const pillGroup = {
        display: "flex",
        gap: 10,
        background: COLORS.white,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 999,
        padding: "7px 7px 7px 10px",
        maxWidth: 540,
        margin: "0 auto",
    }
    const inputStyle = {
        flex: 1,
        minWidth: 0,
        border: "none",
        outline: "none",
        background: "transparent",
        fontFamily: FONT_BODY,
        fontSize: 16,
        padding: "10px 12px",
        color: COLORS.amethyst,
    }
    const fieldStyle = {
        width: "100%",
        boxSizing: "border-box" as const,
        background: COLORS.white,
        border: `1px solid ${COLORS.border}`,
        borderRadius: 999,
        padding: "14px 20px",
        fontFamily: FONT_BODY,
        fontSize: 16,
        color: COLORS.amethyst,
        outline: "none",
    }
    const buttonStyle = {
        flexShrink: 0,
        fontFamily: FONT_BODY,
        fontWeight: 600,
        fontSize: 16,
        lineHeight: 1,
        border: "none",
        borderRadius: 999,
        padding: "15px 24px",
        cursor: "pointer",
        background: COLORS.purple,
        color: COLORS.white,
        opacity: sending ? 0.6 : 1,
    }
    const errorStyle = {
        color: COLORS.coral,
        fontFamily: FONT_BODY,
        fontSize: 14,
        fontWeight: 500,
        marginTop: 10,
    }

    const avatarSrc = avatar?.src

    // The spinball SVG, overlaid on the avatar photo's ball
    const spinball = (
        <span
            style={{
                position: "absolute",
                left: "18.6%",
                top: "18.4%",
                width: "38%",
                aspectRatio: "1",
                transform: "translate(-50%, -50%) rotate(-12deg)",
            }}
        >
            <svg
                viewBox="0 0 120 120"
                className={`bch-wobble-${uid}`}
                style={{
                    display: "block",
                    width: "100%",
                    height: "100%",
                    overflow: "visible",
                    transformOrigin: "50% 96%",
                }}
            >
                <defs>
                    <radialGradient id={`bball-${uid}`} cx="38%" cy="30%" r="80%">
                        <stop offset="0%" stopColor="#F6A860" />
                        <stop offset="46%" stopColor="#E87B2C" />
                        <stop offset="100%" stopColor="#A94C17" />
                    </radialGradient>
                    <radialGradient id={`bshine-${uid}`} cx="34%" cy="26%" r="44%">
                        <stop offset="0%" stopColor="#ffffff" stopOpacity="0.55" />
                        <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
                    </radialGradient>
                    <radialGradient id={`bao-${uid}`} cx="50%" cy="102%" r="55%">
                        <stop offset="0%" stopColor="#331304" stopOpacity="0.5" />
                        <stop offset="100%" stopColor="#331304" stopOpacity="0" />
                    </radialGradient>
                    <linearGradient
                        id={`streak-${uid}`}
                        gradientUnits="userSpaceOnUse"
                        x1="-6" y1="20" x2="126" y2="20"
                    >
                        <stop offset="0" stopColor="#E8862F" />
                        <stop offset="0.45" stopColor="#FFDDB0" />
                        <stop offset="0.55" stopColor="#FFDDB0" />
                        <stop offset="1" stopColor="#E8862F" />
                    </linearGradient>
                    <filter id={`bgrain-${uid}`}>
                        <feTurbulence
                            type="fractalNoise"
                            baseFrequency="0.9"
                            numOctaves="2"
                            seed="7"
                        />
                        <feColorMatrix
                            type="matrix"
                            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0.9 0.9 0.9 0 0"
                        />
                    </filter>
                    <clipPath id={`bclip-${uid}`}>
                        <circle cx="60" cy="60" r="57" />
                    </clipPath>
                </defs>
                <g clipPath={`url(#bclip-${uid})`}>
                    <rect width="120" height="120" fill={`url(#bball-${uid})`} />
                    <rect
                        width="120" height="120"
                        filter={`url(#bgrain-${uid})`}
                        opacity="0.08"
                    />
                    <g
                        ref={merRef}
                        fill="none"
                        stroke="#2a1206"
                        strokeLinecap="round"
                    />
                    <path
                        d="M 4 60 Q 60 62.5 116 60"
                        fill="none"
                        stroke="#2a1206"
                        strokeWidth="2.6"
                        strokeLinecap="round"
                    />
                    <circle cx="60" cy="60" r="57" fill={`url(#bshine-${uid})`} />
                    <circle cx="60" cy="60" r="57" fill={`url(#bao-${uid})`} />
                </g>
                <g className={`bch-streaks-${uid}`} fill="none" strokeLinecap="round">
                    <path
                        d="M -6 44 Q 60 8 126 40"
                        stroke={`url(#streak-${uid})`}
                        strokeWidth="4"
                        opacity="0.5"
                    />
                    <path
                        d="M 2 26 Q 60 -6 118 22"
                        stroke={`url(#streak-${uid})`}
                        strokeWidth="2.5"
                        opacity="0.3"
                    />
                    <path
                        d="M 115.4 28 A 64 64 0 0 1 123.8 65.6"
                        stroke="#E8862F"
                        strokeWidth="3"
                        opacity="0.32"
                    />
                </g>
            </svg>
        </span>
    )

    return (
        <div
            style={{
                width: "100%",
                fontFamily: FONT_BODY,
                background: pageBackground,
                textAlign: "center",
                padding: "24px 24px 72px",
                boxSizing: "border-box",
            }}
        >
            <style>{`
                @keyframes bch-fade { from { opacity: 0 } to { opacity: 1 } }
                @keyframes bch-spin { to { transform: rotate(360deg) } }
                @keyframes bch-wobble {
                    0%, 100% { transform: rotate(-2.2deg) }
                    50% { transform: rotate(2.6deg) }
                }
                @keyframes bch-shimmer {
                    0%, 100% { opacity: calc(var(--streak-o) * 0.45) }
                    50% { opacity: var(--streak-o) }
                }
                .bch-wobble-${uid} { animation: bch-wobble 2.6s ease-in-out infinite }
                .bch-streaks-${uid} path { animation: bch-shimmer 1.2s ease-in-out infinite }
                .bch-streaks-${uid} path:nth-child(1) { --streak-o: 0.5 }
                .bch-streaks-${uid} path:nth-child(2) { --streak-o: 0.3; animation-delay: -0.4s }
                .bch-streaks-${uid} path:nth-child(3) { --streak-o: 0.32; animation-delay: -0.8s }
                @media (prefers-reduced-motion: reduce) {
                    .bch-wobble-${uid}, .bch-streaks-${uid} path { animation: none }
                }
                .bch-row-${uid} { display: grid; grid-template-columns: 1fr 1fr; gap: 10px }
                @media (max-width: 520px) {
                    .bch-row-${uid} { grid-template-columns: 1fr }
                }
            `}</style>

            <div
                key={state}
                style={{ animation: "bch-fade 0.18s ease", maxWidth: 720, margin: "0 auto" }}
            >
                {state === 1 && (
                    <div style={{ position: "relative", paddingTop: 60 }}>
                        {avatarSrc && (
                            <div
                                style={{
                                    position: "relative",
                                    zIndex: 2,
                                    width: 300,
                                    height: 210,
                                    margin: "0 auto -70px",
                                }}
                            >
                                <span
                                    style={{
                                        position: "absolute",
                                        left: "50%",
                                        bottom: 0,
                                        width: 210,
                                        height: 210,
                                        transform: "translateX(-50%)",
                                        background: COLORS.purple,
                                        borderRadius: "50%",
                                    }}
                                />
                                <img
                                    src={avatarSrc}
                                    alt=""
                                    style={{
                                        position: "absolute",
                                        left: "50%",
                                        bottom: -4,
                                        width: 250,
                                        transform: "translateX(-56%)",
                                    }}
                                />
                            </div>
                        )}
                        <div
                            style={{
                                position: "relative",
                                zIndex: 1,
                                background: COLORS.tint,
                                borderRadius: 36,
                                padding: "96px 44px 48px",
                            }}
                        >
                            <h1 style={{ ...headingStyle, fontSize: "clamp(32px, 5vw, 48px)", marginBottom: 14 }}>
                                Check your brand's presence in virtual worlds
                            </h1>
                            <p style={{ ...bodyStyle, maxWidth: 560, marginBottom: 28 }}>
                                Find out where your brand already appears across
                                Roblox, Fortnite and beyond, whether you've
                                activated or not.
                            </p>
                            <form onSubmit={submitBrand} noValidate>
                                <div style={pillGroup}>
                                    <input
                                        style={inputStyle}
                                        placeholder="Enter your brand name"
                                        value={brandField}
                                        onChange={(e) => {
                                            setBrandField(e.target.value)
                                            setBrandError("")
                                        }}
                                        aria-label="Brand name"
                                    />
                                    <button type="submit" style={buttonStyle}>
                                        Check presence
                                    </button>
                                </div>
                                {brandError && <p style={errorStyle}>{brandError}</p>}
                            </form>
                            <p style={{ fontFamily: FONT_BODY, fontSize: 14, color: COLORS.muted, marginTop: 18 }}>
                                Free · built by a GEEIQ analyst · delivered within 2 working days
                            </p>
                        </div>
                    </div>
                )}

                {state === 2 && (
                    <div>
                        <h2 style={{ ...headingStyle, fontSize: "clamp(26px, 4vw, 36px)", marginBottom: 18 }}>
                            Discovering brand visibility for {brand}
                        </h2>
                        {avatarSrc && (
                            <div
                                style={{
                                    position: "relative",
                                    width: 190,
                                    margin: "0 auto 6px",
                                    lineHeight: 0,
                                }}
                            >
                                <img src={avatarSrc} alt="" style={{ width: "100%" }} />
                                {/* Erases the photo ball's baked-in streaks; hides under the SVG ball */}
                                <span
                                    style={{
                                        position: "absolute",
                                        left: "18.64%",
                                        top: "15.9%",
                                        width: "40.6%",
                                        aspectRatio: "1",
                                        transform: "translate(-50%, -50%)",
                                        borderRadius: "50%",
                                        background: pageBackground,
                                    }}
                                />
                                {spinball}
                            </div>
                        )}
                        <div
                            style={{
                                height: 8,
                                background: COLORS.tint,
                                borderRadius: 999,
                                overflow: "hidden",
                                maxWidth: 540,
                                margin: "8px auto 28px",
                            }}
                        >
                            <div
                                style={{
                                    height: "100%",
                                    width: `${progress}%`,
                                    background: COLORS.purple,
                                    borderRadius: 999,
                                    transition: "width 0.6s cubic-bezier(0.4, 0, 0.2, 1)",
                                }}
                            />
                        </div>
                        <ul style={{ listStyle: "none", padding: 0, margin: "0 auto", maxWidth: 380, textAlign: "left", display: "grid", gap: 14 }}>
                            {DISCOVERY_STEPS.map((label, i) => (
                                <li
                                    key={label}
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: 12,
                                        fontFamily: FONT_BODY,
                                        color: steps[i] === 2 ? COLORS.amethyst : COLORS.muted,
                                    }}
                                >
                                    <span
                                        style={{
                                            flexShrink: 0,
                                            width: 22,
                                            height: 22,
                                            borderRadius: "50%",
                                            boxSizing: "border-box",
                                            border: `2px solid ${steps[i] === 2 ? COLORS.purple : COLORS.tint}`,
                                            borderTopColor: steps[i] === 1 ? COLORS.purple : undefined,
                                            background: steps[i] === 2 ? COLORS.purple : "transparent",
                                            animation: steps[i] === 1 ? "bch-spin 0.7s linear infinite" : undefined,
                                            position: "relative",
                                        }}
                                    >
                                        {steps[i] === 2 && (
                                            <svg viewBox="0 0 18 18" style={{ position: "absolute", inset: 0 }}>
                                                <path
                                                    d="M 5 9.5 L 8 12.5 L 13.5 6"
                                                    fill="none"
                                                    stroke="#fff"
                                                    strokeWidth="2"
                                                    strokeLinecap="round"
                                                />
                                            </svg>
                                        )}
                                    </span>
                                    {label}
                                </li>
                            ))}
                        </ul>
                    </div>
                )}

                {state === 3 && (
                    <div>
                        <h2 style={{ ...headingStyle, fontSize: "clamp(26px, 4vw, 36px)", marginBottom: 18 }}>
                            We found activity for {brand}
                        </h2>
                        <p style={{ ...bodyStyle, marginBottom: 20 }}>
                            Enter your work email and a GEEIQ analyst will build
                            your report. It lands in your inbox within 2 working
                            days.
                        </p>
                        <form onSubmit={submitEmail} noValidate>
                            <div style={{ display: "grid", gap: 10, maxWidth: 540, margin: "0 auto" }}>
                                <div className={`bch-row-${uid}`}>
                                    <input
                                        style={fieldStyle}
                                        type="text"
                                        placeholder="First name"
                                        autoComplete="given-name"
                                        value={firstName}
                                        onChange={(e) => {
                                            setFirstName(e.target.value)
                                            setEmailError("")
                                        }}
                                        aria-label="First name"
                                    />
                                    <input
                                        style={fieldStyle}
                                        type="text"
                                        placeholder="Last name"
                                        autoComplete="family-name"
                                        value={lastName}
                                        onChange={(e) => {
                                            setLastName(e.target.value)
                                            setEmailError("")
                                        }}
                                        aria-label="Last name"
                                    />
                                </div>
                                <input
                                    style={fieldStyle}
                                    type="text"
                                    placeholder="Job title"
                                    autoComplete="organization-title"
                                    value={jobTitle}
                                    onChange={(e) => {
                                        setJobTitle(e.target.value)
                                        setEmailError("")
                                    }}
                                    aria-label="Job title"
                                />
                                <input
                                    style={fieldStyle}
                                    type="email"
                                    placeholder="Work email"
                                    autoComplete="email"
                                    value={emailField}
                                    onChange={(e) => {
                                        setEmailField(e.target.value)
                                        setEmailError("")
                                    }}
                                    aria-label="Work email"
                                />
                                <button
                                    type="submit"
                                    style={{ ...buttonStyle, width: "100%", padding: "16px 24px" }}
                                    disabled={sending}
                                >
                                    {sending ? "Sending..." : "Request my report"}
                                </button>
                            </div>
                            {/* Honeypot: hidden from humans, bots fill it */}
                            <div
                                aria-hidden="true"
                                style={{ position: "absolute", left: -9999, width: 1, height: 1, overflow: "hidden" }}
                            >
                                <label htmlFor={`hp-${uid}`}>Company website</label>
                                <input id={`hp-${uid}`} ref={hpRef} type="text" tabIndex={-1} autoComplete="off" />
                            </div>
                            {emailError && <p style={errorStyle}>{emailError}</p>}
                        </form>
                        <p style={{ fontFamily: FONT_BODY, fontSize: 14, color: COLORS.muted, marginTop: 18, maxWidth: 460, marginLeft: "auto", marginRight: "auto" }}>
                            Work emails only. We'll use your email to send your
                            report and occasional GEEIQ research. Unsubscribe any
                            time.
                        </p>
                    </div>
                )}

                {state === 4 && (
                    <div>
                        <h2 style={{ ...headingStyle, fontSize: "clamp(26px, 4vw, 36px)", marginBottom: 18 }}>
                            Your report is on its way
                        </h2>
                        <p style={{ ...bodyStyle, marginBottom: 20 }}>
                            A GEEIQ analyst is pulling the data on {brand} now.
                            Expect your report within 2 working days.
                        </p>
                        <p style={{ ...bodyStyle, marginBottom: 28 }}>
                            In the meantime, our Brands in Gaming 101 report
                            covers how virtual worlds work and why brands are
                            paying attention.
                        </p>
                        <a
                            href={reportUrl}
                            style={{ ...buttonStyle, display: "inline-block", textDecoration: "none", opacity: 1 }}
                        >
                            Read Brands in Gaming 101
                        </a>
                    </div>
                )}
            </div>
        </div>
    )
}

BrandCheckHero.defaultProps = {
    webhookUrl: "REPLACE_WITH_N8N_WEBHOOK_URL",
    reportUrl: "https://www.geeiq.com",
    pageBackground: "#FAF7F2",
}

addPropertyControls(BrandCheckHero, {
    webhookUrl: {
        type: ControlType.String,
        title: "Webhook URL",
        defaultValue: "REPLACE_WITH_N8N_WEBHOOK_URL",
    },
    avatar: {
        type: ControlType.ResponsiveImage,
        title: "Avatar",
    },
    reportUrl: {
        type: ControlType.Link,
        title: "Report link",
    },
    pageBackground: {
        type: ControlType.Color,
        title: "Page bg",
        defaultValue: "#FAF7F2",
    },
})
