import { useEffect, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { PasswordInput } from '@/components/ui/password-input';
import { api } from '@/lib/api';

const inputStyle = 'h-11 w-full rounded-control border border-rule bg-paper px-3 text-body';

export function RecoveryCode({ code, username }: { code: string; username: string }) {
  function download() {
    const url = URL.createObjectURL(new Blob([`ANVAYA recovery code\nServer: ${window.location.origin}\nUsername: ${username}\nCode: ${code}\n\nKeep this private. This code can reset your password once. Replacing it invalidates the previous code.\n`], { type: 'text/plain' }));
    const anchor = document.createElement('a');
    anchor.href = url; anchor.download = 'anvaya-recovery-code.txt'; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return <div className="space-y-3 rounded-control border border-rule bg-paper p-4">
    <h2 className="text-h3 font-semibold">Save your recovery code</h2>
    <p className="text-body text-graphite">Keep this in a password manager or another private place. Anyone with this code can reset your password. It is shown only now and works once.</p>
    <label htmlFor="saved-recovery-code" className="block text-label">Recovery code</label>
    <input id="saved-recovery-code" readOnly value={code} className={inputStyle} onFocus={e => e.target.select()} />
    <Button type="button" variant="outline" onClick={download}>Download recovery code</Button>
  </div>;
}

export function RecoveryPage() {
  const [options, setOptions] = useState<Awaited<ReturnType<typeof api.auth.recoveryOptions>>>();
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    void api.auth.recoveryOptions().then(setOptions).catch(() => setError('Cannot reach ANVAYA. Reload to try again.'));
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setBusy(true);
    try {
      if (password !== repeat) throw new Error('Passwords do not match.');
      await api.auth.resetPassword({ username, code, password });
      setPassword(''); setRepeat(''); setCode(''); setDone(true);
    } catch (e) { setError(e instanceof Error ? e.message : 'Recovery failed'); }
    finally { setBusy(false); }
  }
  return <main className="flex min-h-screen items-center justify-center bg-paper p-6"><section className="w-full max-w-[460px] space-y-5 rounded-panel border border-rule bg-surface p-8 shadow-e1">
    <p className="text-h3 font-semibold">ANVAYA</p>
    <h1 className="text-h1 font-semibold">Recover your account</h1>
    {error && <p role="alert" className="text-body text-int-tampered">{error}</p>}
    {done ? <p role="status" className="text-body">Password reset. All previous sign-in sessions have ended. Sign in with your new password and save a new recovery code in Account.</p> : <form className="space-y-4" onSubmit={submit}>
      <p className="text-body text-graphite">Enter the recovery code you saved when you created your account or generated from Account settings.</p>
      <div><label htmlFor="recovery-username" className="mb-2 block text-label">Username</label><input id="recovery-username" autoComplete="username" required maxLength={128} value={username} onChange={e => setUsername(e.target.value)} className={inputStyle} /></div>
      <div><label htmlFor="recovery-code" className="mb-2 block text-label">Saved recovery code</label><PasswordInput id="recovery-code" autoComplete="off" required maxLength={128} value={code} onChange={e => setCode(e.target.value)} /></div>
      <div><label htmlFor="new-password" className="mb-2 block text-label">New password</label><PasswordInput id="new-password" autoComplete="new-password" required minLength={12} maxLength={1024} value={password} onChange={e => setPassword(e.target.value)} /></div>
      <div><label htmlFor="confirm-password" className="mb-2 block text-label">Repeat new password</label><PasswordInput id="confirm-password" autoComplete="new-password" required minLength={12} maxLength={1024} value={repeat} onChange={e => setRepeat(e.target.value)} /></div>
      <Button type="submit" className="w-full" disabled={busy || !options?.code_available}>{busy ? 'Please wait…' : 'Reset password'}</Button>
      <p className="text-label text-graphite">A saved recovery code is required. A username or support email alone cannot recover your account. Each code works once.</p>
    </form>}
    <p><a href="/overview" className="text-seal underline">Back to sign in</a> · <a href="/privacy" className="text-seal underline">Privacy notice</a></p>
  </section></main>;
}
