import { ThemeControl } from './ThemeControl';
import { createContext, useContext, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { PasswordInput } from '@/components/ui/password-input';
import { api } from '@/lib/api';
import { queryClient } from '@/lib/stream';
import { resetAllStores } from '@/state';
import { LegalLinks, LegalPage, TermsCheckbox } from './Legal';
import { RecoveryCode, RecoveryPage } from './Recovery';

const AuthContext = createContext({ enabled: false, username: '', role: '', multiUser: false });
export const useAuth = () => useContext(AuthContext);

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
  if (['/forgot-password', '/reset-password'].includes(window.location.pathname)) return <RecoveryPage />;
  if (window.location.pathname === '/terms' || window.location.pathname === '/privacy') {
    return <LegalPage privacy={window.location.pathname === '/privacy'} />;
  }
  return <SessionGate>{children}</SessionGate>;
}

function SessionGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Awaited<ReturnType<typeof api.auth.session>> | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [joining, setJoining] = useState(window.location.pathname === '/join');
  const [invite] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get('invite') ?? '');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [signupCode, setSignupCode] = useState('');
  const [savedCode, setSavedCode] = useState(false);
  const currentIdentity = useRef<string | null>(null);
  const needsTerms = session?.multi_user && session.authenticated && !session.terms_accepted;
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
        const identity = next.account_id ?? next.username;
        if (currentIdentity.current !== identity) {
          queryClient.clear(); resetAllStores();
          currentIdentity.current = identity ?? null;
        }
        setSession(next);
        if (next.enabled && !next.authenticated) {
          queryClient.clear();
          resetAllStores();
        }
      } catch { if (active) setError('Cannot reach ANVAYA. Check the server and try again.'); }
    }
    const expire = () => {
      setSession(previous => ({ ...previous, enabled: true, authenticated: false, username: null }));
      queryClient.clear();
      resetAllStores();
      void refresh();
    };
    // Invitations stay in component memory, not browser history or request logs.
    if (window.location.hash.startsWith('#invite=')) window.history.replaceState(null, '', window.location.pathname);
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
      if (needsTerms) {
        if (!accepted || !session.terms_version) return;
        await api.auth.acceptTerms(session.terms_version);
        await check();
        return;
      }
      if (joining) {
        if (!session?.terms_version || !accepted) throw new Error('Read and accept the Terms and Privacy notice.');
        if (password !== repeatPassword) throw new Error('Passwords do not match.');
        const result = await api.auth.register(invite, username, password, session.terms_version);
        setSignupCode(result.recovery_code); setPassword(''); setRepeatPassword('');
        setJoining(false);
        window.history.replaceState(null, '', '/overview');
        return;
      }
      await api.auth.login(username, password);
      setPassword(''); setRepeatPassword('');
      queryClient.clear(); resetAllStores();
      if (joining) { window.location.replace('/account'); return; }
      await check();
    } catch (err) { setError(err instanceof Error ? err.message : 'Sign-in failed'); }
    finally { setBusy(false); }
  }
  if (signupCode) return <main className="flex min-h-screen items-center justify-center bg-paper p-4 sm:p-6"><section className="w-full max-w-[460px] space-y-5 rounded-panel border border-rule bg-surface p-5 sm:p-8"><div className="flex justify-end"><ThemeControl /></div><h1 className="text-h1 font-semibold">Account created</h1><RecoveryCode code={signupCode} username={username} /><label className="flex items-center gap-3 text-body"><input type="checkbox" checked={savedCode} onChange={e => setSavedCode(e.target.checked)} />I saved my recovery code in a private place.</label><Button disabled={!savedCode} onClick={() => setSignupCode('')}>Continue to sign in</Button></section></main>;
  if (session && (!session.enabled || (session.authenticated && !needsTerms))) {
    return <AuthContext.Provider value={{ enabled: session.enabled, username: session.username ?? '', role: session.role ?? '', multiUser: !!session.multi_user }}><div key={session.account_id ?? session.username ?? 'local'} className="h-full">{children}</div></AuthContext.Provider>;
  }
  return <main className="flex min-h-screen items-center justify-center bg-paper p-4 sm:p-6">
    <section className="w-full max-w-[420px] rounded-panel border border-rule bg-surface p-5 sm:p-8 shadow-e1">
      <div className="mb-6 flex justify-end"><ThemeControl /></div>
      <div className="mb-8 flex items-center gap-3"><span aria-hidden className="size-3.5 rounded-[2px] bg-seal" /><span className="text-h3 font-semibold tracking-[0.04em]">ANVAYA</span></div>
      <h1 className="mb-2 text-h1 font-semibold">{needsTerms ? 'Before you continue' : session ? (joining ? 'Create your workspace' : 'Sign in') : 'Connecting to ANVAYA'}</h1>
      <p className="mb-6 text-body text-graphite">{needsTerms ? 'Please review the terms and privacy notice for this educational pilot.' : session ? (joining ? 'Your own account, logs and collector key. For authorized testing and learning.' : 'Open your private log workspace.') : 'Checking your session…'}</p>
      {error && <p role="alert" className="mb-4 text-body text-int-tampered">{error}</p>}
      {session ? <form onSubmit={login} className="space-y-5">
        {!needsTerms && <>
          <div><label htmlFor="username" className="mb-2 block text-label font-medium">Username</label><input id="username" autoComplete="username" required maxLength={joining ? 64 : 128} value={username} onChange={(e) => setUsername(e.target.value)} className="h-11 w-full rounded-control border border-rule bg-paper px-3 text-body" /></div>
          <div><label htmlFor="password" className="mb-2 block text-label font-medium">Password</label><PasswordInput key={joining ? 'signup-password' : 'login-password'} id="password" autoComplete={joining ? 'new-password' : 'current-password'} required minLength={joining ? 12 : undefined} maxLength={1024} value={password} onChange={(e) => setPassword(e.target.value)} /></div>
          {joining && <div><label htmlFor="repeat-password" className="mb-2 block text-label font-medium">Repeat password</label><PasswordInput id="repeat-password" autoComplete="new-password" required maxLength={1024} value={repeatPassword} onChange={e => setRepeatPassword(e.target.value)} /></div>}
        </>}
        {(joining || needsTerms) && <TermsCheckbox checked={accepted} onChange={setAccepted} />}
        {joining && !invite && !session.public_signup && <p role="alert" className="text-label text-int-tampered">Open the complete invitation link provided by the owner.</p>}
        <Button type="submit" className="w-full" disabled={busy || ((joining || !!needsTerms) && !accepted) || (joining && !invite && !session.public_signup)}>{busy ? 'Please wait…' : needsTerms ? 'Accept and continue' : joining ? 'Create account' : 'Sign in'}</Button>
        {needsTerms && <Button type="button" variant="outline" onClick={async () => { await api.auth.logout(); window.dispatchEvent(new Event('anvaya:unauthorized')); }}>Decline and sign out</Button>}
      </form> : error && <Button onClick={check}>Try again</Button>}
      {!needsTerms && session?.multi_user && <p className="mt-5 text-label">{joining ? <a href="/overview" className="text-seal underline">Already have an account? Sign in</a> : session.public_signup && <a href="/join" className="text-seal underline">Create a free account</a>}</p>}
      {!joining && !needsTerms && session?.multi_user && <p className="mt-4 text-label"><a href="/forgot-password" className="text-seal underline">Forgot password?</a></p>}
      {!joining && !needsTerms && <div className="mt-6 border-t border-rule pt-5"><LegalLinks /></div>}
    </section>
  </main>;
}
