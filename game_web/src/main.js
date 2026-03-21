import './style.css';

const el = document.getElementById('rules');
fetch(`${import.meta.env.BASE_URL}guess-number-rules.txt`)
  .then((r) => r.text())
  .then((t) => {
    el.textContent = t.trim();
  })
  .catch(() => {
    el.textContent = '無法載入規則文字。';
  });
