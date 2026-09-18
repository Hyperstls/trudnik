/**
 * Чат 2.0 (B5): разделители дат, локальное время, оптимистичная отправка
 * со статусами («отправляется» → «отправлено» → «ошибка» + повтор),
 * polling-fallback и перевыпуск WS-токена перед реконнектом.
 *
 * Конфиг — window.CHAT_CONFIG из templates/chat.html:
 *   { applicationId, currentUserId, lastMessageId }
 * Глобальные зависимости: apiFetch, escapeHtml, NotificationsWS (опционально),
 * showToast (опционально).
 */
(function () {
    'use strict';

    var config = window.CHAT_CONFIG || {};
    var applicationId = config.applicationId || '';
    var currentUserId = config.currentUserId || '';
    var lastMessageId = config.lastMessageId || '';

    var container = null; // #chat-messages, заполняется на load

    // Оптимистичные сообщения: client_message_id → { content, rowId, ts }
    var pending = {};

    var timeFmt = new Intl.DateTimeFormat('ru-RU', { hour: '2-digit', minute: '2-digit' });
    var RU_MONTHS_GEN = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
        'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'];

    var STATUS_ICONS = {
        sending: '<svg class="w-3.5 h-3.5 animate-pulse" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>',
        sent: '<svg class="w-3.5 h-3.5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m4.5 12.75 6 6 9-13.5"/></svg>',
        error: '<svg class="w-3.5 h-3.5 text-red-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m0 3.75h.008v.008H12v-.008ZM21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>'
    };

    // ── Время и даты ─────────────────────────────────────────────

    function parseIsoTs(ts) {
        if (!ts) return null;
        var s = String(ts).trim();
        // Safari не парсит >3 цифр дробных секунд — усекаем
        s = s.replace(/(\.\d{3})\d+/, '$1');
        // created_at в БД — UTC: если смещение не указано, считаем UTC
        if (!/(Z|[+-]\d{2}:?\d{2})$/i.test(s)) s += 'Z';
        var d = new Date(s);
        return isNaN(d.getTime()) ? null : d;
    }

    function formatTime(ts) {
        var d = parseIsoTs(ts);
        return d ? timeFmt.format(d) : '';
    }

    function dayKey(d) {
        return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate();
    }

    function dayLabel(d) {
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        var day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
        var diffDays = Math.round((today - day) / 86400000);
        if (diffDays === 0) return 'Сегодня';
        if (diffDays === 1) return 'Вчера';
        var label = day.getDate() + ' ' + RU_MONTHS_GEN[day.getMonth()];
        if (day.getFullYear() !== today.getFullYear()) label += ' ' + day.getFullYear();
        return label;
    }

    function createDivider(label, key) {
        var div = document.createElement('div');
        div.className = 'chat-date-divider flex items-center gap-3 py-1';
        div.setAttribute('data-day', key);
        div.innerHTML =
            '<span class="flex-1 border-t border-neutral-200"></span>' +
            '<time class="chat-date-label text-[11px] font-medium text-neutral-400 px-1"></time>' +
            '<span class="flex-1 border-t border-neutral-200"></span>';
        div.querySelector('time').textContent = label;
        return div;
    }

    /** Пересчитать серверные дивидеры в локальной TZ (история отрендерена по UTC). */
    function rebuildDividers() {
        if (!container) return;
        var old = container.querySelectorAll('.chat-date-divider');
        for (var i = 0; i < old.length; i++) old[i].remove();
        var rows = container.querySelectorAll('.msg-row[data-ts]');
        var prevKey = null;
        for (var j = 0; j < rows.length; j++) {
            var d = parseIsoTs(rows[j].getAttribute('data-ts'));
            if (!d) continue;
            var key = dayKey(d);
            if (key !== prevKey) {
                container.insertBefore(createDivider(dayLabel(d), key), rows[j]);
                prevKey = key;
            }
        }
    }

    /** Переписать время всех сообщений в локальной TZ (сервер режет сырую строку UTC). */
    function rewriteTimes() {
        if (!container) return;
        var times = container.querySelectorAll('.msg-time[datetime]');
        for (var i = 0; i < times.length; i++) {
            var formatted = formatTime(times[i].getAttribute('datetime'));
            if (formatted) times[i].textContent = formatted;
        }
    }

    /** Вставить дивидер, если день нового сообщения отличается от последнего в ленте. */
    function insertDividerIfNeeded(ts) {
        var d = parseIsoTs(ts);
        if (!d || !container) return;
        var rows = container.querySelectorAll('.msg-row[data-ts]');
        var lastRow = rows.length ? rows[rows.length - 1] : null;
        var lastD = lastRow ? parseIsoTs(lastRow.getAttribute('data-ts')) : null;
        if (lastD && dayKey(lastD) === dayKey(d)) return;
        container.appendChild(createDivider(dayLabel(d), dayKey(d)));
    }

    // ── Сообщения ────────────────────────────────────────────────

    function setStatus(row, status, cmid) {
        var el = row.querySelector('.msg-status');
        if (!el) return;
        el.setAttribute('data-status', status);
        el.innerHTML = STATUS_ICONS[status] || '';
        if (status === 'error') {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'msg-retry ml-1 underline font-medium text-xs text-white';
            btn.textContent = 'Повторить';
            btn.addEventListener('click', function () { retryMessage(cmid); });
            el.appendChild(btn);
        }
    }

    function buildRow(msg, isMine) {
        var row = document.createElement('div');
        row.className = 'msg-row flex ' + (isMine ? 'justify-end' : 'justify-start') + ' animate-fade-in';
        if (msg.id) row.id = 'msg-' + msg.id;
        if (msg.created_at) row.setAttribute('data-ts', msg.created_at);

        var bubble = document.createElement('div');
        bubble.className = 'max-w-[80%] px-4 py-2 rounded-2xl shadow-sm text-sm leading-relaxed break-words ' +
            (isMine ? 'bg-primary-500 text-white rounded-br-md' : 'bg-neutral-100 text-neutral-800 rounded-bl-md');

        var content = document.createElement('span');
        content.className = 'msg-content';
        content.textContent = msg.content || '';

        var meta = document.createElement('div');
        meta.className = 'msg-meta flex items-center justify-end gap-1 text-xs mt-0.5 ' +
            (isMine ? 'text-white/60' : 'text-neutral-400');

        var time = document.createElement('time');
        time.className = 'msg-time';
        if (msg.created_at) time.setAttribute('datetime', msg.created_at);
        time.textContent = formatTime(msg.created_at);
        meta.appendChild(time);

        if (isMine) {
            var status = document.createElement('span');
            status.className = 'msg-status inline-flex items-center';
            status.setAttribute('data-status', 'sent');
            status.innerHTML = STATUS_ICONS.sent;
            meta.appendChild(status);
        }

        bubble.appendChild(content);
        bubble.appendChild(meta);
        row.appendChild(bubble);
        return row;
    }

    function scrollSmooth() {
        if (container) container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    }

    function highlight(row) {
        var bubble = row.querySelector('div');
        if (!bubble) return;
        bubble.style.transition = 'box-shadow 0.5s ease';
        bubble.style.boxShadow = '0 0 0 3px rgba(217,119,6,0.3)';
        setTimeout(function () { bubble.style.boxShadow = ''; }, 1500);
    }

    function unescapeHtml(s) {
        var d = document.createElement('div');
        d.innerHTML = s || '';
        return d.textContent;
    }

    /** Найти оптимистичный ряд с тем же текстом (fallback, когда cmid недоступен). */
    function findOptimisticByContent(serverContent) {
        var raw = unescapeHtml(serverContent);
        var rows = container.querySelectorAll('.msg-row[data-cmid]');
        for (var i = 0; i < rows.length; i++) {
            var cmid = rows[i].getAttribute('data-cmid');
            if (pending[cmid] && pending[cmid].content === raw) return rows[i];
        }
        return null;
    }

    /** Привязать реальное серверное сообщение к оптимистичному ряду. */
    function finalizeRow(row, msg) {
        if (msg.id) row.id = 'msg-' + msg.id;
        row.removeAttribute('data-cmid');
        if (msg.created_at) {
            row.setAttribute('data-ts', msg.created_at);
            var time = row.querySelector('.msg-time');
            if (time) {
                time.setAttribute('datetime', msg.created_at);
                time.textContent = formatTime(msg.created_at);
            }
        }
        setStatus(row, 'sent');
    }

    /**
     * Добавить сообщение в ленту с дедупликацией:
     * 1) по серверному id (poll/WS могут прислать уже отрисованное);
     * 2) по client_message_id (идемпотентная отправка / retry);
     * 3) по тексту среди оптимистичных (fallback).
     */
    function addMessage(msg, isMine) {
        if (!container) return null;
        if (msg.id && document.getElementById('msg-' + msg.id)) return null;

        var cmid = msg.client_message_id;
        if (cmid && pending[cmid]) {
            var entry = pending[cmid];
            delete pending[cmid];
            var prow = document.getElementById(entry.rowId);
            if (prow) {
                finalizeRow(prow, msg);
                return prow;
            }
        }
        if (isMine) {
            var opt = findOptimisticByContent(msg.content);
            if (opt) {
                delete pending[opt.getAttribute('data-cmid')];
                finalizeRow(opt, msg);
                return opt;
            }
        }

        var row = buildRow(msg, isMine);
        insertDividerIfNeeded(msg.created_at);
        container.appendChild(row);
        highlight(row);
        scrollSmooth();
        return row;
    }

    // ── Отправка (оптимистичная, идемпотентная по client_message_id) ──

    function makeClientMessageId() {
        if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID();
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
            var r = Math.random() * 16 | 0;
            return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
        });
    }

    function addOptimistic(content, cmid) {
        var tempId = 'msg-local-' + cmid;
        var nowIso = new Date().toISOString();
        var row = buildRow({ sender_id: currentUserId, content: content, created_at: nowIso }, true);
        row.id = tempId;
        row.setAttribute('data-cmid', cmid);
        pending[cmid] = { content: content, rowId: tempId, ts: Date.now() };
        insertDividerIfNeeded(nowIso);
        container.appendChild(row);
        setStatus(row, 'sending');
        scrollSmooth();
        return row;
    }

    async function deliver(content, cmid, row) {
        setStatus(row, 'sending');
        try {
            var abortCtrl = new AbortController();
            var timeoutId = setTimeout(function () { abortCtrl.abort(); }, 15000);
            var resp = await apiFetch('/api/send_message', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    application_id: applicationId,
                    content: content,
                    client_message_id: cmid
                }),
                signal: abortCtrl.signal
            });
            clearTimeout(timeoutId);

            if (!resp.ok) {
                var errData = await resp.json().catch(function () { return {}; });
                if (resp.status === 429 && window.showToast) {
                    window.showToast('Слишком много сообщений — подождите немного', 'error');
                }
                throw new Error(errData.message || errData.error || ('Ошибка отправки (' + resp.status + ')'));
            }

            var data = await resp.json().catch(function () { return {}; });
            // Серверная идемпотентность: при дубле вернётся существующий message_id.
            // Реальный id привязываем сразу — poll/WS-дубликат отсекается по id,
            // а запись в pending остаётся до финализации по client_message_id.
            if (data.message_id) row.id = 'msg-' + data.message_id;
            if (data.created_at) {
                row.setAttribute('data-ts', data.created_at);
                var time = row.querySelector('.msg-time');
                if (time) {
                    time.setAttribute('datetime', data.created_at);
                    time.textContent = formatTime(data.created_at);
                }
            }
            setStatus(row, 'sent');
            await pollMessages();
        } catch (e) {
            setStatus(row, 'error', cmid);
            if (window.showToast) {
                if (e && e.name === 'AbortError') {
                    window.showToast('⏱ Превышено время ожидания. Попробуйте ещё раз.', 'error');
                } else {
                    window.showToast('❌ ' + ((e && e.message) || 'Ошибка отправки сообщения'), 'error');
                }
            }
        }
    }

    function retryMessage(cmid) {
        var entry = pending[cmid];
        if (!entry) return;
        var row = document.getElementById(entry.rowId);
        if (!row) {
            delete pending[cmid];
            return;
        }
        deliver(entry.content, cmid, row);
    }

    async function sendMessage(event) {
        if (event) event.preventDefault();
        var input = document.getElementById('message-input');
        var content = input.value.trim();
        if (!content) return;

        var cmid = makeClientMessageId();
        var row = addOptimistic(content, cmid);
        input.value = '';
        input.style.height = 'auto';
        await deliver(content, cmid, row);
    }

    // ── Polling (рекурсивный setTimeout + AbortController + backoff) ──

    var chatPollTimer = null;
    var chatPollDelay = 3000;
    var chatAbortController = null;

    async function pollMessages() {
        try {
            var url = '/api/messages/' + applicationId + '/poll' +
                (lastMessageId ? '?since_id=' + encodeURIComponent(lastMessageId) : '');
            var resp = await apiFetch(url, {
                signal: chatAbortController ? chatAbortController.signal : undefined
            });
            if (!resp.ok) return;
            var data = await resp.json();
            for (var i = 0; i < data.messages.length; i++) {
                var msg = data.messages[i];
                if (String(msg.id) !== String(lastMessageId)) {
                    addMessage(msg, msg.sender_id === currentUserId);
                    lastMessageId = msg.id;
                }
            }
            // Сброс задержки при успешном запросе
            chatPollDelay = 3000;
        } catch (e) {
            if (e && e.name === 'AbortError') return;
            // Exponential backoff: 3s → 6s → 12s → 24s → 30s
            chatPollDelay = Math.min(30000, chatPollDelay * 2);
        }
    }

    function scheduleNextPoll() {
        chatAbortController = new AbortController();
        chatPollTimer = setTimeout(async function () {
            await pollMessages();
            scheduleNextPoll();
        }, chatPollDelay);
    }

    function startChatPolling() {
        stopChatPolling();
        chatPollDelay = 3000;
        chatAbortController = new AbortController();
        chatPollTimer = setTimeout(async function () {
            await pollMessages();
            scheduleNextPoll();
        }, chatPollDelay);
    }

    function stopChatPolling() {
        if (chatPollTimer) {
            clearTimeout(chatPollTimer);
            chatPollTimer = null;
        }
        if (chatAbortController) {
            chatAbortController.abort();
            chatAbortController = null;
        }
    }

    window.addEventListener('beforeunload', stopChatPolling);

    // ── WebSocket: события + перевыпуск токена при обрыве ────────

    var WS_WATCHDOG_DELAY = 45000;
    var wsWatchdogTimer = null;

    function isWsConnected() {
        var ws = window.NotificationsWS;
        return !!(ws && ws.ws && ws.ws.readyState === WebSocket.OPEN);
    }

    /** Перевыпросить WS-токен (TTL 5 мин) и переподключиться. */
    async function refreshWsTokenAndReconnect() {
        var nws = window.NotificationsWS;
        if (!nws || isWsConnected()) return;
        try {
            var resp = await apiFetch('/api/ws/token');
            if (!resp.ok) return;
            var data = await resp.json();
            if (data && data.token) {
                // connect() — no-op, если соединение уже устанавливается
                nws.connect(data.token);
            }
        } catch (e) {
            // Остаёмся на polling — watchdog сработает снова при следующем обрыве
        }
    }

    function scheduleWsWatchdog() {
        clearWsWatchdog();
        wsWatchdogTimer = setTimeout(function () {
            if (!isWsConnected()) refreshWsTokenAndReconnect();
        }, WS_WATCHDOG_DELAY);
    }

    function clearWsWatchdog() {
        if (wsWatchdogTimer) {
            clearTimeout(wsWatchdogTimer);
            wsWatchdogTimer = null;
        }
    }

    function onWsConnected() {
        clearWsWatchdog();
        stopChatPolling();
        pollMessages(); // Подтянуть пропущенные за время обрыва
    }

    function onWsDisconnected() {
        startChatPolling();
        // Токен живёт 5 мин: если реконнект затянулся — перевыпускаем сами
        scheduleWsWatchdog();
    }

    function onWsNewMessage(payload) {
        var msg = payload && payload.data;
        if (!msg) return;
        // Событие глобальное — рендерим только сообщения ЭТОГО чата
        if (msg.application_id !== applicationId) return;
        addMessage({
            id: msg.message_id || msg.id,
            sender_id: msg.sender_id,
            content: (msg.content != null) ? msg.content : msg.text,
            created_at: msg.created_at,
            client_message_id: msg.client_message_id
        }, msg.sender_id === currentUserId);
    }

    // ── Инициализация ────────────────────────────────────────────

    window.addEventListener('load', function () {
        container = document.getElementById('chat-messages');
        if (!container) return;

        var form = document.getElementById('chat-form');
        var msgInput = document.getElementById('message-input');

        // Серверная история отрендерена по UTC — пересчитываем в локальную TZ
        rebuildDividers();
        rewriteTimes();
        container.scrollTop = container.scrollHeight;

        if (msgInput) {
            msgInput.addEventListener('input', function () {
                this.style.height = 'auto';
                this.style.height = Math.min(this.scrollHeight, 128) + 'px';
            });
            msgInput.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    if (form) {
                        if (form.requestSubmit) form.requestSubmit();
                        else form.dispatchEvent(new Event('submit', { cancelable: true }));
                    }
                }
            });
        }
        if (form) form.addEventListener('submit', sendMessage);

        // Polling только если WebSocket не подключён
        if (!isWsConnected()) {
            startChatPolling();
        } else {
            pollMessages();
        }

        if (window.NotificationsWS) {
            window.NotificationsWS.on('connected', onWsConnected);
            window.NotificationsWS.on('disconnected', onWsDisconnected);
            window.NotificationsWS.on('new_message', onWsNewMessage);
        }
    });
})();
