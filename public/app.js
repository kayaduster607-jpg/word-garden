/** 页面协调器：练习、词库、记录和账号。业务数据通过独立 API 模块同步。 */
import { request, setCsrf, escapeHtml as e, toast, speak, eventId } from './api.js';
import { normalize, matches, letterMarkup, TypingMeter } from './typing.js';
import { meaningFor, grammarMarkup, mergeGrammar } from './prompts.js';

const state = {
  user: null, catalog: null, progress: {}, stats: {}, view: 'practice',
  kind: 'vocabulary', category: '全部', search: '', page: 0, queue: [], index: 0,
  reveal: false, hints: 0, helped: false, wrong: false, checked: false, input: '', showErrors: false,
  pending: null, saving: false, filter: '全部', lastSync: 0,
};
const meter = new TypingMeter();
const root = document.querySelector('#app');
let timer;

function currentCard() { return state.queue[state.index]; }
function targetFor(card) { return card.answer || card.en; }
function chinesePrompt(text) {
  // 原资料标题有时直接列出英语答案；默写区去掉英文，来源详情仍保留原文。
  return text.replace(/[A-Za-z]+(?:[ ’'./-][A-Za-z]+)*/g, '…');
}
function cardState(card) {
  const item = state.progress[card.id];
  if (!item) return '未学习';
  if (item.repetitions >= 3 && item.interval_days >= 7) return '已掌握';
  return item.due <= Date.now() / 1000 ? '待复习' : '学习中';
}

function selectQueue(card = null) {
  const now = Date.now() / 1000;
  const candidates = state.catalog.cards.filter(item =>
    (state.kind === 'sentences' ? item.kind === 'sentence' : item.kind !== 'sentence') &&
    !item.template && (state.filter === '全部' || item.category === state.filter));
  candidates.sort((a, b) => {
    const pa = state.progress[a.id], pb = state.progress[b.id];
    const rank = p => !p ? 1 : p.due <= now ? 0 : 2;
    return rank(pa) - rank(pb) || (pa?.due || 0) - (pb?.due || 0);
  });
  state.queue = card ? [card] : candidates.slice(0, state.user?.goal || 20);
  state.index = 0;
  resetPrompt();
}

function resetPrompt() {
  state.reveal = false; state.hints = 0; state.helped = false;
  state.wrong = false; state.checked = false; state.pending = null;
  state.input = '';
  state.showErrors = false;
  meter.reset();
}

async function sync() {
  if (!state.user) return;
  const result = await request('state');
  state.progress = result.progress; state.stats = result.stats;
  state.lastSync = Date.now();
  const badge = document.querySelector('#sync-label');
  if (badge) badge.textContent = '进度已同步';
}

function sidebar() {
  return `<aside class="sidebar">
    <button id="brand-home" class="brand" aria-label="词间首页"><img src="/assets/sprout.svg" alt="" width="40" height="40"><span>词间<small>WORD GARDEN</small></span></button>
    <nav aria-label="主要导航">${[['practice', '⌨', '拼写学习'], ['library', '▤', '词汇手册'], ['history', '▥', '学习记录']].map(([id, icon, text]) =>
      `<button class="nav-item ${state.view === id ? 'active' : ''}" data-view="${id}" ${state.view === id ? 'aria-current="page"' : ''}><span aria-hidden="true">${icon}</span>${text}</button>`).join('')}</nav>
    <div class="sidebar-note">在词汇的土壤里，<br>长出更大的世界。<span>—</span></div>
    <button id="account-button" class="account"><span class="avatar">${state.user ? e(state.user.username[0].toUpperCase()) : '访'}</span><span>${e(state.user?.username || '访客体验')}<small id="sync-label">${state.user ? '进度已同步' : '登录后跨设备同步'}</small></span><span>↗</span></button>
  </aside>`;
}

function render() {
  clearInterval(timer);
  const titles = { practice: ['让表达，落在指尖。', 'RECALL · TYPE · REMEMBER'], library: ['把词放回语境里。', '词汇 · 搭配 · 高频句子'], history: ['每一次回想，都算数。', 'YOUR LEARNING JOURNEY'], account: ['安心学习，自在切换。', 'YOUR WORD GARDEN'] };
  const [title, subtitle] = titles[state.view];
  root.innerHTML = `${sidebar()}<main id="main" tabindex="-1">
    <header class="page-heading"><div><p class="eyebrow">${subtitle}</p><h1>${title}</h1></div><div class="header-date">${new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', timeZone: 'Asia/Shanghai' }).format(new Date())}<small>${state.user ? '今日 ' + (state.stats.today || 0) + ' / ' + state.user.goal : '每天一点，慢慢生长'}</small></div></header>
    ${!state.user ? '<div class="guest-banner">正在访客体验，练习记录仅在当前页面有效。<button id="banner-login" class="text-button">登录并同步 ↗</button></div>' : ''}
    ${state.view === 'practice' ? practiceMarkup() : state.view === 'library' ? libraryMarkup() : state.view === 'history' ? historyMarkup() : accountMarkup()}
    <footer class="page-footer">CET-6 写作与翻译表达库<span>词间 · 把认识的词，变成能用的表达。</span></footer>
  </main><dialog id="detail-dialog"></dialog>`;
  bindNavigation();
  if (state.view === 'practice') bindPractice();
  if (state.view === 'library') bindLibrary();
  if (state.view === 'account') bindAccount();
}

function practiceMarkup() {
  const card = currentCard();
  const counts = state.catalog.cards.reduce((sum, item) => { sum[item.kind === 'sentence' ? 'sentences' : 'vocabulary']++; return sum; }, { vocabulary: 0, sentences: 0 });
  return `<div class="practice-controls"><div class="tabs" role="group" aria-label="练习内容">
    <button data-kind="vocabulary" class="${state.kind === 'vocabulary' ? 'selected' : ''}" aria-pressed="${state.kind === 'vocabulary'}">单词与词组 <small>${counts.vocabulary}</small></button>
    <button data-kind="sentences" class="${state.kind === 'sentences' ? 'selected' : ''}" aria-pressed="${state.kind === 'sentences'}">高频句子 <small>${counts.sentences}</small></button></div>
    <label class="filter-label">范围 <select id="practice-filter"><option>全部</option><option ${state.filter === '写作表达' ? 'selected' : ''}>写作表达</option><option ${state.filter === '翻译词汇' ? 'selected' : ''}>翻译词汇</option></select></label><span class="mode-label">默写模式</span></div>
    <div class="practice-layout"><section class="typing-workspace" aria-label="拼写练习">
    ${!card ? `<div class="session-done"><img src="/assets/sprout.svg" alt="" width="64"><h2>这一轮，记住了。</h2><p>已完成 ${state.queue.length} 条练习。明天再回想一次，让记忆更牢。</p><button id="restart" class="primary">再练一轮</button></div>` : `
      <div class="prompt-meta"><span>${e(card.category)} / ${e(chinesePrompt(card.topic))}</span><span>${state.index + 1} / ${state.queue.length}</span></div>
      <div class="grammar-row">${grammarMarkup(card)}<span>${card.otherPos ? '本条考查此词性' : e(card.grammarNote || '')}</span></div>
      <h2 class="chinese-prompt">${e(chinesePrompt(meaningFor(card)))}</h2>
      ${card.promptContext ? `<p class="chinese-context">${e(card.promptContext)}</p>` : ''}
      <p class="prompt-note">${card.kind === 'sentence' && card.zh.startsWith('语境提示') ? '这是关键词提示，请回忆资料中的完整例句。' : card.template ? '句架练习：占位符也按原样输入；可主动提示。' : '看中文，回忆英文。答案藏在下划线里。'}</p>
      <form id="typing-form"><label class="sr-only" for="typing-input">输入英文答案</label>
        <div class="typing-capture"><div id="letter-display" class="letter-display ${targetFor(card).length > 35 ? 'sentence-blanks' : ''}" aria-hidden="true"></div>
        <textarea id="typing-input" class="direct-typing-input" rows="2" lang="en" inputmode="text" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" aria-describedby="typing-feedback typing-instruction"></textarea></div>
        <p id="typing-instruction" class="input-instruction">点击下划线直接输入英文，按 <kbd>Enter</kbd> 提交。</p>
        <div id="typing-feedback" class="feedback" role="status">忽略大小写和句末标点；单词、词序和拼写需正确。</div>
        <div class="typing-actions"><button id="check-button" class="primary" type="submit">检查拼写 <span>↵</span></button><button id="letter-hint" class="secondary" type="button">提示一个字母</button><button id="reveal-answer" class="text-button" type="button">查看答案</button><button id="read-answer" class="text-button" type="button" aria-label="朗读英文答案">♫ 朗读</button></div>
      </form>
      <details id="usage-detail" class="usage-detail" ${state.checked ? 'open' : ''}><summary>答对后查看搭配与来源</summary><div id="usage-content">先完成拼写，再看用法。</div></details>
    `}
    <div class="typing-metrics"><div><strong>${Math.min(state.index, state.queue.length)}<small> / ${state.queue.length}</small></strong><span>当前进度</span></div><div><strong id="metric-time">00:00</strong><span>本条用时</span></div><div><strong id="metric-wpm">—</strong><span>WPM</span></div><div><strong id="metric-accuracy">—</strong><span>输入准确率</span></div></div>
    <p class="keyboard-note"><kbd>Enter</kbd> 检查 / 下一条 <kbd>Esc</kbd> 清空输入 <span>用过提示的内容会更早复习。</span></p></section>
    <aside class="garden-panel"><img src="/assets/ginkgo.webp" alt="银杏幼苗与根系的植物插画"><div><p>每一次回想，<br>都是一次生长。</p><span>GROW A LITTLE, EVERY DAY.</span></div></aside></div>`;
}

function bindNavigation() {
  document.querySelector('#brand-home').onclick = () => { state.view = 'practice'; render(); };
  document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', async () => {
    state.view = button.dataset.view;
    if (state.user) { try { await sync(); } catch (error) { toast(error.message); } }
    render();
  }));
  document.querySelector('#account-button').onclick = () => { state.view = 'account'; render(); };
  const login = document.querySelector('#banner-login');
  if (login) login.onclick = () => { state.view = 'account'; render(); };
}

function bindPractice() {
  document.querySelectorAll('[data-kind]').forEach(button => button.onclick = () => {
    state.kind = button.dataset.kind; selectQueue(); render();
  });
  document.querySelector('#practice-filter').onchange = event => { state.filter = event.target.value; selectQueue(); render(); };
  const input = document.querySelector('#typing-input');
  if (!input) { document.querySelector('#restart').onclick = () => { selectQueue(); render(); }; return; }
  input.value = state.input;
  if (state.checked) {
    input.readOnly = true;
    document.querySelector('#check-button').textContent = '下一条 →';
    document.querySelector('#usage-content').innerHTML = cardDetail(currentCard());
    document.querySelector('#typing-feedback').textContent = '本条已完成并记录，按 Enter 进入下一条。';
  }
  updateLetters();
  timer = setInterval(updateMetrics, 1000);
  input.addEventListener('input', event => {
    if (event.isComposing || state.checked) return;
    state.input = input.value;
    state.showErrors = false;
    meter.update(input.value, targetFor(currentCard()));
    updateLetters(); updateMetrics();
  });
  input.addEventListener('paste', event => { event.preventDefault(); toast('这一条自己拼出来，更容易记住。'); });
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); submitAnswer(); }
    if (event.key === 'Escape' && !state.checked) { input.value = ''; state.input = ''; meter.previous = ''; updateLetters(); }
  });
  document.querySelector('#typing-form').onsubmit = event => { event.preventDefault(); submitAnswer(); };
  document.querySelector('#letter-hint').onclick = () => {
    state.helped = true;
    const target = normalize(targetFor(currentCard()));
    // 提示第一个尚未正确输入的字母，不只重复提示已经打对的部分。
    let firstWrong = 0;
    while (firstWrong < input.value.length && normalize(input.value)[firstWrong] === target[firstWrong]) firstWrong++;
    state.hints = Math.min(target.length, Math.max(state.hints + 1, firstWrong + 1));
    updateLetters(); input.focus();
  };
  document.querySelector('#reveal-answer').onclick = () => { state.helped = true; state.reveal = !state.reveal; updateLetters(); input.focus(); };
  document.querySelector('#read-answer').onclick = () => { state.helped = true; speak(targetFor(currentCard())); };
  if (window.matchMedia('(min-width: 681px)').matches) input.focus({ preventScroll: true });
}

function updateLetters() {
  const input = document.querySelector('#typing-input');
  const display = document.querySelector('#letter-display');
  if (input && display) display.innerHTML = letterMarkup(input.value, targetFor(currentCard()), state.reveal || state.checked, state.hints, state.showErrors || state.checked);
}

function updateMetrics() {
  const stats = meter.snapshot();
  const time = document.querySelector('#metric-time');
  if (!time) return;
  time.textContent = `${String(Math.floor(stats.seconds / 60)).padStart(2, '0')}:${String(stats.seconds % 60).padStart(2, '0')}`;
  document.querySelector('#metric-wpm').textContent = meter.keys ? stats.wpm : '—';
  document.querySelector('#metric-accuracy').textContent = meter.keys ? stats.accuracy + '%' : '—';
}

async function submitAnswer() {
  if (state.saving) return;
  if (state.checked) { state.index++; resetPrompt(); render(); document.querySelector('#typing-input')?.focus(); return; }
  const input = document.querySelector('#typing-input');
  const feedback = document.querySelector('#typing-feedback');
  const card = currentCard();
  if (!input.value.trim()) { feedback.textContent = '先输入你想到的英文；想不起来可以提示一个字母。'; input.focus(); return; }
  if (!matches(input.value, targetFor(card))) {
    state.wrong = true;
    state.showErrors = true;
    feedback.textContent = '还差一点。红色位置有误，请修改后再按 Enter；答案仍保持隐藏。';
    feedback.classList.add('error'); updateLetters(); return;
  }
  state.pending ||= { cardId: card.id, rating: state.helped || state.wrong ? 'again' : 'good', mode: 'dictation', eventId: eventId() };
  state.saving = true;
  const button = document.querySelector('#check-button');
  button.disabled = true; button.textContent = state.user ? '正在同步…' : '正在记录…';
  try {
    if (state.user) {
      await request('review', state.pending);
      await sync();
    } else {
      const old = state.progress[card.id];
      state.progress[card.id] = { repetitions: state.pending.rating === 'good' ? (old?.repetitions || 0) + 1 : 0, interval_days: 1, due: Date.now() / 1000 + (state.pending.rating === 'again' ? 600 : 86400) };
    }
    state.checked = true; meter.finished = performance.now(); input.readOnly = true;
    feedback.textContent = state.pending.rating === 'again' ? '拼对了。这条用过提示或有误，将在 10 分钟后优先复习。' : '拼写正确，记忆又扎实了一点。';
    feedback.classList.remove('error'); feedback.classList.add('success');
    button.textContent = '下一条 →';
    for (const id of ['letter-hint', 'reveal-answer']) document.getElementById(id).disabled = true;
    const details = document.querySelector('#usage-detail');
    details.open = true; details.querySelector('summary').textContent = '搭配与来源';
    document.querySelector('#usage-content').innerHTML = cardDetail(card);
    updateLetters(); updateMetrics();
  } catch (error) {
    feedback.textContent = '尚未确认同步成功：' + error.message + ' 保留当前输入，点击重试。';
    feedback.classList.add('error'); button.textContent = '重试同步 ↻';
    if (error.status === 401) toast('会话已过期，请在“我的账号”重新登录。');
  } finally { state.saving = false; button.disabled = false; }
}

function filteredLibrary() {
  const query = state.search.trim().toLowerCase();
  return state.catalog.cards.filter(card =>
    (!query || [card.en, meaningFor(card), card.posLabel, card.usage, card.example].some(text => text.toLowerCase().includes(query))) &&
    (state.category === '全部' || state.category === '高频句子' ? state.category === '全部' || card.kind === 'sentence' : card.category === state.category && card.kind !== 'sentence'));
}

function libraryMarkup() {
  const list = filteredLibrary();
  const pages = Math.max(1, Math.ceil(list.length / 12));
  state.page = Math.min(state.page, pages - 1);
  return `<section class="library"><label class="search-field"><span aria-hidden="true">⌕</span><input id="search-input" type="search" placeholder="搜索英文、中文、搭配或例句" aria-label="搜索词库" value="${e(state.search)}"></label>
    <div class="tabs library-tabs">${['全部', '写作表达', '翻译词汇', '高频句子'].map(name => `<button data-category="${name}" class="${state.category === name ? 'selected' : ''}" aria-pressed="${state.category === name}">${name}</button>`).join('')}</div>
    <div id="library-results">${libraryRows(list, pages)}</div>
    <p class="source-note">${e(state.catalog.source)} · “高频”为原资料分类，未经独立频率统计。句架含占位符，完整例句可用于拼写；非官方唯一译文。</p></section>`;
}

function libraryRows(list, pages) {
  return `<div class="vocab-table"><div class="table-head"><span>表达</span><span>中文与语境</span><span>状态</span></div>
    ${list.slice(state.page * 12, state.page * 12 + 12).map(card => `<button class="vocab-row" data-card="${card.id}"><span class="english-expression">${e(card.en)}<small>${grammarMarkup(card)}</small></span><span>${e(meaningFor(card))}<small>${e(card.usage || card.topic)}</small></span><span class="status-tag">${cardState(card)}</span></button>`).join('') || '<p class="empty">没有找到，换个关键词试试。</p>'}</div>
    <div class="pagination"><span>共 ${list.length} 条 · 点击查看用法并练习</span><div><button id="previous-page" class="secondary" ${state.page === 0 ? 'disabled' : ''} aria-label="上一页">←</button><span>${state.page + 1} / ${pages}</span><button id="next-page" class="secondary" ${state.page + 1 >= pages ? 'disabled' : ''} aria-label="下一页">→</button></div></div>`;
}

function bindLibrary() {
  document.querySelector('#search-input').oninput = event => {
    state.search = event.target.value; state.page = 0;
    const list = filteredLibrary();
    document.querySelector('#library-results').innerHTML = libraryRows(list, Math.max(1, Math.ceil(list.length / 12)));
    bindLibraryRows();
  };
  document.querySelectorAll('[data-category]').forEach(button => button.onclick = () => { state.category = button.dataset.category; state.page = 0; render(); });
  bindLibraryRows();
}

function cardDetail(card) {
  return `<p class="detail-english">${e(card.en)}</p><div class="grammar-row">${grammarMarkup(card)}</div><p>${e(meaningFor(card))}</p>${card.promptContext ? `<p>${e(card.promptContext)}</p>` : ''}${card.otherPos ? `<p class="muted">其他常见用法：${e(card.otherPos)}。本条按上方义项练习。</p>` : ''}${card.usage ? `<p><strong>搭配与用法</strong> ${e(card.usage)}</p>` : ''}${card.example ? `<blockquote lang="en">${e(card.example)}</blockquote>` : ''}<p class="source-note">${e(card.note)}<br>资料章节：${e(card.sources[0].heading)}${card.dictionaryUrl ? `<br><a href="${e(card.dictionaryUrl)}" target="_blank" rel="noopener noreferrer">在剑桥词典核对词性与义项 ↗</a>` : ''}</p>`;
}

function bindLibraryRows() {
  document.querySelector('#previous-page').onclick = () => { state.page--; render(); };
  document.querySelector('#next-page').onclick = () => { state.page++; render(); };
  document.querySelectorAll('[data-card]').forEach(button => button.onclick = () => {
    const card = state.catalog.cards.find(item => item.id === button.dataset.card);
    const dialog = document.querySelector('#detail-dialog');
    dialog.innerHTML = `<button id="close-detail" class="dialog-close" aria-label="关闭词条">×</button>${cardDetail(card)}<p class="muted">${card.template ? '含占位符或同义替换的资料条目。练习时按本条目标形式输入。' : '默写时会隐藏英文，只显示提示和下划线。'}${card.en !== targetFor(card) ? '本轮使用资料中第一个表达：' + e(targetFor(card)) : ''}</p><button id="practice-this" class="primary">练习这一条 →</button>`;
    dialog.showModal();
    document.querySelector('#close-detail').onclick = () => dialog.close();
    document.querySelector('#practice-this').onclick = () => { dialog.close(); state.view = 'practice'; state.kind = card.kind === 'sentence' ? 'sentences' : 'vocabulary'; selectQueue(card); render(); document.querySelector('#typing-input').focus(); };
  });
}

function historyMarkup() {
  const stats = state.stats;
  return `<section class="history"><div class="summary-grid">${[['今日练习', stats.today || 0, '条不同表达'], ['待复习', stats.due || 0, '条表达'], ['已掌握', stats.mastered || 0, '至少 3 次正确且间隔 ≥ 7 天'], ['连续学习', stats.streak || 0, '天']].map(([label, value, detail]) => `<div><span>${label}</span><strong>${value}</strong><small>${detail}</small></div>`).join('')}</div>
    <h2>最近的积累</h2><p class="muted">按北京时间统计；同一天重复练习同一条，只计入一条今日表达。</p>
    <div class="history-table"><div class="history-row table-head"><span>日期</span><span>表达数</span><span>练习次数</span><span>需重练</span></div>${(stats.daily || []).slice(0, 30).map(day => `<div class="history-row"><span>${day.day}</span><span>${day.cards}</span><span>${day.reviews}</span><span>${day.mistakes}</span></div>`).join('') || '<p class="empty">还没有账号记录。完成一次拼写，就会种下第一颗种子。</p>'}</div>
    <p class="source-note">这里使用简明的间隔复习规则：正确后 1、3、7 天逐步延长；使用提示或拼错后 10 分钟重练。统计反映本网站练习记录，不代表考试得分。</p></section>`;
}

function accountMarkup() {
  if (!state.user) return `<section class="account-layout"><div class="account-form"><p class="eyebrow">WELCOME BACK</p><h2>接着上次，继续生长。</h2><p class="muted">登录同一账号，手机和电脑共享学习进度。</p><form id="login-form"><label>账号<input name="username" autocomplete="username" required maxlength="32" placeholder="你的学习账号"></label><label>密码<input name="password" type="password" autocomplete="current-password" required maxlength="128" placeholder="输入密码"></label><p id="login-feedback" class="feedback" role="status"></p><button class="primary" type="submit">登录词间 →</button></form><p class="source-note">账号由服务器管理员创建。首次使用请按部署说明创建自己的账号。</p><button class="text-button" id="back-to-demo">先体验拼写学习</button></div><div class="account-art"><img src="/assets/ginkgo.webp" alt="银杏幼苗插画"></div></section>`;
  return `<section class="settings"><h2>${e(state.user.username)} 的词间</h2><p class="muted">进度保存在服务器。切换设备后登录同一账号，打开页面时会自动读取最新记录。</p>
    <form id="goal-form"><label>每天练习目标 <input name="goal" type="number" min="5" max="200" value="${state.user.goal}" required></label><button class="secondary">保存目标</button></form>
    <div class="settings-actions"><button id="export-progress" class="secondary">导出个人练习记录</button><button id="refresh-progress" class="secondary">同步最新进度</button><button id="logout-button" class="text-button">退出登录</button></div>
    <details class="password-details"><summary>修改密码</summary><form id="password-form"><label>当前密码<input type="password" name="oldPassword" autocomplete="current-password" required></label><label>新密码<input type="password" name="newPassword" autocomplete="new-password" minlength="12" maxlength="128" required></label><label>确认新密码<input type="password" name="confirm" autocomplete="new-password" minlength="12" maxlength="128" required></label><button class="secondary">更新密码并退出其他设备</button></form></details>
    <p class="source-note">个人记录导出用于查阅。迁移和灾难恢复请使用服务器完整数据库备份。离线时不会显示“同步成功”；页面会保留本条答案供你重试。</p></section>`;
}

function bindAccount() {
  if (!state.user) {
    document.querySelector('#back-to-demo').onclick = () => { state.view = 'practice'; render(); };
    document.querySelector('#login-form').onsubmit = async event => {
      event.preventDefault();
      const form = event.currentTarget, button = form.querySelector('button');
      button.disabled = true;
      try {
        const data = Object.fromEntries(new FormData(form));
        const user = await request('login', data);
        state.user = user; setCsrf(user.csrf);
        await sync(); selectQueue(); state.view = 'practice'; render(); toast('已登录，进度已同步。');
      } catch (error) { document.querySelector('#login-feedback').textContent = error.message; }
      finally { button.disabled = false; }
    };
    return;
  }
  document.querySelector('#goal-form').onsubmit = async event => {
    event.preventDefault();
    try { const goal = Number(new FormData(event.currentTarget).get('goal')); await request('settings', { goal }); state.user.goal = goal; toast('每日目标已保存，下轮练习生效。'); }
    catch (error) { toast(error.message); }
  };
  document.querySelector('#refresh-progress').onclick = async () => { try { await sync(); toast('已读取服务器最新进度。'); } catch (error) { toast(error.message); } };
  document.querySelector('#export-progress').onclick = async () => {
    try {
      const data = await request('export');
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'wordgarden-progress.json'; link.click(); URL.revokeObjectURL(url);
    } catch (error) { toast(error.message); }
  };
  document.querySelector('#logout-button').onclick = async () => {
    try { await request('logout', {}); resetLogin(); render(); } catch (error) { toast(error.message); }
  };
  document.querySelector('#password-form').onsubmit = async event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.newPassword !== data.confirm) return toast('两次输入的新密码不一致。');
    try { await request('password', data); resetLogin(); render(); toast('密码已更新，请重新登录。'); } catch (error) { toast(error.message); }
  };
}

function resetLogin() {
  state.user = null; state.progress = {}; state.stats = {}; setCsrf(''); selectQueue();
}

async function initialize() {
  try {
    const catalog = await request('catalog');
    const grammarResponse = await fetch('/assets/grammar.json', { cache: 'no-store' });
    if (!grammarResponse.ok) throw new Error('词性资料加载失败，请刷新后重试。');
    state.catalog = mergeGrammar(catalog, await grammarResponse.json());
    try { const user = await request('me'); state.user = user; setCsrf(user.csrf); await sync(); }
    catch (error) { if (error.status !== 401) toast('暂未读到账号状态：' + error.message); }
    selectQueue(); render();
  } catch (error) {
    root.innerHTML = `<main class="loading"><h1>暂时没能翻开词间</h1><p>${e(error.message)}</p><button id="reload" class="primary">重新连接</button></main>`;
    document.querySelector('#reload').onclick = initialize;
  }
}

// 返回页面或每隔半分钟获取最新进度，不替换正在输入的内容。
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && state.user) sync().catch(error => toast('同步未完成：' + error.message));
});
setInterval(() => { if (state.user && !document.hidden && !state.saving) sync().catch(() => {
  const badge = document.querySelector('#sync-label'); if (badge) badge.textContent = '连接中断，等待重试';
}); }, 30000);
initialize();
