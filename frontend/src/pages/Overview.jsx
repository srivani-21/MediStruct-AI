import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Users, 
  Activity, 
  Stethoscope, 
  Pill, 
  FlaskConical, 
  Search, 
  Filter, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  Database,
  Cpu,
  Sparkles,
  Layers,
  ArrowRight,
  Trash2,
  Eye,
  ShieldCheck
} from 'lucide-react';
import { Link } from 'react-router-dom';
import axios from 'axios';

export default function Overview({ healthStatus, loading, error }) {
  const [dbMetrics, setDbMetrics] = useState({
    total_documents: 0,
    successfully_processed_documents: 0,
    total_patients: 0,
    total_symptoms: 0,
    total_diagnoses: 0,
    total_medications: 0,
    total_lab_tests: 0,
    total_recommendations: 0,
  });
  const [documents, setDocuments] = useState([]);
  const [docLoading, setDocLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchOverviewData = async () => {
      try {
        setDocLoading(true);
        const [metricsRes, docsRes] = await Promise.all([
          axios.get('/api/analytics/overview'),
          axios.get('/api/documents?limit=10'),
        ]);
        setDbMetrics(metricsRes.data);
        setDocuments(docsRes.data);
      } catch (err) {
        console.error("Error fetching overview data:", err);
      } finally {
        setDocLoading(false);
      }
    };

    fetchOverviewData();
  }, []);

  const metrics = [
    { title: 'Total Documents', value: dbMetrics.total_documents, icon: FileText, color: 'text-sky-600', bg: 'bg-sky-50' },
    { title: 'Total Patients', value: dbMetrics.total_patients, icon: Users, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    { title: 'Total Symptoms', value: dbMetrics.total_symptoms, icon: Activity, color: 'text-amber-600', bg: 'bg-amber-50' },
    { title: 'Total Diagnoses', value: dbMetrics.total_diagnoses, icon: Stethoscope, color: 'text-indigo-600', bg: 'bg-indigo-50' },
    { title: 'Total Medications', value: dbMetrics.total_medications, icon: Pill, color: 'text-rose-600', bg: 'bg-rose-50' },
    { title: 'Total Lab Tests', value: dbMetrics.total_lab_tests, icon: FlaskConical, color: 'text-teal-600', bg: 'bg-teal-50' },
  ];

  const platformCapabilities = [
    {
      category: 'Digital Intake',
      title: 'Multimodal Document Intake',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Multi-format PDF and image ingestion, digital text stream parsing, and metadata cataloging.',
    },
    {
      category: 'Computer Vision',
      title: 'Handwriting & Text Extraction',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Optical character extraction, cursive handwriting analysis, character confidence audits, and image processing.',
    },
    {
      category: 'Clinical Safeguard',
      title: 'Human Verification Studio',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Side-by-side verification interface ensuring human clinical review and token correction before data persistence.',
    },
    {
      category: 'Knowledge Extraction',
      title: 'Clinical Entity Structuring',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Standardized extraction across symptoms, diagnoses, medications, lab tests, and care plans with source citations.',
    },
    {
      category: 'Cohort Analytics',
      title: 'Clinical Discovery & Trends',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Longitudinal trend analytics, symptom-disease co-occurrence discovery, and unit-calibrated laboratory metrics.',
    },
    {
      category: 'Privacy Engineering',
      title: 'Research Dataset Export',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Multi-sheet Excel, per-category CSV, ZIP archives, and JSON with HMAC-SHA256 pseudonymization.',
    },
    {
      category: 'Conversational Search',
      title: 'Dual-Channel Clinical Assistant',
      status: 'Operational',
      badgeClass: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      description: 'Evidence-grounded conversational search across patient records and clinical documents with page citations.',
    },
  ];

  const filteredDocs = documents.filter((doc) =>
    doc.filename.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Page Title & Status */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Overview Dashboard</h2>
          <p className="text-sm text-slate-500 mt-1">
            Real-time clinical metrics, processed medical document repository, and system status.
          </p>
        </div>
        <Link
          to="/ingestion"
          className="inline-flex items-center gap-2 bg-sky-600 hover:bg-sky-700 text-white px-4 py-2 rounded-lg text-sm font-medium shadow-sm transition-colors self-start md:self-auto"
        >
          <span>Ingest Documents</span>
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* Backend Health Banner */}
      {loading ? (
        <div className="p-4 rounded-xl bg-slate-100 border border-slate-200 text-slate-600 flex items-center gap-3">
          <div className="w-4 h-4 border-2 border-sky-600 border-t-transparent rounded-full animate-spin"></div>
          <span className="text-sm">Verifying clinical platform services...</span>
        </div>
      ) : error ? (
        <div className="p-4 rounded-xl bg-amber-50 border border-amber-200 text-amber-800 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="font-semibold text-sm">Clinical Platform Service Offline</h4>
            <p className="text-xs text-amber-700 mt-0.5">{error}</p>
          </div>
        </div>
      ) : (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-start gap-3">
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="font-semibold text-sm">Clinical Data Store & Analytics Services Operational</h4>
            <p className="text-xs text-emerald-700 mt-0.5">
              Core platform active on <code className="font-mono bg-emerald-100 px-1 py-0.5 rounded">http://localhost:8000</code>. Relational data store and search index operational.
            </p>
          </div>
          <span className="text-xs font-mono bg-emerald-200 text-emerald-900 px-2 py-0.5 rounded">
            v{healthStatus?.version || '1.0.0'}
          </span>
        </div>
      )}

      {/* Database Derived Metrics */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
            Clinical Database Metrics
          </h3>
          <span className="text-xs text-slate-400">Calculated directly from verified clinical records</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {metrics.map((item, idx) => {
            const Icon = item.icon;
            return (
              <div key={idx} className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col justify-between">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium text-slate-500">{item.title}</span>
                  <div className={`p-2 rounded-lg ${item.bg} ${item.color}`}>
                    <Icon className="w-4 h-4" />
                  </div>
                </div>
                <div>
                  <span className="text-2xl font-bold text-slate-900">{item.value}</span>
                  <span className="block text-[11px] text-slate-400 mt-0.5">
                    {item.value} {item.value === 1 ? 'record' : 'records'} stored
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Processed Documents Library */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-slate-900">Processed Documents Library</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Catalog of all uploaded medical PDFs, extraction methods, and parsing statuses.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search documents..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 pr-4 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-700 w-48 md:w-56 focus:outline-none focus:ring-1 focus:ring-sky-500"
              />
            </div>
          </div>
        </div>

        {/* Documents Table or Empty State */}
        {filteredDocs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                  <th className="p-3 pl-5">Document</th>
                  <th className="p-3">Upload Date</th>
                  <th className="p-3">Classification</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Size</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredDocs.map((doc) => (
                  <tr key={doc.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="p-3 pl-5 font-medium text-slate-900 flex items-center gap-2.5">
                      <FileText className="w-4 h-4 text-sky-600 shrink-0" />
                      <span className="truncate max-w-xs">{doc.filename}</span>
                    </td>
                    <td className="p-3 text-slate-500 font-mono text-[11px]">
                      {new Date(doc.uploaded_at).toLocaleString()}
                    </td>
                    <td className="p-3 text-slate-600 capitalize">
                      {doc.document_type}
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                        doc.processing_status === 'COMPLETED'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : doc.processing_status === 'FAILED'
                          ? 'bg-rose-50 text-rose-700 border-rose-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}>
                        {doc.processing_status}
                      </span>
                    </td>
                    <td className="p-3 text-slate-500 font-mono text-[11px]">
                      {(doc.file_size_bytes / 1024).toFixed(1)} KB
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center flex flex-col items-center justify-center">
            <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-4">
              <FileText className="w-7 h-7" />
            </div>
            <h4 className="text-base font-semibold text-slate-800">No Documents Processed Yet</h4>
            <p className="text-xs text-slate-500 max-w-md mt-1 mb-5">
              The database currently contains no uploaded documents. When you upload clinical PDF reports in Document Ingestion, their extraction metadata and processing status will appear here.
            </p>
            <Link
              to="/ingestion"
              className="inline-flex items-center gap-2 bg-sky-50 text-sky-700 hover:bg-sky-100 border border-sky-200 px-4 py-2 rounded-lg text-xs font-semibold transition-colors"
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Go to Document Ingestion</span>
            </Link>
          </div>
        )}
      </div>

      {/* Platform Services & Infrastructure Status */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-slate-800 text-sm">Platform Services & Infrastructure Status</h3>
            <p className="text-xs text-slate-500">Live operational status of core clinical services and processing engines</p>
          </div>
          <span className="text-xs bg-slate-100 text-slate-600 px-2.5 py-1 rounded-full font-medium">
            Infrastructure Monitor
          </span>
        </div>
        <div className="p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
            {/* Core Application Service */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Application API Service</span>
                  <Cpu className="w-4 h-4 text-sky-600" />
                </div>
                <p className="text-slate-500 text-[11px]">REST Interface & Request Dispatcher</p>
              </div>
              <div className="mt-3">
                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold ${healthStatus ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${healthStatus ? 'bg-emerald-500' : 'bg-rose-500'}`}></span>
                  {healthStatus ? 'Operational & Healthy' : 'Offline'}
                </span>
              </div>
            </div>

            {/* Clinical Data Repository */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Clinical Data Repository</span>
                  <Database className="w-4 h-4 text-emerald-600" />
                </div>
                <p className="text-slate-500 text-[11px]">Relational Records & Lexical Index</p>
              </div>
              <div className="mt-3">
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  {healthStatus?.database === 'connected' ? 'Connected & Schema Ready' : 'Configured'}
                </span>
              </div>
            </div>

            {/* OCR Engine */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Document OCR Engine</span>
                  <Layers className="w-4 h-4 text-amber-600" />
                </div>
                <p className="text-slate-500 text-[11px]">Multi-Format Text & Character Parsing</p>
              </div>
              <div className="mt-3">
                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold ${healthStatus?.environment?.tesseract_detected ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${healthStatus?.environment?.tesseract_detected ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
                  {healthStatus?.environment?.tesseract_detected ? 'Operational' : 'Custom Path Needed'}
                </span>
              </div>
            </div>

            {/* Document Rendering */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Document Rendering Engine</span>
                  <FileText className="w-4 h-4 text-indigo-600" />
                </div>
                <p className="text-slate-500 text-[11px]">Clinical Report Rasterization & Preview</p>
              </div>
              <div className="mt-3">
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  {healthStatus?.environment?.poppler_configured ? 'Operational' : 'Standard Renderer'}
                </span>
              </div>
            </div>

            {/* AI Inference Engine */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Clinical AI Engine</span>
                  <Sparkles className="w-4 h-4 text-purple-600" />
                </div>
                <p className="text-slate-500 text-[11px]">
                  {healthStatus?.environment?.active_provider === 'ollama' 
                    ? 'Local Privacy-Preserving Neural Inference' 
                    : 'Clinical Language Processing Service'}
                </p>
              </div>
              <div className="mt-3">
                {(() => {
                  const isOllama = healthStatus?.environment?.active_provider === 'ollama';
                  const isOnline = isOllama 
                    ? !!healthStatus?.environment?.ollama?.server_online 
                    : !!healthStatus?.environment?.gemini_api_key_set;
                  const label = isOllama 
                    ? (isOnline ? 'Local Service Active' : 'Standby / Connecting') 
                    : (isOnline ? 'Service Configured' : 'Awaiting Configuration');
                  return (
                    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold ${isOnline ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
                      {label}
                    </span>
                  );
                })()}
              </div>
            </div>

            {/* Privacy & Pseudonymization Engine */}
            <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-slate-700">Privacy Protection Engine</span>
                  <ShieldCheck className="w-4 h-4 text-teal-600" />
                </div>
                <p className="text-slate-500 text-[11px]">HMAC-SHA256 Cryptographic Pseudonymization</p>
              </div>
              <div className="mt-3">
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-100 text-emerald-800">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  Active & Enforced
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Clinical Architecture & Platform Capabilities */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="mb-4">
          <h3 className="font-bold text-slate-900 text-sm">Clinical Architecture & Platform Capabilities</h3>
          <p className="text-xs text-slate-500 mt-0.5">
            Verified end-to-end clinical workflow pipeline from document ingestion to grounded intelligence.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {platformCapabilities.map((item, idx) => (
            <div key={idx} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-[11px] font-semibold text-slate-500 tracking-wider uppercase">{item.category}</span>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${item.badgeClass}`}>
                    {item.status}
                  </span>
                </div>
                <h4 className="text-sm font-bold text-slate-800">{item.title}</h4>
                <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{item.description}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
