import { StrictMode } from "react"
import { createRoot } from "react-dom/client"

import "./index.css"

const rootElement = document.getElementById("root")

if (rootElement === null) {
  throw new Error("The Observatory root element is missing")
}

const rootModule = import.meta.env.DEV
  ? import("./dev/development-app")
  : import("./app/production-app")

void rootModule.then(({ App }) => {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>
  )
})
