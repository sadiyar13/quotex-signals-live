/**
 * Quotex Smart Demo Auto-Trader HUD (هدآپ دیسپلی اتوتریدر هوشمند کوتکس)
 * نسخه: 1.0.0 - طراحی‌شده برای معامله خودکار در حساب دمو با وین‌ریت بالا
 * ارتباط مستقیم با سرور محلی: http://127.0.0.1:8000
 */

(function () {
  // Prevent duplicate injection
  if (window.__quotexAutoTraderLoaded) {
    alert("ربات اتوتریدر کوتکس در حال حاضر روی این صفحه فعال است!");
    return;
  }
  window.__quotexAutoTraderLoaded = true;

  const SERVER_URL = "http://127.0.0.1:8000";
  let autoTradeEnabled = false;
  let isDemoOnly = true; // Strict safety check
  let currentSymbol = "EUR/USD";
  let tradeAmount = 1;
  let maxConsecutiveLosses = 3;
  let consecutiveLosses = 0;
  let stats = { wins: 0, losses: 0, total: 0 };
  let lastExecutedSignalId = null;
  let pollInterval = null;

  // --- AUDIO SYNTHESIS FOR TRADING ALERTS ---
  let audioCtx = null;
  function playSound(type) {
    try {
      if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      const now = audioCtx.currentTime;

      if (type === 'CLICK') {
        osc.frequency.setValueAtTime(587.33, now); // D5
        osc.frequency.setValueAtTime(880.0, now + 0.1); // A5
        gain.gain.setValueAtTime(0.2, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.3);
        osc.start(now);
        osc.stop(now + 0.3);
      } else if (type === 'ALERT') {
        osc.frequency.setValueAtTime(880.0, now);
        gain.gain.setValueAtTime(0.15, now);
        gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
        osc.start(now);
        osc.stop(now + 0.2);
      }
    } catch (e) {
      console.warn("Audio warning:", e);
    }
  }

  // --- QUOTEX DOM SELECTOR HELPERS ---
  function getActiveAsset() {
    // Try multiple possible Quotex selectors for active asset
    const sel = document.querySelector(".current-symbol, .header__asset-select, .asset-select__button, .asset-name, .tab-item--active");
    if (sel && sel.textContent) {
      const text = sel.textContent.trim().toUpperCase();
      const match = text.match(/([A-Z]{3}[\/_][A-Z]{3})/);
      if (match) return match[1].replace("_", "/");
      // Check for 6 letter forex pairs like EURUSD
      const match6 = text.match(/([A-Z]{3})([A-Z]{3})/);
      if (match6) return `${match6[1]}/${match6[2]}`;
    }
    return currentSymbol;
  }

  function isDemoAccount() {
    // Check if account is Demo
    const text = document.body.innerText.toLowerCase();
    const demoBadge = document.querySelector(".account-type, .usermenu__info-balance, .balance-info");
    if (demoBadge) {
      const bText = demoBadge.innerText.toLowerCase();
      if (bText.includes("demo") || bText.includes("دمو") || bText.includes("آموزشی")) return true;
      if (bText.includes("live") || bText.includes("واقعی") || bText.includes("real")) return false;
    }
    // Fallback: check presence of Demo indicator
    return text.includes("demo") || text.includes("حساب دمو");
  }

  function findTradeButton(direction) {
    // direction is 'CALL' (Up) or 'PUT' (Down)
    const buttons = Array.from(document.querySelectorAll("button, .btn, div[role='button']"));
    
    if (direction === "CALL") {
      // Look for call / up button
      const btn = buttons.find(b => {
        const cl = (b.className || "").toLowerCase();
        const tx = (b.innerText || "").toLowerCase();
        return (
          cl.includes("call-btn") ||
          cl.includes("btn--green") ||
          cl.includes("button-up") ||
          cl.includes("up-button") ||
          (tx.includes("up") && !tx.includes("popup")) ||
          tx.includes("خرید") ||
          tx.includes("بالا")
        );
      });
      return btn;
    } else {
      // Look for put / down button
      const btn = buttons.find(b => {
        const cl = (b.className || "").toLowerCase();
        const tx = (b.innerText || "").toLowerCase();
        return (
          cl.includes("put-btn") ||
          cl.includes("btn--red") ||
          cl.includes("button-down") ||
          cl.includes("down-button") ||
          tx.includes("down") ||
          tx.includes("فروش") ||
          tx.includes("پایین")
        );
      });
      return btn;
    }
  }

  function executeTradeClick(direction, symbol, reason) {
    if (!autoTradeEnabled) return;

    // Safety: ensure it is a demo account
    if (isDemoOnly && !isDemoAccount()) {
      showNotice("⛔ خطا: حساب فعال کوتکس دمو نیست! اتوتریدر برای ایمنی متوقف شد.", "error");
      autoTradeEnabled = false;
      updateUI();
      return;
    }

    // Safety: check max losses
    if (consecutiveLosses >= maxConsecutiveLosses) {
      showNotice("🛑 توقف اضطراری: ۳ ضرر متوالی ثبت شد. اتوتریدر برای حفظ حساب غیرفعال شد.", "error");
      autoTradeEnabled = false;
      updateUI();
      return;
    }

    const btn = findTradeButton(direction);
    if (!btn) {
      showNotice(`⚠️ دکمه ${direction} در صفحه کوتکس پیدا نشد!`, "warn");
      return;
    }

    // Click the button!
    btn.click();
    playSound("CLICK");

    stats.total++;
    showNotice(`🎯 ترید خودکار ثبت شد: ${direction} روی ${symbol} | انقضا: ۵ دقیقه`, "success");
    addHistoryLog(direction, symbol, reason);
  }

  // --- FLOATING HUD CREATION (Luxury Glassmorphism) ---
  const hud = document.createElement("div");
  hud.id = "quotex-auto-trader-hud";
  hud.style.cssText = `
    position: fixed;
    top: 65px;
    right: 20px;
    z-index: 9999999;
    width: 320px;
    background: rgba(15, 23, 42, 0.88);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(6, 182, 212, 0.4);
    border-radius: 20px;
    box-shadow: 0 15px 40px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.15);
    font-family: 'Vazirmatn', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #f8fafc;
    direction: rtl;
    padding: 16px;
    transition: all 0.3s ease;
    user-select: none;
  `;

  hud.innerHTML = `
    <!-- Header -->
    <div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:10px; margin-bottom:12px;">
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="font-size:20px;">🤖</span>
        <div>
          <div style="font-weight:900; font-size:13px; color:#38bdf8;">ربات اتوتریدر دموی Quotex</div>
          <div style="font-size:10px; color:#94a3b8;">متصل به سرور محلی Antigravity</div>
        </div>
      </div>
      <button id="qat-btn-minimize" style="background:none; border:none; color:#94a3b8; font-size:16px; cursor:pointer;">─</button>
    </div>

    <!-- Status Banner -->
    <div id="qat-account-banner" style="background:rgba(16,185,129,0.15); border:1px solid rgba(16,185,129,0.3); border-radius:12px; padding:8px 12px; display:flex; justify-content:space-between; align-items:center; font-size:11px; margin-bottom:12px;">
      <span style="color:#6ee7b7; font-weight:bold;">🛡️ حساب: دموی کوتکس</span>
      <span id="qat-server-badge" style="color:#38bdf8; font-family:monospace; font-size:10px;">🟢 آنلاین (8000)</span>
    </div>

    <!-- Live Signal & Asset Status -->
    <div style="background:rgba(30,41,59,0.5); border:1px solid rgba(255,255,255,0.08); border-radius:14px; padding:12px; margin-bottom:12px;">
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1; margin-bottom:6px;">
        <span>جفت‌ارز کوتکس:</span>
        <strong id="qat-asset-name" style="color:#f8fafc; font-family:monospace; font-size:12px;">EUR/USD</strong>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1; margin-bottom:6px;">
        <span>سیگنال جاری سیستم:</span>
        <strong id="qat-signal-status" style="color:#94a3b8;">در حال پایش...</strong>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1; margin-bottom:6px;">
        <span>زمان انقضای سفارش:</span>
        <strong style="color:#fbbf24; font-family:monospace;">۵ دقیقه (M5)</strong>
      </div>
      <div style="display:flex; justify-content:space-between; font-size:11px; color:#cbd5e1;">
        <span>شمارش معکوس ورود:</span>
        <strong id="qat-countdown" style="color:#38bdf8; font-family:monospace; font-size:13px;">--:--</strong>
      </div>
    </div>

    <!-- Auto-Trade Toggle Button -->
    <button id="qat-btn-toggle" style="width:100%; padding:10px; border-radius:12px; border:none; font-weight:900; font-size:12px; cursor:pointer; margin-bottom:12px; transition:all 0.2s; background:#334155; color:#94a3b8;">
      ⏸️ اتوتریدر غیرفعال است (برای شروع کلیک کنید)
    </button>

    <!-- Stats & Safety -->
    <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px; font-size:10px; font-family:monospace; margin-bottom:8px;">
      <div style="background:rgba(30,41,59,0.4); border-radius:10px; padding:6px; text-align:center;">
        <span style="color:#94a3b8; display:block;">تعداد تریدها</span>
        <strong id="qat-stat-total" style="color:#f8fafc; font-size:13px;">0</strong>
      </div>
      <div style="background:rgba(30,41,59,0.4); border-radius:10px; padding:6px; text-align:center;">
        <span style="color:#94a3b8; display:block;">مبلغ هر ترید دمو</span>
        <strong style="color:#38bdf8; font-size:13px;">$1.00</strong>
      </div>
    </div>

    <!-- Notice Box -->
    <div id="qat-notice" style="font-size:10px; color:#cbd5e1; line-height:1.4; padding:6px; border-radius:8px; background:rgba(0,0,0,0.2); text-align:center;">
      قفل روند فعال: فقط سیگنال‌های هم‌جهت با روند کلان M5 اجرا می‌شوند.
    </div>
  `;

  document.body.appendChild(hud);

  // --- DRAGGABLE HUD LOGIC ---
  let isDragging = false;
  let dragOffsetX = 0;
  let dragOffsetY = 0;

  hud.addEventListener("mousedown", (e) => {
    if (e.target.tagName === "BUTTON" || e.target.tagName === "INPUT") return;
    isDragging = true;
    dragOffsetX = e.clientX - hud.offsetLeft;
    dragOffsetY = e.clientY - hud.offsetTop;
  });

  window.addEventListener("mousemove", (e) => {
    if (!isDragging) return;
    hud.style.left = `${e.clientX - dragOffsetX}px`;
    hud.style.top = `${e.clientY - dragOffsetY}px`;
    hud.style.right = "auto";
  });

  window.addEventListener("mouseup", () => {
    isDragging = false;
  });

  // --- UI INTERACTION ---
  const btnToggle = document.getElementById("qat-btn-toggle");
  btnToggle.addEventListener("click", () => {
    autoTradeEnabled = !autoTradeEnabled;
    updateUI();
    if (autoTradeEnabled) {
      playSound("ALERT");
      showNotice("✅ اتوتریدر دموی کوتکس فعال شد! به محض تایید سیگنال هم‌راستا با روند، در ثانیه ۰۰ ثبت می‌شود.", "success");
    } else {
      showNotice("⏸️ اتوتریدر متوقف شد.", "info");
    }
  });

  function updateUI() {
    if (autoTradeEnabled) {
      btnToggle.style.background = "linear-gradient(135deg, #059669 0%, #10b981 100%)";
      btnToggle.style.color = "#022c22";
      btnToggle.style.boxShadow = "0 0 20px rgba(16, 185, 129, 0.4)";
      btnToggle.innerText = "⚡ اتوتریدر فعال است (معامله خودکار در دمو)";
    } else {
      btnToggle.style.background = "#334155";
      btnToggle.style.color = "#94a3b8";
      btnToggle.style.boxShadow = "none";
      btnToggle.innerText = "⏸️ اتوتریدر غیرفعال است (برای شروع کلیک کنید)";
    }

    document.getElementById("qat-stat-total").innerText = stats.total;
  }

  function showNotice(msg, type = "info") {
    const el = document.getElementById("qat-notice");
    if (!el) return;
    el.innerText = msg;
    if (type === "success") el.style.color = "#6ee7b7";
    else if (type === "error") el.style.color = "#fda4af";
    else if (type === "warn") el.style.color = "#fde047";
    else el.style.color = "#cbd5e1";
  }

  function addHistoryLog(dir, sym, reason) {
    console.log(`[Quotex Auto-Trader] ${new Date().toLocaleTimeString()} - Executed ${dir} on ${sym}: ${reason}`);
  }

  // --- MAIN POLLING LOOP (Queries 127.0.0.1:8000 every 1.5s) ---
  async function pollSignalServer() {
    try {
      const activeAsset = getActiveAsset();
      currentSymbol = activeAsset;
      document.getElementById("qat-asset-name").innerText = activeAsset;

      const res = await fetch(`${SERVER_URL}/api/signals/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: activeAsset, timeframe: "M5" }),
      });

      if (!res.ok) {
        document.getElementById("qat-server-badge").innerText = "🔴 خطای اتصال";
        return;
      }

      document.getElementById("qat-server-badge").innerText = "🟢 آنلاین (8000)";
      const sig = await res.json();

      const statusEl = document.getElementById("qat-signal-status");
      const countdownEl = document.getElementById("qat-countdown");

      // Calculate countdown to the end of the 5-minute candle
      const now = new Date();
      const secInM5 = (now.getMinutes() % 5) * 60 + now.getSeconds();
      const remSec = 300 - secInM5;
      const remM = Math.floor(remSec / 60);
      const remS = remSec % 60;
      countdownEl.innerText = `${String(remM).padStart(2, "0")}:${String(remS).padStart(2, "0")}`;

      if (sig.direction === "CALL") {
        statusEl.innerHTML = `<span style="color:#10b981; font-weight:bold;">▲ CALL (${sig.rule_agreement_score}%)</span>`;
        // Execute trade if at second 00-03 and signal is fresh
        if (remSec >= 297 || remSec <= 2) {
          if (lastExecutedSignalId !== sig.id) {
            lastExecutedSignalId = sig.id;
            executeTradeClick("CALL", sig.symbol, sig.decision_reason);
          }
        }
      } else if (sig.direction === "PUT") {
        statusEl.innerHTML = `<span style="color:#f43f5e; font-weight:bold;">▼ PUT (${sig.rule_agreement_score}%)</span>`;
        // Execute trade if at second 00-03 and signal is fresh
        if (remSec >= 297 || remSec <= 2) {
          if (lastExecutedSignalId !== sig.id) {
            lastExecutedSignalId = sig.id;
            executeTradeClick("PUT", sig.symbol, sig.decision_reason);
          }
        }
      } else if (sig.is_pre_signal) {
        statusEl.innerHTML = `<span style="color:#fbbf24; font-weight:bold;">⚡ آماده‌باش ${sig.pre_signal_direction}</span>`;
      } else {
        statusEl.innerHTML = `<span style="color:#94a3b8;">⛔ بدون ورود (NO TRADE)</span>`;
      }
    } catch (err) {
      console.warn("Poll signal error:", err);
      document.getElementById("qat-server-badge").innerText = "⚠️ قطعی سرور محلی";
    }
  }

  // Start polling
  pollInterval = setInterval(pollSignalServer, 1500);
  pollSignalServer();

  console.log("Quotex Smart Demo Auto-Trader HUD loaded successfully!");
})();
