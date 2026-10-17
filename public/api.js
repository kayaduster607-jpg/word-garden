/** 同源请求统一处理；会话在 HttpOnly Cookie 中，不将密码或 token 存进本地存储。 */
export let csrf = '';
export function setCsrf(value) { csrf = value || ''; }

export async function request(path, body) {
  const response = await fetch(`/api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    credentials: 'same-origin',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || '操作未完成，请重试。');
    error.status = response.status;
    throw error;
  }
  return data;
}

/** 所有词库文本进入 HTML 前转义，源资料和账号名均不能注入脚本。 */
export function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
}

export function toast(message) {
  const element = document.querySelector('#toast');
  element.textContent = message;
  element.classList.add('visible');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('visible'), 5000);
}

export function speak(text) {
  if (!('speechSynthesis' in window)) return toast('此浏览器不支持朗读，请使用支持系统语音的浏览器。');
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = 'en-US';
  utterance.rate = 0.85;
  window.speechSynthesis.speak(utterance);
}

export function eventId() {
  // HTTPS 使用原生 UUID；本机 HTTP 预览也可安全生成不重复的事件编号。
  if (crypto.randomUUID) return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}
