/**
 * Инициализация WebSocket и Push-уведомлений при загрузке страницы.
 */

document.addEventListener('DOMContentLoaded', function() {
    // Инициализация WebSocket (только для аутентифицированных пользователей)
    const token = window.TRUDNIK_CONFIG?.jwtToken;
    if (token && window.NotificationsWS) {
        window.NotificationsWS.connect(token);

        // Обработчик новых уведомлений
        window.NotificationsWS.on('notification', function(data) {
            // Показываем toast-уведомление (если есть функция showToast)
            if (typeof showToast === 'function') {
                showToast(data.data?.text || 'Новое уведомление', 'info');
            }

            // Если пользователь на странице уведомлений — добавляем в список
            const notificationsList = document.getElementById('notifications-list');
            if (notificationsList && data.data) {
                // Добавляем новое уведомление в начало списка
                // (конкретная реализация зависит от структуры страницы)
            }
        });

        // Обработчик новых сообщений чата
        window.NotificationsWS.on('new_message', function(data) {
            if (typeof showToast === 'function') {
                const senderName = data.data?.sender_name || 'Пользователь';
                showToast(`Новое сообщение от ${senderName}`, 'info');
            }

            // Если пользователь на странице чата — добавляем сообщение
            const chatMessages = document.getElementById('chat-messages');
            if (chatMessages && data.data) {
                // Добавляем сообщение в чат
                // (конкретная реализация зависит от структуры страницы)
            }
        });

        // Обработчик отключения
        window.NotificationsWS.on('disconnected', function() {
            console.debug('WebSocket отключён');
        });
    }

    // Передаём CSRF-токен в Service Worker (нужен для pushsubscriptionchange)
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        const csrfToken = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_token='))
            ?.split('=')[1] || '';
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
