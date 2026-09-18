/**
 * invite-worker.js — модальное окно приглашения трудника на задание.
 *
 * Замена нативного prompt() (workers.html, favorites.html):
 * select с открытыми заданиями текущего пользователя + кнопка «Пригласить».
 *
 * Готового JSON-endpoint «мои открытые задания» нет, поэтому список
 * лениво подгружается один раз со страницы /my-jobs?status=open
 * (парсинг карточек через DOMParser, результат кэшируется на время жизни
 * страницы; ошибки не кэшируются — при следующем открытии повторная попытка).
 *
 * Использование: window.InviteWorker.open(workerId, workerName, btn).
 * При успехе кнопка btn переводится в состояние «✓ Приглашён».
 *
 * Классы Tailwind — только литералы (файл сканируется при сборке CSS).
 */
(function() {
    'use strict';

    var dialog = null;
    var nameEl = null;
    var labelEl = null;
    var selectEl = null;
    var emptyEl = null;
    var submitBtn = null;
    var jobsCache = null;   // null = ещё не загружали
    var current = null;     // {workerId, btn}

    function toast(message, type) {
        if (window.showToast) window.showToast(message, type);
    }

    // fetch с CSRF: предпочитаем глобальный apiFetch (base.html подключает api.js),
    // fallback — fetch + X-CSRF-Token из <meta name="csrf-token">.
    function apiCall(url, opts) {
        if (window.apiFetch) return window.apiFetch(url, opts);
        opts = opts || {};
        var method = (opts.method || 'GET').toUpperCase();
        if (method !== 'GET') {
            var meta = document.querySelector('meta[name="csrf-token"]');
            if (meta) {
                opts.headers = opts.headers || {};
                opts.headers['X-CSRF-Token'] = meta.getAttribute('content');
            }
        }
        return fetch(url, opts);
    }

    function addOption(value, text) {
        var opt = document.createElement('option');
        opt.value = value;
        opt.textContent = text;
        selectEl.appendChild(opt);
    }

    function setBusy(busy) {
        submitBtn.disabled = busy;
        submitBtn.textContent = busy ? '...' : 'Пригласить';
    }

    function buildDialog() {
        dialog = document.createElement('dialog');
        dialog.id = 'invite-modal';
        dialog.className = 'modal-content animate-scale-in';
        dialog.setAttribute('aria-labelledby', 'invite-modal-title');

        var titleEl = document.createElement('h3');
        titleEl.id = 'invite-modal-title';
        titleEl.className = 'text-lg font-bold text-neutral-800 mb-1';
        titleEl.textContent = 'Пригласить на задание';

        nameEl = document.createElement('p');
        nameEl.className = 'text-sm text-neutral-500 mb-4';

        labelEl = document.createElement('label');
        labelEl.setAttribute('for', 'invite-modal-job-select');
        labelEl.className = 'block text-sm font-medium text-neutral-700 mb-2';
        labelEl.textContent = 'К какому заданию пригласить';

        selectEl = document.createElement('select');
        selectEl.id = 'invite-modal-job-select';
        selectEl.className = 'w-full px-4 py-2.5 bg-neutral-50 border border-neutral-200 rounded-xl text-sm focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all mb-4';

        emptyEl = document.createElement('div');
        emptyEl.className = 'text-sm text-neutral-500 mb-4 hidden';
        emptyEl.appendChild(document.createTextNode('У вас нет открытых заданий. '));
        var newJobLink = document.createElement('a');
        newJobLink.href = '/job/new';
        newJobLink.className = 'text-primary-600 hover:underline font-medium';
        newJobLink.textContent = 'Создать задание';
        emptyEl.appendChild(newJobLink);

        var btnRow = document.createElement('div');
        btnRow.className = 'flex gap-3 justify-end';

        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'px-5 py-2.5 bg-neutral-100 hover:bg-neutral-200 text-neutral-700 rounded-xl text-sm font-medium transition-colors';
        cancelBtn.textContent = 'Отмена';

        submitBtn = document.createElement('button');
        submitBtn.type = 'button';
        submitBtn.className = 'px-5 py-2.5 bg-primary-500 hover:bg-primary-600 text-white rounded-xl text-sm font-medium transition-colors disabled:opacity-50';
        submitBtn.textContent = 'Пригласить';

        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(submitBtn);

        dialog.appendChild(titleEl);
        dialog.appendChild(nameEl);
        dialog.appendChild(labelEl);
        dialog.appendChild(selectEl);
        dialog.appendChild(emptyEl);
        dialog.appendChild(btnRow);
        document.body.appendChild(dialog);

        cancelBtn.addEventListener('click', function() { dialog.close(); });
        submitBtn.addEventListener('click', submitInvite);
        // Клик по подложке dialog закрывает (target — сам dialog)
        dialog.addEventListener('click', function(e) {
            if (e.target === dialog) dialog.close();
        });
    }

    // Открытые задания текущего пользователя: парсим /my-jobs?status=open —
    // в каждой карточке ссылка-заголовок /jobs/<uuid> с <h3> названием.
    function fetchOpenJobs() {
        if (jobsCache) return Promise.resolve(jobsCache);
        return apiCall('/my-jobs?status=open', {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        }).then(function(resp) {
            if (!resp.ok) throw new Error('HTTP ' + resp.status);
            return resp.text();
        }).then(function(html) {
            var doc = new DOMParser().parseFromString(html, 'text/html');
            var jobs = [];
            var seen = {};
            var anchors = doc.querySelectorAll('a[href^="/jobs/"]');
            anchors.forEach(function(a) {
                var match = (a.getAttribute('href') || '').match(/^\/jobs\/([0-9a-fA-F-]{36})$/);
                if (!match) return;
                var h3 = a.querySelector('h3');
                if (!h3 || seen[match[1]]) return;
                seen[match[1]] = true;
                jobs.push({ id: match[1], title: h3.textContent.trim() });
            });
            jobsCache = jobs;
            return jobs;
        });
    }

    function fillJobs(jobs) {
        selectEl.innerHTML = '';
        if (!jobs.length) {
            labelEl.classList.add('hidden');
            selectEl.classList.add('hidden');
            emptyEl.classList.remove('hidden');
            submitBtn.disabled = true;
            return;
        }
        addOption('', '— Выберите задание —');
        jobs.forEach(function(job) { addOption(job.id, job.title); });
        selectEl.disabled = false;
        if (jobs.length === 1) selectEl.value = jobs[0].id;
        submitBtn.disabled = false;
    }

    function showLoadError() {
        selectEl.innerHTML = '';
        addOption('', 'Не удалось загрузить задания');
        submitBtn.disabled = true;
        toast('Не удалось загрузить список заданий', 'error');
    }

    function markInvited(btn) {
        if (!btn) return;
        btn.disabled = true;
        btn.title = 'Уже приглашён';
        btn.classList.add('opacity-60');
        btn.classList.remove('accept-btn');
        var span = btn.querySelector('.invite-text');
        if (span) span.textContent = '✓ Приглашён';
    }

    function submitInvite() {
        var jobId = selectEl.value;
        if (!jobId) {
            toast('Выберите задание', 'warning');
            return;
        }
        if (!current || !current.workerId) return;
        setBusy(true);

        apiCall('/api/invite/' + encodeURIComponent(jobId) + '/' + encodeURIComponent(current.workerId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '' })
        }).then(function(resp) {
            return resp.json().then(function(data) {
                if (resp.ok && data && data.success) {
                    toast('Приглашение отправлено', 'success');
                    markInvited(current.btn);
                    dialog.close();
                } else {
                    toast((data && data.error) || 'Не удалось отправить приглашение', 'error');
                    setBusy(false);
                }
            });
        }).catch(function() {
            toast('Ошибка соединения', 'error');
            setBusy(false);
        });
    }

    function open(workerId, workerName, btn) {
        if (!dialog) buildDialog();
        current = { workerId: workerId, btn: btn };

        nameEl.textContent = workerName || '';
        labelEl.classList.remove('hidden');
        selectEl.classList.remove('hidden');
        emptyEl.classList.add('hidden');
        selectEl.innerHTML = '';
        addOption('', 'Загрузка…');
        selectEl.disabled = true;
        submitBtn.disabled = true;
        submitBtn.textContent = 'Пригласить';

        dialog.showModal();

        fetchOpenJobs().then(fillJobs).catch(showLoadError);
    }

    window.InviteWorker = { open: open };
})();
