"use strict";

const accessToken = document.querySelector('meta[name="mirror-token"]').content;
const buttons = Array.from(document.querySelectorAll("[data-command]"));
const statusEl = document.getElementById("status");
const reviewEl = document.getElementById("review");
let busy = false;

async function sendCommand(command) {
  if (busy) return;
  busy = true;
  buttons.forEach(button => { button.disabled = true; });
  reviewEl.textContent = "";
  statusEl.textContent = "Capturing and analyzing…";

  try {
    const response = await fetch("/api/cmd", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Mirror-Token": accessToken },
      body: JSON.stringify({ cmd: command })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.ok) {
      statusEl.textContent = data.error || `Analysis failed (${response.status}).`;
      return;
    }
    statusEl.textContent = "Done. Playing AI-generated feedback on the speaker.";
    reviewEl.textContent =
      `${data.review.overall_score}/100 · ${data.review.verdict}: ${data.review.reasoning_short}`;
  } catch {
    statusEl.textContent = "Connection lost. Refresh the page before trying again.";
  } finally {
    busy = false;
    buttons.forEach(button => { button.disabled = false; });
  }
}

buttons.forEach(button => {
  button.addEventListener("click", () => sendCommand(button.dataset.command));
});
