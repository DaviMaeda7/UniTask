(() => {
  const shell = document.querySelector('.auth-shell');
  if (!shell) return;
  const login = document.getElementById('login-form');
  const register = document.getElementById('register-form');
  function setMode(mode) {
    const isRegister = mode === 'register';
    login.hidden = isRegister;
    register.hidden = !isRegister;
    document.getElementById('auth-switch-login').hidden = isRegister;
    document.getElementById('auth-switch-register').hidden = !isRegister;
    document.getElementById('auth-title').textContent = isRegister ? 'Crie sua conta' : 'Bem-vindo de volta!';
    document.getElementById('auth-intro').textContent = isRegister ? 'Comece sua jornada no UniTask.' : 'Entre para continuar seus projetos.';
    document.querySelectorAll('[data-set-mode].auth-tab').forEach(btn => btn.setAttribute('aria-pressed', String(btn.dataset.setMode === mode)));
    history.replaceState(null, '', isRegister ? '/entrar?modo=cadastro' : '/entrar');
  }
  document.querySelectorAll('[data-set-mode]').forEach(btn => btn.addEventListener('click', () => setMode(btn.dataset.setMode)));
  setMode(shell.dataset.initialMode);
})();
