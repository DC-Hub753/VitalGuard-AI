import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../store/AuthContext.tsx';
import { ShieldCheck, UserCheck, Stethoscope, HeartPulse } from 'lucide-react';

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError('');
    setBusy(true);
    try {
      await login(username.trim(), password);
      navigate('/dashboard', { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to sign in.');
    } finally {
      setBusy(false);
    }
  }

  function fillDemo(u: string, p: string) {
    setUsername(u);
    setPassword(p);
    setError('');
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center px-4 py-10">
      <section className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-2xl">
        <div className="mb-6">
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-400">VitalGuard AI</p>
          <h1 className="mt-2 text-2xl font-bold tracking-tight">Clinical Portal Login</h1>
          <p className="mt-1 text-xs text-slate-400">
            Sign in with your role-authorized credentials. Access tokens expire after 15 minutes.
          </p>
        </div>

        <form className="space-y-4" onSubmit={submit}>
          <div>
            <label htmlFor="username" className="mb-1.5 block text-xs font-medium text-slate-300">
              Username
            </label>
            <input
              id="username"
              autoComplete="username"
              required
              maxLength={128}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
              placeholder="e.g. clinician, nurse, admin"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1.5 block text-xs font-medium text-slate-300">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={1024}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm outline-none focus:border-cyan-500 focus:ring-2 focus:ring-cyan-500/20"
            />
          </div>

          {error && (
            <p role="alert" className="rounded-lg border border-rose-900 bg-rose-950/60 px-3 py-2 text-xs text-rose-200">
              {error}
            </p>
          )}

          <button
            disabled={busy}
            className="w-full rounded-lg bg-cyan-500 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="mt-6 border-t border-slate-800 pt-5">
          <p className="text-[11px] font-medium uppercase tracking-wider text-slate-400 mb-2">
            Demo Role Quick-Fill:
          </p>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => fillDemo('admin', 'AdminPass123!')}
              className="flex flex-col items-center justify-center p-2 rounded-lg border border-slate-800 bg-slate-950/60 hover:bg-slate-800 hover:border-slate-700 text-xs text-slate-300 transition"
            >
              <ShieldCheck size={16} className="text-amber-400 mb-1" />
              <span className="font-semibold text-[11px]">Admin</span>
            </button>
            <button
              type="button"
              onClick={() => fillDemo('clinician', 'ClinicianPass123!')}
              className="flex flex-col items-center justify-center p-2 rounded-lg border border-slate-800 bg-slate-950/60 hover:bg-slate-800 hover:border-slate-700 text-xs text-slate-300 transition"
            >
              <Stethoscope size={16} className="text-teal-400 mb-1" />
              <span className="font-semibold text-[11px]">Clinician</span>
            </button>
            <button
              type="button"
              onClick={() => fillDemo('nurse', 'NursePass123!')}
              className="flex flex-col items-center justify-center p-2 rounded-lg border border-slate-800 bg-slate-950/60 hover:bg-slate-800 hover:border-slate-700 text-xs text-slate-300 transition"
            >
              <HeartPulse size={16} className="text-cyan-400 mb-1" />
              <span className="font-semibold text-[11px]">Nurse</span>
            </button>
          </div>
        </div>

        <p className="mt-5 text-[11px] leading-4 text-slate-500 text-center">
          Demo only. This system is not clinically validated and must not be used for real patient care.
        </p>
      </section>
    </main>
  );
}
