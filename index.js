const http = require("http");
const https = require("https");
const url = require("url");

// --- Configuration via Environment Variables ---
const PORT = process.env.PORT || 3000;
const INTERVAL_MS = (parseInt(process.env.PING_INTERVAL_MINUTES, 10) || 5) * 60 * 1000;
// Comma-separated list of URLs to ping
// e.g. PING_URLS=https://my-bot-1.ais.cloud/webhook,https://my-bot-2.ais.cloud/webhook
const PING_URLS = process.env.PING_URLS
  ? process.env.PING_URLS.split(",").map((u) => u.trim()).filter(Boolean)
  : [];

// --- HTTP Server ---
const server = http.createServer((req, res) => {
  if (req.url === "/health") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "awake", uptime: process.uptime(), targets: PING_URLS.length }));
    return;
  }

  res.writeHead(200, { "Content-Type": "text/plain" });
  res.end("never-sleep is running");
});

// --- Ping Function ---
function ping(targetUrl) {
  return new Promise((resolve) => {
    const parsed = new URL(targetUrl);
    const client = parsed.protocol === "https:" ? https : http;

    const req = client.get(targetUrl, { timeout: 15000 }, (res) => {
      res.resume(); // drain response
      console.log(`[${new Date().toISOString()}] PING ${targetUrl} -> ${res.statusCode}`);
      resolve(res.statusCode);
    });

    req.on("error", (err) => {
      console.log(`[${new Date().toISOString()}] PING ${targetUrl} -> ERROR: ${err.message}`);
      resolve(null);
    });

    req.on("timeout", () => {
      req.destroy();
      console.log(`[${new Date().toISOString()}] PING ${targetUrl} -> TIMEOUT`);
      resolve(null);
    });
  });
}

// --- Self-Ping (keep this service itself alive) ---
function selfPing() {
  const selfUrl = `http://localhost:${PORT}/health`;
  http.get(selfUrl, (res) => res.resume()).on("error", () => {});
}

// --- Main Loop ---
async function keepAlive() {
  console.log(`[${new Date().toISOString()}] Running keep-alive cycle...`);

  // Ping all target URLs in parallel
  if (PING_URLS.length > 0) {
    await Promise.all(PING_URLS.map(ping));
  }

  // Self-ping
  selfPing();
}

// --- Start ---
server.listen(PORT, () => {
  console.log(`never-sleep is running on port ${PORT}`);
  console.log(`Ping interval: ${INTERVAL_MS / 1000}s`);
  console.log(`Targets (${PING_URLS.length}): ${PING_URLS.length > 0 ? PING_URLS.join(", ") : "(none, self-ping only)"}`);

  // Run immediately, then on interval
  keepAlive();
  setInterval(keepAlive, INTERVAL_MS);
});
