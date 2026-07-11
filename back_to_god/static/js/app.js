const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

document.querySelectorAll("[data-copy]").forEach((button) => {
  const original = button.innerHTML;

  button.addEventListener("click", async () => {
    const value = button.dataset.copy;
    if (!value) return;

    try {
      await navigator.clipboard.writeText(value);
      button.textContent = "Copied";
      window.setTimeout(() => {
        button.innerHTML = original;
      }, 1500);
    } catch {
      button.textContent = "Select text";
    }
  });
});

document.querySelectorAll("[data-print-page]").forEach((button) => {
  button.addEventListener("click", () => window.print());
});

document.querySelectorAll("[data-safe-back]").forEach((button) => {
  button.addEventListener("click", () => {
    const fallbackUrl = button.dataset.fallbackUrl || "/";
    const hasSameOriginReferrer = document.referrer && document.referrer.startsWith(window.location.origin);
    if (window.history.length > 1 && hasSameOriginReferrer) {
      window.history.back();
      window.setTimeout(() => {
        if (document.visibilityState === "visible") {
          window.location.assign(fallbackUrl);
        }
      }, 700);
      return;
    }
    window.location.assign(fallbackUrl);
  });
});

let activeConfirmResolve = null;
let activeTextResolve = null;

function closeConfirmModal(modal, confirmed) {
  if (!modal || !activeConfirmResolve) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  activeConfirmResolve(Boolean(confirmed));
  activeConfirmResolve = null;
}

function ensureConfirmModal() {
  let modal = document.querySelector("[data-confirm-modal]");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.className = "confirm-modal hidden";
  modal.dataset.confirmModal = "1";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = `
    <section class="confirm-panel" role="document">
      <span class="confirm-icon material-symbols-rounded">warning</span>
      <div class="grid gap-1">
        <strong data-confirm-title>Confirm action</strong>
        <p data-confirm-message>This action needs confirmation.</p>
      </div>
      <div class="confirm-actions">
        <button class="material-button material-button-tonal" type="button" data-confirm-cancel>
          <span class="material-symbols-rounded text-[20px]">close</span>
          <span>Cancel</span>
        </button>
        <button class="material-button material-button-filled danger-action" type="button" data-confirm-accept>
          <span class="material-symbols-rounded text-[20px]">check</span>
          <span>Confirm</span>
        </button>
      </div>
    </section>
  `;
  document.body.appendChild(modal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.closest("[data-confirm-cancel]")) {
      closeConfirmModal(modal, false);
    }
    if (event.target.closest("[data-confirm-accept]")) {
      closeConfirmModal(modal, true);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) {
      closeConfirmModal(modal, false);
    }
  });

  return modal;
}

function openConfirmModal(message, options = {}) {
  const modal = ensureConfirmModal();
  if (activeConfirmResolve) {
    closeConfirmModal(modal, false);
  }

  modal.querySelector("[data-confirm-title]").textContent = options.title || "Confirm action";
  modal.querySelector("[data-confirm-message]").textContent = message || "Continue?";
  const accept = modal.querySelector("[data-confirm-accept]");
  accept.querySelector("span:last-child").textContent = options.confirmLabel || "Confirm";
  accept.classList.toggle("danger-action", options.danger !== false);

  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");

  return new Promise((resolve) => {
    activeConfirmResolve = resolve;
    window.requestAnimationFrame(() => accept.focus({ preventScroll: true }));
  });
}

function closeTextModal(modal, value) {
  if (!modal || !activeTextResolve) return;
  modal.classList.add("hidden");
  modal.setAttribute("aria-hidden", "true");
  activeTextResolve(value);
  activeTextResolve = null;
}

function ensureTextModal() {
  let modal = document.querySelector("[data-text-modal]");
  if (modal) return modal;

  modal = document.createElement("div");
  modal.className = "confirm-modal hidden";
  modal.dataset.textModal = "1";
  modal.setAttribute("role", "dialog");
  modal.setAttribute("aria-modal", "true");
  modal.setAttribute("aria-hidden", "true");
  modal.innerHTML = `
    <section class="confirm-panel text-modal-panel" role="document">
      <span class="confirm-icon material-symbols-rounded">edit</span>
      <div class="grid gap-2">
        <strong data-text-modal-title>Edit</strong>
        <textarea class="material-field text-modal-input" data-text-modal-input maxlength="900"></textarea>
      </div>
      <div class="confirm-actions">
        <button class="material-button material-button-tonal" type="button" data-text-modal-cancel>
          <span class="material-symbols-rounded text-[20px]">close</span>
          <span>Cancel</span>
        </button>
        <button class="material-button material-button-filled" type="button" data-text-modal-save>
          <span class="material-symbols-rounded text-[20px]">save</span>
          <span>Save</span>
        </button>
      </div>
    </section>
  `;
  document.body.appendChild(modal);

  modal.addEventListener("click", (event) => {
    if (event.target === modal || event.target.closest("[data-text-modal-cancel]")) {
      closeTextModal(modal, null);
    }
    if (event.target.closest("[data-text-modal-save]")) {
      closeTextModal(modal, modal.querySelector("[data-text-modal-input]").value);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.classList.contains("hidden")) {
      closeTextModal(modal, null);
    }
  });

  return modal;
}

function openTextModal(title, value = "") {
  const modal = ensureTextModal();
  if (activeTextResolve) {
    closeTextModal(modal, null);
  }

  modal.querySelector("[data-text-modal-title]").textContent = title || "Edit";
  const input = modal.querySelector("[data-text-modal-input]");
  input.value = value;
  modal.classList.remove("hidden");
  modal.setAttribute("aria-hidden", "false");

  return new Promise((resolve) => {
    activeTextResolve = resolve;
    window.requestAnimationFrame(() => {
      input.focus({ preventScroll: true });
      input.setSelectionRange(input.value.length, input.value.length);
    });
  });
}

document.querySelectorAll(".app-menu").forEach((menu) => {
  document.addEventListener("click", (event) => {
    if (!menu.open || menu.contains(event.target)) return;
    menu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      menu.open = false;
    }
  });
});

const themeCookieName = "btg_theme";
const themeCookieMaxAge = 60 * 60 * 24 * 365;

function setCookieTheme(theme) {
  document.cookie = `${themeCookieName}=${theme}; path=/; max-age=${themeCookieMaxAge}; SameSite=Lax`;
}

function updateThemeButtons(theme) {
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    const isDark = theme === "dark";
    const icon = button.querySelector(".theme-toggle-icon");

    button.setAttribute("aria-label", isDark ? "Switch to light mode" : "Switch to dark mode");
    button.setAttribute("title", isDark ? "Switch to light mode" : "Switch to dark mode");
    button.dataset.themeCurrent = theme;

    if (icon) {
      icon.textContent = isDark ? "light_mode" : "dark_mode";
    }
  });
}

function applyTheme(theme, persist = true) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;

  const themeColor = document.querySelector('meta[name="theme-color"]');
  if (themeColor) {
    themeColor.setAttribute("content", theme === "dark" ? "#07110d" : "#101812");
  }

  if (persist) {
    setCookieTheme(theme);
  }

  updateThemeButtons(theme);
}

const initialTheme = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
applyTheme(initialTheme, false);

document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
    applyTheme(current === "dark" ? "light" : "dark");
  });
});

const scrollControls = document.querySelector("[data-scroll-controls]");
const scrollButtons = document.querySelectorAll("[data-scroll-target]");

function maxScrollY() {
  return Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
}

function updateScrollControls() {
  if (!scrollControls) return;
  const maxY = maxScrollY();
  const currentY = window.scrollY || document.documentElement.scrollTop || 0;

  scrollControls.classList.toggle("is-short-page", maxY < 120);
  scrollControls.classList.toggle("is-at-top", currentY <= 28);
  scrollControls.classList.toggle("is-at-bottom", maxY - currentY <= 28);
}

let scrollTicking = false;
function scheduleScrollUpdate() {
  if (scrollTicking) return;
  scrollTicking = true;
  window.requestAnimationFrame(() => {
    updateScrollControls();
    scrollTicking = false;
  });
}

scrollButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const target = button.dataset.scrollTarget;
    window.scrollTo({
      top: target === "bottom" ? maxScrollY() : 0,
      behavior: prefersReducedMotion ? "auto" : "smooth",
    });
  });
});

window.addEventListener("scroll", scheduleScrollUpdate, { passive: true });
window.addEventListener("resize", scheduleScrollUpdate, { passive: true });
updateScrollControls();

function onlyDigits(value) {
  return (value || "").replace(/\D/g, "");
}

function luhnValid(value) {
  let total = 0;
  const reversed = value.split("").reverse();
  reversed.forEach((character, index) => {
    let digit = Number(character);
    if (index % 2 === 1) {
      digit *= 2;
      if (digit > 9) digit -= 9;
    }
    total += digit;
  });
  return total % 10 === 0;
}

function dobFromSaId(value) {
  const digits = onlyDigits(value).slice(0, 13);
  if (digits.length !== 13 || !luhnValid(digits)) return "";

  const yy = Number(digits.slice(0, 2));
  const mm = Number(digits.slice(2, 4));
  const dd = Number(digits.slice(4, 6));
  const currentYear = new Date().getFullYear() % 100;
  const fullYear = (yy > currentYear ? 1900 : 2000) + yy;
  const date = new Date(Date.UTC(fullYear, mm - 1, dd));

  if (
    date.getUTCFullYear() !== fullYear ||
    date.getUTCMonth() !== mm - 1 ||
    date.getUTCDate() !== dd
  ) {
    return "";
  }

  return `${fullYear}-${String(mm).padStart(2, "0")}-${String(dd).padStart(2, "0")}`;
}

function ageLabelFromDob(value) {
  if (!value) return "Not added";
  const [year, month, day] = value.slice(0, 10).split("-").map(Number);
  if (!year || !month || !day) return "Not added";
  const today = new Date();
  let age = today.getFullYear() - year;
  const birthdayPassed =
    today.getMonth() + 1 > month ||
    (today.getMonth() + 1 === month && today.getDate() >= day);
  if (!birthdayPassed) age -= 1;
  return age >= 0 ? `${age} years` : "Not added";
}

document.querySelectorAll("[data-id-number]").forEach((input) => {
  const dobTarget = document.querySelector(input.dataset.dobTarget);
  const ageTarget = input.dataset.ageTarget ? document.querySelector(input.dataset.ageTarget) : null;
  const syncDob = () => {
    input.value = onlyDigits(input.value).slice(0, 13);
    const dob = dobFromSaId(input.value);
    if (dobTarget && (input.value || dob)) dobTarget.value = dob;
    if (ageTarget) ageTarget.value = ageLabelFromDob(dob || dobTarget?.value || "");
    input.setCustomValidity(input.value && !dob ? "Enter a valid 13-digit South African ID number." : "");
  };

  input.addEventListener("input", syncDob);
  dobTarget?.addEventListener("change", syncDob);
  syncDob();
});

document.querySelectorAll("[data-identity-type]").forEach((select) => {
  const form = select.closest("form");
  if (!form) return;
  const saInput = form.querySelector('input[name="id_number"]');
  const foreignInput = form.querySelector('input[name="foreign_id_number"]');
  const nationalityInput = form.querySelector('input[name="nationality"]');
  const dobInput = form.querySelector('input[name="date_of_birth"]');
  const ageInput = form.querySelector("[data-age-target]")
    ? document.querySelector(form.querySelector("[data-age-target]").dataset.ageTarget)
    : form.querySelector('input[id$="_age"]');
  const saLabel = saInput?.closest("label");
  const foreignLabel = foreignInput?.closest("label");

  const syncIdentityFields = () => {
    const isForeign = select.value === "foreign";
    saLabel?.classList.toggle("identity-hidden", isForeign);
    foreignLabel?.classList.toggle("identity-hidden", !isForeign);

    if (saInput) {
      saInput.disabled = isForeign;
      if (isForeign) {
        saInput.value = "";
        saInput.setCustomValidity("");
      }
    }
    if (foreignInput) {
      foreignInput.disabled = !isForeign;
      if (!isForeign) foreignInput.value = "";
    }
    if (nationalityInput) {
      nationalityInput.readOnly = !isForeign;
      if (!isForeign) nationalityInput.value = "South Africa";
      if (isForeign && nationalityInput.value === "South Africa") nationalityInput.value = "";
    }
    if (dobInput) {
      dobInput.readOnly = !isForeign;
      if (!isForeign && saInput) {
        const dob = dobFromSaId(saInput.value);
        if (dob) dobInput.value = dob;
      }
    }
    if (ageInput && dobInput) {
      ageInput.value = ageLabelFromDob(dobInput.value);
    }
  };

  select.addEventListener("change", syncIdentityFields);
  saInput?.addEventListener("input", syncIdentityFields);
  dobInput?.addEventListener("change", syncIdentityFields);
  syncIdentityFields();
});

const passwordInput = document.querySelector("[data-password-strength]");
const passwordRules = document.querySelector("[data-password-rules]");

if (passwordInput && passwordRules) {
  const rules = {
    length: (value) => value.length >= 8,
    upper: (value) => /[A-Z]/.test(value),
    lower: (value) => /[a-z]/.test(value),
    number: (value) => /\d/.test(value),
    symbol: (value) => /[^A-Za-z0-9]/.test(value),
  };

  passwordInput.addEventListener("input", () => {
    Object.entries(rules).forEach(([rule, test]) => {
      passwordRules.querySelector(`[data-rule="${rule}"]`)?.classList.toggle("valid", test(passwordInput.value));
    });
  });
}

const motionTargets = document.querySelectorAll(
  [
    ".section-heading",
    ".landing-intro-card",
    ".vision-row",
    ".scripture-panel",
    ".pillar-grid article",
    ".schedule-card",
    ".app-feature-panel",
    ".remember-option",
    ".auth-card",
    ".message-list-item",
  ].join(",")
);

if (!prefersReducedMotion && "IntersectionObserver" in window) {
  motionTargets.forEach((element, index) => {
    element.classList.add("motion-ready");
    element.style.transitionDelay = `${Math.min(index % 6, 5) * 35}ms`;
  });

  const motionObserver = new IntersectionObserver(
    (entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("motion-visible");
        observer.unobserve(entry.target);
      });
    },
    { rootMargin: "0px 0px -10% 0px", threshold: 0.1 }
  );

  motionTargets.forEach((element) => motionObserver.observe(element));
} else {
  motionTargets.forEach((element) => element.classList.add("motion-visible"));
}

const profileInput = document.querySelector("[data-profile-input]");
const profilePreview = document.querySelector("[data-profile-preview]");
const profileFallback = document.querySelector("[data-profile-fallback]");
let activeProfilePreviewUrl = null;

if (profileInput && profilePreview) {
  profileInput.addEventListener("change", () => {
    const file = profileInput.files && profileInput.files[0];
    if (!file) return;

    if (activeProfilePreviewUrl) {
      URL.revokeObjectURL(activeProfilePreviewUrl);
    }

    activeProfilePreviewUrl = URL.createObjectURL(file);
    profilePreview.src = activeProfilePreviewUrl;
    profilePreview.classList.remove("hidden");

    if (profileFallback) {
      profileFallback.classList.add("hidden");
    }
  });
}

function updateBadge(selector, value) {
  document.querySelectorAll(selector).forEach((badge) => {
    badge.textContent = value;
    badge.classList.toggle("hidden", Number(value) <= 0);
  });
}

async function pollNotifications() {
  if (!document.querySelector("[data-notification-count], [data-message-count]")) return;
  try {
    const response = await fetch("/notifications/poll", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const payload = await response.json();
    updateBadge("[data-notification-count]", payload.unread || 0);
    updateBadge("[data-message-count]", payload.unreadMessages || 0);
  } catch {
    // Polling is best-effort; the app still works without it.
  }
}

async function pingPresence() {
  if (!csrfToken) return;
  try {
    await fetch("/messages/presence", {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        Accept: "application/json",
      },
    });
  } catch {
    // Presence quietly retries on the next interval.
  }
}

if (document.body && csrfToken) {
  let notificationTimer = null;
  const scheduleNotificationPoll = (delay = document.hidden ? 14000 : 5000) => {
    window.clearTimeout(notificationTimer);
    notificationTimer = window.setTimeout(async () => {
      await pollNotifications();
      scheduleNotificationPoll();
    }, delay);
  };

  window.setInterval(pingPresence, 25000);
  pollNotifications();
  scheduleNotificationPoll();
  document.addEventListener("visibilitychange", () => scheduleNotificationPoll(1200));
}

const protectedFinance = document.querySelector("[data-protected-finance]");

if (protectedFinance) {
  document.body.classList.add("finance-protected-active");
  document.body.dataset.financeWatermark = protectedFinance.dataset.watermark || "Back to God AOG";
  protectedFinance.addEventListener("contextmenu", (event) => event.preventDefault());
  document.addEventListener("keydown", (event) => {
    const key = event.key.toLowerCase();
    if (key === "printscreen") {
      document.body.classList.add("finance-capture-warning");
      window.setTimeout(() => document.body.classList.remove("finance-capture-warning"), 1800);
    }
  });
}

function refreshFinanceEmptyState() {
  const empty = document.querySelector("[data-finance-empty]");
  if (!empty) return;
  const visibleSlips = [...document.querySelectorAll("[data-finance-slip]")].filter(
    (item) => !item.classList.contains("hidden")
  );
  empty.classList.toggle("hidden", visibleSlips.length > 0);
}

document.querySelectorAll("[data-finance-slip][data-visible-until]").forEach((item) => {
  if (item.dataset.financeHideOnExpiry !== "1" || !item.dataset.visibleUntil) return;
  const expiry = new Date(item.dataset.visibleUntil).getTime();
  if (Number.isNaN(expiry)) return;
  const hideSlip = () => {
    item.remove();
    refreshFinanceEmptyState();
  };
  const delay = expiry - Date.now();
  if (delay <= 0) {
    hideSlip();
  } else {
    window.setTimeout(hideSlip, Math.min(delay, 2147483647));
  }
});

refreshFinanceEmptyState();

function initAudienceControls(root = document) {
  root.querySelectorAll("[data-audience-control]").forEach((control) => {
    if (control.dataset.audienceReady === "1") return;
    control.dataset.audienceReady = "1";
    const picker = control.querySelector("[data-audience-picker]");
    const choices = control.querySelectorAll("[data-audience-choice]");
    const search = control.querySelector("[data-audience-search]");
    const syncAudience = () => {
      const selected = control.querySelector("[data-audience-choice]:checked")?.value || "everyone";
      picker?.classList.toggle("is-hidden", selected !== "specific");
      picker?.querySelectorAll('input[type="checkbox"]').forEach((checkbox) => {
        checkbox.disabled = selected !== "specific";
      });
    };

    choices.forEach((choice) => choice.addEventListener("change", syncAudience));
    search?.addEventListener("input", () => {
      const query = (search.value || "").trim().toLowerCase();
      control.querySelectorAll("[data-audience-user]").forEach((item) => {
        item.classList.toggle("hidden", query && !item.dataset.searchText.includes(query));
      });
    });
    syncAudience();
  });
}

function initTimelineEditControls(root = document) {
  root.querySelectorAll("[data-timeline-edit-toggle]").forEach((button) => {
    if (button.dataset.timelineEditReady === "1") return;
    button.dataset.timelineEditReady = "1";
    button.addEventListener("click", () => {
      const panel = document.getElementById(button.getAttribute("aria-controls"));
      if (!panel) return;
      const willOpen = panel.classList.contains("hidden");
      panel.classList.toggle("hidden", !willOpen);
      button.setAttribute("aria-expanded", willOpen ? "true" : "false");
      if (willOpen) {
        if (!prefersReducedMotion) {
          panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
        panel.querySelector('input[name="title"]')?.focus({ preventScroll: true });
      }
    });
  });

  root.querySelectorAll("[data-timeline-edit-cancel]").forEach((button) => {
    if (button.dataset.timelineCancelReady === "1") return;
    button.dataset.timelineCancelReady = "1";
    button.addEventListener("click", () => {
      const panel = button.closest("[data-timeline-edit-form]");
      if (!panel) return;
      panel.classList.add("hidden");
      document
        .querySelector(`[data-timeline-edit-toggle][aria-controls="${panel.id}"]`)
        ?.setAttribute("aria-expanded", "false");
    });
  });
}

function initFinanceEditControls(root = document) {
  root.querySelectorAll("[data-finance-edit-toggle]").forEach((button) => {
    if (button.dataset.financeEditReady === "1") return;
    button.dataset.financeEditReady = "1";
    button.addEventListener("click", () => {
      const panel = document.getElementById(button.getAttribute("aria-controls"));
      if (!panel) return;
      const willOpen = panel.classList.contains("hidden");
      panel.classList.toggle("hidden", !willOpen);
      button.setAttribute("aria-expanded", willOpen ? "true" : "false");
      if (willOpen) {
        if (!prefersReducedMotion) {
          panel.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
        panel.querySelector('input[name="title"]')?.focus({ preventScroll: true });
      }
    });
  });

  root.querySelectorAll("[data-finance-edit-cancel]").forEach((button) => {
    if (button.dataset.financeCancelReady === "1") return;
    button.dataset.financeCancelReady = "1";
    button.addEventListener("click", () => {
      const panel = button.closest("[data-finance-edit-form]");
      if (!panel) return;
      panel.classList.add("hidden");
      document
        .querySelector(`[data-finance-edit-toggle][aria-controls="${panel.id}"]`)
        ?.setAttribute("aria-expanded", "false");
    });
  });
}

initAudienceControls();
initTimelineEditControls();
initFinanceEditControls();

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-confirm-action]");
  if (!form) return;
  if (form.dataset.confirmed === "1") {
    delete form.dataset.confirmed;
    return;
  }
  event.preventDefault();
  const message = form.dataset.confirmAction || "Continue?";
  const confirmed = await openConfirmModal(message, {
    title: "Please confirm",
    confirmLabel: "Continue",
  });
  if (confirmed) {
    form.dataset.confirmed = "1";
    form.requestSubmit();
  }
});

function liveFragmentHasDraft(fragment) {
  const activeElement = document.activeElement;
  if (!activeElement || !fragment.contains(activeElement)) return false;
  if (!["INPUT", "TEXTAREA", "SELECT"].includes(activeElement.tagName)) return false;
  return Boolean(activeElement.value && String(activeElement.value).trim());
}

function initLiveFragments(root = document) {
  root.querySelectorAll("[data-live-fragment]").forEach((fragment) => {
    if (fragment.dataset.liveFragmentReady === "1") return;
    fragment.dataset.liveFragmentReady = "1";

    const poll = async () => {
      if (!document.body.contains(fragment)) return;
      let delay = document.hidden ? 30000 : 8000;
      if (liveFragmentHasDraft(fragment)) {
        window.setTimeout(poll, delay);
        return;
      }

      try {
        const url = new URL(fragment.dataset.liveFragmentUrl, window.location.origin);
        const currentUrl = new URL(window.location.href);
        currentUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value));
        url.searchParams.set("since", fragment.dataset.liveLatest || "");
        const response = await fetch(url, { headers: { Accept: "application/json" } });
        if (response.ok) {
          const payload = await response.json();
          if (payload.latestUpdate) fragment.dataset.liveLatest = payload.latestUpdate;
          if (payload.changed && payload.html) {
            fragment.insertAdjacentHTML("beforebegin", payload.html);
            const replacement = fragment.previousElementSibling;
            fragment.remove();
            if (replacement?.matches("[data-live-fragment]")) {
              initLiveFragments(document);
            }
            return;
          }
        }
      } catch {
        delay = 16000;
      }
      window.setTimeout(poll, delay);
    };

    window.setTimeout(poll, document.hidden ? 30000 : 8000);
  });
}

initLiveFragments();
document.addEventListener("visibilitychange", () => initLiveFragments());

let timelineFeed = document.querySelector("[data-timeline-feed]");

function timelineFeedHasDraft() {
  if (!timelineFeed) return false;
  const activeElement = document.activeElement;
  if (!activeElement || !timelineFeed.contains(activeElement)) return false;
  if (!["INPUT", "TEXTAREA"].includes(activeElement.tagName)) return false;
  return Boolean(activeElement.value && activeElement.value.trim());
}

async function pollTimelineFeed() {
  if (!timelineFeed?.dataset.timelinePollUrl) return;
  if (timelineFeedHasDraft()) return;

  const url = new URL(timelineFeed.dataset.timelinePollUrl, window.location.origin);
  url.searchParams.set("q", timelineFeed.dataset.timelineQuery || "");
  url.searchParams.set("since", timelineFeed.dataset.timelineLatest || "");

  try {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const payload = await response.json();
    if (!payload.changed) {
      if (payload.latestUpdate) timelineFeed.dataset.timelineLatest = payload.latestUpdate;
      return;
    }
    if (payload.html) {
      timelineFeed.insertAdjacentHTML("beforebegin", payload.html);
      const replacement = timelineFeed.previousElementSibling;
      timelineFeed.remove();
      timelineFeed = replacement?.matches("[data-timeline-feed]") ? replacement : document.querySelector("[data-timeline-feed]");
      if (timelineFeed && payload.latestUpdate) {
        timelineFeed.dataset.timelineLatest = payload.latestUpdate;
      }
      if (timelineFeed) {
        initAudienceControls(timelineFeed);
        initTimelineEditControls(timelineFeed);
      }
    }
  } catch {
    // Timeline polling resumes on the next interval.
  }
}

if (timelineFeed) {
  window.setInterval(pollTimelineFeed, 4500);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) pollTimelineFeed();
  });
}

document.addEventListener("submit", async (event) => {
  const form = event.target.closest("[data-timeline-like-form]");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector("[data-timeline-like-button]");
  const count = form.querySelector("[data-timeline-like-count]");
  try {
    const response = await fetch(form.action, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        Accept: "application/json",
      },
      body: new FormData(form),
    });
    if (!response.ok) return;
    const payload = await response.json();
    button?.classList.toggle("active", Boolean(payload.liked));
    if (count) count.textContent = payload.count;
    if (payload.latestUpdate && timelineFeed) {
      timelineFeed.dataset.timelineLatest = payload.latestUpdate;
    }
  } catch {
    // Like/unlike can be retried by the user.
  }
});

const chatThread = document.querySelector("[data-chat-thread]");

if (chatThread) {
  const messagesContainer = chatThread.querySelector("[data-chat-messages]");
  const form = chatThread.querySelector("[data-chat-form]");
  const presenceLabel = chatThread.querySelector("[data-chat-presence]");
  const imageInput = chatThread.querySelector("[data-chat-image-input]");
  const videoInput = chatThread.querySelector("[data-chat-video-input]");
  const fileInput = chatThread.querySelector("[data-chat-file-input]");
  const imageButton = chatThread.querySelector("[data-chat-image-button]");
  const videoButton = chatThread.querySelector("[data-chat-video-button]");
  const fileButton = chatThread.querySelector("[data-chat-file-button]");
  const voiceButton = chatThread.querySelector("[data-chat-voice-button]");
  const voiceCancel = chatThread.querySelector("[data-chat-voice-cancel]");
  const voiceStatus = chatThread.querySelector("[data-chat-voice-status]");
  const actionPopover = chatThread.querySelector("[data-chat-action-popover]");
  let lastMessageId = 0;
  let lastChangeAt = "";
  let voiceRecorder = null;
  let voiceChunks = [];
  let cancelVoiceSend = false;
  let activeActionMessage = null;
  let longPressTimer = null;
  let longPressStart = null;
  let suppressNextMessageClick = false;
  const longPressDelay = 520;

  messagesContainer?.querySelectorAll("[data-message-id]").forEach((item) => {
    lastMessageId = Math.max(lastMessageId, Number(item.dataset.messageId || 0));
    if (item.dataset.messageUpdated && item.dataset.messageUpdated > lastChangeAt) {
      lastChangeAt = item.dataset.messageUpdated;
    }
  });

  function chatIsNearEnd() {
    if (!messagesContainer) return true;
    return messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < 120;
  }

  function scrollChatToEnd() {
    if (messagesContainer) {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
  }

  function formatMessageTime(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(undefined, {
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(date);
  }

  function clearLongPressTimer() {
    window.clearTimeout(longPressTimer);
    longPressTimer = null;
    longPressStart = null;
  }

  function messageHasActions(item) {
    return (
      item.dataset.messageCanEdit === "1" ||
      item.dataset.messageCanDelete === "1" ||
      Boolean(item.dataset.attachmentDeleteUrl)
    );
  }

  function hideChatActionPopover() {
    activeActionMessage?.classList.remove("action-open");
    activeActionMessage = null;
    if (!actionPopover) return;
    actionPopover.classList.add("hidden");
    actionPopover.setAttribute("aria-hidden", "true");
    actionPopover.innerHTML = "";
  }

  function buildChatAction(action, icon, label, danger = false) {
    const button = document.createElement("button");
    button.className = `chat-action-button${danger ? " danger" : ""}`;
    button.type = "button";
    button.dataset.chatAction = action;
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.innerHTML = `<span class="material-symbols-rounded">${icon}</span>`;
    return button;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(value, max));
  }

  function showChatActionPopover(item) {
    if (!actionPopover || !messageHasActions(item)) return;
    clearLongPressTimer();
    hideChatActionPopover();
    activeActionMessage = item;

    if (item.dataset.messageCanEdit === "1") {
      actionPopover.appendChild(buildChatAction("edit", "edit", "Edit message"));
    }
    if (item.dataset.attachmentDeleteUrl) {
      actionPopover.appendChild(buildChatAction("deleteAttachment", "attach_file", "Delete attachment", true));
    }
    if (item.dataset.messageCanDelete === "1") {
      actionPopover.appendChild(buildChatAction("delete", "delete", "Delete message", true));
    }

    if (!actionPopover.children.length) return;
    item.classList.add("action-open");
    actionPopover.classList.remove("hidden");
    actionPopover.setAttribute("aria-hidden", "false");
    suppressNextMessageClick = true;

    const shellRect = chatThread.getBoundingClientRect();
    const itemRect = item.getBoundingClientRect();
    const popoverRect = actionPopover.getBoundingClientRect();
    const top = clamp(
      itemRect.top - shellRect.top + (itemRect.height - popoverRect.height) / 2,
      8,
      chatThread.clientHeight - popoverRect.height - 8
    );
    let left = item.classList.contains("mine")
      ? itemRect.left - shellRect.left - popoverRect.width - 8
      : itemRect.right - shellRect.left + 8;

    if (left < 8 || left + popoverRect.width > chatThread.clientWidth - 8) {
      left = clamp(
        itemRect.left - shellRect.left,
        8,
        chatThread.clientWidth - popoverRect.width - 8
      );
    }

    actionPopover.style.top = `${top}px`;
    actionPopover.style.left = `${left}px`;
  }

  async function editChatMessage(item) {
    const bodyElement = item.querySelector("[data-message-body]");
    const currentBody = bodyElement?.textContent || "";
    const nextBody = await openTextModal("Edit message", currentBody);
    if (nextBody === null || !nextBody.trim()) return;
    try {
      const response = await fetch(item.dataset.messageEditUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          Accept: "application/json",
        },
        body: JSON.stringify({ body: nextBody.trim() }),
      });
      if (!response.ok) return;
      if (bodyElement) bodyElement.textContent = nextBody.trim();
      item.dataset.messageCanEdit = "1";
      item.querySelector("[data-message-edited]")?.remove();
      const time = item.querySelector("[data-message-time]");
      if (time) {
        const edited = document.createElement("span");
        edited.dataset.messageEdited = "1";
        edited.textContent = " edited";
        time.after(edited);
      }
    } catch {
      // The edit can be retried by the user.
    }
  }

  async function deleteChatMessage(item) {
    const confirmed = await openConfirmModal("Delete this message?", {
      title: "Delete message",
      confirmLabel: "Delete",
    });
    if (!confirmed) return;
    try {
      const response = await fetch(item.dataset.messageDeleteUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
          Accept: "application/json",
        },
      });
      if (!response.ok) return;
      markMessageDeleted(item);
    } catch {
      // The delete can be retried by the user.
    }
  }

  async function deleteChatAttachment(item) {
    if (!item.dataset.attachmentDeleteUrl) return;
    const confirmed = await openConfirmModal("Delete this attachment?", {
      title: "Delete attachment",
      confirmLabel: "Delete",
    });
    if (!confirmed) return;
    try {
      const response = await fetch(item.dataset.attachmentDeleteUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
          Accept: "application/json",
        },
      });
      if (!response.ok) return;
      item
        .querySelectorAll(".chat-media-link, .chat-attachment-link, .chat-image, .chat-audio, .chat-video")
        .forEach((node) => node.remove());
      item.dataset.attachmentDeleteUrl = "";
      if (!messageHasActions(item)) {
        item.removeAttribute("tabindex");
      }
    } catch {
      // The delete can be retried by the user.
    }
  }

  function attachMessageActions(item) {
    if (item.dataset.messageActionsReady === "1") return;
    item.dataset.messageActionsReady = "1";

    if (messageHasActions(item)) {
      item.tabIndex = 0;
    }

    item.addEventListener("pointerdown", (event) => {
      if (event.button && event.button !== 0) return;
      if (event.target.closest("button, input, textarea, select, audio, video")) return;
      longPressStart = { x: event.clientX, y: event.clientY };
      window.clearTimeout(longPressTimer);
      longPressTimer = window.setTimeout(() => showChatActionPopover(item), longPressDelay);
    });

    item.addEventListener("pointermove", (event) => {
      if (!longPressStart) return;
      const moved =
        Math.abs(event.clientX - longPressStart.x) > 12 ||
        Math.abs(event.clientY - longPressStart.y) > 12;
      if (moved) clearLongPressTimer();
    });

    ["pointerup", "pointercancel", "pointerleave"].forEach((eventName) => {
      item.addEventListener(eventName, clearLongPressTimer);
    });

    item.addEventListener("click", (event) => {
      if (!suppressNextMessageClick) return;
      event.preventDefault();
      event.stopPropagation();
      suppressNextMessageClick = false;
    });

    item.addEventListener("contextmenu", (event) => {
      if (!messageHasActions(item)) return;
      event.preventDefault();
      showChatActionPopover(item);
    });

    item.addEventListener("keydown", (event) => {
      if (!["Enter", " "].includes(event.key) || !messageHasActions(item)) return;
      event.preventDefault();
      showChatActionPopover(item);
    });
  }

  function markMessageDeleted(item) {
    hideChatActionPopover();
    item.classList.add("deleted");
    item.dataset.messageCanEdit = "0";
    item.dataset.messageCanDelete = "0";
    item.dataset.attachmentDeleteUrl = "";
    item.removeAttribute("tabindex");
    const small = item.querySelector("small");
    item.querySelectorAll("p, img, audio, video, a, .chat-message-actions, [data-delete-attachment-url]").forEach((node) => node.remove());
    item.querySelector("[data-message-edited]")?.remove();
    const deleted = document.createElement("p");
    deleted.className = "chat-deleted-text";
    deleted.textContent = "Message deleted";
    item.insertBefore(deleted, small || null);
  }

  actionPopover?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-chat-action]");
    if (!button || !activeActionMessage) return;
    event.preventDefault();
    const action = button.dataset.chatAction;
    const item = activeActionMessage;
    hideChatActionPopover();
    if (action === "edit") {
      editChatMessage(item);
    } else if (action === "deleteAttachment") {
      deleteChatAttachment(item);
    } else if (action === "delete") {
      deleteChatMessage(item);
    }
  });

  document.addEventListener("click", (event) => {
    if (!actionPopover || actionPopover.classList.contains("hidden")) return;
    if (actionPopover.contains(event.target) || activeActionMessage?.contains(event.target)) return;
    hideChatActionPopover();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      hideChatActionPopover();
    }
  });

  messagesContainer?.addEventListener("scroll", hideChatActionPopover, { passive: true });

  function buildMessageElement(message) {
    const item = document.createElement("article");
    item.className = `chat-bubble ${message.mine ? "mine" : ""} ${message.deletedAt ? "deleted" : ""}`;
    item.dataset.messageId = message.id;
    item.dataset.messageUpdated = message.updatedAt || message.createdAt || "";
    item.dataset.messageEditUrl = message.editUrl || "";
    item.dataset.messageDeleteUrl = message.deleteUrl || "";
    item.dataset.messageCanEdit = message.mine && message.body && !message.deletedAt ? "1" : "0";
    item.dataset.messageCanDelete = message.mine && !message.deletedAt ? "1" : "0";
    item.dataset.attachmentDeleteUrl = message.mine && !message.deletedAt && message.attachment?.deleteUrl
      ? message.attachment.deleteUrl
      : "";
    if (message.mine && !message.deletedAt) {
      item.tabIndex = 0;
    }

    if (message.deletedAt) {
      const deleted = document.createElement("p");
      deleted.className = "chat-deleted-text";
      deleted.textContent = "Message deleted";
      item.appendChild(deleted);
    } else if (message.attachment?.kind === "image") {
      const link = document.createElement("a");
      link.className = "chat-media-link";
      link.href = message.attachment.viewUrl || message.attachment.url;
      const image = document.createElement("img");
      image.className = "chat-image";
      image.src = message.attachment.url;
      image.alt = "";
      image.loading = "lazy";
      link.appendChild(image);
      item.appendChild(link);
    } else if (message.attachment?.kind === "voice") {
      const audio = document.createElement("audio");
      audio.className = "chat-audio";
      audio.controls = true;
      audio.preload = "metadata";
      audio.src = message.attachment.url;
      item.appendChild(audio);
    } else if (message.attachment?.kind === "video") {
      const link = document.createElement("a");
      link.className = "chat-attachment-link";
      link.href = message.attachment.viewUrl || message.attachment.url;
      link.innerHTML = '<span class="material-symbols-rounded">play_circle</span><span>Open video</span>';
      item.appendChild(link);
    } else if (message.attachment?.kind === "file") {
      const link = document.createElement("a");
      link.className = "chat-attachment-link";
      link.href = message.attachment.viewUrl || message.attachment.url;
      link.innerHTML = '<span class="material-symbols-rounded">attach_file</span><span>Open attachment</span>';
      item.appendChild(link);
    }

    if (!message.deletedAt && message.body) {
      const paragraph = document.createElement("p");
      paragraph.dataset.messageBody = "1";
      paragraph.textContent = message.body;
      item.appendChild(paragraph);
    }

    const time = document.createElement("small");
    const timeText = document.createElement("span");
    timeText.dataset.messageTime = "1";
    timeText.textContent = message.timeLabel || formatMessageTime(message.createdAt);
    time.appendChild(timeText);
    if (message.editedAt && !message.deletedAt) {
      const edited = document.createElement("span");
      edited.dataset.messageEdited = "1";
      edited.textContent = " edited";
      time.appendChild(edited);
    }
    item.appendChild(time);

    attachMessageActions(item);
    return item;
  }

  function renderChatMessage(message, forceScroll = false) {
    if (!messagesContainer) return;
    const existing = messagesContainer.querySelector(`[data-message-id="${message.id}"]`);
    const shouldScroll = forceScroll || (!existing && (message.mine || chatIsNearEnd()));
    const item = buildMessageElement(message);
    if (existing) {
      existing.replaceWith(item);
    } else {
      messagesContainer.appendChild(item);
    }
    lastMessageId = Math.max(lastMessageId, Number(message.id));
    if (message.updatedAt && message.updatedAt > lastChangeAt) {
      lastChangeAt = message.updatedAt;
    }
    if (shouldScroll) scrollChatToEnd();
  }

  async function sendChatForm(formData) {
    const response = await fetch(chatThread.dataset.chatSendUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken,
        Accept: "application/json",
      },
      body: formData,
    });
    if (!response.ok) return false;
    const payload = await response.json();
    (payload.messages || []).forEach((message) => renderChatMessage(message, true));
    return true;
  }

  async function pollChat() {
    try {
      const url = `${chatThread.dataset.chatPollUrl}?after=${lastMessageId}&since=${encodeURIComponent(lastChangeAt)}`;
      const response = await fetch(url, { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const payload = await response.json();
      (payload.changedMessages || []).forEach(renderChatMessage);
      (payload.messages || []).forEach(renderChatMessage);
      if (presenceLabel && payload.presence) {
        presenceLabel.textContent = payload.presence.label;
      }
    } catch {
      // Chat polling resumes on the next interval.
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = form.querySelector('input[name="body"]');
    const body = input?.value.trim() || "";
    const hasAttachment = [imageInput, videoInput, fileInput].some((inputElement) => inputElement?.files && inputElement.files[0]);
    if (!body && !hasAttachment) return;

    try {
      const formData = new FormData(form);
      const sent = await sendChatForm(formData);
      if (sent) {
        input.value = "";
        if (imageInput) imageInput.value = "";
        if (videoInput) videoInput.value = "";
        if (fileInput) fileInput.value = "";
      }
    } catch {
      // Message send can be retried by the user.
    }
  });

  imageButton?.addEventListener("click", () => imageInput?.click());
  videoButton?.addEventListener("click", () => videoInput?.click());
  fileButton?.addEventListener("click", () => fileInput?.click());
  imageInput?.addEventListener("change", () => {
    if (imageInput.files && imageInput.files[0]) {
      form?.requestSubmit();
    }
  });
  videoInput?.addEventListener("change", () => {
    if (videoInput.files && videoInput.files[0]) {
      form?.requestSubmit();
    }
  });
  fileInput?.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      form?.requestSubmit();
    }
  });

  async function stopVoiceRecording() {
    if (voiceRecorder && voiceRecorder.state !== "inactive") {
      voiceRecorder.stop();
    }
  }

  function resetVoiceControls() {
    voiceButton?.classList.remove("recording");
    voiceCancel?.classList.add("hidden");
    voiceStatus?.classList.add("hidden");
  }

  voiceButton?.addEventListener("click", async () => {
    if (voiceRecorder && voiceRecorder.state === "recording") {
      stopVoiceRecording();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      voiceChunks = [];
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      voiceRecorder = new MediaRecorder(stream, { mimeType });
      voiceRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size) voiceChunks.push(event.data);
      };
      voiceRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        resetVoiceControls();
        if (cancelVoiceSend) {
          cancelVoiceSend = false;
          voiceChunks = [];
          return;
        }
        const blob = new Blob(voiceChunks, { type: mimeType });
        if (!blob.size) return;
        const formData = new FormData();
        formData.append("voice_note", blob, `voice-note-${Date.now()}.webm`);
        formData.append("body", "");
        await sendChatForm(formData);
      };
      voiceButton.classList.add("recording");
      voiceCancel?.classList.remove("hidden");
      voiceStatus?.classList.remove("hidden");
      voiceRecorder.start();
    } catch {
      if (voiceStatus) {
        voiceStatus.textContent = "Microphone access was blocked.";
        voiceStatus.classList.remove("hidden");
      }
    }
  });

  voiceCancel?.addEventListener("click", () => {
    cancelVoiceSend = true;
    stopVoiceRecording();
  });

  messagesContainer?.querySelectorAll("[data-message-id]").forEach(attachMessageActions);
  scrollChatToEnd();
  window.setInterval(pollChat, 1800);
}

async function postLiveSignal(url, data) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken,
      Accept: "application/json",
    },
    body: JSON.stringify(data),
  });
  return response.ok ? response.json() : null;
}

function createPeerConnection(onIceCandidate, onTrack) {
  const connection = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
  connection.onicecandidate = (event) => {
    if (event.candidate) onIceCandidate(event.candidate);
  };
  if (onTrack) {
    connection.ontrack = onTrack;
  }
  return connection;
}

const liveStudio = document.querySelector("[data-live-studio]");

if (liveStudio) {
  const video = liveStudio.querySelector("[data-live-local]");
  const empty = liveStudio.querySelector("[data-live-empty]");
  const startButton = liveStudio.querySelector("[data-live-start-camera]");
  const recordingStatus = liveStudio.querySelector("[data-live-recording-status]");
  const endForm = liveStudio.querySelector("[data-live-end-form]");
  const peers = new Map();
  let localStream = null;
  let lastSignalId = 0;
  let liveRecorder = null;
  let liveRecordingParts = [];
  let liveRecordingMimeType = "video/webm";
  const liveRecordingVideoBits = 650000;
  const liveRecordingAudioBits = 64000;

  function setLiveStudioStatus(message) {
    if (recordingStatus) recordingStatus.textContent = message;
  }

  function setLiveEmptyText(message) {
    const target = empty?.querySelector("strong");
    if (target) target.textContent = message;
  }

  function setLiveCameraRecordingState() {
    if (!startButton) return;
    startButton.classList.add("live-recording-button");
    const icon = startButton.querySelector(".material-symbols-rounded");
    const label = startButton.querySelector("span:last-child");
    if (icon) icon.textContent = "radio_button_checked";
    if (label) label.textContent = "Recording";
  }

  async function requestLiveStream() {
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error("Camera access needs a modern browser on localhost or HTTPS.");
    }
    try {
      return await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 854, max: 1280 },
          height: { ideal: 480, max: 720 },
          frameRate: { ideal: 24, max: 30 },
          facingMode: "user",
        },
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (error) {
      if (error?.name === "NotAllowedError" || error?.name === "SecurityError") {
        throw error;
      }
      return navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 854, max: 1280 },
          height: { ideal: 480, max: 720 },
          frameRate: { ideal: 24, max: 30 },
          facingMode: "user",
        },
        audio: false,
      });
    }
  }

  async function ensureLocalStream() {
    if (localStream) return localStream;
    startButton?.setAttribute("disabled", "disabled");
    setLiveStudioStatus("Opening camera...");
    try {
      localStream = await requestLiveStream();
    } catch (error) {
      startButton?.removeAttribute("disabled");
      const message =
        error?.name === "NotAllowedError"
          ? "Camera permission was blocked. Allow camera access in the browser and try again."
          : error?.message || "Camera could not be opened on this browser.";
      setLiveStudioStatus(message);
      setLiveEmptyText("Camera not available");
      throw error;
    }
    if (video) {
      video.srcObject = localStream;
      await video.play().catch(() => {});
    }
    empty?.classList.add("hidden");
    startLiveRecording(localStream);
    startButton?.removeAttribute("disabled");
    setLiveCameraRecordingState();
    setLiveStudioStatus("Camera is live. Recording is being compressed for one saved video.");
    return localStream;
  }

  async function uploadFinalRecording(blob) {
    if (!blob.size || !liveStudio.dataset.recordUrl) return;
    const formData = new FormData();
    formData.append("video_recording", blob, `live-${liveStudio.dataset.liveId}.webm`);

    try {
      const response = await fetch(liveStudio.dataset.recordUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken,
          Accept: "application/json",
        },
        body: formData,
      });
      if (recordingStatus && response.ok) {
        recordingStatus.textContent = `Recording saved as one compressed video: ${(blob.size * 8).toLocaleString()} bits.`;
      } else if (recordingStatus) {
        recordingStatus.textContent = "Recording upload failed. Keep this page open and try ending the live again.";
      }
      return response.ok;
    } catch {
      if (recordingStatus) recordingStatus.textContent = "Recording upload failed. Check the connection and try ending the live again.";
    }
    return false;
  }

  function stopLiveRecording() {
    return new Promise((resolve) => {
      if (!liveRecorder || liveRecorder.state === "inactive") {
        resolve();
        return;
      }

      const finish = () => resolve();
      liveRecorder.addEventListener("stop", finish, { once: true });
      try {
        liveRecorder.requestData();
        liveRecorder.stop();
      } catch {
        resolve();
      }
    });
  }

  async function stopAndUploadFinalRecording() {
    await stopLiveRecording();
    if (!liveRecordingParts.length) return true;

    const recordingBlob = new Blob(liveRecordingParts, { type: liveRecordingMimeType || "video/webm" });
    if (!recordingBlob.size) return true;

    setLiveStudioStatus(`Uploading one compressed video: ${(recordingBlob.size * 8).toLocaleString()} bits...`);
    return uploadFinalRecording(recordingBlob);
  }

  function startLiveRecording(stream) {
    if (liveRecorder) return;
    if (!("MediaRecorder" in window)) {
      setLiveStudioStatus("Camera is live, but this browser cannot save a recording.");
      return;
    }
    const preferredType = [
      "video/webm;codecs=vp9,opus",
      "video/webm;codecs=vp8,opus",
      "video/webm",
      "",
    ].find((type) => !type || MediaRecorder.isTypeSupported(type));
    try {
      const options = {
        videoBitsPerSecond: liveRecordingVideoBits,
        audioBitsPerSecond: liveRecordingAudioBits,
      };
      if (preferredType) options.mimeType = preferredType;
      liveRecorder = new MediaRecorder(stream, options);
      liveRecordingMimeType = liveRecorder.mimeType || preferredType || "video/webm";
    } catch {
      setLiveStudioStatus("Camera is live, but recording is not supported on this browser.");
      return;
    }
    liveRecordingParts = [];
    liveRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size) {
        liveRecordingParts.push(event.data);
      }
    };
    liveRecorder.onstart = () => {
      if (recordingStatus) recordingStatus.textContent = "Recording compressed video locally. It will save once when the live ends.";
    };
    liveRecorder.start();
  }

  async function getPeer(viewerToken) {
    if (peers.has(viewerToken)) return peers.get(viewerToken);
    if (!("RTCPeerConnection" in window)) {
      setLiveStudioStatus("Camera preview is available, but this browser cannot stream to viewers.");
      return null;
    }
    const stream = await ensureLocalStream();
    const peer = createPeerConnection((candidate) => {
      postLiveSignal(liveStudio.dataset.signalUrl, {
        senderRole: "streamer",
        viewerToken,
        type: "ice",
        payload: candidate,
      });
    });
    if (!peer) return null;
    stream.getTracks().forEach((track) => peer.addTrack(track, stream));
    peers.set(viewerToken, peer);
    return peer;
  }

  async function handleStudioSignals() {
    try {
      const response = await fetch(`${liveStudio.dataset.signalsUrl}?role=streamer&after=${lastSignalId}`);
      if (!response.ok) return;
      const payload = await response.json();
      for (const signal of payload.signals || []) {
        lastSignalId = Math.max(lastSignalId, Number(signal.id));
        const peer = await getPeer(signal.viewerToken);
        if (!peer) continue;
        if (signal.type === "offer") {
          await peer.setRemoteDescription(signal.payload);
          const answer = await peer.createAnswer();
          await peer.setLocalDescription(answer);
          await postLiveSignal(liveStudio.dataset.signalUrl, {
            senderRole: "streamer",
            viewerToken: signal.viewerToken,
            type: "answer",
            payload: answer,
          });
        } else if (signal.type === "ice") {
          await peer.addIceCandidate(signal.payload);
        }
      }
    } catch {
      // Studio polling resumes on the next interval.
    }
  }

  startButton?.addEventListener("click", () => ensureLocalStream().catch(() => {}));
  endForm?.addEventListener("submit", async (event) => {
    if (endForm.dataset.readyToSubmit === "1") return;
    event.preventDefault();
    const submitButton = endForm.querySelector('button[type="submit"]');
    submitButton?.setAttribute("disabled", "disabled");
    setLiveStudioStatus("Compressing final recording...");

    const saved = await stopAndUploadFinalRecording();
    if (!saved) {
      submitButton?.removeAttribute("disabled");
      return;
    }

    endForm.dataset.readyToSubmit = "1";
    setLiveStudioStatus("Ending live...");
    endForm.submit();
  });
  window.addEventListener("beforeunload", () => {
    if (liveRecorder && liveRecorder.state === "recording") {
      liveRecorder.requestData();
      liveRecorder.stop();
    }
  });
  if ("RTCPeerConnection" in window) {
    window.setInterval(handleStudioSignals, 1200);
  }
}

const liveWatch = document.querySelector("[data-live-watch]");

if (liveWatch && "RTCPeerConnection" in window) {
  const viewerToken = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  const video = liveWatch.querySelector("[data-live-remote]");
  const empty = liveWatch.querySelector("[data-live-empty]");
  const endedBanner = liveWatch.querySelector("[data-live-ended-banner]");
  let lastSignalId = 0;
  let watchIsEnded = liveWatch.dataset.liveEnded === "1";
  const peer = createPeerConnection((candidate) => {
    postLiveSignal(liveWatch.dataset.signalUrl, {
      viewerToken,
      type: "ice",
      payload: candidate,
    });
  }, (event) => {
    if (video && event.streams[0]) {
      video.srcObject = event.streams[0];
      empty?.classList.add("hidden");
    }
  });

  async function startWatching() {
    try {
      peer.addTransceiver("video", { direction: "recvonly" });
      peer.addTransceiver("audio", { direction: "recvonly" });
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      await postLiveSignal(liveWatch.dataset.signalUrl, {
        viewerToken,
        type: "offer",
        payload: offer,
      });
    } catch {
      // The browser may block WebRTC on unsupported environments.
    }
  }

  async function handleWatchSignals() {
    if (watchIsEnded) return;
    try {
      const response = await fetch(`${liveWatch.dataset.signalsUrl}?viewerToken=${encodeURIComponent(viewerToken)}&after=${lastSignalId}`);
      if (!response.ok) return;
      const payload = await response.json();
      for (const signal of payload.signals || []) {
        lastSignalId = Math.max(lastSignalId, Number(signal.id));
        if (signal.type === "answer") {
          await peer.setRemoteDescription(signal.payload);
        } else if (signal.type === "ice") {
          await peer.addIceCandidate(signal.payload);
        }
      }
    } catch {
      // Watch polling resumes on the next interval.
    }
  }

  async function pollLiveStatus() {
    if (!liveWatch.dataset.statusUrl) return;
    try {
      const response = await fetch(liveWatch.dataset.statusUrl, { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const payload = await response.json();
      if (payload.ended) {
        watchIsEnded = true;
        endedBanner?.classList.remove("hidden");
        empty?.classList.add("hidden");
        peer.close();
      }
    } catch {
      // Status polling resumes on the next interval.
    }
  }

  if (watchIsEnded) {
    endedBanner?.classList.remove("hidden");
  } else {
    startWatching();
  }
  window.setInterval(handleWatchSignals, 850);
  window.setInterval(pollLiveStatus, 2500);
}

const liveEngagement = document.querySelector("[data-live-engagement]");

if (liveEngagement) {
  const host = document.querySelector("[data-live-watch], [data-live-studio]");
  const commentsContainer = liveEngagement.querySelector("[data-live-comments]");
  const commentForm = liveEngagement.querySelector("[data-live-comment-form]");
  let lastCommentId = 0;

  commentsContainer?.querySelectorAll("[data-live-comment-id]").forEach((item) => {
    lastCommentId = Math.max(lastCommentId, Number(item.dataset.liveCommentId || 0));
  });

  function renderLiveComment(comment) {
    if (!commentsContainer || commentsContainer.querySelector(`[data-live-comment-id="${comment.id}"]`)) return;
    const item = document.createElement("article");
    item.className = "live-comment";
    item.dataset.liveCommentId = comment.id;
    const name = document.createElement("strong");
    name.textContent = comment.name;
    const body = document.createElement("p");
    body.textContent = comment.body;
    item.append(name, body);
    commentsContainer.appendChild(item);
    lastCommentId = Math.max(lastCommentId, Number(comment.id));
    commentsContainer.scrollTop = commentsContainer.scrollHeight;
  }

  function updateReactionCounts(reactions, myReaction = "") {
    Object.entries(reactions || {}).forEach(([key, value]) => {
      liveEngagement.querySelectorAll(`[data-reaction-count="${key}"]`).forEach((item) => {
        item.textContent = value;
      });
    });
    liveEngagement.querySelectorAll("[data-reaction-type]").forEach((button) => {
      button.classList.toggle("active", button.dataset.reactionType === myReaction);
    });
  }

  async function pollEngagement() {
    if (!host?.dataset.engagementUrl) return;
    try {
      const response = await fetch(`${host.dataset.engagementUrl}?after=${lastCommentId}`, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return;
      const payload = await response.json();
      (payload.comments || []).forEach(renderLiveComment);
      updateReactionCounts(payload.reactions, payload.myReaction);
    } catch {
      // Engagement polling resumes on the next interval.
    }
  }

  commentForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = commentForm.querySelector('input[name="body"]');
    const body = input?.value.trim();
    if (!body || !host?.dataset.commentUrl) return;
    try {
      const response = await fetch(host.dataset.commentUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken,
          Accept: "application/json",
        },
        body: JSON.stringify({ body }),
      });
      if (!response.ok) return;
      const payload = await response.json();
      (payload.comments || []).forEach(renderLiveComment);
      input.value = "";
    } catch {
      // Comment can be retried by the user.
    }
  });

  liveEngagement.querySelectorAll("[data-reaction-type]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!host?.dataset.reactUrl) return;
      try {
        const response = await fetch(host.dataset.reactUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken,
            Accept: "application/json",
          },
          body: JSON.stringify({ reactionType: button.dataset.reactionType }),
        });
        if (!response.ok) return;
        const payload = await response.json();
        updateReactionCounts(payload.reactions, payload.myReaction);
      } catch {
        // Reaction can be retried by the user.
      }
    });
  });

  window.setInterval(pollEngagement, 1800);
}
