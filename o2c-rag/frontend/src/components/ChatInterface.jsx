import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sendMessage, resumeChat } from "../api";
import ApprovalCard from "./ApprovalCard.jsx";
import "./ChatInterface.css";

export default function ChatInterface({ sessionId, setSessionId }) {
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
          agent: res.agent || "",
          approval_request: res.approval_request || null,
          thread_id: res.session_id,
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

  const handleApproval = async (msgIndex, approved, comment) => {
    const msg = messages[msgIndex];
    if (!msg?.thread_id) return;

    setLoading(true);

    // Update the message to show the decision inline
    setMessages((prev) =>
      prev.map((m, i) =>
        i === msgIndex
          ? {
              ...m,
              approval_request: null,
              content:
                m.content +
                `\n\n---\n*${approved ? "Approved" : "Rejected"}${comment ? `: ${comment}` : ""}*`,
            }
          : m
      )
    );

    try {
      const res = await resumeChat(msg.thread_id, approved, comment);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources,
          agent: res.agent || "",
          approval_request: res.approval_request || null,
          thread_id: res.session_id,
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

  const agentLabel = (agent) => {
    if (!agent) return "AI";
    const map = {
      customer_agent: "Customer",
      order_agent: "Orders",
      fulfillment_agent: "Fulfillment",
      finance_agent: "Finance",
      analytics_agent: "Analytics",
      rag_agent: "Documents",
    };
    return map[agent] || "AI";
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
            <div className="empty-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
            </div>
            <h3>O2C AI Suite</h3>
            <p>Ask about customers, orders, deliveries, invoices, payments, or query your uploaded documents.</p>
            <div className="empty-suggestions">
              <span className="suggestion">"Show me overdue invoices"</span>
              <span className="suggestion">"Create a sales order for customer C001"</span>
              <span className="suggestion">"What's the revenue this quarter?"</span>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="message-label">
              {msg.role === "user" ? "You" : msg.role === "error" ? "Error" : (
                <>
                  {agentLabel(msg.agent)}
                  {msg.agent && <span className="agent-badge">{msg.agent.replace("_agent", "")}</span>}
                </>
              )}
            </div>
            <div className="message-body">
              {msg.role === "assistant" ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
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
            {msg.approval_request && (
              <ApprovalCard
                data={msg.approval_request}
                onRespond={(approved, comment) => handleApproval(i, approved, comment)}
                disabled={loading}
              />
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
          placeholder="Ask about your O2C data or documents..."
          value={input}
          disabled={loading}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
        />
        <button
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
}
