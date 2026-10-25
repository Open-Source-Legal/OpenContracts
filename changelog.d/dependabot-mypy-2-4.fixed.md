- Fixed the optional conversation-manager check in anonymous WebSocket chats
  so it remains compatible with mypy 2.4 without expanding the agent protocol.
  Pinned the existing `preshed` dependency to 3.0.13 so fresh CI image builds
  can load spaCy models instead of failing with the 3.0.14 tokenizer regression.
