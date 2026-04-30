/**
 * alpine-helpers.js — Reusable Alpine.js components for Amplifier dashboards.
 *
 * Components registered on Alpine:init:
 *  - copyButton(url)     — Copy a URL to clipboard with visual feedback.
 *  - autosave(key, ms)   — Persist form state to localStorage with debounce.
 *  - commandPalette()    — Cmd/Ctrl+K global command palette.
 *
 * Keyboard shortcuts:
 *  - Ctrl/Cmd+K → dispatches 'amplifier:open-command-palette' on document.
 */

document.addEventListener('alpine:init', function () {

  // ── copyButton ──────────────────────────────────────────────────────────────
  /**
   * Usage: <button x-data="copyButton(url)" @click="copy()">
   *          <span x-text="copied ? 'Copied!' : 'Copy URL'"></span>
   *        </button>
   */
  Alpine.data('copyButton', function (url) {
    return {
      copied: false,
      async copy() {
        try {
          await navigator.clipboard.writeText(url);
          this.copied = true;
          setTimeout(() => { this.copied = false; }, 1500);
        } catch (err) {
          // Fallback for browsers without clipboard API
          var ta = document.createElement('textarea');
          ta.value = url;
          ta.style.cssText = 'position:fixed;opacity:0;pointer-events:none';
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          this.copied = true;
          setTimeout(() => { this.copied = false; }, 1500);
        }
      }
    };
  });


  // ── autosave ────────────────────────────────────────────────────────────────
  /**
   * Persist all named form inputs to localStorage on change.
   * Restores saved values on init.
   *
   * Usage: <form x-data="autosave('wizard-step-1')">
   *          <input name="budget" ...>
   *        </form>
   *
   * Call this.clear() to wipe saved state (e.g. on successful submit).
   */
  Alpine.data('autosave', function (key, debounceMs) {
    debounceMs = debounceMs !== undefined ? debounceMs : 500;
    var _timer = null;

    return {
      _key: 'amplifier_autosave_' + key,

      init() {
        // Restore saved values
        try {
          var saved = JSON.parse(localStorage.getItem(this._key) || 'null');
          if (saved && typeof saved === 'object') {
            var form = this.$el.closest ? this.$el.closest('form') : this.$el;
            if (!form || form.tagName !== 'FORM') form = this.$el;
            Object.keys(saved).forEach(function (name) {
              var el = form.querySelector('[name="' + name + '"]');
              if (!el) return;
              if (el.type === 'checkbox' || el.type === 'radio') {
                el.checked = !!saved[name];
              } else {
                el.value = saved[name];
              }
            });
          }
        } catch (_) {}

        // Wire up input listener
        var self = this;
        this.$el.addEventListener('input', function () {
          clearTimeout(_timer);
          _timer = setTimeout(function () { self._save(); }, debounceMs);
        });
      },

      _save() {
        try {
          var form = this.$el.closest ? this.$el.closest('form') : this.$el;
          if (!form || form.tagName !== 'FORM') form = this.$el;
          var data = {};
          new FormData(form).forEach(function (val, name) { data[name] = val; });
          localStorage.setItem(this._key, JSON.stringify(data));
        } catch (_) {}
      },

      clear() {
        try { localStorage.removeItem(this._key); } catch (_) {}
      }
    };
  });


  // ── commandPalette ──────────────────────────────────────────────────────────
  /**
   * Global command palette. Toggle with Ctrl/Cmd+K or by setting open=true.
   *
   * Usage:
   *   <div x-data="commandPalette" x-show="open" @keydown.escape.window="open=false">
   *     <input x-model="query" @input="filter()" placeholder="Search commands…">
   *     <ul>
   *       <template x-for="item in filtered" :key="item.label">
   *         <li @click="execute(item)" x-text="item.label"></li>
   *       </template>
   *     </ul>
   *   </div>
   *
   * Populate items via: Alpine.store or pass items array after init.
   */
  Alpine.data('commandPalette', function () {
    return {
      open: false,
      query: '',
      items: [],
      filtered: [],

      init() {
        // Listen for custom open event dispatched by keyboard shortcut below
        var self = this;
        document.addEventListener('amplifier:open-command-palette', function () {
          self.open = true;
          self.query = '';
          self.filter();
          // Focus the search input on next tick
          self.$nextTick && self.$nextTick(function () {
            var input = self.$el.querySelector('input');
            if (input) input.focus();
          });
        });

        // Initial filter pass
        this.filter();
      },

      filter() {
        var q = this.query.trim().toLowerCase();
        if (!q) {
          this.filtered = this.items.slice();
          return;
        }
        this.filtered = this.items.filter(function (item) {
          return item.label && item.label.toLowerCase().includes(q);
        });
      },

      execute(item) {
        this.open = false;
        this.query = '';
        this.filter();
        if (item && typeof item.action === 'function') {
          item.action();
        } else if (item && item.href) {
          window.location.href = item.href;
        }
      },

      close() {
        this.open = false;
        this.query = '';
        this.filter();
      }
    };
  });

}); // end alpine:init


// ── Global keyboard shortcut: Ctrl/Cmd+K → open command palette ──────────────

document.addEventListener('keydown', function (evt) {
  if ((evt.ctrlKey || evt.metaKey) && evt.key === 'k') {
    evt.preventDefault();
    document.dispatchEvent(new CustomEvent('amplifier:open-command-palette'));
  }
});
