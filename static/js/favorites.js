/**
 * Возвращает CSRF-токен из мета-тега.
 * @returns {string}
 */
function getCSRFToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

/**
 * Единая функция переключения избранного.
 * Вызывается из любого шаблона с одинаковой сигнатурой.
 *
 * @param {string} workerId - UUID трудника
 * @param {HTMLElement} btn - DOM-элемент кнопки
 */
function toggleFavorite(workerId, btn, event) {
    if (!workerId || !btn) {
        console.error('toggleFavorite: missing workerId or btn');
        return;
    }

    // Предотвращаем всплытие, если передан event
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }

    // Получаем текущий статус из data-атрибута
    const isFavorited = btn.dataset.favorited === 'true';

    // Оптимистичное обновление UI
    if (isFavorited) {
        // Удаляем из избранного
        updateButtonUI(btn, false);
        
        fetch('/api/favorites/remove', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({ worker_id: workerId })
        })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                updateButtonUI(btn, true); // откат
                if (window.showToast) {
                    window.showToast('❌ ' + (data.error || 'Не удалось удалить'), 'error');
                }
            }
        })
        .catch(() => {
            updateButtonUI(btn, true); // откат
            if (window.showToast) {
                window.showToast('❌ Ошибка сети', 'error');
            }
        });
    } else {
        // Добавляем в избранное
        updateButtonUI(btn, true);
        
        fetch('/api/favorites/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({ worker_id: workerId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                if (window.showToast) {
                    window.showToast('✅ Трудник добавлен в избранное!', 'success');
                }
            } else {
                updateButtonUI(btn, false); // откат
                if (window.showToast) {
                    window.showToast('❌ ' + (data.error || 'Не удалось добавить'), 'error');
                }
            }
        })
        .catch(() => {
            updateButtonUI(btn, false); // откат
            if (window.showToast) {
                window.showToast('❌ Ошибка сети', 'error');
            }
        });
    }
}

const SVG_STAR = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon></svg>';
const SVG_HEART = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"></path></svg>';

function updateButtonUI(btn, isFavorited) {
    const icon = btn.querySelector('.favorite-icon');
    const text = btn.querySelector('.favorite-text');
    
    btn.dataset.favorited = isFavorited ? 'true' : 'false';
    
    if (isFavorited) {
        btn.classList.remove('contact-btn');
        btn.classList.add('reject-btn');
        if (icon) icon.innerHTML = SVG_HEART;
        if (text) text.textContent = 'Удалить из избранного';
    } else {
        btn.classList.remove('reject-btn');
        btn.classList.add('contact-btn');
        if (icon) icon.innerHTML = SVG_STAR;
        if (text) text.textContent = 'В избранное';
    }
}

// Проверка статуса избранного при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.favorite-btn').forEach(btn => {
        const workerId = btn.dataset.workerId;
        if (!workerId) return;
        
        // Пропускаем проверку для уже известных избранных (например, на странице избранного)
        if (btn.dataset.favorited === 'true') return;
        
        fetch('/api/favorites/check', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({ worker_id: workerId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success && data.is_favorited) {
                updateButtonUI(btn, true);
            }
        })
        .catch(e => console.error('Ошибка проверки избранного:', e));
    });
});

/**
 * Переключение избранного для работодателя (через API).
 * Использует эндпоинты /api/employers/favorites/add и /api/employers/favorites/remove.
 *
 * @param {string} employerId - UUID работодателя
 * @param {HTMLElement} btn  - DOM-элемент кнопки
 * @param {Event}      event - Событие (для остановки всплытия)
 */
function toggleEmployerFavorite(employerId, btn, event) {
    if (!employerId || !btn) {
        console.error('toggleEmployerFavorite: missing employerId or btn');
        return;
    }

    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }

    const isFavorited = btn.dataset.favorited === 'true';

    if (isFavorited) {
        // Удаляем
        updateEmployerFavoriteUI(btn, false);
        fetch('/api/employers/favorites/remove', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({ employer_id: employerId })
        })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                updateEmployerFavoriteUI(btn, true);
                if (window.showToast) {
                    window.showToast('❌ ' + (data.error || 'Не удалось удалить'), 'error');
                }
            } else {
                if (window.showToast) {
                    window.showToast('✅ Работодатель удалён из избранного', 'success');
                }
                // Перезагружаем страницу, чтобы удалить карточку из DOM на странице избранного
                setTimeout(() => location.reload(), 800);
            }
        })
        .catch(() => {
            updateEmployerFavoriteUI(btn, true);
            if (window.showToast) {
                window.showToast('❌ Ошибка сети', 'error');
            }
        });
    } else {
        // Добавляем
        updateEmployerFavoriteUI(btn, true);
        fetch('/api/employers/favorites/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCSRFToken()
            },
            body: JSON.stringify({ employer_id: employerId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                if (window.showToast) {
                    window.showToast('✅ Работодатель добавлен в избранное!', 'success');
                }
            } else {
                updateEmployerFavoriteUI(btn, false);
                if (window.showToast) {
                    window.showToast('❌ ' + (data.error || 'Не удалось добавить'), 'error');
                }
            }
        })
        .catch(() => {
            updateEmployerFavoriteUI(btn, false);
            if (window.showToast) {
                window.showToast('❌ Ошибка сети', 'error');
            }
        });
    }
}

function updateEmployerFavoriteUI(btn, isFavorited) {
    const icon = btn.querySelector('.favorite-icon');
    const text = btn.querySelector('.favorite-text');

    btn.dataset.favorited = isFavorited ? 'true' : 'false';

    if (isFavorited) {
        btn.classList.remove('contact-btn');
        btn.classList.add('reject-btn');
        if (icon) icon.innerHTML = SVG_HEART;
        if (text) text.textContent = 'Удалить из избранного';
    } else {
        btn.classList.remove('reject-btn');
        btn.classList.add('contact-btn');
        if (icon) icon.innerHTML = SVG_STAR;
        if (text) text.textContent = 'В избранное';
    }
}

// Делегированный обработчик для кнопки удаления работодателя из избранного (CSP-совместимый)
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.unfavorite-employer-btn');
    if (!btn) return;
    e.preventDefault();
    const employerId = btn.dataset.employerId;
    toggleEmployerFavorite(employerId, btn, e);
});
