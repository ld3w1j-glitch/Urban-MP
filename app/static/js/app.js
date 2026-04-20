document.addEventListener('DOMContentLoaded', () => {
  const alerts = document.querySelectorAll('.alert');
  if (alerts.length) {
    setTimeout(() => {
      alerts.forEach((alert) => {
        alert.style.transition = 'opacity .35s ease';
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 350);
      });
    }, 3500);
  }
  const root = document.documentElement;
  const buttons = document.querySelectorAll('[data-theme-button]');
  const logos = document.querySelectorAll('[data-dark-logo][data-light-logo]');
  function applyTheme(theme) {
    root.setAttribute('data-theme', theme);
    localStorage.setItem('urban-mp-theme', theme);
    buttons.forEach((button) => button.classList.toggle('active', button.dataset.themeButton === theme));
    logos.forEach((logo) => { logo.src = theme === 'light' ? logo.dataset.lightLogo : logo.dataset.darkLogo; });
  }
  const savedTheme = localStorage.getItem('urban-mp-theme') || root.getAttribute('data-theme') || 'dark';
  applyTheme(savedTheme);
  buttons.forEach((button) => button.addEventListener('click', () => applyTheme(button.dataset.themeButton)));
});