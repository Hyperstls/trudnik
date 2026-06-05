/**
 * Единая функция переключения избранного.
 * Вызывается из любого шаблона с одинаковой сигнатурой.
 * 
 * @param {string} workerId - UUID трудника
 * @param {HTMLElement} btn - DOM-элемент кнопки
 */
function toggleFavorite(workerId, btn) {
    if (!workerId || !btn) {
        console.error('toggleFavorite: missing workerId or btn');
        return;
    }

    // Предотвращаем всплытие, если передан event
    if (window.event) {
        window.event.stopPropagation();
        window.event.preventDefault();
    }

    // Получаем текущий статус из data-атрибута
    const isFavorited = btn.dataset.favorited === 'true';

    // Оптимистичное обновление UI
    if (isFavorited) {
        // Удаляем из избранного
        updateButtonUI(btn, false);
        
        fetch('/api/favorites/remove', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ worker_id: workerId })
        })
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                updateButtonUI(btn, true); // откат
                alert('Ошибка: ' + (data.error || 'Не удалось удалить'));
            }
        })
        .catch(() => {
            updateButtonUI(btn, true); // откат
            alert('Ошибка сети');
        });
    } else {
        // Добавляем в избранное
        updateButtonUI(btn, true);
        
        fetch('/api/favorites/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ worker_id: workerId })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                alert('Трудник добавлен в избранное!');
            } else {
                updateButtonUI(btn, false); // откат
                alert('Ошибка: ' + (data.error || 'Не удалось добавить'));
            }
        })
        .catch(() => {
            updateButtonUI(btn, false); // откат
            alert('Ошибка сети');
        });
    }
}

function updateButtonUI(btn, isFavorited) {
    const icon = btn.querySelector('.favorite-icon');
    const text = btn.querySelector('.favorite-text');
    
    btn.dataset.favorited = isFavorited ? 'true' : 'false';
    
    if (isFavorited) {
        btn.classList.remove('bg-yellow-500', 'hover:bg-yellow-600');
        btn.classList.add('bg-red-500', 'hover:bg-red-600');
        if (icon) icon.textContent = '❤️';
        if (text) text.textContent = 'Удалить из избранного';
    } else {
        btn.classList.remove('bg-red-500', 'hover:bg-red-600');
        btn.classList.add('bg-yellow-500', 'hover:bg-yellow-600');
        if (icon) icon.textContent = '⭐';
        if (text) text.textContent = 'В избранное';
    }
}

// Проверка статуса избранного при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.favorite-btn').forEach(btn => {
        const workerId = btn.dataset.workerId;
        if (!workerId) return;
        
        fetch('/api/favorites/check', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
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
