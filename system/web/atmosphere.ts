// The density field changes shape; the canvas and its grain never rotate or move.
export function mountAtmosphere() {
  const canvas = document.createElement('canvas');
  canvas.className = 'atmosphere';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const context = canvas.getContext('2d');
  if (!context) return;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const bins = 1024;
  const edges = new Float32Array(bins);
  const widths = new Float32Array(bins);
  const strengths = new Float32Array(bins);
  let radius: Float32Array, angles: Uint16Array, grain: Float32Array, fade: Float32Array;
  let pixels: ImageData;
  let frame = 0, resizeFrame = 0, last = 0, time = 0;

  function resize() {
    const scale = Math.min(1, 720 / Math.max(innerWidth, innerHeight));
    const w = canvas.width = Math.ceil(innerWidth * scale);
    const h = canvas.height = Math.ceil(innerHeight * scale);
    const count = w * h;
    pixels = context!.createImageData(w, h);
    radius = new Float32Array(count);
    angles = new Uint16Array(count);
    grain = new Float32Array(count);
    fade = new Float32Array(count);
    let seed = 7319;
    for (let i = 0; i < count; i++) {
      const u = (i % w) / w, v = Math.floor(i / w) / h;
      const dx = (u - .55) / .62, dy = (v - .54) / .34;
      radius[i] = Math.hypot(dx, dy);
      angles[i] = Math.min(bins - 1, Math.floor((Math.atan2(dy, dx) + Math.PI) / (2 * Math.PI) * bins));
      seed = (Math.imul(seed, 1664525) + 1013904223) | 0;
      grain[i] = (seed >>> 0) / 4294967296;
      fade[i] = Math.min(1, Math.max(0, (v - .12) / .12), Math.max(0, (.96 - v) / .12));
      pixels.data[i * 4] = 194;
      pixels.data[i * 4 + 1] = 218;
      pixels.data[i * 4 + 2] = 255;
    }
    draw();
  }
  function draw() {
    // Standing modes expand different parts independently, with no rigid rotation.
    const a = Math.sin(time * .43), b = Math.sin(time * .31 + 1.2);
    const c = Math.sin(time * .57 + .4);
    for (let j = 0; j < bins; j++) {
      const angle = j / bins * Math.PI * 2 - Math.PI;
      edges[j] = .93 + .18 * Math.sin(angle * 2 + .6) * a
        + .12 * Math.cos(angle * 3 - .8) * b + .07 * Math.sin(angle * 5) * c;
      widths[j] = .1 + .055 * (1 + Math.sin(angle * 3 + .4) * b);
      strengths[j] = .42 + .58 * Math.pow(.5 + .5 * Math.sin(angle * 2.4 + .8 + c * .7), 2);
    }
    for (let i = 0; i < radius.length; i++) {
      const j = angles[i], distance = radius[i] - edges[j];
      const core = Math.exp(-Math.pow(distance / widths[j], 2));
      const dust = Math.exp(-Math.pow((distance - .05) / .3, 2));
      const presence = strengths[j] * fade[i];
      const density = (core * .7 + dust * .16) * presence;
      // Smooth activation of fixed grains avoids binary flicker as the field evolves.
      const activation = Math.min(1, Math.max(0, (density - grain[i]) * 10 + .5));
      const fleck = activation * activation * (3 - 2 * activation) * (.2 + grain[i] * .3);
      pixels.data[i * 4 + 3] = Math.min(190, 255 * ((core * .19 + dust * .065) * presence + fleck));
    }
    context!.putImageData(pixels, 0, 0);
  }
  function animate(now: number) {
    if (now - last >= 1000 / 24) {
      time += Math.min(now - last, 100) / 1000;
      last = now;
      draw();
    }
    frame = requestAnimationFrame(animate);
  }
  function sync() {
    cancelAnimationFrame(frame);
    last = performance.now();
    if (!document.hidden && !motion.matches) frame = requestAnimationFrame(animate);
  }
  resize();
  sync();
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(resize);
  });
  motion.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync);
}
