/**
 * CareKey Core Client JavaScript
 * Lightweight, accessible vanilla JS helper functions.
 */

(function () {
    'use strict';

    /**
     * Announce dynamic status or alert messages to screen readers.
     * @param {string} message - Message text to be spoken.
     * @param {'polite' | 'assertive'} priority - Priority level for the live region.
     */
    function announce(message, priority = 'polite') {
        const regionId = priority === 'assertive' ? 'aria-live-assertive' : 'aria-live-polite';
        const region = document.getElementById(regionId);
        if (!region) return;

        // Clear previous message then re-inject to trigger screen reader announcement
        region.textContent = '';
        window.setTimeout(() => {
            region.textContent = message;
        }, 50);
    }

    /**
     * Copy text to clipboard with screen reader announcement and visual feedback.
     */
    function copyText(text, btnElement) {
        if (!navigator.clipboard) {
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                if (btnElement) {
                    const originalText = btnElement.textContent;
                    btnElement.textContent = 'Copied!';
                    setTimeout(() => { btnElement.textContent = originalText; }, 2000);
                }
                announce('Copied to clipboard');
            } catch (err) {
                announce('Failed to copy');
            } finally {
                document.body.removeChild(textarea);
            }
            return;
        }

        navigator.clipboard.writeText(text).then(() => {
            if (btnElement) {
                const originalText = btnElement.textContent;
                btnElement.textContent = 'Copied!';
                setTimeout(() => { btnElement.textContent = originalText; }, 2000);
            }
            announce('Copied to clipboard');
        }).catch(() => {
            announce('Failed to copy');
        });
    }

    /**
     * Toggle password visibility for an input field.
     */
    function toggleInputVisibility(inputId, btnElement) {
        const input = document.getElementById(inputId);
        if (!input) return;
        if (input.type === 'password') {
            input.type = 'text';
            if (btnElement) {
                btnElement.textContent = 'Hide';
                btnElement.setAttribute('aria-label', 'Hide passcode');
            }
            announce('Passcode visible');
        } else {
            input.type = 'password';
            if (btnElement) {
                btnElement.textContent = 'Show';
                btnElement.setAttribute('aria-label', 'Show passcode');
            }
            announce('Passcode hidden');
        }
    }

    /**
     * Toggle passcode element text between masked dots and actual passcode.
     */
    function toggleElementMask(elementId, btnElement) {
        const elem = document.getElementById(elementId);
        if (!elem) return;
        const actual = elem.getAttribute('data-passcode');
        if (!actual) return;

        if (elem.getAttribute('data-masked') === 'true') {
            elem.textContent = actual;
            elem.setAttribute('data-masked', 'false');
            if (btnElement) {
                btnElement.textContent = 'Hide';
                btnElement.setAttribute('aria-label', 'Hide passcode');
            }
            announce('Passcode visible');
        } else {
            elem.textContent = '••••••••••••';
            elem.setAttribute('data-masked', 'true');
            if (btnElement) {
                btnElement.textContent = 'Show';
                btnElement.setAttribute('aria-label', 'Show passcode');
            }
            announce('Passcode hidden');
        }
    }

    // Expose utility globally on window.CareKey
    window.CareKey = {
        announce: announce,
        copyText: copyText,
        toggleInputVisibility: toggleInputVisibility,
        toggleElementMask: toggleElementMask
    };

    // Ensure skip-link properly sets focus on target in older browsers
    document.addEventListener('DOMContentLoaded', () => {
        const skipLink = document.querySelector('.skip-link');
        if (skipLink) {
            skipLink.addEventListener('click', (e) => {
                const targetId = skipLink.getAttribute('href').substring(1);
                const target = document.getElementById(targetId);
                if (target) {
                    target.setAttribute('tabindex', '-1');
                    target.focus();
                }
            });
        }
    });
})();
