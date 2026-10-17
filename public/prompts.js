/** 学习提示的语义层：展示本条义项的词性，兼类信息在答对后的详情中说明。 */
import { escapeHtml as e } from './api.js';

export function meaningFor(card) { return card.promptMeaning || card.zh; }

export function grammarMarkup(card) {
  const code = /^[a-z]+\./.test(card.pos) ? `<span class="pos-code">${e(card.pos)}</span>` : '';
  return `<span class="part-of-speech">${code}<strong>${e(card.posLabel)}</strong></span>`;
}

export function mergeGrammar(catalog, metadata) {
  for (const card of catalog.cards) {
    const detail = metadata[card.id];
    if (!detail?.pos || !detail?.posLabel || !detail?.promptMeaning) {
      throw new Error('词性资料未完整加载，请刷新页面后重试。');
    }
    Object.assign(card, detail);
  }
  return catalog;
}
