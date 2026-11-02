"use strict";

// This changes the illustration only. It never executes Python or pytest.
const sourceToggle = document.querySelector("[data-source-toggle]");
if (sourceToggle) {
  sourceToggle.hidden = false;
  const states = {
    original: {
      operator: ">=",
      explanation: "Both test revisions pass on the unchanged original source.",
      old: "✓ Passed on original code",
      newer: "✓ Passed on original code",
      verdict: "Original-code controls",
      confirmation: "4 passing baselines · 2 passing final controls",
    },
    mutant: {
      operator: ">",
      explanation: "The declared fault excludes the eighteenth birthday.",
      old: "× Caught the fault",
      newer: "✓ Passed. Missed the fault.",
      verdict: "loss_observed",
      confirmation: "3 old/new pairs + passing final controls",
    },
  };
  sourceToggle.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      const selected = button.dataset.source;
      const state = states[selected];
      sourceToggle.querySelectorAll("button").forEach((item) => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      const operator = document.getElementById("source-operator");
      operator.textContent = state.operator;
      operator.classList.toggle("original", selected === "original");
      document.getElementById("fault-explanation").textContent = state.explanation;
      const oldStatus = document.getElementById("old-status");
      oldStatus.textContent = state.old;
      oldStatus.classList.toggle("caught", selected === "mutant");
      oldStatus.classList.toggle("passed", selected === "original");
      document.getElementById("new-status").textContent = state.newer;
      document.getElementById("example-verdict").textContent = state.verdict;
      document.getElementById("example-confirmation").textContent = state.confirmation;
      document.getElementById("example-announcement").textContent = `${state.explanation} ${state.old}. ${state.newer}.`;
    });
  });
}

const tabList = document.querySelector(".install-tabs");
if (tabList) {
  const tabs = [...tabList.querySelectorAll("[role=tab]")];
  const activate = (tab, focus = false) => {
    tabs.forEach((item) => {
      const active = item === tab;
      item.setAttribute("aria-selected", String(active));
      item.tabIndex = active ? 0 : -1;
      document.getElementById(item.getAttribute("aria-controls")).hidden = !active;
    });
    if (focus) tab.focus();
  };
  tabList.hidden = false;
  activate(tabs[0]);
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activate(tab));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== undefined) {
        event.preventDefault();
        activate(tabs[next], true);
      }
    });
  });
}

async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // Fall through to the local selection-based copy method.
    }
  }
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.className = "visually-hidden";
  textarea.setAttribute("readonly", "");
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  return copied;
}

document.querySelectorAll("[data-copy]").forEach((button) => {
  button.hidden = false;
  const label = button.textContent;
  let reset;
  button.addEventListener("click", async () => {
    window.clearTimeout(reset);
    const code = document.getElementById(button.dataset.copy);
    let copied = false;
    try {
      copied = await copyText(code.textContent);
    } catch {
      copied = false;
    }
    if (copied) {
      button.textContent = "Copied ✓";
      document.getElementById("copy-status").textContent = "Code copied to clipboard.";
    } else {
      const selection = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(code);
      selection.removeAllRanges();
      selection.addRange(range);
      button.textContent = "Text selected";
      document.getElementById("copy-status").textContent = "Copy was unavailable. The code is selected; use your keyboard copy shortcut.";
    }
    button.focus({ preventScroll: true });
    reset = window.setTimeout(() => { button.textContent = label; }, 2200);
  });
});
