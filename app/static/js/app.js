// App-level helpers loaded after Alpine.js.
(function () {
  // Attach CSRF token to all fetch requests automatically (same-origin only).
  const meta = document.querySelector('meta[name="csrf-token"]');
  const csrf = meta ? meta.getAttribute('content') : '';
  const originalFetch = window.fetch;
  window.fetch = function (input, init) {
    init = init || {};
    const method = (init.method || (typeof input === 'object' && input.method) || 'GET').toUpperCase();
    if (csrf && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      init.headers = Object.assign({}, init.headers || {}, { 'X-CSRFToken': csrf });
    }
    return originalFetch(input, init);
  };

  // Lightweight toast (fallback when Alpine flash is dismissed).
  window.toast = function (msg, type) {
    const colors = {
      success: 'bg-emerald-600',
      error:   'bg-rose-600',
      info:    'bg-sky-600',
      warning: 'bg-amber-600',
    };
    const el = document.createElement('div');
    el.className = 'fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg shadow-lg text-white text-sm ' + (colors[type || 'info']);
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; }, 2000);
    setTimeout(() => el.remove(), 2400);
  };
})();
