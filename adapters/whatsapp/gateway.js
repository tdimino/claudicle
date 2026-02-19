#!/usr/bin/env node
/**
 * Claudicle WhatsApp Gateway — Baileys
 *
 * Lightweight Node.js gateway that connects to WhatsApp Web via Baileys
 * (linked device, QR code pairing). Incoming messages are written to
 * daemon/inbox.jsonl in the shared Claudicle format. Outbound messages
 * are accepted via an Express HTTP server on POST /send.
 *
 * Ported from TinyClaw patterns, adapted for Baileys + Claudicle inbox.
 */

const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion } = require("@whiskeysockets/baileys");
const express = require("express");
const fs = require("fs");
const path = require("path");
const qrcode = require("qrcode-terminal");

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const GATEWAY_PORT   = parseInt(process.env.WHATSAPP_GATEWAY_PORT || "3847", 10);
const AUTH_DIR       = path.join(__dirname, "auth_info");
const PID_FILE       = path.join(__dirname, "..", "..", "daemon", "whatsapp-gateway.pid");
const LOG_FILE       = path.join(__dirname, "..", "..", "daemon", "logs", "whatsapp.log");

// Inbox path — daemon/inbox.jsonl (shared with Slack listener)
const INBOX_FILE     = path.join(__dirname, "..", "..", "daemon", "inbox.jsonl");

// Security
const ALLOWED_SENDERS = (process.env.WHATSAPP_ALLOWED_SENDERS || "")
    .split(",").map(s => s.trim()).filter(Boolean);
const RATE_LIMIT      = parseInt(process.env.WHATSAPP_RATE_LIMIT || "10", 10);
const RATE_WINDOW_MS  = 60_000; // 1 minute

// ---------------------------------------------------------------------------
// Logging
// ---------------------------------------------------------------------------

function ensureDir(filePath) {
    const dir = path.dirname(filePath);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function log(level, message) {
    const ts = new Date().toISOString();
    const line = `[${ts}] [${level}] ${message}`;
    console.log(line);
    ensureDir(LOG_FILE);
    fs.appendFileSync(LOG_FILE, line + "\n");
}

// ---------------------------------------------------------------------------
// Rate Limiting (per-sender, ported from TinyClaw)
// ---------------------------------------------------------------------------

const rateLimits = new Map();

function isRateLimited(senderId) {
    if (RATE_LIMIT <= 0) return false;
    const now = Date.now();
    let entry = rateLimits.get(senderId);

    if (!entry || now - entry.windowStart > RATE_WINDOW_MS) {
        rateLimits.set(senderId, { count: 1, windowStart: now });
        return false;
    }

    entry.count++;
    return entry.count > RATE_LIMIT;
}

// ---------------------------------------------------------------------------
// Phone Normalization
// ---------------------------------------------------------------------------

function jidToPhone(jid) {
    // Baileys JIDs: "15551234567@s.whatsapp.net"
    const num = (jid || "").split("@")[0];
    return num.startsWith("+") ? num : "+" + num;
}

function phoneToJid(phone) {
    const num = phone.replace(/[^0-9]/g, "");
    return num + "@s.whatsapp.net";
}

// ---------------------------------------------------------------------------
// Message Deduplication
// ---------------------------------------------------------------------------

const processedMessages = new Set();
const MAX_DEDUP = 1000;

function isDuplicate(msgId) {
    if (processedMessages.has(msgId)) return true;
    processedMessages.add(msgId);
    if (processedMessages.size > MAX_DEDUP) {
        const first = processedMessages.values().next().value;
        processedMessages.delete(first);
    }
    return false;
}

// ---------------------------------------------------------------------------
// Inbox Writer — append to daemon/inbox.jsonl
// ---------------------------------------------------------------------------

function writeToInbox(entry) {
    ensureDir(INBOX_FILE);
    fs.appendFileSync(INBOX_FILE, JSON.stringify(entry) + "\n");
}

// ---------------------------------------------------------------------------
// Baileys Connection
// ---------------------------------------------------------------------------

let sock = null;

async function startSocket() {
    ensureDir(AUTH_DIR + "/dummy");
    const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
    const { version } = await fetchLatestBaileysVersion();

    sock = makeWASocket({
        version,
        auth: state,
        printQRInTerminal: false, // We handle QR display ourselves
        logger: require("pino")({ level: "silent" }),
    });

    // --- QR Code ---
    sock.ev.on("connection.update", (update) => {
        const { connection, lastDisconnect, qr } = update;

        if (qr) {
            log("INFO", "Scan this QR code with WhatsApp:");
            console.log();
            qrcode.generate(qr, { small: true });
            console.log();
            log("INFO", "Open WhatsApp → Settings → Linked Devices → Link a Device");
        }

        if (connection === "close") {
            const code = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = code !== DisconnectReason.loggedOut;
            log("WARN", `Connection closed (code ${code}). ${shouldReconnect ? "Reconnecting..." : "Logged out — delete auth_info/ and re-pair."}`);
            if (shouldReconnect) {
                sock.ev.removeAllListeners();
                setTimeout(startSocket, 3000);
            } else {
                process.exit(1);
            }
        }

        if (connection === "open") {
            log("INFO", "WhatsApp connected and ready!");
        }
    });

    // --- Auth Credential Updates ---
    sock.ev.on("creds.update", saveCreds);

    // --- Incoming Messages ---
    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        if (type !== "notify") return;

        for (const msg of messages) {
            try {
                await handleIncoming(msg);
            } catch (err) {
                log("ERROR", `Message handling error: ${err.message}`);
            }
        }
    });
}

// ---------------------------------------------------------------------------
// Incoming Message Handler
// ---------------------------------------------------------------------------

async function handleIncoming(msg) {
    const msgId = msg.key.id;

    // Skip self-sent messages
    if (msg.key.fromMe) return;

    // Skip non-individual chats (groups)
    if (msg.key.remoteJid.endsWith("@g.us")) return;

    // Deduplication
    if (isDuplicate(msgId)) return;

    // Extract text (conversation = plain text, extendedTextMessage = quoted/link preview)
    const text = msg.message?.conversation
        || msg.message?.extendedTextMessage?.text
        || "";
    if (!text.trim()) return;

    const phone = jidToPhone(msg.key.remoteJid);
    const pushName = msg.pushName || phone;

    // Allowlist check — secure default: reject all if list is empty
    if (ALLOWED_SENDERS.length === 0) {
        log("WARN", `Rejected (no allowlist configured): ${phone}`);
        return;
    }
    if (!ALLOWED_SENDERS.includes(phone)) {
        log("WARN", `Blocked non-allowlisted sender: ${phone}`);
        return;
    }

    // Rate limiting
    if (isRateLimited(phone)) {
        log("WARN", `Rate limited: ${phone}`);
        return;
    }

    log("INFO", `Message from ${pushName} (${phone}): ${text.substring(0, 80)}`);

    // Write to shared inbox in Claudicle format
    const entry = {
        ts:           Date.now() / 1000,
        channel:      `whatsapp:${phone}`,
        thread_ts:    `whatsapp:${phone}`,   // WhatsApp DMs are single-threaded
        user_id:      phone,
        display_name: pushName,
        text:         text,
        handled:      false,
    };

    writeToInbox(entry);
    log("INFO", `Queued to inbox: ${phone} → "${text.substring(0, 50)}"`);
}

// ---------------------------------------------------------------------------
// Express HTTP Server — POST /send for outbound messages
// ---------------------------------------------------------------------------

const app = express();
app.use(express.json());

app.post("/send", async (req, res) => {
    const { phone, text } = req.body;
    if (!phone || !text) {
        return res.status(400).json({ error: "Missing 'phone' or 'text'" });
    }
    if (!sock) {
        return res.status(503).json({ error: "WhatsApp not connected" });
    }

    // Validate phone is on allowlist (if configured)
    const normalized = phone.startsWith("+") ? phone : "+" + phone.replace(/[^0-9]/g, "");
    if (ALLOWED_SENDERS.length > 0 && !ALLOWED_SENDERS.includes(normalized)) {
        log("WARN", `Blocked outbound to non-allowlisted number: ${phone}`);
        return res.status(403).json({ error: "Recipient not on allowlist" });
    }

    try {
        const jid = phoneToJid(phone);
        await sock.sendMessage(jid, { text });
        log("INFO", `Sent to ${phone}: ${text.substring(0, 80)}`);
        res.json({ ok: true, phone, length: text.length });
    } catch (err) {
        log("ERROR", `Send failed to ${phone}: ${err.message}`);
        res.status(500).json({ error: err.message });
    }
});

app.get("/health", (req, res) => {
    const connected = sock?.ws?.readyState === 1;
    res.json({
        status: connected ? "connected" : "disconnected",
        uptime: process.uptime(),
        allowedSenders: ALLOWED_SENDERS.length,
        rateLimit: RATE_LIMIT,
    });
});

// ---------------------------------------------------------------------------
// PID File
// ---------------------------------------------------------------------------

function writePidFile() {
    ensureDir(PID_FILE);
    fs.writeFileSync(PID_FILE, String(process.pid));
}

function removePidFile() {
    try { fs.unlinkSync(PID_FILE); } catch {}
}

// ---------------------------------------------------------------------------
// Graceful Shutdown
// ---------------------------------------------------------------------------

async function shutdown(signal) {
    log("INFO", `Shutting down (${signal})...`);
    removePidFile();
    if (sock) {
        try { sock.end(undefined); } catch {}
    }
    process.exit(0);
}

process.on("SIGINT",  () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

(async () => {
    log("INFO", `Claudicle WhatsApp Gateway starting on port ${GATEWAY_PORT}`);
    log("INFO", `Allowed senders: ${ALLOWED_SENDERS.length > 0 ? ALLOWED_SENDERS.join(", ") : "(none — will reject all)"}`);
    log("INFO", `Rate limit: ${RATE_LIMIT} msgs/min per sender`);

    writePidFile(); // Write PID immediately so --status works during connection

    app.listen(GATEWAY_PORT, () => {
        log("INFO", `HTTP server listening on :${GATEWAY_PORT}`);
    });

    await startSocket();
})();
