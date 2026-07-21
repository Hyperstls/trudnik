/**
 * Trudnik Base JavaScript
 * Extracted from base.html inline scripts
 */

/**
 * Handle search form submit (desktop)
 */
function handleSearchSubmit(form) {
    var input = form.querySelector('input');
    var value = input ? input.value.trim() : '';
    if (!value) return false;
    return true;
}

/**
 * Toggle mobile search bar
 */
function toggleMobileSearch() {
    var bar = document.getElementById('mobile-search-bar');
    var input = document.getElementById('mobile-search-input');
    if (bar && input) {
        bar.classList.toggle('hidden');
        if (!bar.classList.contains('hidden')) {
            input.focus();
        }
    }
}

/**
 * Show a toast notification
 * @param {string} message - text
 * @param {string} type - 'success' | 'error' | 'warning' | 'info'
 */
window.showToast = function(message, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) return;

    var toast = document.createElement('div');
    toast.className = 'toast animate-slide-in';

    // F2: Добавляем role для accessibility
    // role="alert" для ошибок (assertive), role="status" для остальных (polite)
    if (type === 'error' || type === 'danger') {
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'assertive');
    } else {
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');
    }

    var bgColors = {
        success: 'bg-success text-white',
        error: 'bg-danger text-white',
        warning: 'bg-warning text-neutral-800',
        info: 'bg-info text-white'
    };
    toast.className += ' ' + (bgColors[type] || bgColors.info);

    var iconMap = {
        success: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>',
        error: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>',
        warning: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>',
        info: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>'
    };

    var closeBtn = '<button class="toast-close-btn ml-auto shrink-0 hover:opacity-75" aria-label="Закрыть">' +
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">' +
        '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>';

    toast.innerHTML = (iconMap[type] || iconMap.info) +
        '<span class="flex-1"></span>' +
        closeBtn;
    toast.querySelector('span.flex-1').textContent = message;

    container.appendChild(toast);

    var toastCloseBtn = toast.querySelector('.toast-close-btn');
    if (toastCloseBtn) {
        toastCloseBtn.addEventListener('click', function() { toast.remove(); });
    }

    setTimeout(function() {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(100%)';
        setTimeout(function() { toast.remove(); }, 300);
    }, 3500);
};

// Process queued flash messages
if (window._toastQueue && window._toastQueue.length) {
    window._toastQueue.forEach(function(t) { window.showToast(t.message, t.category); });
    window._toastQueue = [];
}

/**
 * F7: Focus trap для модальных окон
 * Удерживает фокус внутри модального окна при навигации Tab
 * @param {HTMLElement} element - контейнер модального окна
 */
window.trapFocus = function(element) {
    const focusable = element.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    
    element.addEventListener('keydown', function(e) {
        if (e.key !== 'Tab') return;
        if (e.shiftKey) {
            if (document.activeElement === first) {
                last.focus();
                e.preventDefault();
            }
        } else {
            if (document.activeElement === last) {
                first.focus();
                e.preventDefault();
            }
        }
    });
};

// ========================================
// Custom Confirm Modal
// ========================================
window.showConfirm = function(message, onConfirm, options) {
    options = options || {};
    var modal = document.getElementById('confirm-modal');
    var msgEl = document.getElementById('confirm-modal-message');
    var titleEl = document.getElementById('confirm-modal-title');
    var okBtn = document.getElementById('confirm-modal-ok');
    var cancelBtn = document.getElementById('confirm-modal-cancel');

    if (!modal || !msgEl) {
        if (confirm(message)) onConfirm();
        return;
    }

    titleEl.textContent = options.title || 'Подтвердите действие';
    msgEl.textContent = message;
    okBtn.textContent = options.okText || 'Подтвердить';
    okBtn.className = (options.danger !== false ? 'bg-danger hover:bg-red-700' : 'bg-primary-500 hover:bg-primary-600') + ' text-white px-5 py-2.5 rounded-xl text-sm font-medium transition-colors';

    var previousActiveElement = document.activeElement;

    function close() {
        modal.close();
        document.body.style.overflow = '';
        if (previousActiveElement && previousActiveElement.focus) {
            previousActiveElement.focus();
        }
    }

    okBtn.onclick = function() { close(); if (onConfirm) onConfirm(); };
    cancelBtn.onclick = close;

    // Close on backdrop click (native <dialog> behavior)
    modal.addEventListener('click', function(e) {
        if (e.target === modal) close();
    });

    modal.showModal();
    document.body.style.overflow = 'hidden';

    if (okBtn) okBtn.focus();

    window.trapFocus(modal);

    function handleEscape(e) {
        if (e.key === 'Escape') {
            close();
            modal.removeEventListener('keydown', handleEscape);
        }
    }

    modal.addEventListener('keydown', handleEscape);
};

// ========================================
// PWA Install Prompt
// ========================================
(function() {
    var deferredPrompt;
    var banner = document.getElementById('install-banner');
    var installBtn = document.getElementById('install-banner-btn');
    var closeBtn = document.getElementById('install-banner-close');

    window.addEventListener('beforeinstallprompt', function(e) {
        e.preventDefault();
        deferredPrompt = e;
        if (banner) {
            banner.style.display = 'block';
            banner.classList.remove('hidden');
        }
    });

    if (installBtn) {
        installBtn.addEventListener('click', function() {
            if (deferredPrompt) {
                deferredPrompt.prompt();
                deferredPrompt.userChoice.then(function(result) {
                    console.log('PWA install:', result.outcome);
                    deferredPrompt = null;
                    if (banner) { banner.style.display = 'none'; banner.classList.add('hidden'); }
                });
            } else if (banner) {
                banner.style.display = 'none';
                banner.classList.add('hidden');
            }
        });
    }

    if (closeBtn && banner) {
        closeBtn.addEventListener('click', function() {
            banner.style.display = 'none';
            banner.classList.add('hidden');
        });
    }

    if (window.matchMedia('(display-mode: standalone)').matches) {
        if (banner) { banner.style.display = 'none'; banner.classList.add('hidden'); }
    }
})();

// ========================================
// Offline/Online Status Detection
// ========================================
(function() {
    var offlineBar = document.getElementById('offline-bar');

    function setOffline(offline) {
        if (offlineBar) {
            if (offline) {
                offlineBar.classList.remove('hidden');
                offlineBar.style.display = 'block';
            } else {
                offlineBar.classList.add('hidden');
                offlineBar.style.display = 'none';
                window.showToast && window.showToast('Соединение восстановлено', 'success');
            }
        }
        var main = document.querySelector('main');
        if (main) {
            main.style.paddingTop = offline ? '2.5rem' : '';
        }
    }

    window.addEventListener('online', function() { setOffline(false); });
    window.addEventListener('offline', function() { setOffline(true); });
    if (!navigator.onLine) setOffline(true);
})();

// Floating-label for select elements
(function() {
    function updateSelectLabel(select) {
        var hasValue = select.value && select.value !== '';
        if (hasValue) {
            select.setAttribute('data-has-value', '');
        } else {
            select.removeAttribute('data-has-value');
        }
    }
    document.addEventListener('DOMContentLoaded', function() {
        var selects = document.querySelectorAll('.floating-label-group select');
        for (var i = 0; i < selects.length; i++) {
            updateSelectLabel(selects[i]);
            selects[i].addEventListener('change', function() { updateSelectLabel(this); });
        }
    });
    if (window.MutationObserver) {
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1 && node.tagName === 'SELECT') {
                        var group = node.closest('.floating-label-group');
                        if (group) {
                            updateSelectLabel(node);
                            node.addEventListener('change', function() { updateSelectLabel(this); });
                        }
                    }
                });
            });
        });
        observer.observe(document.documentElement, { childList: true, subtree: true });
    }
})();

// Desktop search form submit handler
document.addEventListener('DOMContentLoaded', function() {
    var form = document.getElementById('desktop-search-form');
    if (form) {
        form.addEventListener('submit', function(e) {
            if (!handleSearchSubmit(this)) e.preventDefault();
        });
    }
});

// Mobile search button handlers
document.addEventListener('DOMContentLoaded', function() {
    var btn = document.getElementById('mobile-search-btn');
    if (btn) btn.addEventListener('click', toggleMobileSearch);

    var closeBtn = document.getElementById('mobile-search-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', toggleMobileSearch);

    var input = document.getElementById('mobile-search-input');
    if (input) {
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                var v = this.value.trim();
                if (v) window.location.href = '/?city=' + encodeURIComponent(v);
                toggleMobileSearch();
            }
        });
    }
});

// Global image error handler for avatar fallback
document.addEventListener('error', function(e) {
    if (e.target.tagName === 'IMG' && e.target.classList.contains('js-avatar-img')) {
        var p = e.target.parentElement;
        var s = p ? p.querySelector('.avatar-smiley') : null;
        if (s) { s.style.display = ''; }
        e.target.style.display = 'none';
    }
}, true);

// Global confirm-form handler
document.addEventListener('submit', function(e) {
    var form = e.target.closest('.js-confirm-form');
    if (form && !form.dataset.confirmHandled) {
        e.preventDefault();
        e.stopImmediatePropagation();
        form.dataset.confirmHandled = '1';
        var msg = form.getAttribute('data-confirm') || 'Подтвердите действие';
        var self = form;
        window.showConfirm(msg, function() {
            delete self.dataset.confirmHandled;
            self.submit();
        });
    }
});

// Global auto-submit handler for file inputs
document.addEventListener('change', function(e) {
    if (e.target.classList.contains('js-auto-submit') && e.target.form) {
        e.target.form.submit();
    }
});

// ========================================
// Service Worker Registration
// ========================================
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function() {
        navigator.serviceWorker.register('/sw.js')
            .then(function(reg) { console.log('SW registered:', reg.scope); })
            .catch(function(err) { console.error('SW registration failed:', err); });
    });
}

// ========================================
// CSRF Token Setup
// ========================================
(function() {
    /** Глобальный доступ к CSRF-токену из мета-тега. */
    window.getCSRFToken = function() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    };
    var csrfToken = window.getCSRFToken();
    if (!csrfToken) return;

    document.addEventListener('DOMContentLoaded', function() {
        try {
            document.querySelectorAll('form').forEach(function(form) {
                if (!form.querySelector('input[name="_csrf_token"]')) {
                    var input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = '_csrf_token';
                    input.value = csrfToken;
                    form.appendChild(input);
                }
            });
        } catch(e) { console.warn('CSRF form inject error:', e); }
    });

    // Добавляем токен в fetch-заголовки
    var origFetch = window.fetch;
    window.fetch = function(url, options) {
        try {
            options = options || {};
            var urlObj;
            try { urlObj = new URL(url, window.location.href); } catch(e) {
                return origFetch.call(this, url, options);
            }
            if (urlObj.origin !== window.location.origin) {
                return origFetch.call(this, url, options);
            }
            var method = (options.method || 'GET').toUpperCase();
            if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
                return origFetch.call(this, url, options);
            }
            options.headers = options.headers || {};
            if (!(options.headers instanceof Headers)) {
                options.headers = new Headers(options.headers);
            }
            if (!options.headers.has('X-CSRF-Token')) {
                options.headers.set('X-CSRF-Token', csrfToken);
            }
        } catch(e) { console.warn('CSRF fetch patch error:', e); }
        return origFetch.call(this, url, options);
    };

    // Отправляем CSRF-токен в Service Worker
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({
            type: 'UPDATE_CSRF_TOKEN',
            token: csrfToken
        });
    }
})();

// ========================================
// XSS Protection Utility
// ========================================
window.escapeHtml = function(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.appendChild(document.createTextNode(str));
    return d.innerHTML;
};

// ========================================
// Loading Overlay
// ========================================
document.addEventListener('submit', function(e) {
    var form = e.target;
    if (form.tagName === 'FORM' && !form.hasAttribute('data-no-loader')) {
        var overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'flex';
    }
});

document.addEventListener('click', function(e) {
    var link = e.target.closest('a.needs-loader');
    if (link) {
        var overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.style.display = 'flex';
    }
});

window.addEventListener('pageshow', function() {
    var overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = 'none';
});

// ========================================
// Password Show/Hide Toggle
// ========================================
(function() {
    function addToggle(pwInput) {
        if (pwInput._toggleReady) return;
        pwInput._toggleReady = true;
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'absolute right-2 top-1/2 -translate-y-1/2 text-xs text-neutral-400 hover:text-neutral-600 bg-white/80 rounded px-1.5 py-0.5 select-none';
        btn.textContent = 'Показать';
        btn.setAttribute('tabindex', '-1');
        btn.setAttribute('aria-label', 'Показать пароль');
        var wrap = document.createElement('span');
        wrap.className = 'relative block';
        pwInput.parentNode.insertBefore(wrap, pwInput);
        wrap.appendChild(pwInput);
        wrap.appendChild(btn);
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            var hide = pwInput.type === 'password';
            pwInput.type = hide ? 'text' : 'password';
            btn.textContent = hide ? 'Скрыть' : 'Показать';
            btn.setAttribute('aria-label', hide ? 'Скрыть пароль' : 'Показать пароль');
        });
    }
    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('input[type="password"]').forEach(addToggle);
    });
    // MutationObserver: динамически добавленные поля
    if (window.MutationObserver) {
        var obs = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                m.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) {
                        if (node.type === 'password') addToggle(node);
                        if (node.querySelectorAll) node.querySelectorAll('input[type="password"]').forEach(addToggle);
                    }
                });
            });
        });
        document.addEventListener('DOMContentLoaded', function() {
            obs.observe(document.body, { childList: true, subtree: true });
        });
    }
})();
