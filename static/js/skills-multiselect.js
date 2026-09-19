/**
 * SkillsMultiselect — мультиселект навыков (поиск + dropdown + chips).
 * Используется в register.html и profile.html (templates/_skills_multiselect.html).
 *
 * API:
 *   SkillsMultiselect.init(containerId, options)
 *     containerId — id корневого div.skills-multiselect
 *     options:
 *       max            — максимум выбранных навыков (по умолчанию 5)
 *       withNamesField — синхронизировать скрытое поле name="skills"
 *                        (id="skills-hidden") списком имён через запятую
 *       selectedIds    — массив или строка id через запятую (предвыбор при редактировании)
 *
 * Форма получает: по одному скрытому input name="skill_ids" на каждый
 * выбранный навык (бэкенд читает getlist и/или comma-joined — оба варианта).
 */
(function() {
    'use strict';

    var IDS = {
        selected: 'selected-skills',
        search: 'skill-search',
        dropdownBtn: 'skills-dropdown-btn',
        dropdown: 'skills-dropdown',
        list: 'skills-list',
        placeholder: 'skills-placeholder',
        arrow: 'skills-arrow',
        hiddenInputs: 'skills-hidden-inputs',
        namesHidden: 'skills-hidden'
    };

    function init(containerId, options) {
        var container = document.getElementById(containerId);
        if (!container) return null;
        options = options || {};

        var max = options.max || parseInt(container.getAttribute('data-max'), 10) || 5;
        var withNamesField = !!options.withNamesField;

        var selectedContainer = document.getElementById(IDS.selected);
        var dropdownBtn = document.getElementById(IDS.dropdownBtn);
        var dropdown = document.getElementById(IDS.dropdown);
        var skillsList = document.getElementById(IDS.list);
        var placeholder = document.getElementById(IDS.placeholder);
        var arrow = document.getElementById(IDS.arrow);
        var skillSearch = document.getElementById(IDS.search);
        var hiddenInputsBox = document.getElementById(IDS.hiddenInputs);
        var namesHidden = withNamesField ? document.getElementById(IDS.namesHidden) : null;
        if (!selectedContainer || !dropdownBtn || !dropdown || !skillsList || !hiddenInputsBox) return null;

        var skillNameById = {};
        var selectedIds = [];
        var initial = options.selectedIds != null
            ? options.selectedIds
            : (container.getAttribute('data-selected-ids') || '');
        if (typeof initial === 'string') {
            initial = initial.split(',');
        }
        initial.forEach(function(s) {
            s = String(s).trim();
            if (s && selectedIds.indexOf(s) === -1) selectedIds.push(s);
        });
        selectedIds = selectedIds.slice(0, max);

        function updateUI() {
            // Скрытые поля формы: один input name="skill_ids" на навык
            hiddenInputsBox.innerHTML = '';
            selectedIds.forEach(function(id) {
                var h = document.createElement('input');
                h.type = 'hidden';
                h.name = 'skill_ids';
                h.value = id;
                hiddenInputsBox.appendChild(h);
            });
            if (namesHidden) {
                namesHidden.value = selectedIds.map(function(id) {
                    return skillNameById[id] || id;
                }).join(',');
            }

            // Chips + placeholder
            if (selectedIds.length === 0) {
                selectedContainer.innerHTML = '';
                placeholder.textContent = 'Выберите навыки';
                placeholder.classList.remove('text-neutral-700');
                placeholder.classList.add('text-neutral-500');
            } else {
                placeholder.textContent = 'Выбрано: ' + selectedIds.length;
                placeholder.classList.remove('text-neutral-500');
                placeholder.classList.add('text-neutral-700');
                selectedContainer.innerHTML = '';
                selectedIds.forEach(function(id) {
                    var span = document.createElement('span');
                    span.className = 'inline-flex items-center gap-1 bg-primary-50 text-primary-700 px-2.5 py-1 rounded-lg text-xs font-medium';
                    span.textContent = skillNameById[id] || id;
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.className = 'remove-skill ml-0.5 hover:text-danger transition-colors';
                    btn.setAttribute('data-skill', id);
                    btn.setAttribute('aria-label', 'Убрать навык ' + (skillNameById[id] || id));
                    btn.textContent = '×';
                    span.appendChild(btn);
                    selectedContainer.appendChild(span);
                });
            }

            // Чекбоксы в списке: отмеченные + блокировка при достижении лимита
            var limitReached = selectedIds.length >= max;
            skillsList.querySelectorAll('input[type="checkbox"]').forEach(function(cb) {
                cb.checked = selectedIds.indexOf(cb.value) !== -1;
                cb.disabled = limitReached && !cb.checked;
            });
        }

        function openDropdown() {
            dropdown.classList.remove('hidden');
            dropdownBtn.setAttribute('aria-expanded', 'true');
            if (arrow) arrow.style.transform = 'rotate(180deg)';
        }
        function closeDropdown() {
            dropdown.classList.add('hidden');
            dropdownBtn.setAttribute('aria-expanded', 'false');
            if (arrow) arrow.style.transform = 'rotate(0deg)';
        }

        function filterSkills() {
            openDropdown();
            var q = (skillSearch && skillSearch.value || '').toLowerCase();
            skillsList.querySelectorAll('label.skill-filter-item').forEach(function(item) {
                var skillName = (item.getAttribute('data-skill') || '').toLowerCase();
                item.style.display = skillName.indexOf(q) !== -1 ? 'flex' : 'none';
            });
        }

        if (skillSearch) {
            skillSearch.addEventListener('input', filterSkills);
            skillSearch.addEventListener('focus', openDropdown);
        }

        fetch('/api/skills')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                var skills = data.skills || [];
                if (skills.length === 0) {
                    skillsList.innerHTML = '<span class="text-neutral-400">Нет доступных навыков</span>';
                    return;
                }
                skills.forEach(function(s) { skillNameById[s.id] = s.name; });
                skillsList.innerHTML = '';
                skills.forEach(function(s) {
                    var label = document.createElement('label');
                    label.className = 'skill-filter-item flex items-center gap-2 px-2 py-1.5 hover:bg-neutral-50 rounded cursor-pointer text-sm';
                    label.setAttribute('data-skill', s.name);
                    var cb = document.createElement('input');
                    cb.type = 'checkbox';
                    cb.value = s.id;
                    cb.className = 'skill-checkbox rounded border-neutral-300 text-primary-500 focus:ring-primary-500';
                    var span = document.createElement('span');
                    span.className = 'text-neutral-700';
                    span.textContent = s.name;
                    label.appendChild(cb);
                    label.appendChild(span);
                    skillsList.appendChild(label);
                });

                skillsList.querySelectorAll('.skill-checkbox').forEach(function(cb) {
                    cb.addEventListener('change', function() {
                        if (this.checked) {
                            if (selectedIds.indexOf(this.value) === -1 && selectedIds.length < max) {
                                selectedIds.push(this.value);
                            } else {
                                this.checked = false;
                            }
                        } else {
                            selectedIds = selectedIds.filter(function(s) { return s !== cb.value; });
                        }
                        updateUI();
                    });
                });
                updateUI();
            })
            .catch(function() {
                skillsList.innerHTML = '<span class="text-red-400">Ошибка загрузки</span>';
            });

        dropdownBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (dropdown.classList.contains('hidden')) { openDropdown(); } else { closeDropdown(); }
        });

        document.addEventListener('click', function(e) {
            if (!dropdownBtn.contains(e.target) && !dropdown.contains(e.target) &&
                (!skillSearch || !skillSearch.contains(e.target))) {
                closeDropdown();
            }
        });

        selectedContainer.addEventListener('click', function(e) {
            var removeBtn = e.target.closest('.remove-skill');
            if (!removeBtn) return;
            var id = removeBtn.getAttribute('data-skill');
            selectedIds = selectedIds.filter(function(s) { return s !== id; });
            updateUI();
        });

        updateUI();
        return {
            getSelectedIds: function() { return selectedIds.slice(); }
        };
    }

    window.SkillsMultiselect = { init: init };
})();
