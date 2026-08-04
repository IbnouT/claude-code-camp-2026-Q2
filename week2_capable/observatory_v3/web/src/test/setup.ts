import "@testing-library/jest-dom/vitest"

Object.defineProperty(window, "scrollTo", {
  configurable: true,
  value: () => {},
})

// jsdom has no EventSource; notification streams need a quiet stand-in.
if (typeof globalThis.EventSource === "undefined") {
  class TestEventSource {
    addEventListener(): void {}
    removeEventListener(): void {}
    close(): void {}
  }
  Object.defineProperty(globalThis, "EventSource", {
    configurable: true,
    value: TestEventSource,
  })
}
