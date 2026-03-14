const API_BASE = "/api";

export async function uploadDocument(file) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const text = await res.text();
    try {
      const err = JSON.parse(text);
      throw new Error(err.detail || "Upload failed");
    } catch (e) {
      if (e.message && e.message !== "Upload failed") throw e;
      throw new Error(text || "Upload failed");
    }
  }
  return res.json();
}

export async function sendMessage(message, sessionId) {
  let res;
  try {
    res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  } catch (err) {
    throw new Error("Cannot reach the server. Is the backend running?");
  }

  if (!res.ok) {
    const text = await res.text();
    let detail = `Server error (${res.status})`;
    try {
      const err = JSON.parse(text);
      detail = err.detail || detail;
    } catch {}
    throw new Error(detail);
  }

  const text = await res.text();
  if (!text) throw new Error("Empty response from server");
  return JSON.parse(text);
}

export async function resumeChat(threadId, approved, comment = "") {
  let res;
  try {
    res = await fetch(`${API_BASE}/chat/resume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId, approved, comment }),
    });
  } catch (err) {
    throw new Error("Cannot reach the server. Is the backend running?");
  }

  if (!res.ok) {
    const text = await res.text();
    let detail = `Server error (${res.status})`;
    try {
      const err = JSON.parse(text);
      detail = err.detail || detail;
    } catch {}
    throw new Error(detail);
  }

  const text = await res.text();
  if (!text) throw new Error("Empty response from server");
  return JSON.parse(text);
}

export async function getDocuments() {
  const res = await fetch(`${API_BASE}/documents`);
  if (!res.ok) throw new Error("Failed to fetch documents");
  return res.json();
}

export async function deleteDocument(documentId) {
  const res = await fetch(`${API_BASE}/documents/${documentId}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error("Failed to delete document");
  return res.json();
}

export async function getStats() {
  const res = await fetch(`${API_BASE}/stats`);
  if (!res.ok) throw new Error("Failed to fetch stats");
  return res.json();
}
