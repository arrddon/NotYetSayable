// Keep the waiting period independent of disabled/busy/network state.
export function revealButtonAfterDelay(node: HTMLElement) {
  node.inert = true;
  node.dataset.reveal = 'waiting';
  node.addEventListener('click', (event) => {
    if (node.inert) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, { capture: true });
  window.setTimeout(() => {
    if (!node.isConnected) return;
    node.inert = false;
    node.dataset.reveal = 'ready';
  }, 3000);
}
