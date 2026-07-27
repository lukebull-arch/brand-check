import "./style.css";

// The webhook that notifies our team. Fulfilment is manual.
const WEBHOOK_URL = "REPLACE_WITH_N8N_WEBHOOK_URL";

// Free / personal domains we reject in the email gate. Extend as needed.
const FREE_EMAIL_DOMAINS = [
  "gmail.com",
  "googlemail.com",
  "outlook.com",
  "hotmail.com",
  "live.com",
  "msn.com",
  "yahoo.com",
  "yahoo.co.uk",
  "icloud.com",
  "me.com",
  "proton.me",
  "protonmail.com",
  "aol.com",
  "gmx.com",
  "gmx.co.uk",
  "mail.com",
  "yandex.com",
  "zoho.com",
];

// Standard email format check.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// SECURITY NOTE: this client holds no secret or signing key. Signature
// verification, domain re-validation and rate limiting all happen
// server-side in n8n. Nothing here is trusted by the backend.

const pageLoadedAt = Date.now();
let brandName = "";

const states = {};
document.querySelectorAll("[data-state]").forEach((el) => {
  states[el.dataset.state] = el;
});

const brandForm = document.getElementById("brand-form");
const brandInput = document.getElementById("brand-input");
const brandError = document.getElementById("brand-error");

const emailForm = document.getElementById("email-form");
const firstNameInput = document.getElementById("first-name-input");
const lastNameInput = document.getElementById("last-name-input");
const jobTitleInput = document.getElementById("job-title-input");
const emailInput = document.getElementById("email-input");
const emailError = document.getElementById("email-error");
const emailSubmit = document.getElementById("email-submit");
const honeypot = document.getElementById("company_website");

const progressBar = document.getElementById("progress-bar");
const stepEls = Array.from(document.querySelectorAll("#discovery-steps [data-step]"));

// Swap the visible state with a short fade.
function goToState(n) {
  const current = document.querySelector(".state--active");
  const next = states[String(n)];
  if (current === next) return;

  const reveal = () => {
    if (current) {
      current.classList.remove("state--active");
      current.hidden = true;
    }
    next.hidden = false;
    // Force reflow so the opacity transition runs from 0.
    void next.offsetWidth;
    next.classList.add("state--active");
  };

  if (current) {
    current.style.opacity = "0";
    setTimeout(reveal, 160);
  } else {
    reveal();
  }
}

function setBrand(name) {
  brandName = name;
  document.querySelectorAll("[data-brand]").forEach((el) => {
    el.textContent = name;
  });
}

function showError(el, message) {
  el.textContent = message;
  el.hidden = false;
}

function clearError(el) {
  el.textContent = "";
  el.hidden = true;
}

// State 1 -> 2
brandForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const value = brandInput.value.trim();
  if (!value) {
    showError(brandError, "Enter a brand name to check.");
    return;
  }
  clearError(brandError);
  setBrand(value);
  goToState(2);
  runDiscovery();
});

brandInput.addEventListener("input", () => clearError(brandError));

// State 2: theatre only. No network requests happen here.
function runDiscovery() {
  progressBar.style.width = "0";
  stepEls.forEach((el) => {
    el.removeAttribute("data-active");
    el.removeAttribute("data-done");
  });

  // Progress bar: fast start, brief pause near 70%, then complete. ~4s total.
  const keyframes = [
    { at: 40, to: 45 },
    { at: 900, to: 68 },
    { at: 1700, to: 70 }, // brief pause around 70%
    { at: 2600, to: 88 },
    { at: 3900, to: 100 },
  ];
  keyframes.forEach((k) => {
    setTimeout(() => {
      progressBar.style.transition = "width 0.6s cubic-bezier(0.4, 0, 0.2, 1)";
      progressBar.style.width = k.to + "%";
    }, k.at);
  });

  // Steps tick in sequence: spinner -> purple tick.
  const stepStart = [200, 1200, 2200, 3200];
  const stepDone = [1100, 2100, 3100, 3900];

  stepEls.forEach((el, i) => {
    setTimeout(() => el.setAttribute("data-active", ""), stepStart[i]);
    setTimeout(() => {
      el.removeAttribute("data-active");
      el.setAttribute("data-done", "");
    }, stepDone[i]);
  });

  // Move on once the theatre completes.
  setTimeout(() => goToState(3), 4200);
}

// State 3 -> 4
emailForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const firstName = firstNameInput.value.trim();
  const lastName = lastNameInput.value.trim();
  const jobTitle = jobTitleInput.value.trim();
  const email = emailInput.value.trim().toLowerCase();

  if (!firstName || !lastName || !jobTitle) {
    showError(emailError, "Fill in every field so we know who to build the report for.");
    return;
  }

  if (!EMAIL_RE.test(email)) {
    showError(emailError, "Enter a valid email address.");
    return;
  }

  const domain = email.split("@")[1];
  if (FREE_EMAIL_DOMAINS.includes(domain)) {
    showError(
      emailError,
      "That looks like a personal email. Enter your work email so we know who to build the report for."
    );
    return;
  }

  clearError(emailError);
  emailSubmit.disabled = true;
  const originalLabel = emailSubmit.textContent;
  emailSubmit.textContent = "Sending...";

  const payload = {
    brand: brandName,
    email,
    firstName,
    lastName,
    jobTitle,
    submittedAt: new Date().toISOString(),
    pageUrl: window.location.href,
    elapsedMs: Date.now() - pageLoadedAt,
    hp: honeypot ? honeypot.value : "",
  };

  try {
    const res = await fetch(WEBHOOK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("Bad response " + res.status);
    goToState(4);
  } catch (err) {
    showError(
      emailError,
      "Something went wrong on our end. Try again, or email us and we'll sort it manually."
    );
    emailSubmit.disabled = false;
    emailSubmit.textContent = originalLabel;
  }
});

[firstNameInput, lastNameInput, jobTitleInput, emailInput].forEach((el) =>
  el.addEventListener("input", () => clearError(emailError))
);

// Spinning basketball (loading screen). We model longitude seams on a sphere
// rotating about a vertical axis: each seam runs pole to pole and its sideways
// bulge is R*sin(angle). Seams on the front (cos > 0) are drawn, fading out as
// they reach the limb, so they sweep across and vanish at the edges, converging
// at the poles where the finger holds the ball. That reads as a real spin, where
// a flat image rotation just looks like tumbling.
(function initSpinball() {
  const group = document.getElementById("spinball-mer");
  if (!group) return;

  const SVG_NS = "http://www.w3.org/2000/svg";
  const CX = 60;
  const R = 54;
  const TOP_Y = CX - R; // 6
  const BOT_Y = CX + R; // 114
  const SEAMS = 8; // longitude lines around the ball
  const PERIOD_MS = 1800; // one full revolution

  const paths = [];
  for (let i = 0; i < SEAMS; i++) {
    const p = document.createElementNS(SVG_NS, "path");
    group.appendChild(p);
    paths.push(p);
  }

  function frame(angle) {
    for (let i = 0; i < SEAMS; i++) {
      const theta = angle + (i * 2 * Math.PI) / SEAMS;
      const cos = Math.cos(theta);
      const opacity = Math.min(1, Math.max(0, cos * 2.2));
      const p = paths[i];
      if (opacity <= 0.01) {
        p.setAttribute("opacity", "0");
        continue;
      }
      // Projected meridian is a half-ellipse: horizontal radius R*sin(theta),
      // vertical radius R, from top pole to bottom pole. Rounder than a parabola.
      const rx = Math.abs(R * Math.sin(theta)).toFixed(1);
      const sweep = Math.sin(theta) >= 0 ? 1 : 0;
      p.setAttribute("d", `M ${CX} ${TOP_Y} A ${rx} ${R} 0 0 ${sweep} ${CX} ${BOT_Y}`);
      p.setAttribute("opacity", opacity.toFixed(2));
      // Seams thin as they wrap toward the edge (seen more edge-on)
      p.setAttribute("stroke-width", (1.7 + 1.2 * cos).toFixed(2));
    }
  }

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    frame(0.6); // a pleasant static pose
    return;
  }

  let start = null;
  function tick(now) {
    if (start === null) start = now;
    const angle = ((now - start) / PERIOD_MS) * 2 * Math.PI;
    frame(angle);
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
})();
