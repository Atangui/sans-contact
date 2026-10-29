/* Network witness for the demo page, in the spirit of the application's own guard
   (src/sanscontact/privacy): every attempt to open a connection is counted and shown.
   The Content-Security-Policy of index.html already blocks them; this only makes it visible.
   Loaded first, before any other script. */
(function () {
  "use strict";

  const witness = {
    attempts: 0,
    baseline: null,
    note() { this.attempts += 1; },
    /** Attempts made through the APIs below, plus resources fetched after the page has loaded. */
    count() {
      const loaded = this.baseline === null ? 0 : performance.getEntriesByType("resource").length - this.baseline;
      return this.attempts + Math.max(0, loaded);
    },
  };

  function wrapMethod(owner, name) {
    const original = owner && owner[name];
    if (typeof original !== "function") return;
    owner[name] = function (...args) {
      witness.note();
      return original.apply(this, args);
    };
  }

  function wrapConstructor(name) {
    const Original = window[name];
    if (typeof Original !== "function") return;
    const Wrapped = function (...args) {
      witness.note();
      return new Original(...args);
    };
    Wrapped.prototype = Original.prototype;
    window[name] = Wrapped;
  }

  wrapMethod(window, "fetch");
  wrapMethod(XMLHttpRequest.prototype, "open");
  wrapMethod(navigator, "sendBeacon");
  wrapConstructor("WebSocket");
  wrapConstructor("EventSource");
  document.addEventListener("securitypolicyviolation", () => witness.note());
  window.addEventListener("load", () => { witness.baseline = performance.getEntriesByType("resource").length; });

  window.SansContactNetwork = witness;
})();
