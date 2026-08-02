const expectedNode = "24.18.0"
const expectedNpm = "11.16.0"
const userAgent = process.env.npm_config_user_agent ?? ""
const npmMatch = /(?:^|\s)npm\/(?<version>[^\s]+)/u.exec(userAgent)
const activeNode = process.versions.node
const activeNpm = npmMatch?.groups?.version

if (activeNode !== expectedNode) {
  throw new Error(
    `Node ${expectedNode} is required, active version is ${activeNode}. Run nvm use.`
  )
}

if (activeNpm !== expectedNpm) {
  throw new Error(
    `npm ${expectedNpm} is required, active version is ${activeNpm ?? "unknown"}.`
  )
}

console.log(`Runtime matches Node ${activeNode} and npm ${activeNpm}.`)
