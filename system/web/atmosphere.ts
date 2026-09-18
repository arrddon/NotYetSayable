// A small, decorative canvas keeps the grain stable while the ribbons drift.
export function mountAtmosphere() {
  const canvas = document.createElement('canvas');
  canvas.className = 'atmosphere';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const context = canvas.getContext('2d');
  if (!context) return;
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  let frame = 0;
  let last = 0;
  let time = 0;
  let grain: Float32Array;
  function resize() {
    canvas.width = Math.min(300, Math.ceil(innerWidth / 3));
    canvas.height = Math.min(400, Math.ceil(innerHeight / 3));
    grain = Float32Array.from({ length: canvas.width * canvas.height }, () => Math.random());
    draw();
  }
  function draw() {
    const w = canvas.width, h = canvas.height;
    const pixels = context!.createImageData(w, h);
    for (let x = 0; x < w; x++) {
      const u = x / w;
      const upper = .23 + .15 * Math.sin(u * 3.8 + time);
      const lower = .78 + .17 * Math.sin(u * 4.2 - time * .7 + 1.4);
      for (let y = 0; y < h; y++) {
        const distance = Math.min(Math.abs(y / h - upper), Math.abs(y / h - lower));
        const density = Math.exp(-Math.pow(distance / .034, 2)) * .62;
        const i = y * w + x;
        pixels.data[i * 4] = 210;
        pixels.data[i * 4 + 1] = 223;
        pixels.data[i * 4 + 2] = 255;
        pixels.data[i * 4 + 3] = grain[i] < density ? 66 : 0;
      }
    }
    context!.putImageData(pixels, 0, 0);
  }
  function animate(now: number) {
    if (now - last >= 100) {
      time += Math.min(now - last, 150) / 24000;
      last = now;
      draw();
    }
    frame = requestAnimationFrame(animate);
  }
  function sync() {
    cancelAnimationFrame(frame);
    last = performance.now();
    if (!motion.matches && !document.hidden) frame = requestAnimationFrame(animate);
    else draw();
  }
  resize();
  sync();
  window.addEventListener('resize', resize);
  motion.addEventListener('change', sync);
  document.addEventListener('visibilitychange', sync);
}
