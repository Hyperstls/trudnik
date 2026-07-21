/**
 * Инициализация WebSocket и Push-уведомлений при загрузке страницы.
 */

document.addEventListener('DOMContentLoaded', function() {
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = String(text || '');
        return div.innerHTML;
    }

    // Инициализация WebSocket (только для аутентифицированных пользователей)
    // JWT-токен для WS НЕ встраивается в HTML (XSS) — запрашиваем через /api/ws/token.
    if (window.TRUDNIK_CONFIG?.userId && window.NotificationsWS) {
        // Обработчики регистрируются ДО connect(), чтобы не потерать первые события.

        // Обработчик новых уведомлений
        window.NotificationsWS.on('notification', function(data) {
            // Показываем toast-уведомление (если есть функция showToast)
            if (typeof showToast === 'function') {
                showToast(data.data?.text || 'Новое уведомление', 'info');
            }

            // Если пользователь на странице уведомлений — добавляем в список
            const notificationsList = document.getElementById('notifications-list');
            if (notificationsList && data.data) {
                const notif = data.data;
                const item = document.createElement('div');
                item.className = 'flex items-start gap-3 p-4 bg-white border border-neutral-100 rounded-xl hover:bg-neutral-50 transition-colors cursor-pointer';
                item.innerHTML = '<div class="w-10 h-10 rounded-full bg-primary-100 flex items-center justify-center shrink-0">' +
                    '<svg class="w-5 h-5 text-primary-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                    '<path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path></svg></div>' +
                    '<div class="flex-1 min-w-0"><p class="text-sm text-neutral-800"></p>' +
                    '<span class="text-xs text-neutral-400"></span></div>';
                item.querySelector('p').textContent = notif.text || notif.message || 'Новое уведомление';
                item.querySelector('span').textContent = notif.created_at || 'Только что';
                notificationsList.insertBefore(item, notificationsList.firstChild);
            }
        });

        // Обработчик новых сообщений чата
        window.NotificationsWS.on('new_message', function(data) {
            if (typeof showToast === 'function') {
                const senderName = data.data?.sender_name || 'Пользователь';
                showToast(`Новое сообщение от ${senderName}`, 'info');
            }

            // Если пользователь на странице чата — добавляем сообщение
            const chatMessages = document.getElementById('messages');
            if (chatMessages && data.data) {
                const msg = data.data;
                const isMine = msg.sender_id === (window.TRUDNIK_CONFIG?.userId || '');
                const wrapper = document.createElement('div');
                wrapper.className = 'flex ' + (isMine ? 'justify-end' : 'justify-start') + ' animate-fade-in';
                const bubble = document.createElement('div');
                bubble.className = 'max-w-[80%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed break-words ' +
                    (isMine ? 'bg-primary-500 text-white rounded-br-md' : 'bg-neutral-100 text-neutral-800 rounded-bl-md');
                bubble.textContent = msg.content || '';
                const time = document.createElement('div');
                time.className = 'text-[10px] mt-1 ' + (isMine ? 'text-white/60' : 'text-neutral-400') + ' text-right';
                time.textContent = (msg.created_at || '').substring(11, 16) || '';
                bubble.appendChild(time);
                wrapper.appendChild(bubble);
                chatMessages.appendChild(wrapper);
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        });

        // Обработчик отключения
        window.NotificationsWS.on('disconnected', function() {
            console.debug('WebSocket отключён');
        });

        // Токен запрашивается по защищённому эндпоинту (GET — CSRF не нужен)
        (async function() {
            try {
                const resp = await fetch('/api/ws/token');
                if (!resp.ok) { console.warn('WS token endpoint returned', resp.status); return; }
                const data = await resp.json();
                if (data.token) {
                    window.NotificationsWS.connect(data.token);
                }
            } catch (e) {
                console.error('WS token fetch failed:', e);
            }
        })();
    }

    // Передаём CSRF-токен в Service Worker (нужен для pushsubscriptionchange)
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content
            || document.cookie.split('; ').find(row => row.startsWith('csrf_token='))?.split('=')[1]
            || '';
        if (csrfToken) {
            navigator.serviceWorker.controller.postMessage({
                type: 'SET_CSRF_TOKEN',
                token: csrfToken
            });
        }
    }

    // Инициализация Push-уведомлений
    if (window.PushNotifications && window.TRUDNIK_CONFIG?.pushEnabled) {
        window.PushNotifications.init().then(function(initialized) {
            if (initialized) {
                // Проверяем, подписан ли уже пользователь
                window.PushNotifications.checkSubscription().then(function(isSubscribed) {
                    if (!isSubscribed && Notification.permission === 'default') {
                        // Показываем кнопку "Включить уведомления" если ещё не спрашивали
                        const pushBtn = document.getElementById('enable-push-btn');
                        if (pushBtn) {
                            pushBtn.style.display = 'block';
                            pushBtn.addEventListener('click', function() {
                                window.PushNotifications.subscribe().then(function(success) {
                                    if (success) {
                                        pushBtn.style.display = 'none';
                                        if (typeof showToast === 'function') {
                                            showToast('Push-уведомления включены', 'success');
                                        }
                                    }
                                });
                            });
                        }
                    }
                });
            }
        });
    }
});
