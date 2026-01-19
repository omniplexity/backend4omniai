// OmniAI Actions

window.appActions = window.appActions || {};

window.appActions.rerunFromAssistantMessage = async function rerunFromAssistantMessage(assistantMsgId) {
  const threadId = window.state.activeThreadId;
  const assistantMsg = window.state.messagesById[assistantMsgId];
  if (!assistantMsg) return;

  const run = assistantMsg.metadata?.run || window.state.run; // fallback
  const userMsgId = assistantMsg.metadata?.source_user_message_id
    || inferUserMessageIdForAssistant(assistantMsgId, threadId);

  const userMsg = window.state.messagesById[userMsgId];
  if (!userMsg?.content) return;

  // Use your existing "send" pipeline but override run settings:
  return window.appActions.sendMessage({
    threadId,
    content: userMsg.content,
    runOverride: run,
    mode: "rerun",          // optional label for analytics/UI
    source: { assistantMsgId, userMsgId }
  });
};

function inferUserMessageIdForAssistant(assistantMsgId, threadId) {
  const msgs = window.state.threadsById[threadId]?.messages || [];
  const idx = msgs.findIndex(m => m.id === assistantMsgId);
  for (let i = idx - 1; i >= 0; i--) {
    if (msgs[i].role === "user") return msgs[i].id;
  }
  return null;
}

// Assuming sendMessage is defined elsewhere, or we need to implement it here
// For now, placeholder
window.appActions.sendMessage = async function({ threadId, content, runOverride, mode, source }) {
  // This should integrate with the existing send logic
  console.log('Sending message with rerun:', { threadId, content, runOverride, mode, source });
  // TODO: Implement actual send logic
};