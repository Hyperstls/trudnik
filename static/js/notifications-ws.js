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
        const wsUrl = this._getWsUrl();

        try {
            this.ws = new WebSocket(`${wsUrl}?token=${encodeURIComponent(token)}`);
        } catch (e) {
            console.error('Ошибка создания WebSocket:', e);
            this.isConnecting = false;
            this._scheduleReconnect(token);
            return;
        }

        this.ws.onopen = () => {
            console.log('WebSocket подключён');
            this.isConnecting = false;
            this.reconnectAttempts = 0;
            this._emit('connected', {});
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this._handleMessage(data);
            } catch (e) {
                console.warn('Не удалось разобрать WebSocket сообщение:', event.data);
            }
        };

        this.ws.onclose = (event) => {
            console.log(`WebSocket закрыт (код: ${event.code})`);
            this.isConnecting = false;
            this._emit('disconnected', { code: event.code });

            if (event.code !== 1000 && event.code !== 1001) {
                this._scheduleReconnect(token);
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

    _scheduleReconnect(token) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.warn('Достигнут лимит попыток переподключения WebSocket');
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(
            this.reconnectDelay * Math.pow(1.5, this.reconnectAttempts - 1),
            this.maxReconnectDelay
        );

        console.log(`Переподключение WebSocket через ${delay / 1000}с (попытка ${this.reconnectAttempts})`);

        setTimeout(() => {
            this.connect(token);
        }, delay);
    }
}

// Глобальный экземпляр
window.NotificationsWS = new NotificationsWebSocket();
