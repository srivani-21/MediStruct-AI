import React, { useState, useEffect } from 'react';
import { 
  BrowserRouter, 
  Routes, 
  Route, 
  NavLink, 
  Navigate, 
  useLocation 
} from 'react-router-dom';
import { 
  BarChart3, 
  FileText, 
  Database, 
  Activity, 
  Download, 
  MessageSquare, 
  Stethoscope, 
  Info,
  ExternalLink,
  ShieldCheck
} from 'lucide-react';
import axios from 'axios';

// Page components for all 6 modules
import Overview from './pages/Overview';
import DocumentIngestion from './pages/DocumentIngestion';
import StructuredRecords from './pages/StructuredRecords';
import ClinicalDiscovery from './pages/ClinicalDiscovery';
import DatasetExport from './pages/DatasetExport';
import ClinicalRAG from './pages/ClinicalRAG';

const MANDATORY_PROJECT_TITLE = 
  "MediStruct AI: A Smart Healthcare Dataset Generation and Clinical Knowledge Discovery Framework from Unstructured Medical Documents";

// Navigation definition for primary modules: Clinical Discovery, Dataset Export, Clinical RAG
const NAVIGATION_ITEMS = [
  { path: '/', label: 'Overview', icon: BarChart3, exact: true },
  { path: '/ingestion', label: 'Document Ingestion', icon: FileText },
  { path: '/records', label: 'Structured Records', icon: Database },
  { path: '/discovery', label: 'Clinical Discovery', icon: Activity },
  { path: '/export', label: 'Dataset Export', icon: Download },
  { path: '/rag', label: 'Clinical Assistant', icon: MessageSquare },
];

function AppLayout({ healthStatus, loading, error }) {
  const location = useLocation();

  // Find active navigation item title for header breadcrumb
  const currentNav = NAVIGATION_ITEMS.find((item) => 
    item.path === '/' ? location.pathname === '/' : location.pathname.startsWith(item.path)
  );

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans">
      {/* Mandatory Top Clinical Research Notice */}
      <div className="bg-sky-950 text-sky-100 px-4 py-2 text-xs text-center border-b border-sky-900 flex items-center justify-center gap-2">
        <Info className="w-4 h-4 text-sky-400 shrink-0" />
        <span>
          <strong>Clinical Research Notice:</strong> Academic Research and Clinical Knowledge Discovery Prototype. Extracted insights and AI-generated responses are for informational purposes only and do not constitute verified medical advice.
        </span>
      </div>

      <div className="flex flex-1">
        {/* Sidebar Navigation */}
        <aside className="w-64 bg-slate-900 text-slate-100 flex flex-col border-r border-slate-800 shrink-0">
          {/* Brand & Logo */}
          <div className="p-5 border-b border-slate-800 flex items-center gap-3">
            <div className="bg-sky-500 p-2 rounded-lg text-white shadow-md">
              <Stethoscope className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-white">MediStruct AI</h1>
              <p className="text-[11px] text-slate-400">Clinical Research Framework</p>
            </div>
          </div>

          {/* Primary Modules Links */}
          <nav className="p-4 space-y-1.5 flex-1">
            <div className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              Primary Modules
            </div>
            {NAVIGATION_ITEMS.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  className={({ isActive }) =>
                    `w-full flex items-center gap-3 px-3.5 py-2.5 rounded-lg text-xs font-semibold transition-all ${
                      isActive
                        ? 'bg-sky-600 text-white shadow-sm font-bold'
                        : 'text-slate-300 hover:bg-slate-800 hover:text-white'
                    }`
                  }
                >
                  {({ isActive }) => (
                    <>
                      <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                      <span>{item.label}</span>
                    </>
                  )}
                </NavLink>
              );
            })}
          </nav>

          {/* Platform Services Status Card in Sidebar */}
          <div className="p-4 border-t border-slate-800 text-xs">
            <div className="flex items-center justify-between mb-2">
              <span className="text-slate-400 font-medium">Platform Services</span>
              <span className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${healthStatus ? 'bg-emerald-400' : 'bg-rose-400'}`}></span>
                <span className={healthStatus ? 'text-emerald-400 font-semibold text-[11px]' : 'text-rose-400 font-semibold text-[11px]'}>
                  {healthStatus ? 'Operational' : 'Service Offline'}
                </span>
              </span>
            </div>
            <p className="text-slate-500 text-[11px] truncate">
              {healthStatus ? 'Clinical Analytics Core Active' : 'Connecting to local services...'}
            </p>
            <div className="mt-3 pt-3 border-t border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400">
              <a 
                href="http://localhost:8000/docs" 
                target="_blank" 
                rel="noreferrer" 
                className="hover:text-sky-400 flex items-center gap-1"
              >
                <span>API Reference</span>
                <ExternalLink className="w-2.5 h-2.5" />
              </a>
              <span>Clinical Research Edition</span>
            </div>
          </div>
        </aside>

        {/* Main Content Area */}
        <main className="flex-1 flex flex-col overflow-y-auto">
          {/* Header with Mandatory Full Academic Title */}
          <header className="bg-white border-b border-slate-200 px-8 py-4 shadow-sm">
            <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-2">
              <div>
                <h1 className="text-base font-bold text-slate-900 tracking-tight leading-snug">
                  {MANDATORY_PROJECT_TITLE}
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  Current View: <span className="font-semibold text-sky-700">{currentNav?.label || 'Overview'}</span>
                </p>
              </div>
              <div className="flex items-center gap-2 self-start lg:self-auto">
                <span className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                  System Ready
                </span>
                <span className="text-[11px] font-medium px-2.5 py-1 rounded bg-slate-100 text-slate-700 border border-slate-200">
                  Clinical Research Platform
                </span>
              </div>
            </div>
          </header>

          {/* Route Content Outlet */}
          <div className="p-8 max-w-7xl w-full mx-auto flex-1">
            <Routes>
              <Route 
                path="/" 
                element={<Overview healthStatus={healthStatus} loading={loading} error={error} />} 
              />
              <Route path="/ingestion" element={<DocumentIngestion />} />
              <Route path="/records" element={<StructuredRecords />} />
              <Route path="/discovery" element={<ClinicalDiscovery />} />
              <Route path="/export" element={<DatasetExport />} />
              <Route path="/rag" element={<ClinicalRAG />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  const [healthStatus, setHealthStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const checkBackendHealth = async () => {
      try {
        setLoading(true);
        const res = await axios.get('/api/health');
        setHealthStatus(res.data);
        setError(null);
      } catch (err) {
        console.error("Backend health check error:", err);
        setError("Clinical backend service is currently offline. Ensure local services are running on http://localhost:8000.");
      } finally {
        setLoading(false);
      }
    };
    checkBackendHealth();
  }, []);

  return (
    <BrowserRouter>
      <AppLayout healthStatus={healthStatus} loading={loading} error={error} />
    </BrowserRouter>
  );
}
