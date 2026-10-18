/* ============================================================
   EXPENSE TRACKER — Client-Side Application Logic
   Vanilla JavaScript — no frameworks required.
   ============================================================ */

document.addEventListener('DOMContentLoaded', function () {

  // ─── 0. Launch Splash Screen ────────────────────────────────
  // Use localStorage so PWA cold launches always show splash
  const splashKey = 'splitlite_splash_ts';
  const lastSplash = localStorage.getItem(splashKey);
  const now = Date.now();
  // Show splash if never shown, or if more than 30 minutes have passed (covers PWA relaunch)
  const showSplash = !lastSplash || (now - parseInt(lastSplash)) > 30 * 60 * 1000;

  if (showSplash) {
    const splash = document.createElement('div');
    splash.className = 'splash-overlay';
    splash.id = 'appSplash';
    splash.innerHTML = `
      <div class="splash-content">
        <div class="splash-logo-container">
          <svg class="brand-logo-svg" viewBox="0 0 100 100" fill="none" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logo-yellow-grad-splash" x1="50" y1="18" x2="50" y2="48" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stop-color="#F9D423" />
                <stop offset="100%" stop-color="#F1A91A" />
              </linearGradient>
              <linearGradient id="logo-blue-grad-splash" x1="18" y1="36" x2="46" y2="80" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stop-color="#4ebee9" />
                <stop offset="100%" stop-color="#2c82c9" />
              </linearGradient>
              <linearGradient id="logo-red-grad-splash" x1="54" y1="36" x2="82" y2="80" gradientUnits="userSpaceOnUse">
                <stop offset="0%" stop-color="#ff7675" />
                <stop offset="100%" stop-color="#E72E25" />
              </linearGradient>
            </defs>
            <path d="M50 18 L78 33 L50 48 L22 33 Z" fill="url(#logo-yellow-grad-splash)" />
            <path d="M18 36 L46 51 L46 80 L18 65 Z" fill="url(#logo-blue-grad-splash)" />
            <path d="M54 51 L82 36 L82 65 L54 80 Z" fill="url(#logo-red-grad-splash)" />
          </svg>
        </div>
        <h1 class="splash-title">Split<span>Lite</span></h1>
        <p class="splash-credits">made with <span class="heart-pulse">🤍</span> by garv</p>
      </div>
    `;
    document.body.appendChild(splash);

    // Disable scrolling during splash
    document.body.style.overflow = 'hidden';

    // Show for a short time (1.2s) so the app feels fast
    setTimeout(function () {
      splash.style.opacity = '0';
      splash.style.pointerEvents = 'none';

      // Restore scrolling
      document.body.style.overflow = '';

      // Remove from DOM after fade
      setTimeout(function () {
        splash.remove();
      }, 500);
    }, 1200);

    // Record timestamp so PWA relaunches show it again after 30 min
    localStorage.setItem(splashKey, String(now));
  }

  // ─── 1. Sidebar Toggle (Mobile) ─────────────────────────────
  const sidebar = document.querySelector('.sidebar');
  const overlay = document.querySelector('.sidebar-overlay');

  function toggleSidebar() {
    if (!sidebar) return;
    sidebar.classList.toggle('sidebar-open');
    if (overlay) {
      overlay.classList.toggle('active', sidebar.classList.contains('sidebar-open'));
    }
    document.body.style.overflow = sidebar.classList.contains('sidebar-open') ? 'hidden' : '';
  }

  // Expose globally so the hamburger button's onclick can call it
  window.toggleSidebar = toggleSidebar;

  // Close sidebar when overlay is clicked
  if (overlay) {
    overlay.addEventListener('click', function () {
      sidebar.classList.remove('sidebar-open');
      overlay.classList.remove('active');
      document.body.style.overflow = '';
    });
  }

  // Close sidebar on Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && sidebar && sidebar.classList.contains('sidebar-open')) {
      toggleSidebar();
    }
  });


  // ─── 2. Split Calculator ────────────────────────────────────
  const splitTypeSelect = document.getElementById('split_type') || document.querySelector('[name="split_type"]');
  const splitSections = document.querySelectorAll('.split-section');

  function updateSplitSection() {
    if (!splitTypeSelect) return;
    const selected = splitTypeSelect.value;

    splitSections.forEach(function (section) {
      section.classList.remove('active');
    });

    const targetSection = document.getElementById('split-' + selected);
    if (targetSection) {
      targetSection.classList.add('active');
    }

    // For equal splits, auto-calculate if amount is available
    if (selected === 'equal') {
      calculateEqualSplit();
    }
  }

  if (splitTypeSelect) {
    splitTypeSelect.addEventListener('change', updateSplitSection);
    // Set initial state
    updateSplitSection();
  }

  function calculateEqualSplit() {
    var amountInput = document.getElementById('expense_amount') || document.querySelector('[name="amount"]');
    var checkedMembers = document.querySelectorAll('.member-checkbox:checked');
    if (!amountInput || checkedMembers.length === 0) return;

    var total = parseFloat(amountInput.value) || 0;
    var perPerson = total / checkedMembers.length;
    var preview = document.getElementById('equal-split-preview');
    if (preview) {
      preview.textContent = checkedMembers.length > 0
        ? '₹' + perPerson.toFixed(2) + ' per person (' + checkedMembers.length + ' people)'
        : '';
    }
  }

  // Listen for amount changes to recalculate equal split
  var amountField = document.getElementById('expense_amount') || document.querySelector('[name="amount"]');
  if (amountField) {
    amountField.addEventListener('input', function () {
      if (splitTypeSelect && splitTypeSelect.value === 'equal') {
        calculateEqualSplit();
      }
      validateSplitTotals();
    });
  }


  // ─── 3. Dynamic Member Checkboxes ──────────────────────────
  var memberCheckboxes = document.querySelectorAll('.member-checkbox');
  memberCheckboxes.forEach(function (cb) {
    cb.addEventListener('change', function () {
      calculateEqualSplit();
      updateMemberSplitRows();
    });
  });

  function updateMemberSplitRows() {
    var checkedIds = [];
    memberCheckboxes.forEach(function (cb) {
      if (cb.checked) {
        checkedIds.push(cb.value);
      }
    });

    // Show/hide split input rows based on checked members
    var splitRows = document.querySelectorAll('.split-member-row');
    splitRows.forEach(function (row) {
      var memberId = row.getAttribute('data-member-id');
      if (memberId) {
        row.style.display = checkedIds.indexOf(memberId) !== -1 ? 'flex' : 'none';
      }
    });
  }


  // ─── 4. Toast Notifications ─────────────────────────────────
  function getOrCreateToastContainer() {
    var container = document.querySelector('.toast-container');
    if (!container) {
      container = document.createElement('div');
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    return container;
  }

  function showToast(message, type) {
    type = type || 'info';
    var container = getOrCreateToastContainer();

    var icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ'
    };

    var toast = document.createElement('div');
    toast.className = 'toast ' + type;
    toast.innerHTML =
      '<span class="toast-icon">' + (icons[type] || icons.info) + '</span>' +
      '<span class="toast-message">' + escapeHtml(message) + '</span>' +
      '<button class="toast-close" onclick="this.parentElement.remove()">✕</button>';

    container.appendChild(toast);

    // Auto-dismiss after 4.5 seconds
    setTimeout(function () {
      toast.classList.add('fade-out');
      setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 4500);
  }

  // Expose globally
  window.showToast = showToast;


  // ─── 5. Animated Counters ───────────────────────────────────
  function animateCounter(element, target, duration) {
    duration = duration || 1200;
    var start = 0;
    var startTime = null;
    var prefix = element.getAttribute('data-prefix') || '';
    var suffix = element.getAttribute('data-suffix') || '';
    var decimals = parseInt(element.getAttribute('data-decimals'), 10) || 0;

    function easeOutCubic(t) {
      return 1 - Math.pow(1 - t, 3);
    }

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var elapsed = timestamp - startTime;
      var progress = Math.min(elapsed / duration, 1);
      var easedProgress = easeOutCubic(progress);
      var current = start + (target - start) * easedProgress;

      element.textContent = prefix + current.toFixed(decimals) + suffix;

      if (progress < 1) {
        requestAnimationFrame(step);
      }
    }

    requestAnimationFrame(step);
  }

  // Expose globally
  window.animateCounter = animateCounter;

  // Auto-detect and animate elements with data-counter attribute
  var counters = document.querySelectorAll('[data-counter]');
  if (counters.length > 0) {
    var counterObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var el = entry.target;
          var targetValue = parseFloat(el.getAttribute('data-counter')) || 0;
          animateCounter(el, targetValue);
          counterObserver.unobserve(el);
        }
      });
    }, { threshold: 0.3 });

    counters.forEach(function (counter) {
      counterObserver.observe(counter);
    });
  }


  // ─── 6. Auto-Dismiss Django Messages ────────────────────────
  var messages = document.querySelectorAll('.message-item');
  messages.forEach(function (msg, index) {
    setTimeout(function () {
      msg.classList.add('fade-out');
      setTimeout(function () {
        if (msg.parentNode) {
          msg.parentNode.removeChild(msg);
        }
      }, 300);
    }, 4000 + (index * 400));
  });


  // ─── 7. Confirm Dialogs ────────────────────────────────────
  var deleteForms = document.querySelectorAll('form[data-confirm], .delete-form, form.confirm-delete');
  deleteForms.forEach(function (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var message = form.getAttribute('data-confirm') || 'Are you sure you want to delete this? This action cannot be undone.';
      showConfirmDialog(message, function () {
        // Remove the event listener temporarily and submit
        form.removeEventListener('submit', arguments.callee);
        form.submit();
      });
    });
  });

  function showConfirmDialog(message, onConfirm, onCancel) {
    var existing = document.querySelector('.confirm-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    overlay.innerHTML =
      '<div class="confirm-dialog">' +
        '<div class="confirm-icon">⚠️</div>' +
        '<div class="confirm-title">Are you sure?</div>' +
        '<div class="confirm-message">' + escapeHtml(message) + '</div>' +
        '<div class="confirm-actions">' +
          '<button class="btn btn-outline confirm-cancel-btn">Cancel</button>' +
          '<button class="btn btn-danger confirm-ok-btn">Delete</button>' +
        '</div>' +
      '</div>';

    document.body.appendChild(overlay);

    var cancelBtn = overlay.querySelector('.confirm-cancel-btn');
    var okBtn = overlay.querySelector('.confirm-ok-btn');

    function close() {
      overlay.remove();
    }

    cancelBtn.addEventListener('click', function () {
      close();
      if (onCancel) onCancel();
    });

    okBtn.addEventListener('click', function () {
      close();
      if (onConfirm) onConfirm();
    });

    overlay.addEventListener('click', function (e) {
      if (e.target === overlay) {
        close();
        if (onCancel) onCancel();
      }
    });

    document.addEventListener('keydown', function handler(e) {
      if (e.key === 'Escape') {
        close();
        if (onCancel) onCancel();
        document.removeEventListener('keydown', handler);
      }
    });
  }

  // Expose globally
  window.showConfirmDialog = showConfirmDialog;


  // ─── 8. Form Validation ─────────────────────────────────────
  var expenseForm = document.querySelector('.expense-form, form[data-validate]');
  if (expenseForm) {
    expenseForm.addEventListener('submit', function (e) {
      var isValid = true;
      clearValidationErrors();

      // Validate amount
      var amountInput = expenseForm.querySelector('[name="amount"]');
      if (amountInput) {
        var amount = parseFloat(amountInput.value);
        if (isNaN(amount) || amount <= 0) {
          showFieldError(amountInput, 'Amount must be greater than 0');
          isValid = false;
        }
      }

      // Validate description
      var descInput = expenseForm.querySelector('[name="description"]');
      if (descInput && descInput.value.trim() === '') {
        showFieldError(descInput, 'Description is required');
        isValid = false;
      }

      // Validate split totals for non-equal splits
      var splitType = splitTypeSelect ? splitTypeSelect.value : 'equal';
      if (splitType !== 'equal' && amountInput) {
        var splitValid = validateSplitTotals();
        if (!splitValid) {
          isValid = false;
        }
      }

      if (!isValid) {
        e.preventDefault();
        showToast('Please fix the errors in the form.', 'error');
      }
    });
  }

  function validateSplitTotals() {
    if (!splitTypeSelect) return true;
    var splitType = splitTypeSelect.value;
    if (splitType === 'equal') return true;

    var amountInput = document.querySelector('[name="amount"]');
    if (!amountInput) return true;
    var total = parseFloat(amountInput.value) || 0;
    if (total === 0) return true;

    var section = document.getElementById('split-' + splitType);
    if (!section) return true;

    var inputs = section.querySelectorAll('.split-input');
    var sum = 0;
    inputs.forEach(function (input) {
      if (input.closest('.split-member-row') && input.closest('.split-member-row').style.display !== 'none') {
        sum += parseFloat(input.value) || 0;
      }
    });

    var totalRow = section.querySelector('.split-total-row');

    if (splitType === 'percentage') {
      var valid = Math.abs(sum - 100) < 0.01;
      if (totalRow) {
        totalRow.classList.toggle('valid', valid);
        totalRow.classList.toggle('invalid', !valid);
        totalRow.querySelector('.split-total-value').textContent = sum.toFixed(1) + '%';
      }
      return valid;
    } else {
      // exact amounts or shares
      var valid = Math.abs(sum - total) < 0.01;
      if (totalRow) {
        totalRow.classList.toggle('valid', valid);
        totalRow.classList.toggle('invalid', !valid);
        totalRow.querySelector('.split-total-value').textContent = '₹' + sum.toFixed(2);
      }
      return valid;
    }
  }

  // Recalculate on split input change
  document.addEventListener('input', function (e) {
    if (e.target.classList.contains('split-input')) {
      validateSplitTotals();
    }
  });

  function showFieldError(input, message) {
    input.classList.add('error');
    var group = input.closest('.form-group');
    if (group) {
      var errorEl = document.createElement('div');
      errorEl.className = 'form-error';
      errorEl.textContent = message;
      group.appendChild(errorEl);
    }
  }

  function clearValidationErrors() {
    document.querySelectorAll('.form-error').forEach(function (el) {
      el.remove();
    });
    document.querySelectorAll('.form-input.error, .form-select.error').forEach(function (el) {
      el.classList.remove('error');
    });
  }


  // ─── 9. Search Filter ──────────────────────────────────────
  var searchInputs = document.querySelectorAll('.search-filter');
  searchInputs.forEach(function (input) {
    var targetSelector = input.getAttribute('data-target');
    if (!targetSelector) return;

    input.addEventListener('input', function () {
      var query = this.value.toLowerCase().trim();
      var items = document.querySelectorAll(targetSelector);

      items.forEach(function (item) {
        var text = item.textContent.toLowerCase();
        var match = query === '' || text.indexOf(query) !== -1;
        item.style.display = match ? '' : 'none';
      });

      // Toggle empty-state if all hidden
      var container = items.length > 0 ? items[0].parentElement : null;
      if (container) {
        var visibleCount = 0;
        items.forEach(function (item) {
          if (item.style.display !== 'none') visibleCount++;
        });

        var emptyMsg = container.querySelector('.search-empty');
        if (visibleCount === 0 && !emptyMsg) {
          emptyMsg = document.createElement('div');
          emptyMsg.className = 'empty-state search-empty';
          emptyMsg.innerHTML =
            '<div class="empty-icon">🔍</div>' +
            '<div class="empty-title">No results found</div>' +
            '<div class="empty-text">Try adjusting your search terms.</div>';
          container.appendChild(emptyMsg);
        } else if (visibleCount > 0 && emptyMsg) {
          emptyMsg.remove();
        }
      }
    });
  });


  // ─── 10. Notification Bell Dropdown ─────────────────────────
  var bellBtns = document.querySelectorAll('.bell-btn');
  bellBtns.forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var dropdown = btn.closest('.notification-bell').querySelector('.notification-dropdown');
      if (dropdown) {
        dropdown.classList.toggle('active');
      }
      // Close other dropdowns
      document.querySelectorAll('.notification-dropdown.active').forEach(function (dd) {
        if (dd !== dropdown) dd.classList.remove('active');
      });
    });
  });

  // Close dropdown when clicking outside
  document.addEventListener('click', function () {
    document.querySelectorAll('.notification-dropdown.active').forEach(function (dd) {
      dd.classList.remove('active');
    });
  });


  // ─── Utility: HTML Escape ───────────────────────────────────
  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }


  // ─── Auto-focus first input on modals ───────────────────────
  var modals = document.querySelectorAll('.modal');
  modals.forEach(function (modal) {
    var observer = new MutationObserver(function () {
      if (modal.closest('.modal-overlay.active')) {
        var firstInput = modal.querySelector('input:not([type="hidden"]), select, textarea');
        if (firstInput) firstInput.focus();
      }
    });
    var overlay = modal.closest('.modal-overlay');
    if (overlay) {
      observer.observe(overlay, { attributes: true, attributeFilter: ['class'] });
    }
  });


  // ─── Smooth scroll for anchor links ─────────────────────────
  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      var target = document.querySelector(this.getAttribute('href'));
      if (target) {
        e.preventDefault();
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  });


  // ─── Active nav link highlight ──────────────────────────────
  var currentPath = window.location.pathname;
  document.querySelectorAll('.sidebar-nav .nav-link').forEach(function (link) {
    var href = link.getAttribute('href');
    if (href && currentPath === href) {
      link.classList.add('active');
    } else if (href && href !== '/' && currentPath.startsWith(href)) {
      link.classList.add('active');
    }
  });

  // ─── Web Push Notifications ──────────────────────────────
  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding)
      .replace(/\-/g, '+')
      .replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
      outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
  }

  function isSameKey(buffer, key) {
    if (!buffer) return false;
    const bytes = new Uint8Array(buffer);
    return bytes.length === key.length && bytes.every((byte, i) => byte === key[i]);
  }

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function subscribeToPush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
    
    Notification.requestPermission().then(function(permission) {
      if (permission === 'granted') {
        navigator.serviceWorker.ready.then(function(registration) {
          fetch('/api/push/vapid-public-key/')
            .then(response => response.json())
            .then(data => {
              if (!data.public_key) return null;
              const convertedVapidKey = urlBase64ToUint8Array(data.public_key);
              // A subscription made with an older key must be dropped, or subscribe() rejects
              return registration.pushManager.getSubscription()
                .then(function(existing) {
                  if (existing && !isSameKey(existing.options.applicationServerKey, convertedVapidKey)) {
                    return existing.unsubscribe();
                  }
                })
                .then(function() {
                  return registration.pushManager.subscribe({
                    userVisibleOnly: true,
                    applicationServerKey: convertedVapidKey
                  });
                });
            })
            .then(function(subscription) {
              if (!subscription) return null;
              return fetch('/api/push/subscribe/', {
                method: 'POST',
                headers: {
                  'Content-Type': 'application/json',
                  'X-CSRFToken': getCookie('csrftoken')
                },
                body: JSON.stringify(subscription)
              });
            })
            .then(function(response) {
              if (response && response.ok) console.log('Successfully subscribed to push notifications.');
            })
            .catch(function(err) {
              console.error('Failed to subscribe the user: ', err);
            });
        });
      }
    });
  }

  // Attempt subscription after a slight delay to not block rendering
  setTimeout(subscribeToPush, 2000);

});
