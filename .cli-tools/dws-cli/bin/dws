#!/usr/bin/env node

"use strict";

const fs = require("fs");
const path = require("path");
const childProcess = require("child_process");

const binaryPath = path.join(__dirname, "..", "vendor", process.platform === "win32" ? "dws.exe" : "dws");

if (!fs.existsSync(binaryPath)) {
  console.error(`dws binary not found at ${binaryPath}. Reinstall the package.`);
  process.exit(1);
}

const result = childProcess.spawnSync(binaryPath, process.argv.slice(2), {
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status === null ? 1 : result.status);
