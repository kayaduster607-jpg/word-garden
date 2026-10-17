/** 防止词性和义项在任何一个学习入口丢失，也避免在提示中泄露英文答案。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { grammarMarkup, meaningFor, mergeGrammar } from '../public/prompts.js';

const catalog = JSON.parse(fs.readFileSync(new URL('../data/catalog.json', import.meta.url), 'utf8'));
const metadata = JSON.parse(fs.readFileSync(new URL('../public/assets/grammar.json', import.meta.url), 'utf8'));

test('全部词汇有具体词性或短语类型，旧版接口也能合并最新提示', () => {
  const oldCatalog = { cards: catalog.cards.map(card => ({ id: card.id, en: card.en, zh: card.zh })) };
  mergeGrammar(oldCatalog, metadata);
  assert.equal(oldCatalog.cards.length, 683);
  for (const card of oldCatalog.cards) {
    assert.ok(card.pos && card.posLabel && meaningFor(card));
    assert.notEqual(card.posLabel, '词组');
    assert.ok(grammarMarkup(card).includes(card.posLabel));
  }
});

test('兼类词标本条词性，提示有中文含义而不是英文语法占位', () => {
  const get = word => catalog.cards.find(card => card.en === word);
  assert.equal(get('practice').pos, 'n.');
  assert.equal(get('practical').pos, 'adj.');
  assert.equal(get('affect').pos, 'v.');
  assert.equal(get('effect').pos, 'n.');
  assert.equal(get('address').pos, 'v.');
  assert.match(meaningFor(get('important')), /重要/);
  assert.match(meaningFor(get('affect')), /影响/);
  assert.equal(grammarMarkup(get('practice')).includes('practice'), false);
  assert.ok(get('practice').promptContext);
});

test('缺词性时停止显示该版本，不能默默回到无词性提示', () => {
  assert.throws(() => mergeGrammar({ cards: [{ id: 'missing' }] }, {}), /词性资料/);
});
