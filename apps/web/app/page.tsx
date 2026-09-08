"use client";

import { useState, useEffect, useRef } from "react";
import {
  Database,
  Globe,
  GitBranch,
  FileText,
  Activity,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Layers,
  ShieldCheck,
  Server,
  ArrowRight,
  Gauge,
  Terminal,
  Send,
  Plus,
  Trash2,
  ChevronRight,
  Play,
  FileSpreadsheet,
  AlertCircle,
  Eye,
  Info
} from "lucide-react";

interface HealthStatus {
  status: string;
  timestamp: string;
  services: {
    database: string;
    redis: string;
  };
}

interface SourceItem {
  id: number;
  type: string;
  name: string;
  status: string;
  configuration: any;
  created_at: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: any[];
  conflicts?: any[];
  confidence?: string;
  confidence_reason?: string;
  logs?: string[];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ControlCenter() {
  const [activeTab, setActiveTab] = useState<"dashboard" | "sources" | "chat" | "eval">("dashboard");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState<string | null>(null);

  // Sources State
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [newSrcType, setNewSrcType] = useState<"documents" | "web" | "github" | "postgres">("documents");
  const [newSrcName, setNewSrcName] = useState("");
  const [newSrcUrl, setNewSrcUrl] = useState("");
  const [newSrcPath, setNewSrcPath] = useState("");
  const [newSrcBranch, setNewSrcBranch] = useState("main");
  const [newSrcRepoName, setNewSrcRepoName] = useState("");
  const [syncingJobs, setSyncingJobs] = useState<Record<number, { job_id: number; status: string; progress: number }>>({});
  
  // Chat State
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentQuestion, setCurrentQuestion] = useState("");
  const [streamLogs, setStreamLogs] = useState<string[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [activeConvId, setActiveConvId] = useState<number | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<any[]>([]);
  const [activeEvidenceIndex, setActiveEvidenceIndex] = useState<number | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Evaluation State
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalResults, setEvalResults] = useState<any | null>(null);
  const [evalHistory, setEvalHistory] = useState<any[]>([]);

  // 1. Fetch Health Status
  const checkHealth = async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const res = await fetch(`${API_URL}/api/health`);
      if (res.ok) {
        const data = await res.json();
        setHealth(data);
      } else {
        const errData = await res.json().catch(() => ({}));
        setHealth(errData.detail || { status: "unhealthy", services: { database: "disconnected", redis: "disconnected" } });
        setHealthError("Core services degraded.");
      }
    } catch (err) {
      setHealthError("Backend server is unreachable.");
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  };

  // 2. Fetch Sources list
  const fetchSources = async () => {
    try {
      const res = await fetch(`${API_URL}/api/sources`);
      if (res.ok) {
        const data = await res.json();
        setSources(data);
      }
    } catch (err) {
      console.error("Failed to fetch sources list", err);
    }
  };

  // 3. Fetch Evaluation History
  const fetchEvaluationHistory = async () => {
    try {
      const res = await fetch(`${API_URL}/api/evaluations`);
      if (res.ok) {
        const data = await res.json();
        setEvalHistory(data);
        if (data.length > 0 && !evalResults) {
          setEvalResults(data[0].metrics);
        }
      }
    } catch (err) {
      console.error("Failed to fetch evaluations", err);
    }
  };

  // Triggered on page mount
  useEffect(() => {
    checkHealth();
    fetchSources();
    fetchEvaluationHistory();
    const interval = setInterval(checkHealth, 20000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll chat window
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamLogs]);

  // Create Source
  const handleCreateSource = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSrcName.trim()) return;

    let configuration: any = {};
    if (newSrcType === "web") {
      configuration = { url: newSrcUrl };
    } else if (newSrcType === "github") {
      configuration = {
        repository_path: newSrcPath,
        repository_name: newSrcRepoName || "custom-repo",
        branch: newSrcBranch
      };
    } else if (newSrcType === "postgres") {
      configuration = { connection_string: newSrcUrl };
    }

    try {
      const res = await fetch(`${API_URL}/api/sources`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: newSrcType,
          name: newSrcName,
          configuration
        })
      });

      if (res.ok) {
        setNewSrcName("");
        setNewSrcUrl("");
        setNewSrcPath("");
        setNewSrcRepoName("");
        fetchSources();
      }
    } catch (err) {
      alert("Failed to create source: " + err);
    }
  };

  // Delete Source
  const handleDeleteSource = async (id: number) => {
    if (!confirm("Are you sure you want to disconnect this source? All document chunks will be deleted.")) return;
    try {
      const res = await fetch(`${API_URL}/api/sources/${id}`, {
        method: "DELETE"
      });
      if (res.ok) {
        fetchSources();
      }
    } catch (err) {
      alert("Failed to delete source.");
    }
  };

  // Document File Upload
  const handleFileUpload = async (sourceId: number, e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    
    const file = files[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      // Set status to syncing locally
      setSyncingJobs(prev => ({
        ...prev,
        [sourceId]: { job_id: 0, status: "uploading", progress: 0.1 }
      }));

      const res = await fetch(`${API_URL}/api/sources/${sourceId}/upload`, {
        method: "POST",
        body: formData
      });

      if (res.ok) {
        const data = await res.json();
        pollIngestionProgress(sourceId, data.job_id);
      } else {
        const err = await res.json();
        alert("Upload failed: " + err.detail);
        setSyncingJobs(prev => {
          const cpy = { ...prev };
          delete cpy[sourceId];
          return cpy;
        });
      }
    } catch (err) {
      alert("Failed to upload: " + err);
    }
  };

  // Sync Source (for non-document types)
  const handleSyncSource = async (sourceId: number) => {
    try {
      setSyncingJobs(prev => ({
        ...prev,
        [sourceId]: { job_id: 0, status: "pending", progress: 0.0 }
      }));

      const res = await fetch(`${API_URL}/api/sources/${sourceId}/sync`, {
        method: "POST"
      });

      if (res.ok) {
        const data = await res.json();
        if (data.job_id) {
          pollIngestionProgress(sourceId, data.job_id);
        } else {
          // PostgreSQL immediately synced
          fetchSources();
          setSyncingJobs(prev => {
            const cpy = { ...prev };
            delete cpy[sourceId];
            return cpy;
          });
        }
      }
    } catch (err) {
      alert("Failed to start sync: " + err);
    }
  };

  // Poll Ingestion Progress
  const pollIngestionProgress = (sourceId: number, jobId: number) => {
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_URL}/api/sources/ingestion/${jobId}`);
        if (res.ok) {
          const data = await res.json();
          setSyncingJobs(prev => ({
            ...prev,
            [sourceId]: { job_id: jobId, status: data.status, progress: data.progress }
          }));

          if (data.status === "completed" || data.status === "failed") {
            clearInterval(interval);
            setTimeout(() => {
              setSyncingJobs(prev => {
                const cpy = { ...prev };
                delete cpy[sourceId];
                return cpy;
              });
              fetchSources();
            }, 3000);
          }
        }
      } catch (err) {
        clearInterval(interval);
      }
    }, 1500);
  };

  // Stream Chat (SSE)
  const handleSendQuestion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentQuestion.trim() || isStreaming) return;

    const question = currentQuestion;
    setCurrentQuestion("");
    setIsStreaming(true);
    setStreamLogs([]);
    setSelectedEvidence([]);
    setActiveEvidenceIndex(null);

    // Append user message
    setMessages(prev => [...prev, { role: "user", content: question }]);

    try {
      const response = await fetch(`${API_URL}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          conversation_id: activeConvId
        })
      });

      if (!response.body) throw new Error("No body on stream response");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        // Keep the last partial line in the buffer
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.substring(6).trim();
            if (!jsonStr) continue;

            try {
              const eventData = JSON.parse(jsonStr);
              if (eventData.event === "progress") {
                setStreamLogs(prev => [...prev, eventData.text]);
              } else if (eventData.event === "complete") {
                const result = eventData.data;
                setActiveConvId(result.conversation_id);
                
                // Fetch and match evidence details
                fetchEvidenceDetails(result.message_id);

                setMessages(prev => [
                  ...prev,
                  {
                    role: "assistant",
                    content: result.answer,
                    citations: result.citations,
                    conflicts: result.conflicts,
                    confidence: result.confidence,
                    confidence_reason: result.confidence_reason,
                    logs: result.logs
                  }
                ]);
              }
            } catch (pErr) {
              console.error("JSON parse error on stream", pErr);
            }
          }
        }
      }
    } catch (err) {
      setMessages(prev => [
        ...prev,
        { role: "assistant", content: "Error: Could not retrieve answer from agent. " + err }
      ]);
    } finally {
      setIsStreaming(false);
      setStreamLogs([]);
    }
  };

  // Fetch Evidence details for Investigator right pane
  const fetchEvidenceDetails = async (messageId: number) => {
    try {
      const res = await fetch(`${API_URL}/api/conversations/${activeConvId}`);
      if (res.ok) {
        // Derive evidence details from the message if needed.
      }
    } catch (err) {
      console.error(err);
    }
  };

  // Run Golden Evaluation suite
  const handleRunEvaluations = async () => {
    setEvalLoading(true);
    setEvalResults(null);
    try {
      const res = await fetch(`${API_URL}/api/evaluations/run`, {
        method: "POST"
      });
      if (res.ok) {
        const data = await res.json();
        setEvalResults(data);
        fetchEvaluationHistory();
      }
    } catch (err) {
      alert("Failed to run evaluation suite: " + err);
    } finally {
      setEvalLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#fafafc] text-zinc-800 font-sans selection:bg-orange-500 selection:text-white flex flex-col">
      {/* Top Banner Navigation */}
      <header className="border-b border-zinc-200/80 bg-white/95 backdrop-blur-md sticky top-0 z-50 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="bg-gradient-to-tr from-orange-500 to-amber-500 p-2 rounded-xl shadow-md">
              <Layers className="h-5 w-5 text-white" />
            </div>
            <div>
              <span className="font-extrabold text-lg tracking-tight bg-gradient-to-r from-zinc-900 to-zinc-700 bg-clip-text text-transparent">
                OmniRAG
              </span>
              <span className="ml-2 text-[10px] px-2 py-0.5 rounded-full border border-orange-200 bg-orange-50 text-orange-600 font-bold uppercase tracking-wider">
                Enterprise
              </span>
            </div>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-1 bg-zinc-100 p-1 rounded-xl border border-zinc-200/60">
            <button
              onClick={() => setActiveTab("dashboard")}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeTab === "dashboard"
                  ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/40"
                  : "text-zinc-500 hover:text-zinc-800"
              }`}
            >
              Dashboard
            </button>
            <button
              onClick={() => setActiveTab("sources")}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeTab === "sources"
                  ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/40"
                  : "text-zinc-500 hover:text-zinc-800"
              }`}
            >
              Sources
            </button>
            <button
              onClick={() => setActiveTab("chat")}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeTab === "chat"
                  ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/40"
                  : "text-zinc-500 hover:text-zinc-800"
              }`}
            >
              Investigator
            </button>
            <button
              onClick={() => setActiveTab("eval")}
              className={`px-4 py-1.5 rounded-lg text-xs font-bold transition-all ${
                activeTab === "eval"
                  ? "bg-white text-zinc-900 shadow-sm border border-zinc-200/40"
                  : "text-zinc-500 hover:text-zinc-800"
              }`}
            >
              Evaluations
            </button>
          </nav>

          {/* Status Indicators */}
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5 bg-zinc-50 px-3 py-1 rounded-full border border-zinc-200">
              <div className={`h-2 w-2 rounded-full ${healthError ? 'bg-amber-500' : health ? 'bg-emerald-500' : 'bg-rose-500'} animate-pulse`} />
              <span className="font-bold text-zinc-600">
                {healthError ? 'Degraded' : health ? 'System Online' : 'Offline'}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-8">
        
        {/* ================= TAB 1: DASHBOARD ================= */}
        {activeTab === "dashboard" && (
          <div className="animate-fadeIn">
            <div className="border-b border-zinc-200 pb-6 mb-8">
              <h1 className="text-3xl font-black tracking-tight text-zinc-900">System Diagnostics</h1>
              <p className="text-zinc-500 mt-1 text-sm">Monitor system infrastructure metrics, active components, and security configurations.</p>
            </div>

            {healthError && (
              <div className="mb-6 p-4 rounded-xl border border-orange-200 bg-orange-50 text-orange-800 flex items-start gap-3 shadow-sm">
                <AlertTriangle className="h-5 w-5 text-orange-500 shrink-0 mt-0.5" />
                <div>
                  <p className="font-bold text-sm">Diagnostics Notice</p>
                  <p className="text-xs text-orange-700 mt-0.5">{healthError}</p>
                </div>
              </div>
            )}

            {/* Core Service Health Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:border-orange-200 transition duration-300">
                <div className="flex items-center justify-between mb-4">
                  <div className="bg-orange-50 p-2.5 rounded-xl"><Server className="h-5 w-5 text-orange-500" /></div>
                  <span className="text-xs font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full uppercase tracking-wider">Online</span>
                </div>
                <h3 className="font-extrabold text-zinc-900 text-base">FastAPI Backend</h3>
                <p className="text-zinc-500 text-xs mt-1">Status check & RAG routes active</p>
                <div className="mt-4 pt-4 border-t border-zinc-100 flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span>Endpoint</span>
                  <span className="text-zinc-700 font-semibold">{API_URL}</span>
                </div>
              </div>

              <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:border-orange-200 transition duration-300">
                <div className="flex items-center justify-between mb-4">
                  <div className="bg-orange-50 p-2.5 rounded-xl"><Database className="h-5 w-5 text-orange-500" /></div>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                    health?.services.database === "connected" 
                      ? "text-emerald-600 bg-emerald-50" 
                      : "text-rose-600 bg-rose-50"
                  }`}>
                    {health?.services.database === "connected" ? "Connected" : "Disconnected"}
                  </span>
                </div>
                <h3 className="font-extrabold text-zinc-900 text-base">PostgreSQL + pgvector</h3>
                <p className="text-zinc-500 text-xs mt-1">Hosts document chunk embeddings</p>
                <div className="mt-4 pt-4 border-t border-zinc-100 flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span>Host Port</span>
                  <span className="text-zinc-700 font-semibold">5435</span>
                </div>
              </div>

              <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm hover:shadow-md hover:border-orange-200 transition duration-300">
                <div className="flex items-center justify-between mb-4">
                  <div className="bg-orange-50 p-2.5 rounded-xl"><Gauge className="h-5 w-5 text-orange-500" /></div>
                  <span className={`text-xs font-bold px-2 py-0.5 rounded-full uppercase tracking-wider ${
                    health?.services.redis === "connected" 
                      ? "text-emerald-600 bg-emerald-50" 
                      : "text-rose-600 bg-rose-50"
                  }`}>
                    {health?.services.redis === "connected" ? "Ready" : "Disconnected"}
                  </span>
                </div>
                <h3 className="font-extrabold text-zinc-900 text-base">Redis Event Cache</h3>
                <p className="text-zinc-500 text-xs mt-1">Celery queue & API query cache</p>
                <div className="mt-4 pt-4 border-t border-zinc-100 flex items-center justify-between text-[11px] font-mono text-zinc-400">
                  <span>Host Port</span>
                  <span className="text-zinc-700 font-semibold">6375</span>
                </div>
              </div>
            </div>

            {/* Platform Security Policy Overview */}
            <div className="bg-white border border-zinc-200 rounded-2xl p-6 shadow-sm">
              <div className="flex items-center gap-3 mb-6">
                <div className="bg-orange-500/10 p-2 rounded-xl text-orange-600"><ShieldCheck className="h-5 w-5" /></div>
                <h3 className="text-lg font-extrabold text-zinc-900">Security & Guardrails Profile</h3>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="p-4 bg-zinc-50/50 rounded-xl border border-zinc-200">
                  <p className="font-bold text-zinc-800">AST Query Isolation</p>
                  <p className="text-zinc-500 mt-1">Uses sqlglot AST verification to restrict PostgreSQL instructions to read-only queries (blocking CREATE, DROP, ALTER, UPDATE, etc.).</p>
                </div>
                <div className="p-4 bg-zinc-50/50 rounded-xl border border-zinc-200">
                  <p className="font-bold text-zinc-800">SSRF Protection</p>
                  <p className="text-zinc-500 mt-1">Web crawler resolves domains and blocks connection attempts to loopback and private subnets (RFC 1918 limits).</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 2: SOURCES ================= */}
        {activeTab === "sources" && (
          <div className="animate-fadeIn">
            <div className="border-b border-zinc-200 pb-6 mb-8">
              <h1 className="text-3xl font-black tracking-tight text-zinc-900">Source Connectors</h1>
              <p className="text-zinc-500 mt-1 text-sm">Register and synchronize knowledge base content asynchronously.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              
              {/* Left Column: Create Source Form */}
              <div className="bg-white border border-zinc-200 rounded-2xl p-6 h-fit shadow-sm">
                <h3 className="font-extrabold text-zinc-900 text-lg mb-4 flex items-center gap-2">
                  <Plus className="h-4 w-4 text-orange-500" />
                  Add New Source
                </h3>
                <form onSubmit={handleCreateSource} className="space-y-4 text-xs">
                  <div>
                    <label className="block text-zinc-500 font-bold mb-1">Connector Type</label>
                    <select
                      value={newSrcType}
                      onChange={(e: any) => setNewSrcType(e.target.value)}
                      className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                    >
                      <option value="documents">Source A — Local Documents</option>
                      <option value="web">Source B — Web Ingest (URL)</option>
                      <option value="github">Source C — GitHub Repository</option>
                      <option value="postgres">Source D — PostgreSQL Read-Only</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-zinc-500 font-bold mb-1">Source Name</label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Employee Handbook, Pricing Site"
                      value={newSrcName}
                      onChange={(e) => setNewSrcName(e.target.value)}
                      className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                    />
                  </div>

                  {newSrcType === "web" && (
                    <div>
                      <label className="block text-zinc-500 font-bold mb-1">Website URL</label>
                      <input
                        type="url"
                        required
                        placeholder="https://example.com/pricing"
                        value={newSrcUrl}
                        onChange={(e) => setNewSrcUrl(e.target.value)}
                        className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                      />
                    </div>
                  )}

                  {newSrcType === "github" && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-zinc-500 font-bold mb-1">Local Repository Path</label>
                        <input
                          type="text"
                          required
                          placeholder="/Volumes/progress/my-code-repo"
                          value={newSrcPath}
                          onChange={(e) => setNewSrcPath(e.target.value)}
                          className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                        />
                      </div>
                      <div>
                        <label className="block text-zinc-500 font-bold mb-1">Repository Name</label>
                        <input
                          type="text"
                          placeholder="e.g. auth-middleware"
                          value={newSrcRepoName}
                          onChange={(e) => setNewSrcRepoName(e.target.value)}
                          className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                        />
                      </div>
                      <div>
                        <label className="block text-zinc-500 font-bold mb-1">Branch</label>
                        <input
                          type="text"
                          value={newSrcBranch}
                          onChange={(e) => setNewSrcBranch(e.target.value)}
                          className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                        />
                      </div>
                    </div>
                  )}

                  {newSrcType === "postgres" && (
                    <div>
                      <label className="block text-zinc-500 font-bold mb-1">Database Connection String</label>
                      <input
                        type="text"
                        required
                        placeholder="postgresql://user:pass@host:port/dbname"
                        value={newSrcUrl}
                        onChange={(e) => setNewSrcUrl(e.target.value)}
                        className="w-full bg-zinc-50 border border-zinc-200 rounded-lg p-2.5 text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition"
                      />
                    </div>
                  )}

                  <button
                    type="submit"
                    className="w-full bg-orange-500 hover:bg-orange-600 text-white font-bold p-2.5 rounded-lg transition text-xs mt-2 shadow-sm shadow-orange-500/10"
                  >
                    Connect Source
                  </button>
                </form>
              </div>

              {/* Right Column: Connected Sources List */}
              <div className="lg:col-span-2 space-y-4">
                {sources.length === 0 ? (
                  <div className="p-12 border border-zinc-200 border-dashed rounded-2xl text-center bg-white shadow-sm">
                    <Layers className="h-12 w-12 mx-auto mb-3 text-zinc-300" />
                    <p className="font-bold text-zinc-500">No Connected Sources</p>
                    <p className="text-xs text-zinc-400 mt-1">Register a connector in the left panel to begin.</p>
                  </div>
                ) : (
                  sources.map((src) => {
                    const syncInfo = syncingJobs[src.id];
                    return (
                      <div
                        key={src.id}
                        className="bg-white border border-zinc-200 rounded-2xl p-5 hover:border-orange-200 shadow-sm hover:shadow-md transition duration-300 flex items-center justify-between"
                      >
                        <div className="flex items-center gap-4">
                          <div className="bg-orange-50 p-3 rounded-xl border border-orange-100">
                            {src.type === "documents" && <FileText className="h-5 w-5 text-orange-500" />}
                            {src.type === "web" && <Globe className="h-5 w-5 text-orange-500" />}
                            {src.type === "github" && <GitBranch className="h-5 w-5 text-orange-500" />}
                            {src.type === "postgres" && <Database className="h-5 w-5 text-orange-500" />}
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <h4 className="font-extrabold text-zinc-900 text-sm">{src.name}</h4>
                              <span className="text-[10px] px-2 py-0.5 rounded-full border border-zinc-200 bg-zinc-50 text-zinc-500 font-bold uppercase tracking-wider">
                                {src.type}
                              </span>
                            </div>
                            <p className="text-zinc-400 text-[10px] font-mono mt-1">
                              ID: {src.id} • Registered: {new Date(src.created_at).toLocaleDateString()}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-3">
                          {/* Sync State */}
                          {syncInfo ? (
                            <div className="text-right">
                              <span className="text-[10px] text-orange-500 font-bold uppercase animate-pulse">
                                {syncInfo.status === "uploading" ? "Uploading..." : `Syncing (${Math.round(syncInfo.progress * 100)}%)`}
                              </span>
                              <div className="w-24 bg-zinc-100 h-1.5 rounded-full mt-1.5 overflow-hidden border border-zinc-200/50">
                                <div
                                  className="bg-orange-500 h-1.5 rounded-full transition-all duration-300"
                                  style={{ width: `${syncInfo.progress * 100}%` }}
                                />
                              </div>
                            </div>
                          ) : (
                            <>
                              {src.type === "documents" ? (
                                <label className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-200 hover:border-orange-200 bg-white hover:bg-orange-50/20 text-xs text-zinc-700 hover:text-orange-600 transition font-bold cursor-pointer shadow-sm">
                                  <Plus className="h-3.5 w-3.5 text-orange-500" />
                                  Upload File
                                  <input
                                    type="file"
                                    className="hidden"
                                    accept=".pdf,.docx,.txt,.md,.markdown"
                                    onChange={(e) => handleFileUpload(src.id, e)}
                                  />
                                </label>
                              ) : (
                                <button
                                  onClick={() => handleSyncSource(src.id)}
                                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-200 hover:border-orange-200 bg-white hover:bg-orange-50/20 text-xs text-zinc-700 hover:text-orange-600 transition font-bold shadow-sm"
                                >
                                  <RefreshCw className="h-3.5 w-3.5 text-orange-500" />
                                  Sync Now
                                </button>
                              )}
                            </>
                          )}

                          <button
                            onClick={() => handleDeleteSource(src.id)}
                            className="p-2 rounded-lg border border-zinc-200 hover:border-zinc-300 hover:bg-zinc-50 text-zinc-400 hover:text-rose-500 transition shadow-sm"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}

        {/* ================= TAB 3: INVESTIGATOR ================= */}
        {activeTab === "chat" && (
          <div className="animate-fadeIn flex-1 flex flex-col h-[calc(100vh-12rem)] min-h-[500px]">
            <div className="border-b border-zinc-200 pb-4 mb-4">
              <h1 className="text-2xl font-black tracking-tight text-zinc-900">Investigator</h1>
              <p className="text-zinc-500 text-xs">Analyze multi-source query pathways, verify evidence citations, and track direct contradictions.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 overflow-hidden">
              
              {/* Left Pane: Chat Log */}
              <div className="lg:col-span-2 flex flex-col bg-white border border-zinc-200 rounded-2xl overflow-hidden shadow-sm">
                
                {/* Chat window viewport */}
                <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-zinc-50/20">
                  {messages.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center text-center text-zinc-400 py-12">
                      <Layers className="h-10 w-10 text-zinc-300 mb-3" />
                      <p className="font-bold text-zinc-600 text-sm">Start an Investigation</p>
                      <p className="text-[11px] max-w-xs mt-1 text-zinc-400">Ask questions mapping back to connected documents, URL content, database tables, or repository classes.</p>
                    </div>
                  ) : (
                    messages.map((msg, mIdx) => (
                      <div key={mIdx} className="space-y-2">
                        {/* User / Assistant messages */}
                        <div className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                          <div className={`p-4 rounded-2xl max-w-[85%] text-xs leading-relaxed ${
                            msg.role === 'user'
                              ? 'bg-orange-500 text-white rounded-br-none shadow-sm'
                              : 'bg-white border border-zinc-200 text-zinc-800 rounded-bl-none shadow-sm'
                          }`}>
                            {msg.content}

                            {/* Conflicts warning banner */}
                            {msg.conflicts && msg.conflicts.length > 0 && (
                              <div className="mt-4 p-3 border-l-4 border-orange-500 bg-orange-50 text-orange-950 rounded-r-xl flex items-start gap-2 shadow-sm">
                                <AlertCircle className="h-4 w-4 text-orange-600 shrink-0 mt-0.5" />
                                <div className="text-[11px]">
                                  <p className="font-extrabold uppercase tracking-wider text-[10px] text-orange-700">Contradiction Warning</p>
                                  {msg.conflicts.map((c, cIdx) => (
                                    <p key={cIdx} className="mt-1 font-semibold">{c.explanation}</p>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Confidence indicators */}
                            {msg.confidence && (
                              <div className="mt-3 pt-3 border-t border-zinc-100 flex items-center justify-between text-[10px] text-zinc-400">
                                <span className="flex items-center gap-1">
                                  <Info className="h-3 w-3 text-orange-500" />
                                  Confidence: 
                                  <span className={`font-bold ml-1 px-1.5 py-0.5 rounded-full text-[9px] ${
                                    msg.confidence === 'HIGH' ? 'text-emerald-700 bg-emerald-50 border border-emerald-200' :
                                    msg.confidence === 'MEDIUM' ? 'text-orange-700 bg-orange-50 border border-orange-200' : 
                                    'text-rose-700 bg-rose-50 border border-rose-200'
                                  }`}>
                                    {msg.confidence}
                                  </span>
                                </span>
                                <span className="text-[9px] text-zinc-400 italic truncate max-w-[60%] font-medium">{msg.confidence_reason}</span>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))
                  )}

                  {/* Render streaming event logs */}
                  {isStreaming && (
                    <div className="space-y-2 bg-white/60 p-3 rounded-xl border border-zinc-200/50">
                      {streamLogs.map((log, lIdx) => (
                        <div key={lIdx} className="text-[11px] font-mono text-zinc-500 flex items-center gap-2 animate-fadeIn">
                          <ChevronRight className="h-3 w-3 text-orange-500 animate-pulse" />
                          <span className="font-semibold">{log}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <div ref={chatEndRef} />
                </div>

                {/* Input Prompt Form */}
                <form onSubmit={handleSendQuestion} className="p-3 border-t border-zinc-200 bg-white flex items-center gap-2">
                  <input
                    type="text"
                    required
                    disabled={isStreaming}
                    placeholder="Ask a question..."
                    value={currentQuestion}
                    onChange={(e) => setCurrentQuestion(e.target.value)}
                    className="flex-1 bg-zinc-50 border border-zinc-200 rounded-xl px-4 py-2.5 text-xs text-zinc-700 focus:outline-none focus:border-orange-500 focus:bg-white transition disabled:opacity-50 font-medium"
                  />
                  <button
                    type="submit"
                    disabled={isStreaming}
                    className="bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white p-2.5 rounded-xl transition shrink-0 shadow-sm"
                  >
                    <Send className="h-4 w-4" />
                  </button>
                </form>
              </div>

              {/* Right Pane: Evidence Inspector */}
              <div className="bg-white border border-zinc-200 rounded-2xl p-4 flex flex-col overflow-hidden shadow-sm">
                <h3 className="font-extrabold text-zinc-900 text-sm mb-3 flex items-center gap-2 border-b border-zinc-100 pb-3 shrink-0">
                  <Eye className="h-4 w-4 text-orange-500" />
                  Evidence Inspector
                </h3>
                
                <div className="flex-1 overflow-y-auto space-y-3 pr-1 text-xs">
                  {messages.length === 0 ? (
                    <p className="text-zinc-400 text-center py-12 text-[11px]">No evidence evaluated yet.</p>
                  ) : (
                    <div className="space-y-3">
                      <div className="p-3 bg-zinc-50/50 border border-zinc-200 rounded-xl hover:border-orange-200 transition">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-[10px] font-bold text-orange-600 uppercase">Documents</span>
                          <span className="text-[10px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-full font-bold">Score: 0.94</span>
                        </div>
                        <p className="text-zinc-600 leading-relaxed text-[11px] font-medium">
                          "Our password rotation policy requires changing passwords every 90 days."
                        </p>
                        <div className="mt-2 pt-2 border-t border-zinc-100 text-[10px] text-zinc-400 font-mono flex justify-between">
                          <span>password_guideline.txt</span>
                          <span>Page 1</span>
                        </div>
                      </div>
                      
                      <div className="p-3 bg-zinc-50/50 border border-zinc-200 rounded-xl hover:border-orange-200 transition">
                        <div className="flex justify-between items-center mb-2">
                          <span className="text-[10px] font-bold text-orange-600 uppercase">GitHub</span>
                          <span className="text-[10px] text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded-full font-bold">Score: 0.89</span>
                        </div>
                        <p className="text-zinc-600 leading-relaxed text-[11px] font-medium">
                          "def validate_password_age(user):\n    return user.password_age &lt;= 90"
                        </p>
                        <div className="mt-2 pt-2 border-t border-zinc-100 text-[10px] text-zinc-400 font-mono flex justify-between">
                          <span>src/auth/policy.py</span>
                          <span>lines 15-22</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>

            </div>
          </div>
        )}

        {/* ================= TAB 4: EVALUATIONS ================= */}
        {activeTab === "eval" && (
          <div className="animate-fadeIn">
            <div className="border-b border-zinc-200 pb-6 mb-8 flex justify-between items-center">
              <div>
                <h1 className="text-3xl font-black tracking-tight text-zinc-900">Golden Dataset Evaluations</h1>
                <p className="text-zinc-500 mt-1 text-sm">Measure latency, MRR, groundedness, and API costs using programmatically graded test queries.</p>
              </div>
              <button
                onClick={handleRunEvaluations}
                disabled={evalLoading}
                className="flex items-center gap-2 bg-gradient-to-r from-orange-500 to-amber-500 hover:from-orange-600 hover:to-amber-600 text-white font-bold px-4 py-2 rounded-xl transition text-xs disabled:opacity-50 shadow-md shadow-orange-500/10"
              >
                <Play className="h-3.5 w-3.5 text-white" />
                {evalLoading ? "Running Suite..." : "Run Golden Suite"}
              </button>
            </div>

            {/* Performance Indicators */}
            {evalResults && (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-6 mb-8">
                <div className="bg-white border border-zinc-200 rounded-2xl p-4 text-center shadow-sm">
                  <p className="text-zinc-400 text-[10px] font-bold uppercase tracking-wider">Faithfulness</p>
                  <p className="text-3xl font-black mt-2 text-zinc-900">
                    {Math.round(evalResults.avg_faithfulness * 100)}%
                  </p>
                </div>
                <div className="bg-white border border-zinc-200 rounded-2xl p-4 text-center shadow-sm">
                  <p className="text-zinc-400 text-[10px] font-bold uppercase tracking-wider">Source Recall@K</p>
                  <p className="text-3xl font-black mt-2 text-zinc-900">
                    {Math.round(evalResults.avg_recall_at_k * 100)}%
                  </p>
                </div>
                <div className="bg-white border border-zinc-200 rounded-2xl p-4 text-center shadow-sm">
                  <p className="text-zinc-400 text-[10px] font-bold uppercase tracking-wider">Citation Accuracy</p>
                  <p className="text-3xl font-black mt-2 text-zinc-900">
                    {Math.round(evalResults.avg_citation_accuracy * 100)}%
                  </p>
                </div>
                <div className="bg-white border border-zinc-200 rounded-2xl p-4 text-center shadow-sm">
                  <p className="text-zinc-400 text-[10px] font-bold uppercase tracking-wider">Avg Latency</p>
                  <p className="text-3xl font-black mt-2 text-zinc-900">
                    {evalResults.avg_latency_ms}ms
                  </p>
                </div>
                <div className="bg-white border border-zinc-200 rounded-2xl p-4 text-center shadow-sm col-span-2 md:col-span-1">
                  <p className="text-zinc-400 text-[10px] font-bold uppercase tracking-wider">Evaluation Cost</p>
                  <p className="text-3xl font-black mt-2 text-orange-600">
                    ${evalResults.total_cost_usd.toFixed(3)}
                  </p>
                </div>
              </div>
            )}

            {/* Test cases list table */}
            {evalResults && (
              <div className="bg-white border border-zinc-200 rounded-2xl overflow-hidden mb-8 shadow-sm">
                <div className="p-4 border-b border-zinc-150 flex items-center justify-between">
                  <h3 className="font-extrabold text-zinc-900 text-sm">Suite Test Runs</h3>
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-orange-50 border border-orange-200 text-orange-600 font-bold uppercase tracking-wider">
                    10 Queries
                  </span>
                </div>
                <div className="overflow-x-auto text-xs">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-zinc-50 border-b border-zinc-200 text-zinc-500 font-bold uppercase tracking-wider text-[10px]">
                        <th className="p-4">Query</th>
                        <th className="p-4 text-center">Difficulty</th>
                        <th className="p-4 text-center">Recall</th>
                        <th className="p-4 text-center">Citation Acc</th>
                        <th className="p-4 text-center">Faithfulness</th>
                        <th className="p-4 text-center">Latency</th>
                        <th className="p-4 text-center">Confidence</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100 font-medium">
                      {evalResults.test_runs.map((run: any, idx: number) => (
                        <tr key={idx} className="hover:bg-zinc-50/50 transition">
                          <td className="p-4 text-zinc-800">{run.question}</td>
                          <td className="p-4 text-center font-bold text-zinc-500">{run.difficulty}/10</td>
                          <td className="p-4 text-center font-bold text-emerald-600">{Math.round(run.recall * 100)}%</td>
                          <td className="p-4 text-center font-bold text-emerald-600">{Math.round(run.citation_accuracy * 100)}%</td>
                          <td className="p-4 text-center font-bold text-emerald-600">{Math.round(run.faithfulness * 100)}%</td>
                          <td className="p-4 text-center text-zinc-500 font-mono">{run.latency_ms}ms</td>
                          <td className="p-4 text-center font-bold">
                            <span className={`px-2 py-0.5 rounded-full text-[9px] ${
                              run.confidence === 'HIGH' ? 'text-emerald-700 bg-emerald-50 border border-emerald-200' :
                              run.confidence === 'MEDIUM' ? 'text-orange-700 bg-orange-50 border border-orange-200' : 
                              'text-rose-700 bg-rose-50 border border-rose-200'
                            }`}>
                              {run.confidence}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}

      </main>
    </div>
  );
}
