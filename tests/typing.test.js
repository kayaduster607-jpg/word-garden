/** 核验真实默写边界：答案不可提前出现在可见标记中，提示和输入才逐步显示。 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { normalize, matches, letterMarkup, TypingMeter } from '../public/typing.js';

test('单词与完整句子的默写比较允许标点差异，但不允许错词', () => {
  assert.equal(matches('ENHANCE', 'enhance'), true);
  assert.equal(matches("Students' skills", 'Students’ skills.'), true);
  assert.equal(matches('Public transport improves lives', 'Public transport improves life.'), false);
  assert.equal(matches('Regular practice improves skills.', 'Regular practice improves skills.'), true);
  assert.equal(normalize('  A   good idea!  '), 'a good idea');
});

test('初始下划线没有英文答案；自己的错误输入可见', () => {
  const blank = letterMarkup('', 'enhance', false);
  assert.equal(blank.includes('enhance'), false);
  assert.equal((blank.match(/class="letter /g) || []).length, 7);
  assert.equal(/>e<|>n<|>h</.test(blank), false);
  const beforeSubmit = letterMarkup('ex', 'enhance', false);
  assert.equal(beforeSubmit.includes('wrong'), false);
  const typed = letterMarkup('ex', 'enhance', false, 0, true);
  assert.match(typed, /correct">e</);
  assert.match(typed, /wrong">x</);
  assert.equal(typed.includes('>h<'), false);
});

test('字母提示只揭示所请求的前缀；句子按单词画空格', () => {
  assert.match(letterMarkup('', 'enhance', false, 1), />e</);
  assert.equal(letterMarkup('', 'enhance', false, 1).includes('>n<'), false);
  assert.match(letterMarkup('x', 'enhance', true), />e</);
  assert.equal((letterMarkup('', 'Gain experience.', false).match(/blank-word/g) || []).length, 2);
});

test('删除错误字符不会清除本条准确率中的错误记录', () => {
  const meter = new TypingMeter();
  meter.update('x', 'enhance');
  meter.update('', 'enhance');
  meter.update('e', 'enhance');
  assert.equal(meter.keys, 2);
  assert.equal(meter.errors, 1);
  assert.equal(meter.snapshot().accuracy, 50);
});
