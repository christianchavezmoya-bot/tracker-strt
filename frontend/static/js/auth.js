/**
 * HOLO-RTLS — Auth JS
 * Login, 2FA, password reset logic.
 */

let pendingUserId = null;   // For 2FA flow
let pendingSetup2FA = false;

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const rememberEl = document.querySelector('input[name="remember"]');
  const remembered = localStorage.getItem('holo_remember') !== '0';
  if (rememberEl) rememberEl.checked = remembered;
  API.setRemember(remembered);
  if (API.isLoggedIn()) {
    window.location.href = '/';
  }
});

// ── Login ────────────────────────────────────────────────────────────────────
async function handleLogin(event) {
  event.preventDefault();
  const form = document.getElementById('loginForm');
  const btn = document.getElementById('loginBtn');
  const btnText = document.getElementById('loginBtnText');
  const spinner = document.getElementById('loginSpinner');
  const errorEl = document.getElementById('loginError');
  const errorMsg = document.getElementById('loginErrorMsg');

  btn.disabled = true;
  btnText.textContent = 'Signing in...';
  spinner.style.display = 'inline';
  errorEl.style.display = 'none';

  const email = document.getElementById('emailInput').value.trim();
  const password = document.getElementById('passwordInput').value;
  const totpCode = document.getElementById('totpInput')?.value?.trim() || null;
  const remember = document.querySelector('input[name="remember"]')?.checked !== false;
  API.setRemember(remember);

  try {
    const res = await API.post('/auth/login', { email_or_username: email, password, totp_code: totpCode || undefined });
    const data = await API.json(res);

    if (res && res.ok) {
      if (data.requires_2fa) {
        // 2FA required — show code input
        pendingUserId = data.user_id;
        document.getElementById('totpGroup').style.display = 'block';
        document.getElementById('totpInput').focus();
        btn.disabled = false; btnText.textContent = 'Verify & Sign In'; spinner.style.display = 'none';
        return;
      }
      onLoginSuccess(data);
    } else {
      if (data.code === 'account_locked' && data.retry_after_seconds != null) {
        const mins = Math.ceil(data.retry_after_seconds / 60);
        showError(`Account locked. Try again in ${mins} min (${data.retry_after_seconds}s).`);
      } else {
        showError(data.error || 'Login failed');
      }
    }
  } catch (err) {
    showError('Connection error. Please try again.');
  } finally {
    btn.disabled = false; btnText.textContent = 'Sign In'; spinner.style.display = 'none';
  }
}

function onLoginSuccess(data) {
  API.setTokens(data.access_token, data.refresh_token, data.user);
  // Check if user needs to set up 2FA
  if (!data.user.is_2fa_enabled) {
    // Offer 2FA setup (skip for now)
    window.location.href = '/';
  } else {
    window.location.href = '/';
  }
}

function showError(msg) {
  const errorEl = document.getElementById('loginError');
  const errorMsg = document.getElementById('loginErrorMsg');
  errorEl.className = 'auth-error';
  errorMsg.textContent = msg;
  errorEl.style.display = 'flex';
}

function togglePassword() {
  const input = document.getElementById('passwordInput');
  const eye = document.getElementById('toggleEye');
  if (input.type === 'password') {
    input.type = 'text'; eye.className = 'fa-regular fa-eye-slash';
  } else {
    input.type = 'password'; eye.className = 'fa-regular fa-eye';
  }
}

// ── 2FA Setup ─────────────────────────────────────────────────────────────────
async function setup2FA() {
  const res = await API.post('/auth/2fa/setup');
  const data = await API.json(res);
  if (res && res.ok) {
    document.getElementById('qrCodeImg').src = data.qr_code;
    showCard('setup2faCard');
  }
}

async function confirmSetup2FA() {
  const code = document.getElementById('setupTotpInput').value.trim();
  const res = await API.post('/auth/2fa/confirm', { totp_code: code });
  const data = await API.json(res);
  if (res && res.ok) {
    showCard('loginCard');
    showLogin();
    showSuccess('2FA enabled successfully.');
  } else {
    showError(data.error || 'Invalid code');
  }
}

function skipSetup2FA() {
  showCard('loginCard');
  showLogin();
}

// ── Password Reset ────────────────────────────────────────────────────────────
function showPasswordReset() {
  showCard('resetCard');
}

function showLogin() {
  showCard('loginCard');
}

function showCard(id) {
  ['loginCard','setup2faCard','resetCard'].forEach(cid => {
    document.getElementById(cid).style.display = cid === id ? 'block' : 'none';
  });
}

function showSuccess(msg) {
  const errorEl = document.getElementById('loginError');
  const errorMsg = document.getElementById('loginErrorMsg');
  errorEl.className = 'auth-success';
  errorMsg.textContent = msg;
  errorEl.style.display = 'flex';
}

async function handlePasswordReset(event) {
  event.preventDefault();
  const email = document.getElementById('resetEmailInput').value.trim();
  const successEl = document.getElementById('resetSuccess');
  const successMsg = document.getElementById('resetSuccessMsg');
  const devLink = document.getElementById('resetDevLink');
  if (successEl) {
    successEl.style.display = 'none';
    successEl.className = 'auth-success';
  }
  if (devLink) devLink.style.display = 'none';

  const res = await API.post('/auth/password/reset-request', { email });
  const data = await API.json(res);
  if (res && res.ok) {
    const msg = data.message || 'If that email is registered, a reset link has been sent.';
    if (successEl && successMsg) {
      successMsg.textContent = msg;
      successEl.style.display = 'flex';
    }
    if (data.reset_url && devLink) {
      devLink.href = data.reset_url;
      devLink.style.display = 'inline';
    }
  } else if (successEl && successMsg) {
    successMsg.textContent = (data && data.error) || 'Request failed';
    successEl.className = 'auth-error';
    successEl.style.display = 'flex';
  }
}

// ── Logout ────────────────────────────────────────────────────────────────────
async function logout() {
  await API.post('/auth/logout');
  API.clearTokens();
  window.location.href = '/login';
}
