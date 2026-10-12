import { createContext, useContext, useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/stream';
import { resetAllStores } from '@/state';

const AuthContext = createContext({ enabled: false, username: '' });

export function SignOut() {
  const auth = useContext(AuthContext);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (!auth.enabled) return null;
  async function logout() {
    setBusy(true);
    try {
      await api.auth.logout();
      window.dispatchEvent(new Event('anvaya:unauthorized'));
    } catch { setError('Could not sign out. Try again.'); }
    finally { setBusy(false); }
  }
  return <div className="flex items-center gap-2">
    <Button variant="outline" disabled={busy} onClick={logout} aria-label={`Sign out ${auth.username}`}>Sign out</Button>
    {error && <span role="alert" className="text-label text-int-tampered">{error}</span>}
  </div>;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Awaited<ReturnType<typeof api.auth.session>> | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  async function check() {
    try { setSession(await api.auth.session()); setError(''); }
    catch { setError('Cannot reach ANVAYA. Check the server and try again.'); }
  }
  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const next = await api.auth.session();
        if (!active) return;
        setSession(next);
        if (next.enabled && !next.authenticated) {
          queryClient.clear();
          resetAllStores();
        }
      } catch { if (active) setError('Cannot reach ANVAYA. Check the server and try again.'); }
    }
    const expire = () => {
      setSession({ enabled: true, authenticated: false, username: null });
      queryClient.clear();
      resetAllStores();
    };
    void refresh();
    const timer = window.setInterval(refresh, 60_000);
    window.addEventListener('anvaya:unauthorized', expire);
    window.addEventListener('focus', refresh);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener('anvaya:unauthorized', expire);
      window.removeEventListener('focus', refresh);
    };
  }, []);
  async function login(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError('');
    try {
      await api.auth.login(username, password);
      setPassword('');
      await check();
    } catch (err) { setError(err instanceof Error ? err.message : 'Sign-in failed'); }
    finally { setBusy(false); }
  }
  if (session && (!session.enabled || session.authenticated)) {
    return <AuthContext.Provider value={{ enabled: session.enabled, username: session.username ?? '' }}>{children}</AuthContext.Provider>;
  }
  return <main className="flex min-h-screen items-center justify-center bg-paper p-6">
    <section className="w-full max-w-[420px] rounded-panel border border-rule bg-surface p-8 shadow-e1">
      <div className="mb-8 flex items-center gap-3"><span aria-hidden className="size-3.5 rounded-[2px] bg-seal" /><span className="text-h3 font-semibold tracking-[0.04em]">ANVAYA</span></div>
      <h1 className="mb-2 text-h1 font-semibold">{session ? 'Sign in' : 'Connecting to ANVAYA'}</h1>
      <p className="mb-6 text-body text-graphite">{session ? 'Use your administrator account to open the log console.' : 'Checking your session…'}</p>
      {error && <p role="alert" className="mb-4 text-body text-int-tampered">{error}</p>}
      {session ? <form onSubmit={login} className="space-y-5">
        <div><label htmlFor="username" className="mb-2 block text-label font-medium">Username</label><input id="username" autoComplete="username" required maxLength={128} value={username} onChange={(e) => setUsername(e.target.value)} className="h-11 w-full rounded-control border border-rule bg-paper px-3 text-body" /></div>
        <div><label htmlFor="password" className="mb-2 block text-label font-medium">Password</label><input id="password" type="password" autoComplete="current-password" required maxLength={1024} value={password} onChange={(e) => setPassword(e.target.value)} className="h-11 w-full rounded-control border border-rule bg-paper px-3 text-body" /></div>
        <Button type="submit" className="w-full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
      </form> : error && <Button onClick={check}>Try again</Button>}
    </section>
  </main>;
}
