/**
 * Returns a debounced function that delays invocation until after `ms` milliseconds
 * have elapsed since the last call.
 */
export function debounce(fn, ms) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), ms);
  };
}
