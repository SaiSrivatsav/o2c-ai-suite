import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { sendMessage } from "../api";
import "./ChatInterface.css";

export default function ChatInterface({ hasDocuments, sessionId, setSessionId }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef();
  const inputRef = useRef();

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setLoading(true);

    try {
      const res = await sendMessage(text, sessionId);
      if (!sessionId) setSessionId(res.session_id);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "error", content: err.message },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleNewChat = () => {
    setMessages([]);
    setSessionId(null);
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>Chat</h2>
        {messages.length > 0 && (
          <button className="btn-new-chat" onClick={handleNewChat}>
            New Chat
          </button>
        )}
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            {hasDocuments
              ? "Ask a question about your uploaded documents."
              : "Upload a document to start chatting."}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-label">
              {msg.role === "user" ? "You" : msg.role === "error" ? "Error" : "AI"}
            </div>
            <div className="message-body">
              {msg.role === "assistant" ? (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              ) : (
                <p>{msg.content}</p>
              )}
            </div>
            {msg.sources && msg.sources.length > 0 && (
              <div className="sources">
                <span className="sources-label">Sources:</span>
                {msg.sources.map((s, j) => (
                  <span key={j} className="source-tag">
                    {s.document}
                    {s.page != null ? ` (p.${s.page})` : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="message assistant">
            <div className="message-label">AI</div>
            <div className="message-body typing">
              <span /><span /><span />
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="chat-input-area">
        <input
          ref={inputRef}
          type="text"
          placeholder={
            hasDocuments
              ? "Ask a question about your documents..."
              : "Upload a document first"
          }
          value={input}
          disabled={!hasDocuments || loading}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <button
          onClick={handleSend}
          disabled={!hasDocuments || loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
