// Apply the saved theme before the page paints. A file of its own, not inline: the page allows no inline script.
try { var t = localStorage.getItem('scene.theme'); if (t === 'light' || t === 'dark') document.documentElement.dataset.theme = t; } catch (e) {}

// Motion: "full", "calm", or what this computer asks for (Windows "Show animations", macOS "Reduce motion").
// data-motion on <html> is what the styles and js/spring.js read; sceneMotion() sets it again after a change.
// The studio (data-app="studio") always moves in full: it has no Motion setting. The console keeps its own.
(function () {
  var asks = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : null;
  function set() {
    var saved = '';
    if (document.documentElement.dataset.app === 'studio') return void (document.documentElement.dataset.motion = 'full');
    try { saved = localStorage.getItem('scene.motion') || ''; } catch (e) {}
    document.documentElement.dataset.motion = saved === 'full' || saved === 'calm' ? saved : asks && asks.matches ? 'calm' : 'full';
  }
  set();
  if (asks && asks.addEventListener) asks.addEventListener('change', set);
  window.sceneMotion = set;
})();
