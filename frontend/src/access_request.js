import { api } from "./api/client.js";
import { escapeHtml } from "./utils/format.js";
import { setMessage } from "./ui/messages.js";

const USERNAME_RE = /^[A-Za-z0-9._-]{2,32}$/;
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function openAccessRequestForm() {
  document.getElementById("access-request-modal")?.remove();
  document.body.insertAdjacentHTML(
    "beforeend",
    `
      <div id="access-request-modal" class="fixed inset-0 z-50 grid place-items-center bg-slate-950/45 px-4">
        <form id="access-request-form" class="panel w-full max-w-lg p-5">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h2 class="text-xl font-semibold text-slate-950">Request access</h2>
              <p class="mt-1 text-sm text-slate-500">An admin must approve the request before login works.</p>
            </div>
            <button id="access-request-close" class="btn px-3 py-1.5 text-sm" type="button">Close</button>
          </div>

          <div class="mt-4 grid gap-3">
            ${field("access-username", "username", "Username", "text", "letters, numbers, . _ -")}
            ${field("access-password", "password", "Password", "password", "4-64 characters")}
            ${field("access-email", "email", "Email", "email", "optional")}
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-slate-700">Message</span>
              <textarea
                id="access-message"
                name="message"
                maxlength="500"
                rows="4"
                class="min-h-28 rounded-lg border border-slate-200 bg-white/90 px-3 py-2 text-sm outline-none focus:border-emerald-400"
                placeholder="optional note to the admin"
              ></textarea>
              <span id="access-message-count" class="text-xs text-slate-500">0 / 500</span>
            </label>
            <input class="hidden" name="website" tabindex="-1" autocomplete="off" />
            <div id="access-request-error" class="hidden rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"></div>
          </div>

          <div class="mt-5 flex flex-wrap justify-end gap-2">
            <button class="btn px-4 py-2 text-sm" type="button" id="access-request-cancel">Cancel</button>
            <button class="btn-primary px-4 py-2 text-sm" type="submit">Submit Request</button>
          </div>
        </form>
      </div>
    `,
  );

  const modal = document.getElementById("access-request-modal");
  const form = document.getElementById("access-request-form");
  const message = document.getElementById("access-message");
  const count = document.getElementById("access-message-count");
  const close = () => modal?.remove();

  document.getElementById("access-request-close")?.addEventListener("click", close);
  document.getElementById("access-request-cancel")?.addEventListener("click", close);
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) close();
  });
  message?.addEventListener("input", () => {
    count.textContent = `${message.value.length} / 500`;
  });
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitAccessRequest(form, close);
  });
}

async function submitAccessRequest(form, close) {
  const data = new FormData(form);
  const payload = {
    username: String(data.get("username") || "").trim().toLowerCase(),
    password: String(data.get("password") || ""),
    email: optionalString(data.get("email")),
    message: optionalString(data.get("message")),
    website: optionalString(data.get("website")),
  };

  const error = validate(payload);
  if (error) {
    showError(error);
    return;
  }

  try {
    await api("/auth/register-request", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    close();
    setMessage("auth", "Your request was submitted and is waiting for admin approval.", "success");
  } catch (err) {
    showError(err.message || "Could not submit request");
  }
}

function validate(payload) {
  if (!USERNAME_RE.test(payload.username)) {
    return "Username must be 2-32 characters and use only letters, numbers, dot, underscore, or dash.";
  }
  if (payload.password.length < 4 || payload.password.length > 64) {
    return "Password must be 4-64 characters.";
  }
  if (payload.email && (payload.email.length > 254 || !EMAIL_RE.test(payload.email))) {
    return "Email is invalid.";
  }
  if (payload.message && payload.message.length > 500) {
    return "Message must be at most 500 characters.";
  }
  return null;
}

function showError(message) {
  const box = document.getElementById("access-request-error");
  if (!box) return;
  box.textContent = message;
  box.classList.remove("hidden");
}

function optionalString(value) {
  const text = String(value || "").trim();
  return text || null;
}

function field(id, name, label, type, placeholder) {
  return `
    <label class="grid gap-1 text-sm">
      <span class="font-medium text-slate-700">${escapeHtml(label)}</span>
      <input
        id="${escapeHtml(id)}"
        name="${escapeHtml(name)}"
        type="${escapeHtml(type)}"
        placeholder="${escapeHtml(placeholder)}"
        class="h-10 rounded-lg border border-slate-200 bg-white/90 px-3 text-sm outline-none focus:border-emerald-400"
      />
    </label>
  `;
}
