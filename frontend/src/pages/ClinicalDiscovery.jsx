import React, { useState, useEffect } from 'react';
import { 
  Activity, 
  BarChart3, 
  PieChart as PieChartIcon, 
  TrendingUp, 
  Users, 
  Pill, 
  Stethoscope, 
  FlaskConical, 
  FileCheck,
  FileText,
  Clock, 
  Info,
  RefreshCw,
  AlertCircle,
  Filter,
  Search,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  FileSpreadsheet,
  Layers
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  PieChart, 
  Pie, 
  Cell, 
  Legend 
} from 'recharts';
import axios from 'axios';

const PALETTE = ['#0284c7', '#10b981', '#f59e0b', '#6366f1', '#f43f5e', '#14b8a6', '#8b5cf6'];

export default function ClinicalDiscovery() {
  const [activeTab, setActiveTab] = useState('symptoms-diagnoses');
  const [filterDocId, setFilterDocId] = useState('');
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Analytics states
  const [summary, setSummary] = useState({
    total_documents: 0,
    total_patients: 0,
    total_symptoms: 0,
    total_diagnoses: 0,
    total_medications: 0,
    total_lab_results: 0,
    total_recommendations: 0,
    total_clinical_entities: 0,
    category_distribution: [],
  });
  const [insights, setInsights] = useState([]);
  const [symptoms, setSymptoms] = useState([]);
  const [diagnoses, setDiagnoses] = useState([]);
  const [medications, setMedications] = useState([]);
  const [symDiaCoOccur, setSymDiaCoOccur] = useState([]);
  const [medDiaCoOccur, setMedDiaCoOccur] = useState([]);
  const [labs, setLabs] = useState([]);
  const [recommendations, setRecommendations] = useState({
    total_recommendations: 0,
    with_follow_up_instructions_count: 0,
    without_follow_up_count: 0,
    recommendation_records: [],
  });

  // Filter search for tables
  const [searchTerm, setSearchTerm] = useState('');

  // Initial load
  useEffect(() => {
    fetchDocumentList();
  }, []);

  // Fetch all analytics whenever filterDocId changes
  useEffect(() => {
    fetchAllAnalytics();
  }, [filterDocId]);

  const fetchDocumentList = async () => {
    try {
      const res = await axios.get('/api/documents?limit=100');
      setDocuments(res.data);
    } catch (err) {
      console.error('Failed to load documents list for analytics:', err);
    }
  };

  const fetchAllAnalytics = async () => {
    try {
      setLoading(true);
      setError(null);
      const docParam = filterDocId ? `?document_id=${filterDocId}` : '';
      const docParamAnd = filterDocId ? `&document_id=${filterDocId}` : '';

      const [
        sumRes,
        insRes,
        symRes,
        diaRes,
        medRes,
        symDiaRes,
        medDiaRes,
        labRes,
        recRes,
      ] = await Promise.all([
        axios.get(`/api/analytics/clinical-summary${docParam}`),
        axios.get(`/api/analytics/insights${docParam}`),
        axios.get(`/api/analytics/symptoms?limit=10${docParamAnd}`),
        axios.get(`/api/analytics/diagnoses?limit=10${docParamAnd}`),
        axios.get(`/api/analytics/medications?limit=10${docParamAnd}`),
        axios.get(`/api/analytics/co-occurrences/symptom-diagnosis?min_count=1&limit=15${docParamAnd}`),
        axios.get(`/api/analytics/co-occurrences/medication-diagnosis?min_count=1&limit=15${docParamAnd}`),
        axios.get(`/api/analytics/labs?limit=15${docParamAnd}`),
        axios.get(`/api/analytics/recommendations?limit=20${docParamAnd}`),
      ]);

      setSummary(sumRes.data);
      setInsights(insRes.data);
      setSymptoms(symRes.data);
      setDiagnoses(diaRes.data);
      setMedications(medRes.data);
      setSymDiaCoOccur(symDiaRes.data);
      setMedDiaCoOccur(medDiaRes.data);
      setLabs(labRes.data);
      setRecommendations(recRes.data);
    } catch (err) {
      console.error('Failed to fetch clinical analytics:', err);
      setError('Failed to load clinical analytics from the backend database. Please ensure the server is running.');
    } finally {
      setLoading(false);
    }
  };

  // KPI cards metrics array (all 7 required metrics)
  const kpiMetrics = [
    { title: 'Total Patients', value: summary.total_patients, sub: 'Distinct patient records', icon: Users, color: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-200' },
    { title: 'Total Documents', value: summary.total_documents, sub: 'Ingested source files', icon: FileText, color: 'text-sky-600', bg: 'bg-sky-50', border: 'border-sky-200' },
    { title: 'Total Symptoms', value: summary.total_symptoms, sub: 'Documented complaints', icon: Activity, color: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200' },
    { title: 'Total Diagnoses', value: summary.total_diagnoses, sub: 'Clinical assessments', icon: Stethoscope, color: 'text-indigo-600', bg: 'bg-indigo-50', border: 'border-indigo-200' },
    { title: 'Total Medications', value: summary.total_medications, sub: 'Active prescriptions', icon: Pill, color: 'text-rose-600', bg: 'bg-rose-50', border: 'border-rose-200' },
    { title: 'Total Lab Results', value: summary.total_lab_results, sub: 'Diagnostic findings', icon: FlaskConical, color: 'text-teal-600', bg: 'bg-teal-50', border: 'border-teal-200' },
    { title: 'Total Recommendations', value: summary.total_recommendations, sub: 'Physician care advice', icon: FileCheck, color: 'text-purple-600', bg: 'bg-purple-50', border: 'border-purple-200' },
  ];

  // Route breakdown data for medication donut chart
  const routeData = React.useMemo(() => {
    const routeCounts = {};
    medications.forEach(m => {
      Object.entries(m.route_breakdown || {}).forEach(([route, cnt]) => {
        routeCounts[route] = (routeCounts[route] || 0) + cnt;
      });
    });
    return Object.entries(routeCounts).map(([name, value]) => ({ name, value }));
  }, [medications]);

  // Filtered co-occurrences
  const filteredSymDia = symDiaCoOccur.filter(p => 
    !searchTerm || 
    p.symptom_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.diagnosis_name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredLabs = labs.filter(l =>
    !searchTerm ||
    l.test_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    l.unit.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Clinical Knowledge Discovery & Analytics</h2>
            <span className="text-xs bg-sky-100 text-sky-800 font-semibold px-2.5 py-0.5 rounded-full border border-sky-200">
              Cohort Analytics
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Exploratory data analysis, co-occurrence patterns, and unit-isolated clinical findings generated directly from structured clinical records.
          </p>
        </div>

        {/* Global Controls Bar */}
        <div className="flex items-center gap-3 self-start md:self-auto">
          {/* Document Filter Dropdown */}
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 border border-slate-200 rounded-lg shadow-sm text-xs">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={filterDocId}
              onChange={(e) => setFilterDocId(e.target.value)}
              className="bg-transparent font-medium text-slate-700 outline-none cursor-pointer max-w-[200px] truncate"
            >
              <option value="">All Ingested Documents</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={fetchAllAnalytics}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold border border-slate-200 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Protocol Banner */}
      <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl flex items-start gap-3 text-xs text-sky-900">
        <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
        <div>
          <h4 className="font-semibold">Deterministic Database Analysis Guarantee</h4>
          <p className="mt-0.5 text-sky-800 leading-relaxed">
            All metrics, statistical distributions, and association matrices are computed deterministically from verified SQLite records. No AI model is used to synthesize clinical findings. Statistical co-occurrences reflect concurrent documentation in records and do not claim clinical causation.
          </p>
        </div>
      </div>

      {/* Error State Alert */}
      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl flex items-start gap-3 text-xs text-rose-800">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="flex-1">
            <span className="font-bold">Error loading analytics: </span>
            {error}
          </div>
          <button onClick={fetchAllAnalytics} className="underline font-bold text-rose-700">Retry</button>
        </div>
      )}

      {/* Summary KPI Cards: All 7 Required Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3">
        {kpiMetrics.map((kpi, idx) => {
          const Icon = kpi.icon;
          return (
            <div key={idx} className={`bg-white rounded-xl border ${kpi.border} p-3.5 shadow-sm flex flex-col justify-between`}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-[11px] font-semibold text-slate-500 truncate">{kpi.title}</span>
                <div className={`p-1.5 rounded-lg ${kpi.bg} ${kpi.color}`}>
                  <Icon className="w-3.5 h-3.5" />
                </div>
              </div>
              <div>
                <span className="text-xl font-bold text-slate-900 tracking-tight">
                  {loading ? '...' : kpi.value}
                </span>
                <p className="text-[10px] text-slate-400 mt-0.5 truncate">{kpi.sub}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Descriptive Knowledge Insights Panel */}
      <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-4 h-4 text-sky-600" />
            <h3 className="font-bold text-slate-800 text-sm">Evidence-Based Clinical Observations</h3>
          </div>
          <span className="text-[11px] text-slate-400 font-medium">Computed from stored records</span>
        </div>

        {insights.length === 0 ? (
          <div className="py-6 text-center text-xs text-slate-400 bg-slate-50 rounded-lg border border-dashed border-slate-200">
            No descriptive insights generated yet. Ingest and structure medical documents to activate clinical observations.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {insights.map((ins, i) => (
              <div key={i} className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-lg hover:border-sky-300 transition-colors">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-sky-700 bg-sky-100/70 px-2 py-0.5 rounded">
                    {ins.title}
                  </span>
                  <span className="text-[10px] font-semibold text-slate-500 bg-white border border-slate-200 px-1.5 py-0.5 rounded">
                    {ins.supporting_count} record(s)
                  </span>
                </div>
                <p className="text-xs text-slate-700 leading-relaxed mt-1">
                  {ins.observation}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Tabbed Navigation */}
      <div className="border-b border-slate-200 flex items-center gap-2 overflow-x-auto">
        {[
          { id: 'symptoms-diagnoses', label: 'Symptoms & Diagnoses', icon: Stethoscope },
          { id: 'medications', label: 'Medications', icon: Pill },
          { id: 'labs', label: 'Laboratory Results', icon: FlaskConical },
          { id: 'cohort-distribution', label: 'Category Distribution', icon: PieChartIcon },
          { id: 'recommendations', label: 'Recommendations', icon: FileCheck },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap ${
                isActive
                  ? 'border-sky-600 text-sky-700 bg-sky-50/50'
                  : 'border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* --------------------------------------------------------------------- */}
      {/* TAB 1: Symptoms & Diagnoses                                           */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === 'symptoms-diagnoses' && (
        <div className="space-y-6">
          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Top Symptoms Bar Chart */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-slate-800 text-sm">Most Frequently Documented Symptoms</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Ranked by count of stored symptom records</p>
                </div>
                <span className="text-[10px] bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded font-semibold">
                  Top {symptoms.length}
                </span>
              </div>

              {symptoms.length === 0 ? (
                <div className="h-56 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                  No symptom records found
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={symptoms} margin={{ top: 10, right: 20, left: -10, bottom: 25 }}>
                      <XAxis dataKey="symptom_name" tick={{ fontSize: 10 }} interval={0} angle={-15} textAnchor="end" />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px', color: '#fff', fontSize: '11px' }}
                        formatter={(val) => [`${val} record(s)`, 'Frequency']}
                      />
                      <Bar dataKey="count" fill="#f59e0b" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* Top Diagnoses Bar Chart */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-slate-800 text-sm">Most Frequently Documented Diagnoses</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Ranked by count of confirmed & provisional diagnoses</p>
                </div>
                <span className="text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded font-semibold">
                  Top {diagnoses.length}
                </span>
              </div>

              {diagnoses.length === 0 ? (
                <div className="h-56 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                  No diagnosis records found
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={diagnoses} margin={{ top: 10, right: 20, left: -10, bottom: 25 }}>
                      <XAxis dataKey="diagnosis_name" tick={{ fontSize: 10 }} interval={0} angle={-15} textAnchor="end" />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px', color: '#fff', fontSize: '11px' }}
                        formatter={(val) => [`${val} record(s)`, 'Frequency']}
                      />
                      <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* Symptom-Diagnosis Co-Occurrence Analysis Table */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="font-bold text-slate-800 text-sm">Symptom & Diagnosis Co-Occurrence Matrix</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Pairs concurrently documented within the same document or patient record.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
                  <input
                    type="text"
                    placeholder="Search pair..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-8 pr-3 py-1 bg-slate-50 border border-slate-200 rounded-lg text-xs outline-none focus:border-sky-500 w-44"
                  />
                </div>
              </div>
            </div>

            {filteredSymDia.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                No symptom-diagnosis co-occurrences found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Documented Symptom</th>
                      <th className="py-2.5 px-3">Documented Diagnosis</th>
                      <th className="py-2.5 px-3">Co-Occurrence Count</th>
                      <th className="py-2.5 px-3">Supporting Pages</th>
                      <th className="py-2.5 px-3">Clinical Traceability</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredSymDia.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/80">
                        <td className="py-2.5 px-3 font-semibold text-slate-800 flex items-center gap-1.5">
                          <Activity className="w-3 h-3 text-amber-500 shrink-0" />
                          <span>{item.symptom_name}</span>
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-slate-800">
                          <span className="flex items-center gap-1.5">
                            <Stethoscope className="w-3 h-3 text-indigo-500 shrink-0" />
                            <span>{item.diagnosis_name}</span>
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-sky-100 text-sky-800 border border-sky-200">
                            {item.co_occurrence_count} document(s)
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 font-mono text-[11px]">
                          {item.supporting_pages?.length > 0 ? `Page ${item.supporting_pages.join(', ')}` : 'Document citation'}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="text-[10px] text-slate-400 bg-slate-100 px-2 py-0.5 rounded">
                            Statistical Association Only
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 2: Medications                                                    */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === 'medications' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Top Medications Bar Chart */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-slate-800 text-sm">Most Frequently Prescribed Pharmaceuticals</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Top medications ranked by prescription count</p>
                </div>
                <span className="text-[10px] bg-rose-50 text-rose-700 border border-rose-200 px-2 py-0.5 rounded font-semibold">
                  Top {medications.length}
                </span>
              </div>

              {medications.length === 0 ? (
                <div className="h-56 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                  No medication records found
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={medications} margin={{ top: 10, right: 20, left: -10, bottom: 25 }}>
                      <XAxis dataKey="medication_name" tick={{ fontSize: 10 }} interval={0} angle={-15} textAnchor="end" />
                      <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#1e293b', border: 'none', borderRadius: '8px', color: '#fff', fontSize: '11px' }}
                        formatter={(val) => [`${val} prescription(s)`, 'Frequency']}
                      />
                      <Bar dataKey="count" fill="#f43f5e" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* Administration Route Distribution Pie Chart */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-bold text-slate-800 text-sm">Administration Route Distribution</h3>
                  <p className="text-xs text-slate-400 mt-0.5">Proportion of documented routes (Oral, IV, Inhalation, etc.)</p>
                </div>
              </div>

              {routeData.length === 0 ? (
                <div className="h-56 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                  No route records documented
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={routeData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={85}
                        paddingAngle={4}
                        dataKey="value"
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      >
                        {routeData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(val, name) => [`${val} medication(s)`, name]} />
                      <Legend verticalAlign="bottom" height={36} iconSize={8} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* Medication-Diagnosis Co-Occurrence Table */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <h3 className="font-bold text-slate-800 text-sm mb-1">Medication & Diagnosis Co-Prescription Patterns</h3>
            <p className="text-xs text-slate-400 mb-4">
              Pharmaceuticals documented together with diagnosed conditions in the same file.
            </p>

            {medDiaCoOccur.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                No medication-diagnosis co-occurrences found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Prescribed Medication</th>
                      <th className="py-2.5 px-3">Documented Diagnosis</th>
                      <th className="py-2.5 px-3">Co-Occurrence Count</th>
                      <th className="py-2.5 px-3">Supporting Pages</th>
                      <th className="py-2.5 px-3">Note</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {medDiaCoOccur.map((item, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/80">
                        <td className="py-2.5 px-3 font-semibold text-slate-800 flex items-center gap-1.5">
                          <Pill className="w-3 h-3 text-rose-500 shrink-0" />
                          <span>{item.medication_name}</span>
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-slate-800">
                          <span className="flex items-center gap-1.5">
                            <Stethoscope className="w-3 h-3 text-indigo-500 shrink-0" />
                            <span>{item.diagnosis_name}</span>
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold bg-rose-100 text-rose-800 border border-rose-200">
                            {item.co_occurrence_count} document(s)
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 font-mono text-[11px]">
                          {item.supporting_pages?.length > 0 ? `Page ${item.supporting_pages.join(', ')}` : 'Document citation'}
                        </td>
                        <td className="py-2.5 px-3 text-[10px] text-slate-400">
                          Documented Co-Prescription
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 3: Laboratory Results (Unit-Isolated)                             */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === 'labs' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="font-bold text-slate-800 text-sm">Unit-Isolated Laboratory Findings Table</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Tests grouped strictly by (test_name, unit) to prevent invalid cross-unit aggregations.
                </p>
              </div>
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
                <input
                  type="text"
                  placeholder="Filter lab tests..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-8 pr-3 py-1 bg-slate-50 border border-slate-200 rounded-lg text-xs outline-none focus:border-sky-500 w-48"
                />
              </div>
            </div>

            {filteredLabs.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                No laboratory results found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Laboratory Test Name</th>
                      <th className="py-2.5 px-3">Documented Unit</th>
                      <th className="py-2.5 px-3">Records Count</th>
                      <th className="py-2.5 px-3">Observed Range (Min - Max)</th>
                      <th className="py-2.5 px-3">Calculated Average</th>
                      <th className="py-2.5 px-3">Documented Reference Interval</th>
                      <th className="py-2.5 px-3">Diagnostic Flags</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredLabs.map((lab, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/80">
                        <td className="py-2.5 px-3 font-semibold text-slate-800 flex items-center gap-1.5">
                          <FlaskConical className="w-3 h-3 text-teal-500 shrink-0" />
                          <span>{lab.test_name}</span>
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-teal-700 font-bold">
                          {lab.unit}
                        </td>
                        <td className="py-2.5 px-3 text-slate-600 font-medium">
                          {lab.total_records} record(s)
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-700">
                          {lab.numeric_record_count > 0 
                            ? `${lab.min_value} – ${lab.max_value} ${lab.unit}` 
                            : lab.sample_values?.length > 0 
                              ? `Qualitative: ${lab.sample_values.join(', ')}` 
                              : 'No numeric values'}
                        </td>
                        <td className="py-2.5 px-3 font-mono font-bold text-slate-900">
                          {lab.avg_value !== null ? `${lab.avg_value} ${lab.unit}` : 'N/A'}
                        </td>
                        <td className="py-2.5 px-3 text-slate-500 font-mono text-[11px]">
                          {lab.documented_reference_ranges?.length > 0
                            ? lab.documented_reference_ranges.join('; ')
                            : 'Not explicitly documented'}
                        </td>
                        <td className="py-2.5 px-3">
                          <div className="flex items-center gap-1 flex-wrap">
                            {Object.entries(lab.flag_breakdown || {}).map(([flag, count], fIdx) => (
                              <span 
                                key={fIdx} 
                                className={`text-[10px] px-1.5 py-0.5 rounded font-semibold ${
                                  flag.toLowerCase() === 'high' || flag.toLowerCase() === 'critical'
                                    ? 'bg-rose-100 text-rose-800'
                                    : flag.toLowerCase() === 'normal'
                                      ? 'bg-emerald-100 text-emerald-800'
                                      : 'bg-slate-100 text-slate-700'
                                }`}
                              >
                                {flag}: {count}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 4: Cohort Entity Distribution                                     */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === 'cohort-distribution' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Donut Chart */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
              <h3 className="font-bold text-slate-800 text-sm mb-1">Clinical Entity Distribution</h3>
              <p className="text-xs text-slate-400 mb-4">
                Relative proportion of records across all six categories ({summary.total_clinical_entities} total entities).
              </p>

              {summary.total_clinical_entities === 0 ? (
                <div className="h-64 flex items-center justify-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                  No clinical entities documented yet
                </div>
              ) : (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={summary.category_distribution}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={95}
                        paddingAngle={3}
                        dataKey="count"
                        nameKey="category"
                        label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                      >
                        {summary.category_distribution.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(val, name) => [`${val} entities`, name]} />
                      <Legend verticalAlign="bottom" height={36} iconSize={8} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>

            {/* Distribution Breakdown Table */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm flex flex-col justify-between">
              <div>
                <h3 className="font-bold text-slate-800 text-sm mb-1">Entity Breakdown Table</h3>
                <p className="text-xs text-slate-400 mb-4">
                  Detailed category counts and cohort representation percentages.
                </p>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                      <tr>
                        <th className="py-2.5 px-3">Clinical Category</th>
                        <th className="py-2.5 px-3 text-right">Entity Count</th>
                        <th className="py-2.5 px-3 text-right">Cohort Share</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {summary.category_distribution.map((cat, idx) => (
                        <tr key={idx} className="hover:bg-slate-50/80">
                          <td className="py-2.5 px-3 font-semibold text-slate-800 flex items-center gap-2">
                            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: PALETTE[idx % PALETTE.length] }}></span>
                            <span>{cat.category}</span>
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono font-bold text-slate-900">
                            {cat.count}
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-slate-600">
                            {cat.percentage}%
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                <span>Total Entities In Cohort</span>
                <span className="font-bold font-mono text-slate-900">{summary.total_clinical_entities}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 5: Recommendations                                                */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === 'recommendations' && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
              <div>
                <h3 className="font-bold text-slate-800 text-sm">Physician Clinical Recommendations & Follow-Up Plans</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Extracted doctor advice and scheduled follow-ups based strictly on existing database fields.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold px-2.5 py-1 bg-purple-50 text-purple-700 border border-purple-200 rounded-lg">
                  {recommendations.with_follow_up_instructions_count} of {recommendations.total_recommendations} with explicit follow-up
                </span>
              </div>
            </div>

            {recommendations.recommendation_records?.length === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400 bg-slate-50 rounded-lg">
                No clinical recommendations recorded in the database.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-3">Documented Care Recommendation</th>
                      <th className="py-2.5 px-3">Follow-Up Instructions</th>
                      <th className="py-2.5 px-3">Source Page Citation</th>
                      <th className="py-2.5 px-3">Document Reference</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {recommendations.recommendation_records.map((r, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/80">
                        <td className="py-2.5 px-3 font-semibold text-slate-800 flex items-start gap-1.5">
                          <FileCheck className="w-3.5 h-3.5 text-purple-600 shrink-0 mt-0.5" />
                          <span className="leading-relaxed">{r.recommendation_text}</span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-600">
                          {r.follow_up_instructions ? (
                            <span className="inline-flex items-center gap-1 font-medium text-purple-800 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
                              <Clock className="w-3 h-3 text-purple-600" />
                              <span>{r.follow_up_instructions}</span>
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">None explicitly documented</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[11px] text-slate-500">
                          {r.page_number ? `Page ${r.page_number}` : 'Unspecified'}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[10px] text-slate-400">
                          {r.document_id ? r.document_id.slice(0, 16) + '...' : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
