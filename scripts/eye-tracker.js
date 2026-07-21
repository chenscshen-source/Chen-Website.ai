/**
 * Pine AI interactive eye. Source handoff: /Users/shenchen/Desktop/PineAI/handoff/eye-tracker.js
 * The SVG geometry and colors are preserved from the delivered component.
 */
(function (global) {
  'use strict';

  var SVG_MARKUP =
    '<svg class="et-ip" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:100%;height:100%;display:block">' +
      '<path d="M32 0C49.6731 0 64 14.3269 64 32C64 49.6731 49.6731 64 32 64C14.3269 64 0 49.6731 0 32C0 14.3269 14.3269 0 32 0ZM29 21C25.134 21 22 24.5817 22 29C22 33.4183 25.134 37 29 37C32.866 37 36 33.4183 36 29C36 24.5817 32.866 21 29 21ZM45 21C41.134 21 38 24.5817 38 29C38 33.4183 41.134 37 45 37C48.866 37 52 33.4183 52 29C52 24.5817 48.866 21 45 21Z" fill="#004123"/>' +
      '<ellipse cx="29" cy="29" rx="7" ry="8" fill="white"/>' +
      '<ellipse cx="45" cy="29" rx="7" ry="8" fill="white"/>' +
      '<circle class="et-pupil" data-eye="0" cx="31" cy="30" r="4" fill="black"/>' +
      '<circle class="et-pupil" data-eye="1" cx="48" cy="30" r="4" fill="black"/>' +
    '</svg>';

  var EYE_CENTERS = [{ cx: 29, cy: 29 }, { cx: 45, cy: 29 }];
  var DEFAULTS = { size: 120, maxMove: 3, sensitivity: 260, easing: 0.18, recenterOnLeave: true };

  function initEyeTracker(container, options) {
    if (!container) throw new Error('[eye-tracker] container is required');
    var cfg = Object.assign({}, DEFAULTS, options || {});
    container.style.width = cfg.size + 'px';
    container.style.height = cfg.size + 'px';
    container.innerHTML = SVG_MARKUP;

    var svg = container.querySelector('.et-ip');
    var pupils = Array.prototype.slice.call(container.querySelectorAll('.et-pupil'));
    var mouseX = 0, mouseY = 0, hasPointer = false, running = false;
    var targets = EYE_CENTERS.map(function () { return { x: 0, y: 0 }; });
    var current = EYE_CENTERS.map(function () { return { x: 0, y: 0 }; });

    function wake() {
      if (!running) { running = true; requestAnimationFrame(animate); }
    }
    function updateTargets() {
      if (!hasPointer) return;
      var rect = svg.getBoundingClientRect();
      var scale = rect.width / 64;
      EYE_CENTERS.forEach(function (eye, i) {
        var dx = mouseX - (rect.left + eye.cx * scale);
        var dy = mouseY - (rect.top + eye.cy * scale);
        var angle = Math.atan2(dy, dx);
        var move = Math.min(cfg.maxMove, Math.hypot(dx, dy) / cfg.sensitivity * cfg.maxMove);
        targets[i].x = Math.cos(angle) * move;
        targets[i].y = Math.sin(angle) * move;
      });
      wake();
    }
    function animate() {
      var settled = true;
      current.forEach(function (position, i) {
        position.x += (targets[i].x - position.x) * cfg.easing;
        position.y += (targets[i].y - position.y) * cfg.easing;
        pupils[i].setAttribute('transform', 'translate(' + position.x.toFixed(2) + ',' + position.y.toFixed(2) + ')');
        if (Math.hypot(targets[i].x - position.x, targets[i].y - position.y) > 0.01) settled = false;
      });
      if (settled) running = false;
      else requestAnimationFrame(animate);
    }
    function onMove(event) {
      mouseX = event.clientX; mouseY = event.clientY; hasPointer = true;
      updateTargets();
    }
    function onTouch(event) {
      if (event.touches && event.touches.length) {
        mouseX = event.touches[0].clientX; mouseY = event.touches[0].clientY; hasPointer = true;
        updateTargets();
      }
    }
    function onLeave() {
      if (!cfg.recenterOnLeave) return;
      targets.forEach(function (target) { target.x = 0; target.y = 0; });
      wake();
    }

    window.addEventListener('mousemove', onMove);
    window.addEventListener('resize', updateTargets);
    window.addEventListener('touchmove', onTouch, { passive: true });
    document.addEventListener('mouseleave', onLeave);
    return {
      destroy: function () {
        window.removeEventListener('mousemove', onMove);
        window.removeEventListener('resize', updateTargets);
        window.removeEventListener('touchmove', onTouch);
        document.removeEventListener('mouseleave', onLeave);
        container.innerHTML = '';
      }
    };
  }

  if (typeof HTMLElement !== 'undefined' && global.customElements && !global.customElements.get('eye-tracker')) {
    var EyeTrackerElement = function () { return Reflect.construct(HTMLElement, [], EyeTrackerElement); };
    EyeTrackerElement.prototype = Object.create(HTMLElement.prototype);
    EyeTrackerElement.prototype.constructor = EyeTrackerElement;
    EyeTrackerElement.prototype.connectedCallback = function () {
      this.style.display = 'inline-block';
      this._ctrl = initEyeTracker(this, {
        size: parseFloat(this.getAttribute('size')) || DEFAULTS.size,
        sensitivity: parseFloat(this.getAttribute('sensitivity')) || DEFAULTS.sensitivity,
        easing: parseFloat(this.getAttribute('easing')) || DEFAULTS.easing
      });
    };
    EyeTrackerElement.prototype.disconnectedCallback = function () {
      if (this._ctrl) this._ctrl.destroy();
    };
    Object.setPrototypeOf(EyeTrackerElement, HTMLElement);
    global.customElements.define('eye-tracker', EyeTrackerElement);
  }

  global.initEyeTracker = initEyeTracker;
  if (typeof module !== 'undefined' && module.exports) module.exports = { initEyeTracker: initEyeTracker };
})(typeof window !== 'undefined' ? window : this);
