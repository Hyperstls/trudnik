/**
 * apiFetch — обёртка над fetch для API-запросов.
 * Автоматически редиректит на /login при 401 (сессия истекла).
 * Использовать ТОЛЬКО для запросов к API (/api/*, /chat/*, /admin/*).
 * НЕ использовать для WebSocket URL, внешних ресурсов (Яндекс.Карты и т.п.).
 */
async function apiFetch(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 401) {
        window.location.href = '/login?next=' + encodeURIComponent(window.location.pathname);
        throw new Error('Session expired');
    }
    return response;
}
