/**
 * htmx-defaults.js — Global HTMX configuration for Amplifier dashboards.
 *
 * Responsibilities:
 *  1. Inject Authorization header from cookie on every HTMX request.
 *  2. Surface a global toast on response errors.
 *  3. Toggle body.htmx-loading during requests.
 *  4. Set global HTMX defaults.
 */

// ── Global HTMX config ────────────────────────────────────────────────────────
htmx.config.globalViewTransitions = true;
htmx.config.requestClass = 'htmx-request';

// ── Token helpers ─────────────────────────────────────────────────────────────

/**
 * Read a cookie by name. Returns null if not found.
 * Tokens are stored as httponly cookies by the server (admin_token,
 * company_token). For API-style HTMX requests we also check localStorage
 * for an 'amplifier_token' set by the user-facing API layer.
 */
function _amplifierGetToken() {
  // 1. localStorage (user API token)
  var stored = (typeof localStorage !== 'undefined') && localStorage.getItem('amplifier_token');
  if (stored) return stored;
  // 2. company_token cookie (company dashboard)
  var match = document.cookie.match(/(?:^|;\s*)company_token=([^;]*)/);
  if (match) return decodeURIComponent(match[1]);
  // 3. admin_token cookie is httponly — not readable from JS; admin pages use
  //    session cookies directly and don't need an Authorization header.
  return null;
}

// ── Authorization header injection ───────────────────────────────────────────

document.addEventListener('htmx:configRequest', function (evt) {
  var token = _amplifierGetToken();
  if (token) {
    evt.detail.headers['Authorization'] = 'Bearer ' + token;
  }
});

// ── Global loading indicator ──────────────────────────────────────────────────

document.addEventListener('htmx:beforeRequest', function () {
  document.body.classList.add('htmx-loading');
});

document.addEventListener('htmx:afterRequest', function () {
  document.body.classList.remove('htmx-loading');
});

// ── Global toast ──────────────────────────────────────────────────────────────

/**
 * amplifierToast(msg, severity)
 * severity: 'info' | 'success' | 'error' | 'warning'
 * Auto-removes after 4 seconds.
 */
window.amplifierToast = function (msg, severity) {
  severity = severity || 'info';

  var colors = {
    info:    { bg: '#1e3a5f', border: '#1e40af', text: '#93bbfd' },
    success: { bg: '#14532d', border: '#166534', text: '#86efac' },
    error:   { bg: '#7f1d1d', border: '#991b1b', text: '#fca5a5' },
    warning: { bg: '#713f12', border: '#92400e', text: '#fde68a' },
  };
  var c = colors[severity] || colors.info;

  var toast = document.createElement('div');
  toast.setAttribute('role', 'alert');
  toast.style.cssText = [
    'position:fixed', 'bottom:24px', 'right:24px', 'z-index:9999',
    'padding:12px 18px', 'border-radius:8px', 'font-size:14px',
    'font-family:inherit', 'max-width:380px', 'line-height:1.4',
    'box-shadow:0 4px 20px rgba(0,0,0,0.4)',
    'background:' + c.bg,
    'border:1px solid ' + c.border,
    'color:' + c.text,
    'opacity:0', 'transition:opacity 0.2s ease',
  ].join(';');
  toast.textContent = msg;

  document.body.appendChild(toast);
  // Trigger fade-in
  requestAnimationFrame(function () {
    requestAnimationFrame(function () { toast.style.opacity = '1'; });
  });

  // Auto-remove after 4s
  setTimeout(function () {
    toast.style.opacity = '0';
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 220);
  }, 4000);
};

// ── Response error handler ────────────────────────────────────────────────────

document.addEventListener('htmx:responseError', function (evt) {
  var status = evt.detail.xhr ? evt.detail.xhr.status : 0;
  var msg = 'Request failed';
  if (status === 401 || status === 403) msg = 'Session expired — please log in again.';
  else if (status === 404) msg = 'Resource not found.';
  else if (status >= 500) msg = 'Server error (' + status + '). Please try again.';
  else if (status) msg = 'Request failed (' + status + ').';
  window.amplifierToast(msg, 'error');
});
