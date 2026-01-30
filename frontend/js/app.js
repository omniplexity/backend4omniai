import { loadConfig } from "./config.js";
import { login } from "./auth.js";
import {
  get,
  post,
  patch,
  del,
  getMe,
  getAdminUsers,
  patchAdminUser,
  getAdminUsage,
  getAdminAudit,
  getAdminInvites,
  postAdminInvite,
} from "./api.js";
import { createSseStream, createRetryStream } from "./sse.js";
import {
  getState,
  setSelectedConversation,
  updateConversations,
  updateMessages,
  attachStream,
  detachStream,
  pushMessage,
  setProviders,
  updateMessageById,
  setCurrentAssistantMessageId,
  isStreaming,
  setAutoScroll,
  shouldAutoScroll,
  getResumeHint,
  clearActiveStreamMeta,
  setActiveStreamMeta,
  resetVirtualMeasurements,
  setCurrentUser,
  setAdminUsers,
  setAdminUsage,
  setAdminAudit,
  setAdminInvites,
  getSelectedAdminUsers,
  setSelectedAdminUsers,
  getAdminUsers as getAdminUsersState,
  getAdminUsage as getAdminUsageState,
  getAdminAudit as getAdminAuditState,
} from "./state.js";
import {
  renderConversations,
  renderMessages,
  updateStatus,
  showError,
  bindConversationActions,
  bindJumpButton,
  setJumpButtonVisibility,
  showResumeNotice,
  hideResumeNotice,
  updateStreamBadge,
  updateElapsedTime,
  scrollToBottom,
  bindResumeRetry,
  getMessageStreamElement,
  updateMessage,
  setAdminToggleVisible,
  bindAdminToggle,
  showAdminPanel,
  hideAdminPanel,
  bindAdminClose,
  bindAdminUserActions,
  bindAdminRefreshButtons,
  renderAdminUsers,
  renderAdminUsage,
  renderAdminAudit,
  renderAdminInvites,
  bindAdminInviteForm,
  refreshVisibleMessages,
  resetVirtualRange,
  bindAdminBulkButtons,
  bindAdminExportControls,
  bindAdminAuditFilters,
  updateSelectionSummary,
  setBulkButtonsEnabled,
  syncSelectAllCheckbox,
  setAuditFilterControls,
} from "./ui.js";

let elapsedInterval = null;
let auditFilters = { event: "", from: "", to: "" };

function startElapsedTimer() {
  stopElapsedTimer();
  const tick = () => {
    const start = getState().streamStartTime;
    if (!start) {
      updateElapsedTime(0);
      return;
    }
    const seconds = Math.floor((Date.now() - start) / 1000);
    updateElapsedTime(seconds);
  };
  tick();
  elapsedInterval = setInterval(tick, 1000);
}

function stopElapsedTimer() {
  if (elapsedInterval) {
    clearInterval(elapsedInterval);
    elapsedInterval = null;
  }
  updateElapsedTime(0);
}

async function loadCurrentUser() {
  try {
    const payload = await getMe();
    setCurrentUser(payload.user);
    const isAdmin = payload.user?.role === "admin";
    setAdminToggleVisible(Boolean(isAdmin));
    if (!isAdmin) {
      hideAdminPanel();
    }
    return true;
  } catch (err) {
    setAdminToggleVisible(false);
    if (err?.code === "E2000" || err?.code === "E2002") {
      window.location.replace("login.html");
      return false;
    }
    return false;
  }
}

async function refreshAdminUsers() {
  try {
    const payload = await getAdminUsers({ limit: 100 });
    setAdminUsers(payload.users);
    setSelectedAdminUsers([]);
    renderAdminUsers(payload.users);
    handleAdminSelectionChange([]);
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function refreshAdminUsage() {
  try {
    const payload = await getAdminUsage({ limit: 50 });
    setAdminUsage(payload.entries);
    renderAdminUsage(payload.entries, getAdminUsersState());
  } catch (err) {
    showError(err.message, err.code);
  }
}

function filterAuditEntries(entries, filters) {
  if (!entries?.length) return [];
  const fromTs = filters.from ? new Date(`${filters.from}T00:00:00`).getTime() : null;
  const toTs = filters.to ? new Date(`${filters.to}T23:59:59`).getTime() : null;
  return entries.filter((entry) => {
    if (filters.event && entry.action !== filters.event) {
      return false;
    }
    const created = new Date(entry.created_at).getTime();
    if (Number.isNaN(created)) {
      return false;
    }
    if (fromTs != null && Number.isFinite(fromTs) && created < fromTs) {
      return false;
    }
    if (toTs != null && Number.isFinite(toTs) && created > toTs) {
      return false;
    }
    return true;
  });
}

async function refreshAdminAudit(overrides = {}) {
  const params = {
    limit: 50,
    ...auditFilters,
    ...overrides,
  };
  auditFilters = {
    event: params.event || "",
    from: params.from || "",
    to: params.to || "",
  };
  try {
    const payload = await getAdminAudit(params);
    const filtered = filterAuditEntries(payload.entries || [], auditFilters);
    setAdminAudit(filtered);
    renderAdminAudit(filtered);
    setAuditFilterControls(auditFilters);
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function refreshAdminInvites() {
  try {
    const payload = await getAdminInvites();
    setAdminInvites(payload.invites);
    renderAdminInvites(payload.invites);
  } catch (err) {
    showError(err.message, err.code);
  }
}

function handleAdminSelectionChange(selectedIds) {
  setSelectedAdminUsers(selectedIds);
  updateSelectionSummary(selectedIds.length);
  setBulkButtonsEnabled(selectedIds.length > 0);
  syncSelectAllCheckbox(selectedIds.length, getAdminUsersState().length);
}

async function bulkUpdateUsers(status) {
  const ids = getSelectedAdminUsers();
  if (!ids.length) return;
  try {
    await Promise.all(ids.map((userId) => patchAdminUser(userId, { status })));
    await refreshAdminUsers();
  } catch (err) {
    showError(err.message, err.code);
  }
}

function escapeCsv(value) {
  if (value == null) return "";
  const str = String(value);
  if (/[",\n]/.test(str)) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function downloadCsv(filename, headers, rows) {
  const lines = [];
  lines.push(headers.map(escapeCsv).join(","));
  rows.forEach((row) => {
    lines.push(row.map(escapeCsv).join(","));
  });
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

function exportUsersCsv() {
  const users = getAdminUsersState();
  const headers = ["ID", "Username", "Email", "Role", "Status", "Messages/day", "Tokens/day"];
  const rows = users.map((user) => [
    user.id,
    user.username,
    user.email || "",
    user.role,
    user.status,
    user.quotas?.messages_per_day ?? "",
    user.quotas?.tokens_per_day ?? "",
  ]);
  downloadCsv("admin-users.csv", headers, rows);
}

function exportUsageCsv() {
  const entries = getAdminUsageState();
  const headers = ["Date", "User ID", "Username", "Messages used", "Tokens used"];
  const rows = entries.map((entry) => [
    entry.date,
    entry.user_id,
    entry.username || "",
    entry.messages_used,
    entry.tokens_used,
  ]);
  downloadCsv("admin-usage.csv", headers, rows);
}

function exportAuditCsv() {
  const entries = getAdminAuditState();
  const headers = ["Timestamp", "Action", "Actor", "Target", "Details"];
  const rows = entries.map((entry) => [
    entry.created_at,
    entry.action,
    entry.actor_user_id || "system",
    entry.target_id || "—",
    entry.details ? JSON.stringify(entry.details) : "",
  ]);
  downloadCsv("admin-audit.csv", headers, rows);
}

function handleAdminExport(type) {
  if (type === "users") {
    exportUsersCsv();
  }
  if (type === "usage") {
    exportUsageCsv();
  }
  if (type === "audit") {
    exportAuditCsv();
  }
}

function handleAuditFilterApply(filters) {
  auditFilters = {
    event: filters.event || "",
    from: filters.from || "",
    to: filters.to || "",
  };
  refreshAdminAudit(auditFilters);
}

async function refreshAllAdminData() {
  await Promise.all([
    refreshAdminUsers(),
    refreshAdminUsage(),
    refreshAdminAudit(),
    refreshAdminInvites(),
  ]);
}

async function handleAdminToggleStatus(userId, nextStatus) {
  try {
    await patchAdminUser(userId, { status: nextStatus });
    await refreshAdminUsers();
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function handleAdminQuotaSave(userId, quotas) {
  try {
    await patchAdminUser(userId, quotas);
    await refreshAdminUsers();
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function handleAdminInviteSubmit(payload) {
  try {
    await postAdminInvite(payload);
    await refreshAdminInvites();
  } catch (err) {
    showError(err.message, err.code);
  }
}

function setupAdminPanel() {
  bindAdminToggle(() => {
    showAdminPanel();
    refreshAllAdminData();
  });
  bindAdminClose(() => hideAdminPanel());
  bindAdminUserActions({
    onToggleStatus: handleAdminToggleStatus,
    onSaveQuotas: handleAdminQuotaSave,
    onSelectionChange: handleAdminSelectionChange,
    onValidationError: (message) => showError(message),
  });
  bindAdminBulkButtons({
    onBulkEnable: () => bulkUpdateUsers("active"),
    onBulkDisable: () => bulkUpdateUsers("disabled"),
  });
  bindAdminExportControls({
    onExport: handleAdminExport,
  });
  bindAdminAuditFilters({
    onApply: handleAuditFilterApply,
  });
  bindAdminRefreshButtons({
    onUsers: refreshAdminUsers,
    onUsage: refreshAdminUsage,
    onAudit: refreshAdminAudit,
  });
  bindAdminInviteForm(handleAdminInviteSubmit);
  setAuditFilterControls(auditFilters);
  handleAdminSelectionChange([]);
  setBulkButtonsEnabled(false);
}

function setRetryEnabled(enabled) {
  const retryBtn = document.getElementById("retryBtn");
  if (!retryBtn) return;
  retryBtn.disabled = !enabled;
}

function streamCompleted() {
  detachStream();
  stopElapsedTimer();
}

async function handleLoginPage() {
  const form = document.getElementById("loginForm");
  const button = document.getElementById("loginButton");
  const error = document.getElementById("loginError");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    error?.classList.add("hidden");
    try {
      await login({
        username: form.username?.value,
        password: form.password?.value,
      });
      window.location.replace("index.html");
    } catch (err) {
      const message = err?.message || "Invalid credentials";
      if (error) {
        error.textContent = message;
      }
      error.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });
}

function buildStreamHandlers(conversation) {
  const assistantMessageId = getState().currentAssistantMessageId;
  const providerId = conversation.provider || "";
  const model = conversation.model || "";
  let activeProvider = providerId;
  let activeModel = model;
  return {
    meta(data) {
      const resolvedProvider = data.provider_id || providerId || "lmstudio";
      const resolvedModel = data.model || model || "default";
      activeProvider = resolvedProvider;
      activeModel = resolvedModel;
      updateStatus({ provider: resolvedProvider, model: resolvedModel });
      updateStreamBadge("Streaming…");
      startElapsedTimer();
      setRetryEnabled(false);
      setAutoScroll(true);
      scrollToBottom();
      setActiveStreamMeta({
        conversationId: conversation.id,
        assistantMessageId,
        providerId: resolvedProvider,
        model: resolvedModel,
        partialLength: 0,
        startedAt: Date.now(),
      });
      hideResumeNotice();
    },
    delta(data) {
      const messages = getState().messages;
      const message = messages.find((m) => m.id === assistantMessageId);
      if (!message) return;
      const nextContent = `${message.content || ""}${data.text || ""}`;
      const updated = updateMessageById(assistantMessageId, { content: nextContent, isTyping: true });
      if (updated) {
        updateMessage(updated);
      }
      if (shouldAutoScroll()) {
        scrollToBottom();
      }
    },
    final(data) {
      const updated = updateMessageById(assistantMessageId, { isTyping: false });
      if (updated) {
        updateMessage(updated);
      }
      updateStatus({ provider: activeProvider, model: activeModel, token_usage: data?.token_usage });
      updateStreamBadge(null);
      hideResumeNotice();
      setRetryEnabled(false);
      streamCompleted();
      clearActiveStreamMeta();
    },
    error(data) {
      const updated = updateMessageById(assistantMessageId, {
        metaStatus: "[error]",
        errorMessage: data?.message || "Stream failed",
        isTyping: false,
      });
      if (updated) {
        updateMessage(updated);
      }
      updateStreamBadge("Disconnected");
      showResumeNotice("Connection interrupted. Retry to continue.");
      setRetryEnabled(true);
      streamCompleted();
    },
    reconnecting() {
      updateStreamBadge("Reconnecting…");
    },
    disconnected() {
      const updated = updateMessageById(assistantMessageId, {
        metaStatus: "[disconnected]",
        errorMessage: "Connection interrupted. You can retry.",
        isTyping: false,
      });
      if (updated) {
        updateMessage(updated);
      }
      setRetryEnabled(true);
      updateStreamBadge("Disconnected");
      showResumeNotice("A response may have been interrupted.");
      streamCompleted();
    },
    canceled() {
      const updated = updateMessageById(assistantMessageId, {
        metaStatus: "[canceled]",
        isTyping: false,
      });
      if (updated) {
        updateMessage(updated);
      }
      updateStreamBadge("Canceled");
      showResumeNotice("Response canceled. Retry if you like.");
      setRetryEnabled(true);
      streamCompleted();
    },
  };
}

async function handleSend(composer) {
  if (isStreaming()) {
    showError("A stream is already running");
    return;
  }
  const text = composer?.value.trim();
  if (!text) {
    return;
  }
  const state = getState();
  const conversation = state.selectedConversation;
  if (!conversation) {
    showError("Select a conversation first");
    return;
  }
  composer.value = "";
  setRetryEnabled(false);
  pushMessage({ role: "user", content: text });
  renderMessages(getState().messages);
  scrollToBottom();
  const assistantMessage = pushMessage({ role: "assistant", content: "", isTyping: true });
  setCurrentAssistantMessageId(assistantMessage.id);
  renderMessages(getState().messages);
  scrollToBottom();
  setJumpButtonVisibility(false);
  updateStreamBadge(null);
  const stream = createSseStream({
    conversationId: conversation.id,
    providerId: conversation.provider || state.providers[0]?.id || "lmstudio",
    model: conversation.model || "default",
    input: text,
    settings: {},
    onEvent: buildStreamHandlers(conversation),
  });
  attachStream(stream);
  try {
    await stream.start();
  } catch (err) {
    showError(err.message || "Stream failed");
    streamCompleted();
  }
}

async function handleCancel() {
  const stream = getState().stream;
  if (!stream) {
    showError("No active stream to cancel");
    return;
  }
  stream.cancel();
}

async function handleRetry() {
  if (isStreaming()) {
    showError("Finish the current stream first");
    return;
  }
  const state = getState();
  const conversation = state.selectedConversation;
  if (!conversation) {
    showError("Select a conversation to retry");
    return;
  }
  setRetryEnabled(false);
  hideResumeNotice();
  const assistantMessage = pushMessage({ role: "assistant", content: "", isTyping: true });
  setCurrentAssistantMessageId(assistantMessage.id);
  renderMessages(getState().messages);
  scrollToBottom();
  updateStreamBadge(null);
  const stream = createRetryStream(conversation.id, buildStreamHandlers(conversation));
  attachStream(stream);
  try {
    await stream.start();
  } catch (err) {
    showError(err.message || "Retry failed");
    streamCompleted();
  }
}

async function handleRenameConversation(conversation) {
  const title = window.prompt("New title", conversation.title);
  if (!title) return;
  if (!conversation) return;
  try {
    await patch(`/conversations/${conversation.id}`, { title });
    await refreshConversations();
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function handleDeleteConversation(conversation) {
  if (!window.confirm("Delete this conversation?")) return;
  try {
    await del(`/conversations/${conversation.id}`);
    await refreshConversations();
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function startNewConversation() {
  try {
    await post("/conversations", { title: "New chat" });
    await refreshConversations();
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function refreshConversations() {
  try {
    const payload = await get("/conversations");
    updateConversations(payload.conversations);
    renderConversations(payload.conversations, handleSelectConversation, {
      onRename: handleRenameConversation,
      onDelete: handleDeleteConversation,
    });
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function handleSelectConversation(conversation) {
  setSelectedConversation(conversation);
  renderConversations(getState().conversations, handleSelectConversation, {
    onRename: handleRenameConversation,
    onDelete: handleDeleteConversation,
  });
  document.getElementById("composerInput")?.focus();
  try {
    const payload = await get(`/conversations/${conversation.id}/messages`);
    updateMessages(payload.messages);
    resetVirtualMeasurements();
    resetVirtualRange();
    renderMessages(payload.messages);
    scrollToBottom();
    setAutoScroll(true);
    setJumpButtonVisibility(false);
    hideResumeNotice();
    const hint = getResumeHint(conversation.id);
    if (hint) {
      const message = payload.messages.find((msg) => msg.id === hint.assistantMessageId);
      const providerMeta = message?.provider_meta || {};
      const completed =
        providerMeta.completed === true ||
        providerMeta.canceled === true ||
        Boolean(providerMeta.finish_reason) ||
        Boolean(providerMeta.error);
      if (message && !message.token_usage && !completed) {
        showResumeNotice("A response may have been interrupted.");
        setRetryEnabled(true);
      } else {
        hideResumeNotice();
        setRetryEnabled(false);
      }
    } else {
      setRetryEnabled(false);
    }
  } catch (err) {
    showError(err.message, err.code);
  }
}

async function loadProviders() {
  try {
    const payload = await get("/providers");
    const providers = Array.isArray(payload) ? payload : payload?.providers;
    setProviders(Array.isArray(providers) ? providers : []);
  } catch (err) {
    showError(err.message, err.code);
  }
}

function setupScrolling() {
  const streamEl = getMessageStreamElement();
  if (!streamEl) return;
  let scrollRaf = null;
  streamEl.addEventListener("scroll", () => {
    const atBottom =
      streamEl.scrollHeight - streamEl.scrollTop - streamEl.clientHeight <= 80;
    setAutoScroll(atBottom);
    setJumpButtonVisibility(!atBottom);
    if (scrollRaf) {
      cancelAnimationFrame(scrollRaf);
    }
    scrollRaf = requestAnimationFrame(() => {
      refreshVisibleMessages(getState().messages);
    });
  });
}

async function mainApp() {
  const sendBtn = document.getElementById("sendBtn");
  const cancelBtn = document.getElementById("cancelBtn");
  const retryBtn = document.getElementById("retryBtn");
  const composer = document.getElementById("composerInput");

  bindConversationActions(startNewConversation);
  bindJumpButton(() => {
    scrollToBottom();
    setAutoScroll(true);
    setJumpButtonVisibility(false);
  });
  bindResumeRetry(handleRetry);
  setupScrolling();

  sendBtn?.addEventListener("click", () => handleSend(composer));
  cancelBtn?.addEventListener("click", handleCancel);
  retryBtn?.addEventListener("click", handleRetry);

  composer?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend(composer);
    }
    if (event.key === "Escape") {
      event.preventDefault();
      handleCancel();
    }
  });

  setupAdminPanel();
  const authed = await loadCurrentUser();
  if (!authed) {
    return;
  }

  await refreshConversations();
  await loadProviders();
  setRetryEnabled(false);
  setJumpButtonVisibility(false);
}

async function init() {
  try {
    await loadConfig();
    const page = document.body.dataset.page;
    if (page === "login") {
      await handleLoginPage();
    } else {
      await mainApp();
    }
  } catch (err) {
    showError("Unable to boot frontend");
  }
}

init();
