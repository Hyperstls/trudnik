/**
 * apiFetch — обёртка над fetch с автоматическим добавлением:
 * - X-Client-Request-Id для POST/PUT/DELETE (идемпотентность, правило R2)
 * - X-CSRF-Token для мутирующих запросов (безопасность)
 * - Редирект на /login при 401 (сессия истекла)
 *
 * Использовать ТОЛЬКО для запросов к API (/api/*, /chat/*, /admin/*).
 * НЕ использовать для WebSocket URL, внешних ресурсов (Яндекс.Карты и т.п.).
 *
 * ИСКЛЮЧЕНИЕ: background polling для unread-count может использовать сырой fetch()
 * (Wave E.4), чтобы не триггерить redirect на 401.
 */

/**
 * Генерирует UUID v4
 * @returns {string}
 */
function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback для старых браузеров
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

/**
 * apiFetch — идемпотентная обёртка над fetch
 * @param {string} url
 * @param {RequestInit} opts
 * @returns {Promise<Response>}
 */
async function apiFetch(url, opts = {}) {
    const method = (opts.method || 'GET').toUpperCase();
    const isMutating = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);

    const headers = new Headers(opts.headers || {});

    // Добавляем X-Client-Request-Id для мутирующих запросов (R2)
    if (isMutating) {
        headers.set('X-Client-Request-Id', generateUUID());
    }

    // Добавляем CSRF-токен для мутирующих same-origin запросов
    if (isMutating) {
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (csrfMeta) {
            headers.set('X-CSRF-Token', csrfMeta.getAttribute('content'));
        }
    }

    const response = await fetch(url, {
        ...opts,
        headers,
    });

    // Редирект на /login при 401 (сессия истекла)
    if (response.status === 401) {
        window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
        throw new Error('Session expired');
    }

    return response;
}

// Экспортируем для использования в других скриптах
if (typeof window !== 'undefined') {
    window.apiFetch = apiFetch;
    window.generateUUID = generateUUID;
}
