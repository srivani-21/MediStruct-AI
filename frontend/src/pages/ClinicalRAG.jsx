import React, { useState, useEffect, useRef } from 'react';
import { 
  MessageSquare, 
  Send, 
  Sparkles, 
  BookOpen, 
  Sliders, 
  ShieldCheck, 
  ShieldAlert, 
  FileText,
  CornerDownRight,
  Info,
  RefreshCw,
  Layers,
  Database,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle2,
  Trash2,
  Filter,
  ExternalLink
} from 'lucide-react';
import axios from 'axios';

export default function ClinicalRAG() {
  const [topK, setTopK] = useState(4);
  const [queryInput, setQueryInput] = useState('');
  const [selectedDocId, setSelectedDocId] = useState('');
  const [documents, setDocuments] = useState([]);
  
  // Status states
  const [indexStatus, setIndexStatus] = useState({
    total_chunks: 0,
    total_documents_indexed: 0,
    retrieval_backend: 'sqlite_fts5_bm25',
    backend_type: 'lexical_bm25',
    ollama_model: 'qwen3.5:2b',
    ollama_online: false,
  });
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [indexing, setIndexing] = useState(false);
  const [indexMessage, setIndexMessage] = useState(null);

  // Chat conversation session state
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'assistant',
      content: (
        "Welcome to the MediStruct AI Clinical Knowledge Retrieval Assistant. " +
        "You can ask targeted clinical questions regarding your uploaded medical documents. " +
        "All answers are synthesized by your local Ollama model (qwen3.5:2b) and grounded strictly in verified document excerpts with page citations."
      ),
      sources: [],
      sufficient_evidence: true,
      timestamp: new Date().toLocaleTimeString(),
      disclaimer: "Academic Research Prototype. Does not constitute verified medical advice.",
    },
  ]);
  const [sending, setSending] = useState(false);
  const [queryError, setQueryError] = useState(null);
  const [expandedSources, setExpandedSources] = useState({});

  const chatBottomRef = useRef(null);

  const sampleQuestions = [
    "What primary diagnoses were documented across the patient reports?",
    "List all prescribed medications along with their dosages and frequencies.",
    "Were any laboratory test values outside standard reference intervals?",
    "Summarize documented follow-up recommendations and care plans.",
  ];

  // Load documents and RAG status on mount
  useEffect(() => {
    fetchDocuments();
    fetchRAGStatus();
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  const fetchDocuments = async () => {
    try {
      const res = await axios.get('/api/documents/');
      setDocuments(res.data || []);
    } catch (err) {
      console.error('Failed to fetch documents', err);
    }
  };

  const fetchRAGStatus = async () => {
    setLoadingStatus(true);
    try {
      const res = await axios.get('/api/rag/status');
      setIndexStatus(res.data);
    } catch (err) {
      console.error('Failed to fetch RAG status', err);
    } finally {
      setLoadingStatus(false);
    }
  };

  const handleIndexDocuments = async () => {
    setIndexing(true);
    setIndexMessage(null);
    try {
      const payload = selectedDocId ? { document_id: selectedDocId } : {};
      const res = await axios.post('/api/rag/index', payload);
      const data = res.data;
      setIndexMessage({
        type: 'success',
        text: `Successfully indexed ${data.total_chunks_indexed} chunks across ${data.indexed_documents_count} documents. (${data.skipped_documents_count} skipped by safety gate).`,
      });
      fetchRAGStatus();
    } catch (err) {
      console.error('Indexing failed', err);
      setIndexMessage({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to index documents into the retrieval store.',
      });
    } finally {
      setIndexing(false);
    }
  };

  const handleSendMessage = async (textToSend) => {
    const query = (textToSend || queryInput).trim();
    if (!query || sending) return;

    setQueryError(null);
    setQueryInput('');

    // User message
    const userMsgId = 'usr_' + Date.now();
    const userMsg = {
      id: userMsgId,
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setSending(true);

    try {
      const res = await axios.post('/api/rag/query', {
        query: query,
        document_id: selectedDocId || null,
        top_k: topK,
      });

      const assistantMsg = {
        id: 'ast_' + Date.now(),
        role: 'assistant',
        content: res.data.answer,
        sources: res.data.sources || [],
        sufficient_evidence: res.data.sufficient_evidence,
        timestamp: new Date().toLocaleTimeString(),
        disclaimer: res.data.disclaimer,
        retrieval_method: res.data.retrieval_method,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      console.error('RAG query failed', err);
      const errorMsg = {
        id: 'err_' + Date.now(),
        role: 'assistant',
        content: `Error generating response: ${err.response?.data?.detail || err.message || 'Server error'}`,
        sources: [],
        sufficient_evidence: false,
        timestamp: new Date().toLocaleTimeString(),
        disclaimer: 'System execution error.',
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setSending(false);
    }
  };

  const handleClearHistory = () => {
    setMessages([
      {
        id: 'welcome_' + Date.now(),
        role: 'assistant',
        content: "Conversation history cleared. Ready for your next clinical question.",
        sources: [],
        sufficient_evidence: true,
        timestamp: new Date().toLocaleTimeString(),
        disclaimer: "Academic Research Prototype. Does not constitute verified medical advice.",
      },
    ]);
  };

  const toggleSourceCard = (msgId) => {
    setExpandedSources((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Clinical RAG Chatbot</h2>
            <span className="text-xs bg-emerald-100 text-emerald-800 font-medium px-2.5 py-0.5 rounded-full border border-emerald-200">
              Phase 7 • Production
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Evidence-grounded conversational AI using SQLite FTS5 BM25 retrieval and local Ollama (<code className="font-mono text-slate-700 bg-slate-100 px-1 py-0.2 rounded">qwen3.5:2b</code>) with page-level citations.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 font-medium self-start md:self-auto">
          <div className={`w-2.5 h-2.5 rounded-full ${indexStatus.ollama_online ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}`} />
          <span>Ollama: {indexStatus.ollama_online ? 'Online (qwen3.5:2b)' : 'Offline / Standby'}</span>
        </div>
      </div>

      {/* RAG Controls & Index Management */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-sky-50 text-sky-600">
              <Sliders className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-800 text-sm">Retrieval & Scope Controls</h3>
              <p className="text-xs text-slate-500">
                Engine: <span className="font-mono text-slate-700 font-medium">SQLite FTS5 (Lexical BM25)</span> • 100% On-Device
              </p>
            </div>
          </div>

          {/* Document Scope Selector & Index Trigger */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <span>Scope:</span>
            </div>
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-700 font-medium focus:ring-2 focus:ring-sky-500 focus:outline-none"
            >
              <option value="">Entire Ingested Cohort ({documents.length} Docs)</option>
              {documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.filename} ({doc.id.slice(0, 8)}...)
                </option>
              ))}
            </select>

            <button
              onClick={handleIndexDocuments}
              disabled={indexing}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors disabled:bg-slate-300 disabled:cursor-not-allowed"
            >
              {indexing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Indexing...</span>
                </>
              ) : (
                <>
                  <Database className="w-3.5 h-3.5" />
                  <span>Index Documents</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Index Metrics and Top-K Slider */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mt-4 text-xs">
          {/* Index Status Badge */}
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between">
            <div>
              <span className="text-slate-500 block text-[11px]">Knowledge Index Status</span>
              <span className="font-bold text-slate-800 text-sm">
                {loadingStatus ? 'Checking...' : `${indexStatus.total_chunks} Chunks (${indexStatus.total_documents_indexed} Docs)`}
              </span>
            </div>
            <button
              onClick={fetchRAGStatus}
              title="Refresh status"
              className="p-1 text-slate-400 hover:text-slate-600 rounded"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingStatus ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* Top-K Chunk Retrieval Limit */}
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-slate-600 font-medium">Top-K Passage Limit</label>
              <span className="font-mono font-bold text-sky-600 bg-white px-2 py-0.5 rounded border border-slate-200">
                K = {topK}
              </span>
            </div>
            <input
              type="range"
              min="1"
              max="10"
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="w-full accent-sky-600 cursor-pointer"
            />
          </div>

          {/* Strict Grounding Protocol Card */}
          <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-start gap-2.5">
            <ShieldCheck className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-slate-700 block">Strict Grounding Protocol</span>
              <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                If evidence is missing, the AI states: <em>"I could not find sufficient supporting information in the uploaded documents."</em>
              </p>
            </div>
          </div>
        </div>

        {/* Index feedback alert */}
        {indexMessage && (
          <div className={`mt-3 p-3 rounded-lg text-xs flex items-center gap-2 ${
            indexMessage.type === 'success' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' : 'bg-rose-50 text-rose-800 border border-rose-200'
          }`}>
            {indexMessage.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            )}
            <span>{indexMessage.text}</span>
          </div>
        )}
      </div>

      {/* Main Chat Interface */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[600px]">
        {/* Chat Stream Header */}
        <div className="px-5 py-3 border-b border-slate-100 bg-slate-50/70 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-4 h-4 text-sky-600" />
            <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
              Clinical Question-Answering Session
            </span>
          </div>
          <button
            onClick={handleClearHistory}
            className="inline-flex items-center gap-1 text-[11px] text-slate-400 hover:text-slate-600 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Clear History</span>
          </button>
        </div>

        {/* Message Bubble Stream */}
        <div className="flex-1 p-5 overflow-y-auto space-y-4 bg-slate-50/40">
          {messages.map((msg) => {
            const isUser = msg.role === 'user';
            const isExpanded = !!expandedSources[msg.id];
            return (
              <div
                key={msg.id}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}
              >
                <div
                  className={`max-w-2xl rounded-xl p-4 shadow-sm text-xs leading-relaxed ${
                    isUser
                      ? 'bg-sky-600 text-white rounded-br-none'
                      : 'bg-white border border-slate-200 text-slate-800 rounded-bl-none'
                  }`}
                >
                  {/* Sender & Timestamp */}
                  <div className="flex items-center justify-between gap-4 mb-1.5 pb-1 border-b border-white/20 text-[10px] opacity-80">
                    <span className="font-semibold">{isUser ? 'Researcher Query' : 'MediStruct AI (Ollama qwen3.5:2b)'}</span>
                    <span>{msg.timestamp}</span>
                  </div>

                  {/* Body Text */}
                  <div className="whitespace-pre-wrap">{msg.content}</div>

                  {/* Insufficient Evidence Warning Banner */}
                  {!isUser && !msg.sufficient_evidence && (
                    <div className="mt-3 p-2.5 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 flex items-start gap-2">
                      <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                      <span className="text-[11px]">
                        Information absent from indexed records. Safe Harbor rules prevent hallucination.
                      </span>
                    </div>
                  )}

                  {/* Supporting Evidence Citations Drawer */}
                  {!isUser && msg.sources && msg.sources.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => toggleSourceCard(msg.id)}
                        className="flex items-center justify-between w-full text-[11px] font-semibold text-sky-700 hover:text-sky-900 transition-colors"
                      >
                        <span className="flex items-center gap-1.5">
                          <BookOpen className="w-3.5 h-3.5 text-sky-600" />
                          <span>Supporting Evidence & Page Citations ({msg.sources.length})</span>
                        </span>
                        {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                      </button>

                      {isExpanded && (
                        <div className="mt-2.5 space-y-2">
                          {msg.sources.map((src, sIdx) => (
                            <div
                              key={sIdx}
                              className="p-2.5 rounded-lg border border-slate-200 bg-slate-50/70 text-[11px]"
                            >
                              <div className="flex items-center justify-between mb-1.5">
                                <span className="font-semibold text-slate-800 flex items-center gap-1.5">
                                  {src.source_type === 'structured_record' ? (
                                    <Database className="w-3.5 h-3.5 text-purple-600" />
                                  ) : (
                                    <FileText className="w-3.5 h-3.5 text-sky-600" />
                                  )}
                                  <span>{src.filename}</span>
                                </span>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {src.source_type === 'structured_record' ? (
                                    <span className="px-1.5 py-0.5 rounded bg-purple-100 text-purple-800 font-medium text-[10px] border border-purple-200 capitalize">
                                      DB: {src.category ? src.category.replace('_', ' ') : 'Record'}
                                    </span>
                                  ) : (
                                    <span className="px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 font-medium text-[10px] border border-sky-200">
                                      Doc Excerpt
                                    </span>
                                  )}
                                  <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 font-mono font-medium text-[10px] border border-slate-200">
                                    Page {src.page_number}
                                  </span>
                                  {src.is_human_verified && (
                                    <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-medium border border-emerald-200">
                                      Verified
                                    </span>
                                  )}
                                </div>
                              </div>
                              <blockquote className={`text-slate-700 p-2.5 rounded border my-1 leading-relaxed ${
                                src.source_type === 'structured_record' 
                                  ? 'bg-purple-50/40 border-purple-200 border-l-2 border-l-purple-500 font-mono text-[10.5px]'
                                  : 'bg-white border-slate-200 border-l-2 border-l-sky-500 italic text-[11px]'
                              }`}>
                                {src.source_type === 'structured_record' ? src.text_excerpt : `"${src.text_excerpt}"`}
                              </blockquote>
                              {src.relevance_score !== null && src.source_type !== 'structured_record' && (
                                <div className="text-[10px] text-slate-400 text-right">
                                  BM25 Rank Score: {src.relevance_score}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Clinical Disclaimer */}
                  {!isUser && msg.disclaimer && (
                    <div className="mt-3 pt-2 border-t border-slate-100 text-[10px] text-slate-400 italic">
                      {msg.disclaimer}
                    </div>
                  )}
                </div>
              </div>
            );
          })}

          {/* Thinking / Streaming Indicator */}
          {sending && (
            <div className="flex items-start">
              <div className="bg-white border border-slate-200 rounded-xl rounded-bl-none p-3.5 shadow-sm text-xs text-slate-600 flex items-center gap-3">
                <div className="w-4 h-4 border-2 border-sky-600 border-t-transparent rounded-full animate-spin"></div>
                <span>Retrieving evidence and synthesizing grounded answer via Ollama (qwen3.5:2b)...</span>
              </div>
            </div>
          )}

          <div ref={chatBottomRef} />
        </div>

        {/* Quick Suggestion Chips */}
        <div className="px-4 py-2 bg-slate-50/70 border-t border-slate-100 flex items-center gap-2 overflow-x-auto text-xs">
          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider shrink-0 flex items-center gap-1">
            <CornerDownRight className="w-3 h-3" /> Quick Queries:
          </span>
          {sampleQuestions.map((q, idx) => (
            <button
              key={idx}
              onClick={() => handleSendMessage(q)}
              disabled={sending}
              className="px-2.5 py-1 bg-white border border-slate-200 hover:border-sky-300 hover:bg-sky-50 text-slate-700 text-[11px] rounded-full whitespace-nowrap transition-colors disabled:opacity-50"
            >
              {q}
            </button>
          ))}
        </div>

        {/* Input Bar */}
        <div className="p-4 bg-white border-t border-slate-200">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage();
            }}
            className="flex items-center gap-2"
          >
            <input
              type="text"
              placeholder="Ask a clinical question about uploaded medical documents..."
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              disabled={sending}
              className="flex-1 px-4 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-sky-500 focus:bg-white transition-all disabled:bg-slate-100"
            />
            <button
              type="submit"
              disabled={sending || !queryInput.trim()}
              className="inline-flex items-center justify-center p-2.5 bg-sky-600 hover:bg-sky-700 text-white rounded-lg transition-colors disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed shadow-sm"
              title="Send query"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
          <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between px-1">
            <span>Retrieval augmented with SQLite FTS5 BM25 & Ollama local AI</span>
            <span>All responses grounded with page citations</span>
          </div>
        </div>
      </div>
    </div>
  );
}
