/**
 * Cropin Automation Launcher Widget
 * -----------------------------------
 * Drop this script into your friend's website and call CropinLauncher.init()
 * to render a "Launch Cropin Automation" button anywhere on the page.
 *
 * Quick start (add to friend's HTML):
 *
 *   <script src="http://localhost:4445/widget.js"></script>
 *   <div id="cropin-btn"></div>
 *   <script>
 *     CropinLauncher.init({ container: '#cropin-btn' });
 *   </script>
 */

(function (global) {
  "use strict";

  // -------------------------------------------------------------------------
  // Default config – override via CropinLauncher.init(options)
  // -------------------------------------------------------------------------
  const DEFAULTS = {
    launcherUrl: "http://localhost:4445",   // where launcher.py runs
    appUrl: "http://localhost:4444",        // where the main app runs
    container: "#cropin-launcher",          // CSS selector or DOM element
    buttonText: "Launch Cropin Automation",
    buttonStyle: {                          // inline CSS for the button
      padding: "12px 24px",
      fontSize: "15px",
      fontWeight: "600",
      color: "#ffffff",
      background: "#1976d2",
      border: "none",
      borderRadius: "6px",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: "8px",
      transition: "background 0.2s",
    },
    pollInterval: 1500,   // ms between status polls
    openInNewTab: true,   // open the app in a new browser tab
  };

  // -------------------------------------------------------------------------
  // Internal state
  // -------------------------------------------------------------------------
  let cfg = {};
  let btn = null;
  let statusLabel = null;
  let pollTimer = null;
  let launching = false;

  // -------------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------------

  function applyStyles(el, styles) {
    Object.assign(el.style, styles);
  }

  function setButtonState(state) {
    // state: 'idle' | 'launching' | 'running' | 'error'
    const map = {
      idle: {
        text: cfg.buttonText,
        bg: "#1976d2",
        disabled: false,
        status: "",
      },
      launching: {
        text: "Starting…",
        bg: "#1565c0",
        disabled: true,
        status: "Starting Cropin Automation, please wait…",
      },
      running: {
        text: "Open Cropin Automation",
        bg: "#388e3c",
        disabled: false,
        status: "App is running",
      },
      error: {
        text: cfg.buttonText,
        bg: "#c62828",
        disabled: false,
        status: "Failed to start – check that the launcher is running.",
      },
    };

    const s = map[state] || map.idle;
    btn.textContent = s.text;
    btn.style.background = s.bg;
    btn.disabled = s.disabled;
    if (statusLabel) statusLabel.textContent = s.status;
  }

  // -------------------------------------------------------------------------
  // API calls
  // -------------------------------------------------------------------------

  async function fetchStatus() {
    try {
      const res = await fetch(`${cfg.launcherUrl}/api/status`, {
        method: "GET",
        signal: AbortSignal.timeout(3000),
      });
      return res.ok ? res.json() : null;
    } catch {
      return null;
    }
  }

  async function requestLaunch() {
    try {
      const res = await fetch(`${cfg.launcherUrl}/api/launch`, {
        method: "POST",
        signal: AbortSignal.timeout(70000), // 60s app start + buffer
      });
      return res.ok ? res.json() : null;
    } catch {
      return null;
    }
  }

  // -------------------------------------------------------------------------
  // Polling – keep button in sync with actual app state
  // -------------------------------------------------------------------------

  function startPolling() {
    if (pollTimer) return;
    pollTimer = setInterval(async () => {
      if (launching) return; // don't interfere mid-launch
      const data = await fetchStatus();
      if (data && data.running) {
        setButtonState("running");
      } else if (data) {
        setButtonState("idle");
      }
      // If launcher itself is unreachable, leave current state alone
    }, cfg.pollInterval);
  }

  // -------------------------------------------------------------------------
  // Button click handler
  // -------------------------------------------------------------------------

  async function handleClick() {
    if (launching) return;

    // If already running, just open the app
    const status = await fetchStatus();
    if (status && status.running) {
      openApp();
      return;
    }

    launching = true;
    setButtonState("launching");

    const result = await requestLaunch();

    launching = false;

    if (result && (result.status === "launched" || result.status === "already_running")) {
      setButtonState("running");
      openApp();
    } else {
      setButtonState("error");
      // Reset to idle after 4 seconds so user can retry
      setTimeout(() => setButtonState("idle"), 4000);
    }
  }

  function openApp() {
    const url = cfg.appUrl;
    if (cfg.openInNewTab) {
      window.open(url, "_blank", "noopener,noreferrer");
    } else {
      window.location.href = url;
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  function render(container) {
    const wrapper = document.createElement("div");
    wrapper.style.display = "inline-block";

    // The button
    btn = document.createElement("button");
    applyStyles(btn, cfg.buttonStyle);
    btn.textContent = cfg.buttonText;
    btn.setAttribute("type", "button");
    btn.addEventListener("click", handleClick);

    // Hover effect
    btn.addEventListener("mouseenter", () => {
      if (!btn.disabled) btn.style.filter = "brightness(1.1)";
    });
    btn.addEventListener("mouseleave", () => {
      btn.style.filter = "";
    });

    // Status line below button
    statusLabel = document.createElement("div");
    applyStyles(statusLabel, {
      fontSize: "12px",
      color: "#555",
      marginTop: "6px",
      minHeight: "16px",
    });

    wrapper.appendChild(btn);
    wrapper.appendChild(statusLabel);
    container.appendChild(wrapper);
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  const CropinLauncher = {
    /**
     * Initialise and render the launcher button.
     *
     * @param {object} options - Override any DEFAULTS key.
     */
    init(options = {}) {
      cfg = Object.assign({}, DEFAULTS, options, {
        buttonStyle: Object.assign({}, DEFAULTS.buttonStyle, options.buttonStyle),
      });

      // Resolve container
      let container =
        typeof cfg.container === "string"
          ? document.querySelector(cfg.container)
          : cfg.container;

      if (!container) {
        console.warn("[CropinLauncher] Container not found:", cfg.container);
        return;
      }

      render(container);

      // Immediately check status and start polling
      fetchStatus().then((data) => {
        if (data && data.running) setButtonState("running");
      });
      startPolling();
    },
  };

  global.CropinLauncher = CropinLauncher;
})(window);
