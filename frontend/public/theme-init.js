// Resolve before the stylesheet paints; storage can be unavailable in private browsers.
(() => {
  let preference = 'system';
  try { preference = localStorage.getItem('anvaya-theme') || 'system'; } catch { /* use system */ }
  const dark = preference === 'dark' || (preference !== 'light' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.classList.toggle('light', !dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
})();
