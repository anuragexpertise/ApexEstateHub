// onboarding_celebrate.js
// One celebration for every milestone: confetti plus a modal.
//   window.EstateHubCelebrate({kind, title, message, details, key, once})
// kinds: 'live' (agreement signed, society live), 'registered' (master registered a society), 'sealed' (agreement/annexure sealed)
(function(){
  if (typeof window.dash_clientside === 'undefined') { window.dash_clientside = {}; }
  if (!window.dash_clientside.onboarding) { window.dash_clientside.onboarding = {}; }
  if (!window.dash_clientside.estatehub) { window.dash_clientside.estatehub = {}; }

  var KINDS = {
    live:       { icon: '🎉', colour: '#2e9e5b', heading: 'Society is live' },
    registered: { icon: '🏢', colour: '#1d74d8', heading: 'Society registered' },
    sealed:     { icon: '🖋️', colour: '#8e44ad', heading: 'Agreement sealed' }
  };
  var COLOURS = ['#2e9e5b','#1d74d8','#f1c40f','#e74c3c','#9b59b6','#1abc9c'];

  function reducedMotion() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  function confetti() {
    if (reducedMotion()) { return; }
    var canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    canvas.style.cssText = 'position:fixed;left:0;top:0;width:100vw;height:100vh;pointer-events:none;z-index:20000';
    document.body.appendChild(canvas);
    var ctx = canvas.getContext('2d');
    var w = canvas.width = window.innerWidth, h = canvas.height = window.innerHeight;
    var particles = [];
    function burst(x, y, n) {
      for (var i = 0; i < n; i++) {
        particles.push({ x: x, y: y, vx: (Math.random() - 0.5) * 12, vy: Math.random() * -13 - 4,
                         r: Math.random() * 6 + 2, c: COLOURS[Math.floor(Math.random() * COLOURS.length)], life: 110 });
      }
    }
    burst(w / 2, h / 3, 140);
    burst(w * 0.2, h / 2, 50);
    burst(w * 0.8, h / 2, 50);
    (function draw() {
      ctx.clearRect(0, 0, w, h);
      var alive = 0;
      for (var j = 0; j < particles.length; j++) {
        var p = particles[j];
        if (p.life <= 0) { continue; }
        alive++;
        p.vy += 0.4; p.x += p.vx; p.y += p.vy; p.life -= 1;
        ctx.beginPath(); ctx.fillStyle = p.c; ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      }
      if (alive > 0) { requestAnimationFrame(draw); }
      else { try { document.body.removeChild(canvas); } catch (e) {} }
    })();
  }

  function modal(opts) {
    var spec = KINDS[opts.kind] || KINDS.live;
    var prev = document.getElementById('eh-celebrate-modal');
    if (prev) { try { document.body.removeChild(prev); } catch (e) {} }

    var overlay = document.createElement('div');
    overlay.id = 'eh-celebrate-modal';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(15,23,42,0.55);display:flex;align-items:center;' +
                            'justify-content:center;z-index:20001;padding:16px';
    var card = document.createElement('div');
    card.style.cssText = 'background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.3);max-width:440px;width:100%;' +
                         'padding:28px 28px 22px;text-align:center;border-top:6px solid ' + spec.colour;
    var icon = document.createElement('div');
    icon.style.cssText = 'font-size:56px;line-height:1;margin-bottom:8px';
    icon.textContent = spec.icon;
    var title = document.createElement('div');
    title.style.cssText = 'font-size:22px;font-weight:700;color:#1f2937;margin-bottom:6px';
    title.textContent = opts.title || spec.heading;     // textContent only: names come from user data
    card.appendChild(icon); card.appendChild(title);
    if (opts.message) {
      var msg = document.createElement('div');
      msg.style.cssText = 'font-size:14px;color:#4b5563;margin-bottom:10px';
      msg.textContent = opts.message;
      card.appendChild(msg);
    }
    if (opts.details && opts.details.length) {
      var list = document.createElement('div');
      list.style.cssText = 'text-align:left;font-size:12.5px;color:#374151;background:#f3f4f6;border-radius:8px;padding:8px 12px;margin-bottom:10px';
      opts.details.forEach(function (d) {
        var li = document.createElement('div'); li.textContent = '✓ ' + d; list.appendChild(li);
      });
      card.appendChild(list);
    }
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = 'Continue';
    btn.style.cssText = 'margin-top:6px;background:' + spec.colour + ';color:#fff;border:0;border-radius:8px;padding:9px 26px;' +
                        'font-size:14px;font-weight:600;cursor:pointer';
    function close() {
      document.removeEventListener('keydown', onKey);
      try { document.body.removeChild(overlay); } catch (e) {}
    }
    function onKey(e) { if (e.key === 'Escape' || e.key === 'Enter') { close(); } }
    btn.addEventListener('click', close);
    overlay.addEventListener('click', function (e) { if (e.target === overlay) { close(); } });
    document.addEventListener('keydown', onKey);
    card.appendChild(btn);
    overlay.appendChild(card);
    document.body.appendChild(overlay);
    try { btn.focus(); } catch (e) {}
  }

  window.EstateHubCelebrate = function (opts) {
    try {
      opts = opts || {};
      // once per browser per event when a key is given (a page reload must not celebrate again)
      if (opts.key) {
        try {
          if (window.localStorage.getItem(opts.key)) { return; }
          window.localStorage.setItem(opts.key, '1');
        } catch (e) {}
      }
      confetti();
      modal(opts);
    } catch (e) {}
  };

  // Agreement signed -> society live (existing Store-driven trigger from the onboarding hub: {key, name})
  window.dash_clientside.onboarding.celebrate = function (data) {
    var name = data && data.name ? data.name : 'Your society';
    window.EstateHubCelebrate({ kind: 'live', key: data && data.key, title: name + ' is live',
                                message: 'The Agreement is signed and sealed. Enrollment can begin.' });
    return '';
  };

  // Generic triggers: celebrate-store ({kind,title,message,details,key}) and a toast carrying a `celebrate` key
  window.dash_clientside.estatehub.celebrate = function (data) {
    if (data && data.celebrate) { data = data.celebrate; }
    else if (data && data._toast && data._toast.celebrate) { data = data._toast.celebrate; }
    else if (!data || !data.kind) { return window.dash_clientside.no_update; }
    window.EstateHubCelebrate(data);
    return window.dash_clientside.no_update;
  };
})();
