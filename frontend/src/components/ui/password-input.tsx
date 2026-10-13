import { useState, type InputHTMLAttributes } from 'react';
import { Eye, EyeOff } from 'lucide-react';

export function PasswordInput({ className = '', ...props }: Omit<InputHTMLAttributes<HTMLInputElement>, 'type'>) {
  const [visible, setVisible] = useState(false);
  return <div className="relative">
    <input {...props} type={visible ? 'text' : 'password'} className={`h-11 w-full rounded-control border border-rule bg-paper pl-3 pr-12 text-body ${className}`} />
    <button type="button" aria-label={visible ? 'Hide password' : 'Show password'} aria-pressed={visible}
      aria-controls={props.id} disabled={props.disabled} onClick={() => setVisible(!visible)}
      className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-control text-graphite focus-visible:outline-2 focus-visible:outline-seal">
      {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
    </button>
  </div>;
}
