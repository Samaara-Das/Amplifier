// Amplifier User App
document.addEventListener('DOMContentLoaded', function() {
  // Auto-dismiss flash messages after 5 seconds
  document.querySelectorAll('.alert').forEach(function(alert) {
    setTimeout(function() { alert.style.display = 'none'; }, 5000);
  });
});
