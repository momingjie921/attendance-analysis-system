/**
 * Common JS functions for Attendance Analysis System
 * Includes Modal management and common utilities.
 */

// Modal State Variables
let confirmCallback = null;
let cancelCallback = null;
let csrfTokenCache = null;

async function getApiCsrfToken() {
    if (csrfTokenCache) return csrfTokenCache;
    const res = await window.fetch('/api/csrf-token', {
        method: 'GET',
        credentials: 'same-origin',
        headers: { 'Accept': 'application/json' }
    });
    if (!res.ok) throw new Error('Failed to get CSRF token');
    const data = await res.json();
    csrfTokenCache = data?.data?.csrf_token || null;
    if (!csrfTokenCache) throw new Error('Invalid CSRF token payload');
    return csrfTokenCache;
}

(function patchFetchForApiCsrf() {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async function(input, init = {}) {
        const requestUrl = typeof input === 'string' ? input : (input?.url || '');
        const method = ((init && init.method) || (typeof input !== 'string' && input?.method) || 'GET').toUpperCase();
        const isWrite = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
        const isApi = requestUrl.startsWith('/api/');

        if (isApi && isWrite) {
            const token = await getApiCsrfToken();
            const headers = new Headers(init.headers || {});
            headers.set('X-CSRF-Token', token);
            init = {
                ...init,
                credentials: init.credentials || 'same-origin',
                headers
            };
        }
        return originalFetch(input, init);
    };
})();

/**
 * Show a general information/success/error/warning modal
 * @param {string} message - Message content (supports HTML)
 * @param {string} type - 'info', 'success', 'error', 'warning'
 * @param {string} title - Optional custom title
 */
function showModal(message, type = 'info', title = '') {
    const modal = document.getElementById('common-modal');
    if (!modal) return;

    const titleEl = document.getElementById('modal-title');
    const msgEl = document.getElementById('modal-message');
    
    // Set content
    msgEl.innerHTML = message;
    
    // Set icon and color based on type
    let iconClass = 'fa-circle-info';
    let color = '#3B82F6'; // Default Blue
    let defaultTitle = '提示';
    
    if (type === 'success') {
        iconClass = 'fa-circle-check';
        color = '#10B981'; // Green
        defaultTitle = '成功';
    } else if (type === 'error') {
        iconClass = 'fa-circle-exclamation';
        color = '#EF4444'; // Red
        defaultTitle = '错误';
    } else if (type === 'warning') {
        iconClass = 'fa-triangle-exclamation';
        color = '#F59E0B'; // Orange
        defaultTitle = '警告';
    }
    
    // Update Title
    if (titleEl) {
        titleEl.innerHTML = `<i class="fa-solid ${iconClass}" style="color: ${color}; font-size: 20px"></i><span style="font-weight: 600;font-size: 18px; margin-left: 8px">${title || defaultTitle}</span>`;
    }
    
    // Show Modal
    modal.style.display = 'flex';
}

/**
 * Close the general modal
 */
function closeModal() {
    const modal = document.getElementById('common-modal');
    if (modal) {
        modal.style.display = 'none';
    }
}

/**
 * Show a confirmation modal
 * @param {string} message - Confirmation message
 * @param {Function} onConfirm - Callback for Yes
 * @param {Function} onCancel - Callback for No (optional)
 * @param {Object} options - Optional settings { confirmText: 'Yes', confirmType: 'primary'|'danger'|'warning' }
 */
function showConfirmModal(message, onConfirm, onCancel, options = {}) {
    const modal = document.getElementById('confirm-modal');
    if (!modal) return;

    const msgEl = document.getElementById('confirm-message');
    const yesBtn = document.getElementById('confirm-btn-yes');
    const noBtn = document.getElementById('confirm-btn-no');

    msgEl.innerHTML = message; 
    
    // Reset buttons
    if (yesBtn) {
        yesBtn.textContent = options.confirmText || '确定';
        
        // Handle button types
        yesBtn.className = 'modal-btn'; // Reset classes
        if (options.confirmType === 'danger') {
            yesBtn.classList.add('btn-danger'); // Assuming btn-danger class exists in CSS or we add inline style
            yesBtn.style.backgroundColor = '#DC2626';
            yesBtn.style.color = '#FFFFFF';
        } else if (options.confirmType === 'warning') {
            yesBtn.style.backgroundColor = '#F59E0B';
            yesBtn.style.color = '#FFFFFF';
        } else {
            yesBtn.classList.add('modal-btn-primary');
            yesBtn.style.backgroundColor = ''; // Reset inline style
            yesBtn.style.color = '';
        }
    }
    
    if (noBtn) {
        noBtn.textContent = options.cancelText || '取消';
    }

    confirmCallback = onConfirm;
    cancelCallback = onCancel;
    
    modal.style.display = 'flex';
}

/**
 * Close the confirmation modal and trigger callback
 * @param {boolean} isConfirm - true if Yes clicked, false if No clicked
 */
function closeConfirmModal(isConfirm) {
    const modal = document.getElementById('confirm-modal');
    if (!modal) return;

    modal.style.display = 'none';
    if (isConfirm && confirmCallback) {
        confirmCallback();
    } else if (!isConfirm && cancelCallback) {
        cancelCallback();
    }
    // Reset callbacks
    confirmCallback = null;
    cancelCallback = null;
}

// Initialize Global Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    // Click outside to close modals
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                if (this.id === 'common-modal') closeModal();
                if (this.id === 'confirm-modal') closeConfirmModal(false);
            }
        });
    });
});
