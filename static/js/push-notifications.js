/**
 * Push-уведомления Trudnik — клиентская логика
 * Подписка, отписка, управление разрешениями
 */

class PushNotificationsManager {
    constructor() {
        this.swRegistration = null;
        this.vapidPublicKey = null;
        this.isSubscribed = false;
    }

    /**
     * Инициализация: регистрация Service Worker и загрузка VAPID-ключа
     */
    async init() {
        // Проверяем поддержку браузером
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.warn('Push-уведомления не поддерживаются браузером');
            return false;
        }

        try {
            // Регистрируем Service Worker
            this.swRegistration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });

            // Ждём активации
            await navigator.serviceWorker.ready;

            // Получаем VAPID public key с сервера
            const response = await fetch('/notifications/push/vapid-public-key');
            const data = await response.json();
            this.vapidPublicKey = data.public_key;

            // Проверяем текущую подписку
            this.isSubscribed = !!(await this.swRegistration.pushManager.getSubscription());

            return true;
        } catch (error) {
            console.error('Ошибка инициализации push-уведомлений:', error);
            return false;
        }
    }

    /**
     * Запрос разрешения и подписка на push
     */
    async subscribe() {
        if (!this.swRegistration || !this.vapidPublicKey) {
            console.error('PushNotificationsManager не инициализирован');
            return false;
        }

        try {
            // Запрашиваем разрешение
            const permission = await Notification.requestPermission();
            if (permission !== 'granted') {
                console.warn('Разрешение на уведомления не получено');
                return false;
            }

            // Создаём подписку
            const subscription = await this.swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: this._urlBase64ToUint8Array(this.vapidPublicKey)
            });

            // Отправляем подписку на сервер
            const response = await fetch('/notifications/push/subscription', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this._getCSRFToken()
                },
                body: JSON.stringify(subscription.toJSON())
            });

            if (response.ok) {
                this.isSubscribed = true;
                console.log('Push-подписка успешно создана');
                return true;
            }
            return false;
        } catch (error) {
            console.error('Ошибка подписки на push:', error);
            return false;
        }
    }

    /**
     * Отписка от push-уведомлений
     */
    async unsubscribe() {
        if (!this.swRegistration) return false;

        try {
            const subscription = await this.swRegistration.pushManager.getSubscription();
            if (subscription) {
                // Отправляем запрос на удаление подписки на сервер
                await fetch('/notifications/push/subscription', {
                    method: 'DELETE',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': this._getCSRFToken()
                    },
                    body: JSON.stringify({ endpoint: subscription.endpoint })
                });

                // Отписываемся локально
                await subscription.unsubscribe();
                this.isSubscribed = false;
                console.log('Push-подписка удалена');
            }
            return true;
        } catch (error) {
            console.error('Ошибка отписки от push:', error);
            return false;
        }
    }

    /**
     * Проверка статуса подписки
     */
    async checkSubscription() {
        if (!this.swRegistration) return false;
        const subscription = await this.swRegistration.pushManager.getSubscription();
        this.isSubscribed = !!subscription;
        return this.isSubscribed;
    }

    /**
     * Вспомогательная функция: конвертация base64 VAPID ключа в Uint8Array
     */
    _urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding)
            .replace(/\-/g, '+')
            .replace(/_/g, '/');
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) {
            outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
    }

    /**
     * Получение CSRF-токена из кук
     */
    _getCSRFToken() {
        const cookieValue = document.cookie
            .split('; ')
            .find(row => row.startsWith('csrf_token='))
            ?.split('=')[1];
        return cookieValue || '';
    }
}

// Экспорт в глобальную область видимости
window.PushNotifications = new PushNotificationsManager();
