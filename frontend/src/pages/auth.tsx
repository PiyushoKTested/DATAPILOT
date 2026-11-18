
import { useState, type FormEvent, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../lib/auth'
import { Alert, Spinner } from '../components/ui'

const inputStyle =
  'w-full rounded-xl border border-slate-200 bg-white px-4 py-3.5 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-violet-400 focus:ring-4 focus:ring-violet-100'

const submitStyle =
  'flex w-full items-center justify-center gap-2 rounded-xl bg-[#7046e8] px-5 py-3.5 text-sm font-bold text-white shadow-lg shadow-violet-200 transition hover:-translate-y-0.5 hover:bg-[#6036d6] hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60'

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <label className="mb-2 block text-xs font-bold text-slate-700">{label}</label>
      {children}
    </div>
  )
}

function AuthFrame({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: ReactNode
}) {
  const features = [
    { icon: '🪄', title: 'Clean', detail: 'Fix messy data' },
    { icon: '📊', title: 'Explore', detail: 'Make beautiful charts' },
    { icon: '🧠', title: 'Understand', detail: 'Find hidden patterns' },
    { icon: '📄', title: 'Share', detail: 'Create useful reports' },
  ]

  return (
    <main className="min-h-screen w-full bg-[#faf9ff] text-slate-900 lg:grid lg:grid-cols-[1.08fr_0.92fr]">

      {/* LEFT SIDE — FOUNDER STORY */}
      <section className="relative flex flex-col justify-between overflow-hidden bg-[#eee9ff] px-6 py-8 sm:px-10 sm:py-10 lg:min-h-screen lg:px-14 lg:py-12 xl:px-20">

        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-fuchsia-300/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-20 h-96 w-96 rounded-full bg-orange-200/40 blur-3xl" />

        {/* Brand */}
        <Link to="/signup" className="relative z-10 flex w-fit items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#7046e8] text-xl font-black text-white shadow-lg shadow-violet-300">
            D
          </div>
          <div>
            <p className="text-lg font-black tracking-tight">DATAPILOT<span className="text-violet-600">.</span></p>
            <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-violet-600">Your data sidekick</p>
          </div>
        </Link>

        {/* Main story */}
        <div className="relative z-10 my-12 max-w-2xl lg:my-0 lg:py-12">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/80 bg-white/70 px-4 py-2 text-xs font-bold text-violet-700 shadow-sm">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            MADE WITH CURIOSITY, NOT A BIG CORPORATION
          </div>

          <h1 className="max-w-2xl text-4xl font-black leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl xl:text-7xl">
            Data can be
            <br />
            confusing.
            <br />
            <span className="bg-gradient-to-r from-violet-700 via-fuchsia-600 to-orange-500 bg-clip-text text-transparent">
              Understanding it
              <br className="hidden sm:block" /> shouldn't be.
            </span>
            <span className="ml-2 inline-block">✳</span>
          </h1>

          <div className="mt-7 flex items-start gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-xl shadow-sm">
              👋
            </div>
            <div>
              <p className="text-base font-extrabold text-slate-900">Hey, I'm Piyush.</p>
              <p className="mt-1 text-sm leading-6 text-slate-600 sm:text-base">
                A 4th-year B.Tech Computer Science student building a tool
                to make data analysis easier for everyone.
              </p>
            </div>
          </div>

          <p className="mt-6 max-w-xl text-sm leading-7 text-slate-600 sm:text-base">
            You might have sales records, survey responses, college projects
            or business data. You shouldn't need to master Python, SQL or
            statistics just to understand what your data is telling you.
            That's why I started DATAPILOT.
          </p>

          {/* Feature tiles */}
          <div className="mt-9 grid max-w-xl grid-cols-2 gap-3">
            {features.map((feature, index) => (
              <div
                key={feature.title}
                className="group rounded-2xl border border-white/90 bg-white/75 p-4 shadow-sm backdrop-blur transition duration-200 hover:-translate-y-1 hover:shadow-lg"
              >
                <div className="flex items-center justify-between">
                  <span className="text-2xl">{feature.icon}</span>
                  <span className="text-xs font-bold text-violet-300">
                    0{index + 1}
                  </span>
                </div>
                <p className="mt-3 text-sm font-extrabold">{feature.title}</p>
                <p className="mt-1 text-xs text-slate-500">{feature.detail}</p>
              </div>
            ))}
          </div>

          {/* Founder note */}
          <div className="mt-7 max-w-xl rounded-2xl border border-violet-200/70 bg-white/50 p-5">
            <p className="text-sm font-semibold leading-6 text-slate-700">
              "Is it a little vibe-coded? Maybe. Is it built with genuine
              curiosity and the intention to be useful? Absolutely." 💜
            </p>
            <p className="mt-2 text-xs font-medium text-slate-500">
              — Piyush Thakur · B.Tech CSE · Class of 2027
            </p>
          </div>
        </div>

        <p className="relative z-10 text-xs text-slate-500">
          An independent project, built one improvement at a time. ☕
        </p>
      </section>

      {/* RIGHT SIDE — SIGNUP / LOGIN */}
      <section className="relative flex min-h-[620px] items-center justify-center overflow-hidden bg-[#faf9ff] px-5 py-14 sm:px-10 lg:min-h-screen lg:px-12 xl:px-20">
        <div className="pointer-events-none absolute right-0 top-0 h-72 w-72 rounded-full bg-violet-100/60 blur-3xl" />

        <div className="relative z-10 w-full max-w-[440px]">

          <div className="mb-8 lg:hidden">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#7046e8] text-xl font-black text-white">
              D
            </div>
          </div>

          <div className="mb-8">
            <span className="inline-flex rounded-full bg-violet-100 px-3 py-1.5 text-[10px] font-extrabold tracking-wider text-violet-700">
              ✨ YOUR DATA JOURNEY STARTS HERE
            </span>
            <h2 className="mt-5 text-3xl font-black tracking-tight sm:text-4xl">
              {title}
            </h2>
            <p className="mt-3 text-sm leading-6 text-slate-500">{subtitle}</p>
          </div>

          <div className="rounded-[28px] border border-violet-100 bg-white p-6 shadow-[0_20px_70px_-25px_rgba(112,70,232,0.22)] sm:p-9">
            {children}
          </div>

          <div className="mt-7 flex items-center justify-center gap-2 text-xs text-slate-400">
            <span>💜</span>
            <span>Made for curious minds, not just data experts.</span>
          </div>
        </div>
      </section>
    </main>
  )
}

export function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation() as any

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)

    try {
      await login(email.trim(), password)
      navigate(location.state?.from ?? '/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthFrame
      title="Welcome back 👋"
      subtitle="Your workspace is waiting. Let's make sense of some data."
    >
      <form onSubmit={onSubmit} className="space-y-5">
        {error && <Alert kind="error">{error}</Alert>}

        <Field label="Email address">
          <input
            type="email"
            required
            className={inputStyle}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </Field>

        <Field label="Password">
          <input
            type="password"
            required
            className={inputStyle}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Your password"
            autoComplete="current-password"
          />
        </Field>

        <button type="submit" className={submitStyle} disabled={busy}>
          {busy ? <Spinner /> : null}
          Sign in to DATAPILOT →
        </button>
      </form>

      <div className="my-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-slate-100" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">New here?</span>
        <div className="h-px flex-1 bg-slate-100" />
      </div>

      <p className="text-center text-sm text-slate-500">
        Don't have an account?{' '}
        <Link to="/signup" className="font-bold text-violet-600 hover:text-fuchsia-600">
          Create one ✨
        </Link>
      </p>
    </AuthFrame>
  )
}

export function Signup() {
  const { signup } = useAuth()
  const navigate = useNavigate()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(event: FormEvent) {
    event.preventDefault()

    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }

    setBusy(true)
    setError(null)

    try {
      await signup(email.trim(), fullName.trim(), password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create account')
    } finally {
      setBusy(false)
    }
  }

  return (
    <AuthFrame
      title="Let's get started 🚀"
      subtitle="Create your account. Your data deserves a little more love."
    >
      <form onSubmit={onSubmit} className="space-y-5">
        {error && <Alert kind="error">{error}</Alert>}

        <Field label="What should we call you?">
          <input
            required
            className={inputStyle}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            placeholder="Your name"
            autoComplete="name"
          />
        </Field>

        <Field label="Email address">
          <input
            type="email"
            required
            className={inputStyle}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </Field>

        <Field label="Password (at least 8 characters)">
          <input
            type="password"
            required
            minLength={8}
            className={inputStyle}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Create a strong password"
            autoComplete="new-password"
          />
        </Field>

        <button type="submit" className={submitStyle} disabled={busy}>
          {busy ? <Spinner /> : null}
          Create my account ✨
        </button>

        <p className="text-center text-[11px] leading-5 text-slate-400">
          By creating an account, you're ready to make your data make sense.
        </p>
      </form>

      <div className="my-6 flex items-center gap-3">
        <div className="h-px flex-1 bg-slate-100" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Already one of us?</span>
        <div className="h-px flex-1 bg-slate-100" />
      </div>

      <p className="text-center text-sm text-slate-500">
        Already registered?{' '}
        <Link to="/login" className="font-bold text-violet-600 hover:text-fuchsia-600">
          Sign in →
        </Link>
      </p>
    </AuthFrame>
  )
}
