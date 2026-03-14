import { useState, useCallback, useEffect } from "react";
import ChatInterface from "./components/ChatInterface.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ThemeToggle from "./components/ThemeToggle.jsx";
import { getDocuments } from "./api";
import "./App.css";

export default function App() {
  const [documents, setDocuments] = useState([]);
  const [sessionId, setSessionId] = useState(null);

  useEffect(() => {
    getDocuments()
      .then(setDocuments)
      .catch(() => {});
  }, []);

  const handleUploadComplete = useCallback((doc) => {
    setDocuments((prev) => [...prev, doc]);
  }, []);

  const handleDocumentDeleted = useCallback((docId) => {
    setDocuments((prev) => prev.filter((d) => d.document_id !== docId));
  }, []);

  return (
    <div className="app">
      <Sidebar
        documents={documents}
        onDocumentDeleted={handleDocumentDeleted}
        onUploadComplete={handleUploadComplete}
      />
      <main className="main-panel">
        <header className="app-header">
          <div className="app-logo">
            <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <rect width="32" height="32" rx="8" fill="#667eea" />
              <path d="M8 11h16M8 16h10M8 21h13" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
              <circle cx="24" cy="21" r="4" fill="#48bb78" stroke="#667eea" strokeWidth="1.5" />
              <path d="M22.5 21l1 1 2-2" stroke="#fff" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <h1>O2C AI Suite</h1>
          </div>
          <span className="subtitle">Order-to-Cash &middot; Multi-Agent AI</span>
          <div className="header-actions">
            <ThemeToggle />
          </div>
        </header>
        <ChatInterface
          sessionId={sessionId}
          setSessionId={setSessionId}
        />
      </main>
    </div>
  );
}
