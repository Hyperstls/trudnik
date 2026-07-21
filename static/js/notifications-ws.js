/**
 * WebSocket-клиент для реального времени Trudnik
 * Подключается к WebSocket-серверу и обрабатывает события уведомлений и чата.
 */

class NotificationsWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 1000; // Начальная задержка 1 сек
        this.maxReconnectDelay = 30000; // Максимальная задержка 30 сек
        this.isConnecting = false;
        this.pollingTimer = null;
        this.pollingInterval = 30000; // 30 секунд HTTP-polling
        this.listeners = {
            'notification': [],
            'new_message': [],
            'connected': [],
            'disconnected': []
        };
    }

    /**
     * Устанавливает WebSocket-соединение.
     * @param {string} token - JWT токен для аутентификации
     */
    connect(token) {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }
        this.isConnecting = true;
        this.reconnectAttempts = 0;
        const wsUrl = this._getWsUrl();

        try {
            this.ws = new WebSocket(wsUrl);  // БЕЗ токена в URL
        } catch (e) {
            console.error('Ошибка создания WebSocket:', e);
            this.isConnecting = false;
            this._scheduleReconnect();
            return;
        }

        this.ws.onopen = () => {
            // Отправляем токен первым сообщением
            this.ws.send(JSON.stringify({ type: 'auth', token: token }));
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'connected') {
                    this.isConnecting = false;
                    this.reconnectAttempts = 0;
                    this._stopPolling();
                    this._emit('connected', {});
                } else {
                    this._handleMessage(data);
                }
            } catch (e) {
                console.warn('Не удалось разобрать WS сообщение:', event.data);
            }
        };

        this.ws.onclose = (event) => {
            console.log(`WebSocket закрыт (код: ${event.code})`);
            this.isConnecting = false;
            this._emit('disconnected', { code: event.code });
            if (event.code !== 1000 && event.code !== 1001) {
                this._scheduleReconnect();
                this._startPolling();
            }
        };

        this.ws.onerror = (error) => {
            console.error('Ошибка WebSocket:', error);
            this.isConnecting = false;
        };
    }

    /**
     * Закрывает WebSocket-соединение.
     */
    disconnect() {
        this.reconnectAttempts = this.maxReconnectAttempts; // Прекращаем переподключения
        this._stopPolling();
        if (this.ws) {
            this.ws.close(1000, 'Пользователь вышел');
            this.ws = null;
        }
    }

    /**
     * Подписка на событие.
     * @param {string} event - 'notification', 'new_message', 'connected', 'disconnected'
     * @param {function} callback - функция-обработчик
     */
    on(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event].push(callback);
        }
    }

    /**
     * Отписка от события.
     */
    off(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
        }
    }

    /**
     * Отправляет сообщение через WebSocket.
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }

    // --- Приватные методы ---

    _handleMessage(data) {
        const type = data.type;

        switch (type) {
            case 'notification':
                this._emit('notification', data);
                // Обновляем счётчик уведомлений в шапке
                this._updateNotificationCounter(data);
                break;

            case 'new_message':
                this._emit('new_message', data);
                // Обновляем счётчик сообщений
                this._updateChatCounter(data);
                break;

            case 'pong':
                // Heartbeat ответ
                break;

            case 'connected':
                this._emit('connected', data);
                break;

            default:
                console.debug('Неизвестный тип WebSocket сообщения:', type, data);
        }
    }

    _emit(event, data) {
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`Ошибка в обработчике события "${event}":`, e);
                }
            });
        }
    }

    _updateNotificationCounter(data) {
        // Обновляем счётчик непрочитанных уведомлений в навбаре
        const badge = document.getElementById('notifications-badge');
        if (badge) {
            const currentCount = parseInt(badge.textContent) || 0;
            badge.textContent = currentCount + 1;
            badge.style.display = 'inline-block';
        }
    }

    _updateChatCounter(data) {
        // Обновляем счётчик непрочитанных сообщений
        const badge = document.getElementById('chat-badge');
        if (badge) {
            const currentCount = parseInt(badge.textContent) || 0;
            badge.textContent = currentCount + 1;
            badge.style.display = 'inline-block';
        }
    }

    _getWsUrl() {
        // Определяем URL WebSocket-сервера
        // В production: wss://домен/ws (через reverse proxy)
        // В development: ws://localhost:8001/ws
        if (window.TRUDNIK_CONFIG && window.TRUDNIK_CONFIG.wsUrl) {
            return window.TRUDNIK_CONFIG.wsUrl;
        }

        // Автоопределение: заменяем http на ws
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.hostname;

        // На localhost используем отдельный порт 8001 для dev-сервера WebSocket
        if (host === 'localhost' || host === '127.0.0.1') {
            const port = window.TRUDNIK_CONFIG?.wsPort || '8001';
            return `${protocol}//${host}:${port}/ws`;
        }

        // В production WebSocket идёт через reverse proxy на том же хосте/пути /ws
        return `${protocol}//${host}/ws`;
    }

    /**
     * Запускает HTTP-polling как fallback при отсутствии WebSocket.
     */
    _startPolling() {
        if (this.pollingTimer) return; // Уже запущен
        console.log('Запущен HTTP-polling уведомлений (каждые ' + (this.pollingInterval / 1000) + 'с)');
        this._pollUnreadCount();
        this.pollingTimer = setInterval(() => this._pollUnreadCount(), this.pollingInterval);
    }

    /**
     * Останавливает HTTP-polling.
     */
    _stopPolling() {
        if (this.pollingTimer) {
            clearInterval(this.pollingTimer);
            this.pollingTimer = null;
            console.log('HTTP-polling остановлен');
        }
    }

    /**
     * Выполняет один запрос к /api/notifications/unread-count
     * и обновляет счётчик уведомлений.
     */
    async _pollUnreadCount() {
        try {
            const resp = await apiFetch('/api/notifications/unread-count');
            if (!resp.ok) return;
            const data = await resp.json();
            const count = data.unread_count || data.count || 0;
            const badge = document.getElementById('notifications-badge');
            if (badge) {
                if (count > 0) {
                    badge.textContent = count > 99 ? '99+' : count;
                    badge.style.display = 'inline-block';
                } else {
                    badge.style.display = 'none';
                }
            }
        } catch (e) {
            console.warn('Ошибка HTTP-polling уведомлений:', e);
        }
    }

    async _fetchToken() {
        try {
            const resp = await apiFetch('/api/ws/token');
            if (!resp.ok) return null;
            const data = await resp.json();
            return data.token;
        } catch (e) {
            console.warn('Не удалось получить свежий WS-токен:', e);
            return null;
        }
    }

    _scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.warn('Достигнут лимит попыток переподключения WebSocket');
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(
            Math.min(30000, 1000 * Math.pow(2, this.reconnectAttempts)),
            this.maxReconnectDelay
        );

        console.log(`Переподключение WebSocket через ${delay / 1000}с (попытка ${this.reconnectAttempts})`);

        setTimeout(async () => {
            const token = await this._fetchToken();
            if (token) {
                this.connect(token);
            } else {
                this._startPolling();
            }
        }, delay);
    }
}

// Глобальный экземпляр
window.NotificationsWS = new NotificationsWebSocket();
