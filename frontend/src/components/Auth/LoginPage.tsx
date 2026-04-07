import { useState } from 'react'
import { isSupabaseConfigured } from '../../lib/supabase'

interface LoginPageProps {
  onSignIn: (email: string, password: string) => Promise<void>
  onSignUp: (email: string, password: string) => Promise<void>
  onGoogleSignIn: () => Promise<void>
  onSkip: () => void
}

export function LoginPage({ onSignIn, onSignUp, onGoogleSignIn, onSkip }: LoginPageProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    setLoading(true)
    try {
      if (mode === 'signin') {
        await onSignIn(email, password)
      } else {
        await onSignUp(email, password)
        setSuccess('Check your email to confirm your account')
      }
    } catch (err: any) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#090909] text-zinc-100">
      <div className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">
        <header className="flex items-center justify-between py-2">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-sm font-semibold text-zinc-100">
              P
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight text-zinc-100">
                Pointe<span className="text-white/30">.ai</span>
              </h1>
              <p className="text-[11px] uppercase tracking-[0.24em] text-zinc-600">Floor plan workspace</p>
            </div>
          </div>
          <div className="hidden rounded-full border border-white/8 px-3 py-1 text-[10px] uppercase tracking-[0.22em] text-zinc-600 sm:block">
            {mode === 'signin' ? 'Sign in' : 'Create account'}
          </div>
        </header>

        <main className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-md rounded-[28px] border border-white/6 bg-[#101010] p-6 shadow-[0_24px_80px_rgba(0,0,0,0.35)] sm:p-8">
            <div className="mb-8">
              <p className="text-xs uppercase tracking-[0.3em] text-zinc-600">{mode === 'signin' ? 'Welcome back' : 'Create account'}</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-tight text-zinc-100">
                {mode === 'signin' ? 'Sign in to your workspace' : 'Create your workspace'}
              </h2>
              <p className="mt-2 text-sm leading-6 text-zinc-500">
                {mode === 'signin'
                  ? 'Open your saved projects and continue working.'
                  : 'Start a clean workspace for plans, labels and DXF export.'}
              </p>
            </div>

            <div className="mb-6 inline-flex rounded-2xl border border-white/8 bg-zinc-950/80 p-1">
              <button
                type="button"
                onClick={() => {
                  setMode('signin')
                  setError('')
                  setSuccess('')
                }}
                className={`rounded-xl px-4 py-2 text-xs font-medium transition-colors ${
                  mode === 'signin' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => {
                  setMode('signup')
                  setError('')
                  setSuccess('')
                }}
                className={`rounded-xl px-4 py-2 text-xs font-medium transition-colors ${
                  mode === 'signup' ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                Create account
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <label className="block">
                <span className="mb-2 block text-[11px] uppercase tracking-[0.22em] text-zinc-600">Email</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@studio.com"
                  required
                  className="w-full rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none transition-colors focus:border-white/18"
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-[11px] uppercase tracking-[0.22em] text-zinc-600">Password</span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Minimum 6 characters"
                  required
                  minLength={6}
                  className="w-full rounded-2xl border border-white/8 bg-zinc-950 px-4 py-3 text-sm text-zinc-200 placeholder-zinc-600 outline-none transition-colors focus:border-white/18"
                />
              </label>

              {error && (
                <p className="rounded-2xl border border-red-500/15 bg-red-500/8 px-3 py-2.5 text-xs text-red-300">
                  {error}
                </p>
              )}
              {success && (
                <p className="rounded-2xl border border-emerald-500/15 bg-emerald-500/8 px-3 py-2.5 text-xs text-emerald-300">
                  {success}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                className="w-full rounded-2xl border border-white/10 bg-white/[0.06] py-3 text-sm font-medium text-zinc-200 transition-all hover:bg-white/[0.09] disabled:opacity-50"
              >
                {loading ? 'Please wait...' : mode === 'signin' ? 'Sign In' : 'Create Account'}
              </button>
            </form>

            <div className="my-5 flex items-center gap-3">
              <div className="h-px flex-1 bg-white/6" />
              <span className="text-[10px] uppercase tracking-[0.28em] text-zinc-700">or</span>
              <div className="h-px flex-1 bg-white/6" />
            </div>

            <button
              onClick={onGoogleSignIn}
              className="w-full rounded-2xl border border-white/8 bg-zinc-950 py-3 text-sm text-zinc-300 transition-colors hover:border-white/14 hover:bg-white/[0.03]"
            >
              Continue with Google
            </button>

            {!isSupabaseConfigured && (
              <button
                onClick={onSkip}
                className="mt-6 w-full text-center text-xs text-zinc-600 transition-colors hover:text-zinc-400"
              >
                Continue without account (dev mode)
              </button>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
