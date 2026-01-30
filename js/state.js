const RESUME_HINTS_KEY = "omni_stream_resume";

function loadResumeHints() {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(RESUME_HINTS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) {
    console.warn("Unable to load resume hints", e);
    return {};
  }
}

function persistResumeHints() {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(RESUME_HINTS_KEY, JSON.stringify(state.resumeHints));
  } catch (e) {
    console.warn("Unable to persist resume hints", e);
  }
}

const state = {
  conversations: [],
  messages: [],
  selectedConversation: null,
  providers: [],
  stream: null,
  activeStreamId: null,
  currentAssistantMessageId: null,
  streamActive: false,
  streamStartTime: null,
  autoScroll: true,
  lastErrorByConversation: {},
  editingConversationId: null,
  providerSelection: { providerId: null, model: null },
  streamStatusByConversation: {},
  resumeHints: loadResumeHints(),
  activeStreamMeta: null,
  currentUser: null,
  admin: {
    users: [],
    usage: [],
    audit: [],
    invites: [],
    selectedUserIds: [],
  },
};

const virtualization = {
  heights: {},
  averageHeight: 120,
  buffer: 6,
};

function recalcAverageHeight(newHeight) {
  if (!newHeight || newHeight <= 0) {
    return virtualization.averageHeight;
  }
  virtualization.averageHeight =
    virtualization.averageHeight * 0.85 + newHeight * 0.15;
  return virtualization.averageHeight;
}

export function updateConversations(list) {
  state.conversations = list;
}

export function setSelectedConversation(conversation) {
  state.selectedConversation = conversation;
}

export function updateMessages(list) {
  state.messages = list;
}

function ensureMessageId(message) {
  if (message.id) return message.id;
  return `${message.role}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function pushMessage(message) {
  const msgWithId = { ...message, id: ensureMessageId(message) };
  state.messages = [...state.messages, msgWithId];
  return msgWithId;
}

export function updateMessageById(id, updates) {
  state.messages = state.messages.map((msg) => (msg.id === id ? { ...msg, ...updates } : msg));
  const updated = state.messages.find((msg) => msg.id === id);
  return updated;
}

export function getLastMessage() {
  return state.messages[state.messages.length - 1];
}

export function setProviders(list) {
  state.providers = Array.isArray(list) ? list : [];
}

export function getState() {
  return state;
}

export function attachStream(stream) {
  state.stream = stream;
}

export function detachStream() {
  state.stream = null;

  state.activeStreamId = null;
}

export function setActiveStreamId(id) {
  state.activeStreamId = id;
}

export function getActiveStreamId() {
  return state.activeStreamId;
}

export function setCurrentAssistantMessageId(id) {
  state.currentAssistantMessageId = id;
}

export function getCurrentAssistantMessageId() {
  return state.currentAssistantMessageId;
}

export function clearCurrentAssistantMessageId() {
  state.currentAssistantMessageId = null;
}

export function setStreamStatus(conversationId, status) {
  if (!conversationId) return;
  state.streamStatusByConversation[conversationId] = status;
}

export function getStreamStatus(conversationId) {
  return state.streamStatusByConversation[conversationId];
}

export function setActiveStreamMeta(meta) {
  if (!meta?.conversationId) return;
  state.activeStreamMeta = { ...meta };
  state.resumeHints[meta.conversationId] = {
    conversationId: meta.conversationId,
    assistantMessageId: meta.assistantMessageId,
    providerId: meta.providerId,
    model: meta.model,
    partialLength: meta.partialLength ?? 0,
    startedAt: meta.startedAt || Date.now(),
    interrupted: false,
  };
  persistResumeHints();
}

export function getActiveStreamMeta() {
  return state.activeStreamMeta;
}

export function updateActiveStreamMeta(updates) {
  if (!state.activeStreamMeta?.conversationId) return;
  state.activeStreamMeta = { ...state.activeStreamMeta, ...updates };
  const convoId = state.activeStreamMeta.conversationId;
  state.resumeHints[convoId] = { ...state.activeStreamMeta, interrupted: state.resumeHints[convoId]?.interrupted || false };
  persistResumeHints();
}

export function markStreamInterrupted(conversationId) {
  const hint = state.resumeHints[conversationId];
  if (!hint) return;
  hint.interrupted = true;
  persistResumeHints();
}

export function clearActiveStreamMeta() {
  if (state.activeStreamMeta?.conversationId) {
    delete state.resumeHints[state.activeStreamMeta.conversationId];
    persistResumeHints();
  }
  state.activeStreamMeta = null;
}

export function getResumeHint(conversationId) {
  return state.resumeHints[conversationId];
}

export function setStreaming(active) {
  state.streamActive = active;
  state.streamStartTime = active ? Date.now() : null;
}

export function isStreaming() {
  return state.streamActive;
}

export function setAutoScroll(value) {
  state.autoScroll = value;
}

export function shouldAutoScroll() {
  return state.autoScroll;
}

export function setConversationError(conversationId, error) {
  if (!conversationId) return;
  state.lastErrorByConversation[conversationId] = error;
}

export function getConversationError(conversationId) {
  return state.lastErrorByConversation[conversationId];
}

export function clearConversationError(conversationId) {
  if (!conversationId) return;
  delete state.lastErrorByConversation[conversationId];
}

export function setEditingConversation(id) {
  state.editingConversationId = id;
}

export function getEditingConversation() {
  return state.editingConversationId;
}

export function setProviderSelection(selection) {
  state.providerSelection = {
    ...state.providerSelection,
    ...selection,
  };
}

export function getProviderSelection() {
  return state.providerSelection;
}

export function resetProviderSelection() {
  state.providerSelection = { providerId: null, model: null };
}

export function setCurrentUser(user) {
  state.currentUser = user;
}

export function getCurrentUser() {
  return state.currentUser;
}

export function setAdminUsers(list) {
  state.admin.users = list;
}

export function getAdminUsers() {
  return state.admin.users;
}

export function setAdminUsage(list) {
  state.admin.usage = list;
}

export function getAdminUsage() {
  return state.admin.usage;
}

export function setAdminAudit(list) {
  state.admin.audit = list;
}

export function getAdminAudit() {
  return state.admin.audit;
}

export function setAdminInvites(list) {
  state.admin.invites = list;
}

export function getSelectedAdminUsers() {
  return state.admin.selectedUserIds || [];
}

export function setSelectedAdminUsers(ids) {
  state.admin.selectedUserIds = Array.from(new Set(ids.filter(Boolean)));
}

export function toggleAdminUserSelection(id, selected) {
  const current = new Set(state.admin.selectedUserIds || []);
  if (selected) {
    current.add(id);
  } else {
    current.delete(id);
  }
  state.admin.selectedUserIds = Array.from(current);
}

export function clearSelectedAdminUsers() {
  state.admin.selectedUserIds = [];
}

export function recordMessageHeight(id, height) {
  if (!id || height <= 0) return;
  virtualization.heights[id] = height;
  recalcAverageHeight(height);
}

export function getAverageMessageHeight() {
  return virtualization.averageHeight;
}

export function getVirtualBuffer() {
  return virtualization.buffer;
}

export function resetVirtualMeasurements() {
  virtualization.heights = {};
  virtualization.averageHeight = 120;
}

export function getAdminInvites() {
  return state.admin.invites;
}
