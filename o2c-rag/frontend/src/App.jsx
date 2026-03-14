import { useState, useCallback, useEffect } from "react";
import FileUpload from "./components/FileUpload.jsx";
import ChatInterface from "./components/ChatInterface.jsx";
import Sidebar from "./components/Sidebar.jsx";
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
      <Sidebar documents={documents} onDocumentDeleted={handleDocumentDeleted} />
      <main className="main-panel">
        <header className="app-header">
          <h1>O2C RAG Bot</h1>
          <span className="subtitle">
            Upload documents &middot; Ask questions &middot; Get grounded answers
          </span>
        </header>
        <FileUpload onUploadComplete={handleUploadComplete} />
        <ChatInterface
          hasDocuments={documents.length > 0}
          sessionId={sessionId}
          setSessionId={setSessionId}
        />
      </main>
    </div>
  );
}
