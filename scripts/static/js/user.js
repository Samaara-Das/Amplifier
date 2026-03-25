// Amplifier User App

var _lastPendingCount = 0;

document.addEventListener('DOMContentLoaded', function() {
  // Auto-dismiss flash messages after 5 seconds
  document.querySelectorAll('.alert').forEach(function(alert) {
    setTimeout(function() { alert.style.display = 'none'; }, 5000);
  });

  // Request notification permission on first load
  if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
  }

  // Start polling for status updates
  pollStatus();
});

function pollStatus() {
  fetch('/api/status')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var pending = data.pending_drafts || 0;

      // If new drafts appeared since last check, send notification
      if (pending > _lastPendingCount && _lastPendingCount >= 0) {
        var newCount = pending - _lastPendingCount;
        sendNotification(
          'New content ready for review',
          newCount + ' new draft' + (newCount > 1 ? 's' : '') + ' waiting for your approval.'
        );

        // Update badge on Campaigns nav item if it exists
        var badge = document.getElementById('badge-campaigns');
        if (badge) {
          badge.textContent = pending;
          badge.style.display = pending > 0 ? 'inline-flex' : 'none';
        }
      }

      _lastPendingCount = pending;
    })
    .catch(function() {})
    .finally(function() {
      // Poll every 30 seconds
      setTimeout(pollStatus, 30000);
    });
}

function sendNotification(title, body) {
  if (!('Notification' in window)) return;

  if (Notification.permission === 'granted') {
    var n = new Notification(title, {
      body: body,
      icon: '/static/css/user.css', // No icon file, but required param
      requireInteraction: true, // Stays until user dismisses
      tag: 'amplifier-draft', // Replaces previous notification
    });
    n.onclick = function() {
      window.focus();
      window.location.href = '/campaigns';
      n.close();
    };
  } else if (Notification.permission === 'default') {
    Notification.requestPermission().then(function(perm) {
      if (perm === 'granted') {
        sendNotification(title, body);
      }
    });
  }
}
