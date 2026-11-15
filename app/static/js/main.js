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

    // Expose utility globally on window.CareKey
    window.CareKey = {
        announce: announce
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
