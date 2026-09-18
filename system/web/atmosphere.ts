// A quiet, incomplete contour: fine fixed grain, moved as one continuous surface.
// No per-frame noise regeneration, so the texture never sparkles or crawls.
export function mountAtmosphere() {
  const canvas = document.createElement('canvas');
  canvas.className = 'atmosphere';
  canvas.setAttribute('aria-hidden', 'true');
  document.body.prepend(canvas);
  const context = canvas.getContext('2d');
  if (!context) return;
  let resizeFrame = 0;

  function draw() {
    const scale = Math.min(devicePixelRatio || 1, 1.5, 1400 / Math.max(innerWidth, innerHeight));
    const w = canvas.width = Math.ceil(innerWidth * scale);
    const h = canvas.height = Math.ceil(innerHeight * scale);
    const pixels = context!.createImageData(w, h);
    let seed = 7319;
    const random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) | 0;
      return (seed >>> 0) / 4294967296;
    };
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const u = x / w, v = y / h;
        // An off-centre, irregular enclosure suggests a place without drawing a map.
        const dx = (u - .55) / .62, dy = (v - .54) / .34;
        const angle = Math.atan2(dy, dx);
        const radius = Math.sqrt(dx * dx + dy * dy);
        const edge = .95 + .12 * Math.sin(angle * 3 + .6) + .055 * Math.cos(angle * 5 - .8);
        const distance = radius - edge;
        const width = .09 + .045 * (1 + Math.sin(angle * 2 - .4));
        const core = Math.exp(-Math.pow(distance / width, 2));
        const dust = Math.exp(-Math.pow((distance - .05) / .3, 2));
        // Leave gaps and a large quiet centre; nothing competes with the TD screen.
        const fragments = Math.pow(.5 + .5 * Math.sin(angle * 2.4 + .8), 2);
        const fade = Math.min(1, Math.max(0, (v - .12) / .12), Math.max(0, (.96 - v) / .12));
        const presence = (.4 + fragments * .6) * fade;
        const density = (core * .7 + dust * .16) * presence;
        const grain = random();
        const i = (y * w + x) * 4;
        pixels.data[i] = 194;
        pixels.data[i + 1] = 218;
        pixels.data[i + 2] = 255;
        // A soft body remains visible between the fine dither grains.
        const body = (core * .19 + dust * .065) * presence;
        const fleck = grain < density ? .18 + random() * .32 : 0;
        pixels.data[i + 3] = Math.min(190, 255 * (body + fleck));
      }
    }
    context!.putImageData(pixels, 0, 0);
  }
  draw();
  window.addEventListener('resize', () => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(draw);
  });
  document.addEventListener('visibilitychange', () => {
    canvas.style.animationPlayState = document.hidden ? 'paused' : 'running';
  });
}
