// onboarding_celebrate.js
(function(){
  if (typeof window.dash_clientside === 'undefined') {
    window.dash_clientside = {};
  }
  if (!window.dash_clientside.onboarding) {
    window.dash_clientside.onboarding = {};
  }
  window.dash_clientside.onboarding.celebrate = function(eventId) {
    try {
      if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        return;
      }
      var canvas = document.createElement('canvas');
      canvas.style.position = 'fixed';
      canvas.style.left = '0';
      canvas.style.top = '0';
      canvas.style.width = '100vw';
      canvas.style.height = '100vh';
      canvas.style.pointerEvents = 'none';
      canvas.style.zIndex = '20000';
      document.body.appendChild(canvas);
      var ctx = canvas.getContext('2d');
      var w = canvas.width = window.innerWidth;
      var h = canvas.height = window.innerHeight;
      var particles = [];
      var colors = ['#2e9e5b','#1d74d8','#f1c40f','#e74c3c','#9b59b6','#1abc9c'];
      for (var i=0;i<120;i++) {
        particles.push({
          x: w/2, y: h/3,
          vx: (Math.random()-0.5)*10,
          vy: Math.random()*-12 - 4,
          r: Math.random()*6+2,
          c: colors[Math.floor(Math.random()*colors.length)],
          life: 100
        });
      }
      function draw() {
        ctx.clearRect(0,0,w,h);
        var alive = 0;
        for (var j=0;j<particles.length;j++) {
          var p = particles[j];
          if (p.life <= 0) continue;
          alive++;
          p.vy += 0.4;
          p.x += p.vx;
          p.y += p.vy;
          p.life -= 1;
          ctx.beginPath();
          ctx.fillStyle = p.c;
          ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
          ctx.fill();
        }
        if (alive > 0) requestAnimationFrame(draw);
        else {
          try { document.body.removeChild(canvas); } catch(e){}
        }
      }
      draw();
      var card = document.createElement('div');
      card.style.position = 'fixed';
      card.style.left = '50%';
      card.style.top = '50%';
      card.style.transform = 'translate(-50%,-50%)';
      card.style.background = '#fff';
      card.style.padding = '18px 26px';
      card.style.borderRadius = '12px';
      card.style.boxShadow = '0 10px 40px rgba(0,0,0,0.2)';
      card.style.fontSize = '18px';
      card.style.fontWeight = '700';
      card.style.zIndex = '20001';
      card.textContent = '🎉 Society is live';
      document.body.appendChild(card);
      setTimeout(function(){ try { document.body.removeChild(card); } catch(e){} }, 5000);
    } catch(e) {}
  };
})();
