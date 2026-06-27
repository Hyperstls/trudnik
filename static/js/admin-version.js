(function () {
    'use strict';

    /**
     * Admin Version Button — tooltip + copy to clipboard
     * CSP-compliant: no inline handlers, loaded via external script with nonce
     */
    document.addEventListener('DOMContentLoaded', function () {
        const versionEl = document.getElementById('git-version');
        const button = document.getElementById('current-version-btn');

        if (!button) return;

        // --- Read version ---
        let version = versionEl ? (versionEl.textContent || '').trim() : '';
        if (!version) {
            version = 'Неизвестная версия';
        }

        // --- Create tooltip ---
        const tooltip = document.createElement('div');
        tooltip.className = 'version-tooltip';
        document.body.appendChild(tooltip);

        const DEFAULT_BUTTON_TEXT = '🔖 Текущая версия';
        const COPIED_BUTTON_TEXT = '✅ Скопировано';
        let copyTimeout = null;
        let isCopied = false;

        // --- Tooltip positioning ---
        function positionTooltip() {
            const btnRect = button.getBoundingClientRect();
            const tipWidth = tooltip.offsetWidth;
            const tipHeight = tooltip.offsetHeight;

            let left = btnRect.left + (btnRect.width / 2) - (tipWidth / 2);
            let top = btnRect.top - tipHeight - 8;

            // Keep within viewport
            if (left < 4) left = 4;
            if (left + tipWidth > window.innerWidth - 4) {
                left = window.innerWidth - tipWidth - 4;
            }
            if (top < 4) {
                top = btnRect.bottom + 8; // Show below if not enough space above
            }

            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        }

        function showTooltip(text) {
            if (isCopied) return;
            tooltip.textContent = text || version;
            positionTooltip();
            tooltip.classList.add('visible');
        }

        function hideTooltip() {
            tooltip.classList.remove('visible');
        }

        // --- Tooltip event listeners ---
        button.addEventListener('mouseover', function () {
            showTooltip(version);
        });

        button.addEventListener('mouseout', function () {
            hideTooltip();
        });

        button.addEventListener('focus', function () {
            showTooltip(version);
        });

        button.addEventListener('blur', function () {
            hideTooltip();
        });

        // --- Copy to clipboard ---
        button.addEventListener('click', function () {
            if (version === 'Неизвестная версия') {
                showTooltip('Неизвестная версия');
                return;
            }

            // Clear any pending copy timeout
            if (copyTimeout) {
                clearTimeout(copyTimeout);
                copyTimeout = null;
            }

            // Use Clipboard API with fallback
            const doCopy = function () {
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    return navigator.clipboard.writeText(version);
                }
                // Fallback for older browsers / non-HTTPS
                return new Promise(function (resolve, reject) {
                    try {
                        const textarea = document.createElement('textarea');
                        textarea.value = version;
                        textarea.style.position = 'fixed';
                        textarea.style.left = '-9999px';
                        textarea.style.top = '-9999px';
                        document.body.appendChild(textarea);
                        textarea.focus();
                        textarea.select();
                        const success = document.execCommand('copy');
                        document.body.removeChild(textarea);
                        if (success) {
                            resolve();
                        } else {
                            reject(new Error('execCommand copy failed'));
                        }
                    } catch (e) {
                        reject(e);
                    }
                });
            };

            hideTooltip();

            doCopy()
                .then(function () {
                    isCopied = true;
                    button.innerText = COPIED_BUTTON_TEXT;
                    copyTimeout = setTimeout(function () {
                        button.innerText = DEFAULT_BUTTON_TEXT;
                        isCopied = false;
                        copyTimeout = null;
                    }, 2000);
                })
                .catch(function (err) {
                    showTooltip('Ошибка копирования');
                    copyTimeout = setTimeout(function () {
                        hideTooltip();
                        copyTimeout = null;
                    }, 2000);
                });
        });

        // Update tooltip position on scroll/resize
        window.addEventListener('scroll', function () {
            if (tooltip.classList.contains('visible')) {
                positionTooltip();
            }
        }, { passive: true });

        window.addEventListener('resize', function () {
            if (tooltip.classList.contains('visible')) {
                positionTooltip();
            }
        }, { passive: true });
    });
})();
