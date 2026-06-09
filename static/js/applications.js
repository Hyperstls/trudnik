/**
 * applications.js — управление откликами (массовые + индивидуальные операции)
 * Все запросы AJAX, страница НЕ перезагружается.
 */
(function () {
    'use strict';

    // ============================================
    // Состояние
    // ============================================
    let selectedIds = new Set();

    // ============================================
    // Offline Request Queue (retry on reconnect)
    // ============================================
    const OFFLINE_QUEUE_KEY = 'trudnik_offline_queue';
    let offlineQueue = [];

    // Load saved queue from localStorage
    try {
        const saved = localStorage.getItem(OFFLINE_QUEUE_KEY);
        if (saved) offlineQueue = JSON.parse(saved);
    } catch (e) { offlineQueue = []; }

    function saveOfflineQueue() {
        try {
            localStorage.setItem(OFFLINE_QUEUE_KEY, JSON.stringify(offlineQueue));
        } catch (e) { /* storage full - ignore */ }
    }

    function enqueueOffline(url, options) {
        offlineQueue.push({ url: url, options: options, timestamp: Date.now() });
        saveOfflineQueue();
        showToast('Запрос сохранён. Будет отправлен при восстановлении сети.', 'info');
    }

    async function processOfflineQueue() {
        if (offlineQueue.length === 0 || !navigator.onLine) return;
        showToast('Отправка отложенных запросов (' + offlineQueue.length + ')...', 'info');
        const queue = [...offlineQueue];
        offlineQueue = [];
        saveOfflineQueue();

        let successCount = 0, failCount = 0;
        for (const item of queue) {
            try {
                const resp = await fetch(item.url, item.options);
                if (resp.ok) {
                    successCount++;
                } else {
                    // Re-queue on server error
                    offlineQueue.push(item);
                    failCount++;
                }
            } catch (e) {
                // Re-queue on network failure
                offlineQueue.push(item);
                failCount++;
            }
        }
        saveOfflineQueue();

        if (successCount > 0 && failCount === 0) {
            showToast('Все отложенные запросы отправлены (' + successCount + ')', 'success');
        } else if (successCount > 0) {
            showToast('Отправлено: ' + successCount + ', не удалось: ' + failCount, 'warning');
        } else if (failCount > 0) {
            showToast('Не удалось отправить отложенные запросы. Попробуем позже.', 'warning');
        }
        // Reload page to reflect changes if queue was processed
        if (successCount > 0 && offlineQueue.length === 0) {
            setTimeout(() => location.reload(), 1500);
        }
    }

    // Listen for online event to process queue
    window.addEventListener('online', () => {
        processOfflineQueue();
    });

    // Process any pending queue on page load
    if (offlineQueue.length > 0 && navigator.onLine) {
        setTimeout(() => processOfflineQueue(), 1000);
    }

    // ============================================
    // DOM-ссылки
    // ============================================
    const $ = (s) => document.querySelector(s);
    const $$ = (s) => document.querySelectorAll(s);

    // ============================================
    // Массовая панель
    // ============================================
    const massActionsBar = document.getElementById('mass-actions-bar');
    const selectAllCheckbox = document.getElementById('select-all');
    const selectedCountSpan = document.getElementById('selected-count');

    function updateMassActionsBar() {
        const count = selectedIds.size;
        if (!massActionsBar) return;
        if (count > 0) {
            massActionsBar.classList.remove('hidden');
            if (selectedCountSpan) selectedCountSpan.textContent = count;
        } else {
            massActionsBar.classList.add('hidden');
        }
    }

    // ============================================
    // Чекбоксы
    // ============================================
    function initCheckboxes() {
        // Select all
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', function () {
                const checked = this.checked;
                $$('.app-checkbox').forEach(cb => {
                    cb.checked = checked;
                    if (checked) {
                        selectedIds.add(cb.value);
                    } else {
                        selectedIds.delete(cb.value);
                    }
                });
                updateMassActionsBar();
            });
        }

        // Individual checkboxes
        $$('.app-checkbox').forEach(cb => {
            cb.addEventListener('change', function () {
                if (this.checked) {
                    selectedIds.add(this.value);
                } else {
                    selectedIds.delete(this.value);
                    // Uncheck "select all" if any unchecked
                    if (selectAllCheckbox) selectAllCheckbox.checked = false;
                }
                // Check if all are checked
                if (selectAllCheckbox) {
                    const all = $$('.app-checkbox');
                    selectAllCheckbox.checked = all.length > 0 && Array.from(all).every(c => c.checked);
                }
                updateMassActionsBar();
            });
        });
    }

    // ============================================
    // Уведомления (тост) — используем глобальный showToast из base.html
    // ============================================
    function showToast(message, type) {
        if (window.showToast) {
            window.showToast(message, type || 'info');
        }
    }

    // ============================================
    // Custom confirm dialog (uses global showConfirm from base.html)
    // ============================================
    function customConfirm(message) {
        return new Promise(function(resolve) {
            if (window.showConfirm) {
                window.showConfirm(message, function() { resolve(true); });
            } else {
                resolve(confirm(message));
            }
        });
    }

    // ============================================
    // Индивидуальное действие (AJAX)
    // ============================================
    async function singleAction(appId, action, btnElement) {
        // Подтверждение для отклонения принятого отклика
        const card = document.querySelector(`.app-card[data-app-id="${appId}"]`);
        if (action === 'reject' && card && card.dataset.status === 'accepted') {
            const confirmed = await customConfirm('Вы уверены, что хотите отклонить принятого работника? Контактные данные будут скрыты.');
            if (!confirmed) {
                return;
            }
        }

        // Блокируем кнопку на время запроса (защита от двойного клика)
        if (btnElement) {
            btnElement.disabled = true;
            btnElement.style.opacity = '0.5';
            btnElement.style.cursor = 'not-allowed';
        }

        try {
            const resp = await fetch('/api/applications/' + action, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ app_id: appId })
            });
            const data = await resp.json();

            if (data.success) {
                showToast(data.message || 'Готово', 'success');
                updateCardUI(card, appId, data.new_status, data.shift_id);
            } else {
                showToast(data.error || 'Ошибка', 'error');
            }
        } catch (e) {
            if (!navigator.onLine) {
                enqueueOffline('/api/applications/' + action, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ app_id: appId })
                });
            } else {
                showToast('Ошибка соединения с сервером', 'error');
            }
        } finally {
            // Разблокируем кнопку
            if (btnElement) {
                btnElement.disabled = false;
                btnElement.style.opacity = '';
                btnElement.style.cursor = '';
            }
        }
    }

    // ============================================
    // Массовое действие (AJAX)
    // ============================================
    async function batchAction(action) {
        const ids = Array.from(selectedIds);
        if (ids.length === 0) {
            showToast('Не выбрано ни одного отклика', 'warning');
            return;
        }

        // Disable buttons during request
        $$('.mass-action-btn').forEach(b => b.disabled = true);

        try {
            const resp = await fetch('/api/applications/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ app_ids: ids, action: action })
            });
            const data = await resp.json();

            if (data.success) {
                showToast(data.message, 'success');
                // Обновить UI для успешных
                const results = data.results;
                if (results && results.success && results.success.length > 0) {
                    results.success.forEach(item => {
                        const id = typeof item === 'string' ? item : item.id;
                        const newStatus = typeof item === 'string'
                            ? (action === 'reject' ? 'rejected' : 'accepted')
                            : item.new_status;
                        const shiftId = item.shift_id || null;
                        const card = document.querySelector(`.app-card[data-app-id="${id}"]`);
                        updateCardUI(card, id, newStatus, shiftId);
                    });
                }
                if (results && results.errors && results.errors.length > 0) {
                    showToast(results.errors.length + ' ошибок. ' + results.errors[0].error, 'warning');
                }
                // Clear selection
                clearSelection();
            } else {
                // Если все операции провалились — показываем data.message из ответа сервера
                if (data.results && data.results.errors && data.results.errors.length > 0) {
                    const firstError = data.results.errors[0].error;
                    showToast(firstError || data.message || 'Ошибка выполнения', 'error');
                } else {
                    showToast(data.message || data.error || 'Ошибка выполнения', 'error');
                }
            }
        } catch (e) {
            if (!navigator.onLine) {
                enqueueOffline('/api/applications/batch', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ app_ids: Array.from(selectedIds), action: action })
                });
                clearSelection();
            } else {
                showToast('Ошибка соединения с сервером', 'error');
            }
        } finally {
            $$('.mass-action-btn').forEach(b => b.disabled = false);
        }
    }

    // ============================================
    // Обновление UI карточки после действия
    // ============================================
    function updateCardUI(card, appId, newStatus, shiftId) {
        if (!card) return;

        // Обновить data-атрибут статуса на карточке
        card.dataset.status = newStatus;

        const statusBadge = card.querySelector('.status-badge');
        const actionButtons = card.querySelector('.action-buttons');

        // Обновить бейдж статуса
        if (statusBadge) {
            statusBadge.dataset.status = newStatus;
            const statusText = statusBadge.querySelector('.status-text');
            const statusIcon = statusBadge.querySelector('.status-icon');

            if (statusText) {
                const labels = { pending: 'Ожидает', accepted: 'Принят', rejected: 'Отклонён' };
                statusText.textContent = labels[newStatus] || newStatus;
            }
            if (statusIcon) {
                const icons = { pending: '⏳', accepted: '✅', rejected: '❌' };
                statusIcon.textContent = icons[newStatus] || '•';
            }

            // Цвета
            statusBadge.className = statusBadge.className.replace(/badge-\w+/g, '');
            const colors = { pending: 'bg-yellow-100 text-yellow-800', accepted: 'bg-green-100 text-green-800', rejected: 'bg-red-100 text-red-800' };
            statusBadge.classList.add(...colors[newStatus].split(' '));
            statusBadge.classList.add('status-badge');
        }

        // Скрыть контактные данные при отклонении принятого отклика
        const contactSection = card.querySelector('[id^="contact-section-"]');
        if (contactSection && newStatus === 'rejected' && card.dataset.status !== 'rejected') {
            contactSection.innerHTML = `
                <div class="text-xs text-gray-400 italic mt-2">
                    🔒 Контакты скрыты после отклонения
                </div>
            `;
        }

        // Обновить кнопки
        if (actionButtons) {
            actionButtons.innerHTML = buildActionButtonsHTML(appId, newStatus, shiftId);
            // Re-bind events for new buttons
            actionButtons.querySelectorAll('[data-action]').forEach(btn => {
                btn.addEventListener('click', function (e) {
                    e.preventDefault();
                    const action = this.dataset.action;
                    const id = this.dataset.appId;
                    // Передаём саму кнопку для блокировки
                    singleAction(id, action, this);
                });
            });
        }
    }

    // ============================================
    // HTML кнопок в зависимости от статуса
    // ============================================
    function buildActionButtonsHTML(appId, status, shiftId) {
        if (status === 'pending') {
            return `
                <button type="button" data-app-id="${appId}" data-action="accept"
                        class="action-icon-btn accept-btn" title="Принять">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                </button>
                <button type="button" data-app-id="${appId}" data-action="reject"
                        class="action-icon-btn reject-btn" title="Отклонить">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            `;
        } else if (status === 'accepted') {
            const chatHref = shiftId ? `/chat/${shiftId}` : '#';
            return `
                <span class="action-icon-btn accepted-badge" title="Принят">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
                        <polyline points="22 4 12 14.01 9 11.01"></polyline>
                    </svg>
                    <span class="sr-only">Принят</span>
                </span>
                <a href="${chatHref}"
                   class="action-icon-btn chat-btn ${shiftId ? '' : 'opacity-50 pointer-events-none'}"
                   title="Чат" aria-label="Чат">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                    </svg>
                </a>
                <button type="button" data-app-id="${appId}" data-action="reject"
                        class="action-icon-btn reject-btn" title="Отклонить" aria-label="Отклонить">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            `;
        } else if (status === 'rejected') {
            return `
                <span class="action-icon-btn rejected-badge" title="Отклонён">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="15" y1="9" x2="9" y2="15"></line>
                        <line x1="9" y1="9" x2="15" y2="15"></line>
                    </svg>
                    <span class="sr-only">Отклонён</span>
                </span>
                <button type="button" data-app-id="${appId}" data-action="reopen"
                        class="action-icon-btn reopen-btn" title="Повторно принять">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="23 4 23 10 17 10"></polyline>
                        <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path>
                    </svg>
                </button>
            `;
        }
        return '';
    }

    // ============================================
    // Очистка выделения
    // ============================================
    function clearSelection() {
        selectedIds.clear();
        $$('.app-checkbox').forEach(cb => cb.checked = false);
        if (selectAllCheckbox) selectAllCheckbox.checked = false;
        updateMassActionsBar();
    }

    // ============================================
    // Инициализация
    // ============================================
    function init() {
        initCheckboxes();

        // Bind individual action buttons
        $$('.action-icon-btn[data-action]').forEach(btn => {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                const appId = this.dataset.appId;
                const action = this.dataset.action;
                singleAction(appId, action, this);
            });
        });

        // Bind mass action buttons
        $$('.mass-action-btn').forEach(btn => {
            btn.addEventListener('click', function () {
                const action = this.dataset.action;
                batchAction(action);
            });
        });

        // Bind clear selection
        const clearBtn = document.getElementById('clear-selection');
        if (clearBtn) {
            clearBtn.addEventListener('click', function (e) {
                e.preventDefault();
                clearSelection();
            });
        }

        // Keyboard: Escape to clear
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') clearSelection();
        });
    }

    // Ждём DOM
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
