// 3x3 pattern pad: sign-in tab and Account Settings.
//
// The pad is described by its markup (see pattern_pad() in app/dash_apps/pages/login_system.py):
//   .pattern-pad[data-input-id][data-clear-id][data-preview-id][data-confirm-id?]  containing  canvas.pattern-canvas
//   and nine .pattern-dot[data-dot-num="1".."9"].
//
// Everything is delegated from `document`, so it works for pads Dash inserts later (the sign-in form is injected after
// the society is chosen and Account Settings lives in a modal). The previous version bound its listeners once at page load,
// looked for elements the layout did not render, and wrote to a type="hidden" input React ignores.
(function () {
  'use strict';

  var MIN_DOTS = 4;
  var states = new WeakMap();   // pad element -> {selected, drawing, stage, first, pointer}
  var active = null;            // the pad currently being drawn on

  function setDashInput(id, value) {
    // Dash inputs are React-controlled: assigning el.value directly is swallowed. Going through the native setter and
    // then firing a bubbling "input" event is what makes React (and so the Dash callback) see the change.
    var el = id && document.getElementById(id);
    if (!el) { return; }
    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function stateOf(pad) {
    var st = states.get(pad);
    if (!st) { st = { selected: [], drawing: false, stage: 1, first: '', pointer: null }; states.set(pad, st); }
    return st;
  }

  function dotAt(node) {
    var dot = node && node.closest ? node.closest('.pattern-dot') : null;
    return dot && dot.closest('.pattern-pad') ? dot : null;
  }

  function num(dot) { return dot.getAttribute('data-dot-num'); }

  function preview(pad, text, isError) {
    var el = document.getElementById(pad.getAttribute('data-preview-id') || '');
    if (!el) { return; }
    el.textContent = text;
    el.style.color = isError ? '#dc3545' : '';
  }

  function paint(pad, st) {
    var dots = pad.querySelectorAll('.pattern-dot');
    var centers = {};
    var box = pad.getBoundingClientRect();
    Array.prototype.forEach.call(dots, function (d) {
      var n = num(d);
      d.classList.toggle('active', st.selected.indexOf(n) !== -1);
      var r = d.getBoundingClientRect();
      centers[n] = { x: r.left + r.width / 2 - box.left, y: r.top + r.height / 2 - box.top };
    });
    var cv = pad.querySelector('.pattern-canvas');
    var ctx = cv && cv.getContext ? cv.getContext('2d') : null;
    if (!ctx) { return; }
    var ratio = window.devicePixelRatio || 1;
    cv.width = Math.round(box.width * ratio);
    cv.height = Math.round(box.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, box.width, box.height);
    if (!st.selected.length) { return; }
    ctx.strokeStyle = '#667eea';
    ctx.lineWidth = 4;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    st.selected.forEach(function (n, i) {
      var c = centers[n];
      if (i === 0) { ctx.moveTo(c.x, c.y); } else { ctx.lineTo(c.x, c.y); }
    });
    if (st.drawing && st.pointer) { ctx.lineTo(st.pointer.x, st.pointer.y); }
    ctx.stroke();
  }

  function reset(pad, message) {
    var st = stateOf(pad);
    st.selected = []; st.drawing = false; st.stage = 1; st.first = ''; st.pointer = null;
    setDashInput(pad.getAttribute('data-input-id'), '');
    setDashInput(pad.getAttribute('data-confirm-id'), '');
    paint(pad, st);
    preview(pad, message || 'No pattern drawn', false);
  }

  function finish(pad) {
    var st = stateOf(pad);
    st.drawing = false; st.pointer = null;
    var value = st.selected.join('-');
    var confirmId = pad.getAttribute('data-confirm-id');

    if (st.selected.length < MIN_DOTS) {
      st.selected = [];
      paint(pad, st);
      preview(pad, 'Connect at least ' + MIN_DOTS + ' dots', true);
      if (st.stage === 1) { setDashInput(pad.getAttribute('data-input-id'), ''); }
      return;
    }

    if (!confirmId) {                                       // sign-in: one drawing is the value
      setDashInput(pad.getAttribute('data-input-id'), value);
      paint(pad, st);
      preview(pad, st.selected.join(' \u2192 '), false);
      return;
    }

    if (st.stage === 1) {                                   // setting a pattern: first drawing
      st.first = value; st.stage = 2;
      setDashInput(pad.getAttribute('data-input-id'), value);
      setDashInput(confirmId, '');
      paint(pad, st);
      preview(pad, 'Draw it again to confirm', false);
      return;
    }
    if (value === st.first) {                               // second drawing matches
      setDashInput(confirmId, value);
      paint(pad, st);
      preview(pad, 'Confirmed \u2014 press Save pattern', false);
      st.stage = 1;
    } else {
      reset(pad, "That didn't match \u2014 draw the pattern again");
      preview(pad, "That didn't match \u2014 draw the pattern again", true);
    }
  }

  document.addEventListener('pointerdown', function (e) {
    var dot = dotAt(e.target);
    if (!dot) { return; }
    var pad = dot.closest('.pattern-pad');
    var st = stateOf(pad);
    e.preventDefault();
    active = pad;
    st.drawing = true;
    st.selected = [num(dot)];
    preview(pad, st.stage === 2 ? 'Draw it again to confirm' : '\u2026', false);
    paint(pad, st);
  });

  document.addEventListener('pointermove', function (e) {
    if (!active) { return; }
    var st = stateOf(active);
    if (!st.drawing) { return; }
    var box = active.getBoundingClientRect();
    st.pointer = { x: e.clientX - box.left, y: e.clientY - box.top };
    var dot = dotAt(document.elementFromPoint(e.clientX, e.clientY));
    if (dot && dot.closest('.pattern-pad') === active && st.selected.indexOf(num(dot)) === -1) {
      st.selected.push(num(dot));
    }
    paint(active, st);
  });

  function end() {
    if (!active) { return; }
    var pad = active;
    active = null;
    if (stateOf(pad).drawing) { finish(pad); }
  }
  document.addEventListener('pointerup', end);
  document.addEventListener('pointercancel', end);

  document.addEventListener('click', function (e) {
    var btn = e.target && e.target.closest ? e.target.closest('button') : null;
    if (!btn || !btn.id) { return; }
    var pads = document.querySelectorAll('.pattern-pad[data-clear-id]');
    Array.prototype.forEach.call(pads, function (pad) {
      if (pad.getAttribute('data-clear-id') === btn.id) { reset(pad); }
    });
  });
})();
