/** 拼写比较只宽容大小写、引号、句读和多余空格，绝不自动判定近义句正确。 */
import { escapeHtml } from './api.js';

export function normalize(text) {
  return text.normalize('NFKC').replace(/[’‘]/g, "'").replace(/[“”]/g, '"')
    .replace(/[.,!?;:，。！？；："()（）]/g, '').toLowerCase().replace(/\s+/g, ' ').trim();
}

export function matches(input, target) { return normalize(input) === normalize(target); }

export function letterMarkup(input, target, reveal, hintCount = 0, showResult = false) {
  const typed = normalize(input);
  const answer = normalize(target);
  let position = 0;
  return answer.split(' ').map(word => {
    const letters = [...word].map(char => {
      const index = position++;
      const status = index < typed.length ? (showResult ? (typed[index] === char ? 'correct' : 'wrong') : 'typed') : index === typed.length ? 'caret' : 'untyped';
      const visible = reveal || index < hintCount ? char : typed[index] || '\u00a0';
      return `<span class="letter ${status}">${escapeHtml(visible)}</span>`;
    }).join('');
    position++; // 单词之间的空格参与比较，但不画字母下划线。
    return `<span class="blank-word">${letters}</span>`;
  }).join(' ') + (typed.length > answer.length ? `<span class="wrong">${escapeHtml(typed.slice(answer.length))}</span>` : '');
}

export class TypingMeter {
  constructor() { this.reset(); }
  reset() { this.started = 0; this.keys = 0; this.errors = 0; this.previous = ''; this.finished = 0; }
  update(input, target) {
    if (!this.started && input) this.started = performance.now();
    // 粘贴由输入框阻止；只统计本次新插入的字符，不把退格当作正确输入。
    let prefix = 0;
    while (prefix < this.previous.length && prefix < input.length && this.previous[prefix] === input[prefix]) prefix++;
    const added = input.slice(prefix);
    if (added.length) {
      this.keys += added.length;
      for (let i = prefix; i < input.length; i++) {
        const partial = normalize(input.slice(0, i + 1));
        if (!normalize(target).startsWith(partial)) this.errors++;
      }
    }
    this.previous = input;
  }
  snapshot() {
    const elapsed = this.started ? ((this.finished || performance.now()) - this.started) / 1000 : 0;
    const correct = Math.max(0, this.keys - this.errors);
    return { seconds: Math.floor(elapsed), wpm: elapsed > 0 ? Math.round(correct / 5 / (Math.max(1, elapsed) / 60)) : 0,
      accuracy: this.keys ? Math.round(correct / this.keys * 100) : 100 };
  }
}
