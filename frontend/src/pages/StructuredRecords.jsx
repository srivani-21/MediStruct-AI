import React, { useState, useEffect } from 'react';
import { 
  Database, 
  Users, 
  Activity, 
  Stethoscope, 
  Pill, 
  FlaskConical, 
  FileCheck, 
  Search, 
  Filter, 
  Clock, 
  Sparkles,
  Info,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  FileText,
  ChevronRight,
  ShieldAlert,
  ArrowRight
} from 'lucide-react';
import { Link } from 'react-router-dom';
import axios from 'axios';

export default function StructuredRecords() {
  const [activeCategory, setActiveCategory] = useState('patients');
  const [records, setRecords] = useState([]);
  const [counts, setCounts] = useState({
    patients: 0,
    symptoms: 0,
    diagnoses: 0,
    medications: 0,
    labs: 0,
    recommendations: 0,
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Search & Filter
  const [searchTerm, setSearchTerm] = useState('');
  const [filterDocId, setFilterDocId] = useState('');
  const [subFilter, setSubFilter] = useState('');

  // Document list for selection & structuring
  const [documents, setDocuments] = useState([]);
  const [selectedDocToStructure, setSelectedDocToStructure] = useState('');
  const [structuring, setStructuring] = useState(false);
  const [structureMsg, setStructureMsg] = useState(null);
  const [structureError, setStructureError] = useState(null);

  const categories = [
    { id: 'patients', name: 'Patients', icon: Users, count: counts.patients, endpoint: '/api/records/patients' },
    { id: 'symptoms', name: 'Symptoms', icon: Activity, count: counts.symptoms, endpoint: '/api/records/symptoms' },
    { id: 'diagnoses', name: 'Diagnoses', icon: Stethoscope, count: counts.diagnoses, endpoint: '/api/records/diagnoses' },
    { id: 'medications', name: 'Medications', icon: Pill, count: counts.medications, endpoint: '/api/records/medications' },
    { id: 'labs', name: 'Laboratory Results', icon: FlaskConical, count: counts.labs, endpoint: '/api/records/labs' },
    { id: 'recommendations', name: 'Recommendations', icon: FileCheck, count: counts.recommendations, endpoint: '/api/records/recommendations' },
  ];

  // Load documents list and overview metrics on mount
  useEffect(() => {
    fetchDocumentsList();
    fetchCounts();
  }, []);

  // Fetch category data whenever activeCategory, filterDocId, or searchTerm changes
  useEffect(() => {
    fetchCategoryRecords();
  }, [activeCategory, filterDocId, searchTerm, subFilter]);

  const fetchDocumentsList = async () => {
    try {
      const res = await axios.get('/api/documents?limit=100');
      setDocuments(res.data);
      if (res.data.length > 0 && !selectedDocToStructure) {
        setSelectedDocToStructure(res.data[0].id);
      }
    } catch (err) {
      console.error("Failed to fetch documents for structuring:", err);
    }
  };

  const fetchCounts = async () => {
    try {
      const res = await axios.get('/api/analytics/overview');
      const data = res.data;
      setCounts({
        patients: data.total_patients || 0,
        symptoms: data.total_symptoms || 0,
        diagnoses: data.total_diagnoses || 0,
        medications: data.total_medications || 0,
        labs: data.total_lab_tests || 0,
        recommendations: data.total_recommendations || 0,
      });
    } catch (err) {
      console.error("Failed to fetch entity counts:", err);
    }
  };

  const fetchCategoryRecords = async () => {
    setLoading(true);
    setError(null);
    try {
      const currentCat = categories.find(c => c.id === activeCategory);
      const params = {};
      if (filterDocId) params.document_id = filterDocId;
      if (searchTerm.trim()) params.search = searchTerm.trim();
      if (activeCategory === 'symptoms' && subFilter) params.severity = subFilter;
      if (activeCategory === 'labs' && subFilter) params.flag = subFilter;

      const res = await axios.get(currentCat.endpoint, { params });
      setRecords(res.data);
    } catch (err) {
      console.error(`Error fetching ${activeCategory}:`, err);
      setError(err.response?.data?.detail || `Failed to load ${activeCategory} from database.`);
    } finally {
      setLoading(false);
    }
  };

  const handleTriggerStructuring = async () => {
    if (!selectedDocToStructure) return;
    setStructuring(true);
    setStructureMsg(null);
    setStructureError(null);

    try {
      const res = await axios.post(`/api/records/structure/${selectedDocToStructure}`);
      const saved = res.data.entities_saved;
      const totalSaved = (saved.symptoms || 0) + (saved.diagnoses || 0) + 
                         (saved.medications || 0) + (saved.lab_results || 0) + 
                         (saved.recommendations || 0) + (res.data.patient_id ? 1 : 0);

      setStructureMsg({
        text: `Clinical structuring successful! Extracted & persisted ${totalSaved} clinical entities.`,
        details: saved
      });

      // Refresh records and counts
      await fetchCounts();
      await fetchCategoryRecords();
      await fetchDocumentsList();
    } catch (err) {
      console.error("Clinical structuring failed:", err);
      setStructureError(
        err.response?.data?.detail || "AI clinical structuring failed. Please check backend service status."
      );
    } finally {
      setStructuring(false);
    }
  };

  // Helper to lookup filename by document ID
  const getDocFilename = (docId) => {
    const doc = documents.find(d => d.id === docId);
    return doc ? doc.filename : docId;
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Structured Clinical Records</h2>
            <span className="text-xs bg-sky-100 text-sky-800 font-semibold px-2.5 py-0.5 rounded-full border border-sky-200">
              Standardized Records
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Standardized healthcare datasets extracted from clinical documentation with page-level citations and human verification safeguards.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 font-medium self-start md:self-auto">
          <Sparkles className="w-3.5 h-3.5 text-purple-600" />
          <span>Clinical Structuring Pipeline Active</span>
        </div>
      </div>

      {/* Action Bar: Initiate AI Clinical Structuring */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h3 className="font-semibold text-slate-800 text-sm flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-purple-600" />
              <span>AI Clinical Structuring Engine</span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Select an ingested document to extract demographics, symptoms, diagnoses, medications, labs, and care recommendations.
            </p>
          </div>
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <select
              value={selectedDocToStructure}
              onChange={(e) => setSelectedDocToStructure(e.target.value)}
              disabled={structuring || documents.length === 0}
              className="bg-slate-50 border border-slate-300 text-slate-800 text-xs rounded-lg px-3 py-2 outline-none focus:ring-2 focus:ring-sky-500 max-w-xs truncate"
            >
              {documents.length === 0 && <option value="">No documents uploaded</option>}
              {documents.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.filename} ({d.document_type})
                </option>
              ))}
            </select>
            <button
              onClick={handleTriggerStructuring}
              disabled={structuring || !selectedDocToStructure}
              className="inline-flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors disabled:opacity-50 shrink-0"
            >
              {structuring ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Structuring with AI...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Structure with AI</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Structuring Success Banner */}
        {structureMsg && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-900 space-y-2">
            <div className="flex items-center gap-2 font-bold text-emerald-800">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>{structureMsg.text}</span>
            </div>
            {structureMsg.details && (
              <div className="flex flex-wrap gap-3 pt-1 text-[11px] font-mono text-emerald-800">
                <span className="bg-white/80 px-2 py-0.5 rounded border border-emerald-200">
                  Symptoms: {structureMsg.details.symptoms || 0}
                </span>
                <span className="bg-white/80 px-2 py-0.5 rounded border border-emerald-200">
                  Diagnoses: {structureMsg.details.diagnoses || 0}
                </span>
                <span className="bg-white/80 px-2 py-0.5 rounded border border-emerald-200">
                  Medications: {structureMsg.details.medications || 0}
                </span>
                <span className="bg-white/80 px-2 py-0.5 rounded border border-emerald-200">
                  Labs: {structureMsg.details.lab_results || 0}
                </span>
                <span className="bg-white/80 px-2 py-0.5 rounded border border-emerald-200">
                  Recommendations: {structureMsg.details.recommendations || 0}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Structuring Error / Verification Required Banner */}
        {structureError && (
          <div className="p-4 bg-amber-50 border border-amber-300 rounded-xl text-xs text-amber-900 space-y-2">
            <div className="flex items-start gap-2.5">
              <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <div className="flex-1">
                <span className="font-bold text-amber-950 block mb-0.5">Structuring Blocked by Safety Protocol</span>
                <span>{structureError}</span>
                {structureError.includes("verification is strictly required") && (
                  <div className="mt-2">
                    <Link
                      to="/documents"
                      className="inline-flex items-center gap-1.5 px-3 py-1 bg-amber-600 hover:bg-amber-700 text-white rounded text-xs font-semibold shadow-xs transition-colors"
                    >
                      <span>Open Document Ingestion to Verify</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Category Tabs */}
      <div className="bg-white p-2 rounded-xl border border-slate-200 shadow-sm flex flex-wrap gap-2">
        {categories.map((cat) => {
          const Icon = cat.icon;
          const isActive = activeCategory === cat.id;
          return (
            <button
              key={cat.id}
              onClick={() => {
                setActiveCategory(cat.id);
                setSubFilter('');
              }}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-lg text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'bg-slate-50 hover:bg-slate-100 text-slate-600'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span>{cat.name}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                isActive ? 'bg-sky-700 text-white' : 'bg-slate-200 text-slate-700'
              }`}>
                {cat.count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Records Table Container */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {/* Table Controls: Search, Document Filter, Sub-Filter */}
        <div className="p-4 border-b border-slate-200 flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="relative flex-1 max-w-md">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder={`Search in ${categories.find(c => c.id === activeCategory)?.name.toLowerCase()}...`}
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-9 pr-4 py-1.5 bg-slate-50 border border-slate-300 rounded-lg text-xs text-slate-800 focus:bg-white focus:ring-2 focus:ring-sky-500 outline-none"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Filter by Document */}
            <div className="flex items-center gap-1.5">
              <Filter className="w-3.5 h-3.5 text-slate-400" />
              <select
                value={filterDocId}
                onChange={(e) => setFilterDocId(e.target.value)}
                className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-2.5 py-1.5 outline-none focus:ring-2 focus:ring-sky-500 max-w-xs"
              >
                <option value="">All Documents</option>
                {documents.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            </div>

            {/* Category-Specific Sub-Filters */}
            {activeCategory === 'symptoms' && (
              <select
                value={subFilter}
                onChange={(e) => setSubFilter(e.target.value)}
                className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-2.5 py-1.5 outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="">All Severities</option>
                <option value="Mild">Mild</option>
                <option value="Moderate">Moderate</option>
                <option value="Severe">Severe</option>
              </select>
            )}

            {activeCategory === 'labs' && (
              <select
                value={subFilter}
                onChange={(e) => setSubFilter(e.target.value)}
                className="bg-slate-50 border border-slate-300 text-slate-700 text-xs rounded-lg px-2.5 py-1.5 outline-none focus:ring-2 focus:ring-sky-500"
              >
                <option value="">All Flags</option>
                <option value="Normal">Normal</option>
                <option value="High">High</option>
                <option value="Low">Low</option>
                <option value="Critical">Critical</option>
              </select>
            )}

            <button
              onClick={() => {
                fetchCategoryRecords();
                fetchCounts();
              }}
              className="p-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-slate-600 transition-colors"
              title="Refresh records"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Content State: Loading, Error, Table, or Empty */}
        {loading ? (
          <div className="p-16 text-center flex flex-col items-center justify-center">
            <RefreshCw className="w-8 h-8 text-sky-600 animate-spin mb-3" />
            <p className="text-xs text-slate-500">Loading structured clinical records from database...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-xs text-rose-600 space-y-2">
            <AlertCircle className="w-8 h-8 mx-auto text-rose-500" />
            <p className="font-semibold">Failed to load records</p>
            <p className="text-slate-500 max-w-sm mx-auto">{error}</p>
          </div>
        ) : records.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              {/* Category-Specific Table Headers */}
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                  {activeCategory === 'patients' && (
                    <>
                      <th className="p-3 pl-5">Patient Identifier</th>
                      <th className="p-3">Full Name</th>
                      <th className="p-3">Age</th>
                      <th className="p-3">Gender</th>
                      <th className="p-3">Demographics / Notes</th>
                      <th className="p-3">Source Document</th>
                      <th className="p-3 text-right pr-5">Extracted</th>
                    </>
                  )}
                  {activeCategory === 'symptoms' && (
                    <>
                      <th className="p-3 pl-5">Symptom</th>
                      <th className="p-3">Description</th>
                      <th className="p-3">Duration</th>
                      <th className="p-3">Severity</th>
                      <th className="p-3">Page</th>
                      <th className="p-3">Source Document</th>
                      <th className="p-3 text-right pr-5">Recorded</th>
                    </>
                  )}
                  {activeCategory === 'diagnoses' && (
                    <>
                      <th className="p-3 pl-5">Diagnosis</th>
                      <th className="p-3">Clinical Description</th>
                      <th className="p-3">Date</th>
                      <th className="p-3">Status</th>
                      <th className="p-3">Page</th>
                      <th className="p-3">Source Document</th>
                      <th className="p-3 text-right pr-5">Recorded</th>
                    </>
                  )}
                  {activeCategory === 'medications' && (
                    <>
                      <th className="p-3 pl-5">Medication Name</th>
                      <th className="p-3">Dosage / Strength</th>
                      <th className="p-3">Frequency</th>
                      <th className="p-3">Duration</th>
                      <th className="p-3">Route</th>
                      <th className="p-3">Page</th>
                      <th className="p-3">Source Document</th>
                    </>
                  )}
                  {activeCategory === 'labs' && (
                    <>
                      <th className="p-3 pl-5">Laboratory Test</th>
                      <th className="p-3">Result Value</th>
                      <th className="p-3">Numeric</th>
                      <th className="p-3">Unit</th>
                      <th className="p-3">Reference Range</th>
                      <th className="p-3">Flag</th>
                      <th className="p-3">Page</th>
                      <th className="p-3">Source Document</th>
                    </>
                  )}
                  {activeCategory === 'recommendations' && (
                    <>
                      <th className="p-3 pl-5">Physician Recommendation</th>
                      <th className="p-3">Follow-up Instructions</th>
                      <th className="p-3">Page</th>
                      <th className="p-3">Source Document</th>
                      <th className="p-3 text-right pr-5">Recorded</th>
                    </>
                  )}
                </tr>
              </thead>

              {/* Table Rows */}
              <tbody className="divide-y divide-slate-100">
                {records.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/70 transition-colors">
                    {/* Patients View */}
                    {activeCategory === 'patients' && (
                      <>
                        <td className="p-3 pl-5 font-mono font-semibold text-slate-800">
                          {r.patient_identifier || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3 font-medium text-slate-900">
                          {r.name || <span className="text-slate-400 italic">Not documented</span>}
                        </td>
                        <td className="p-3 font-mono text-slate-700">
                          {r.age !== null && r.age !== undefined ? r.age : <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3 capitalize text-slate-700">
                          {r.gender || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3 text-slate-600 max-w-xs truncate">
                          {r.demographic_notes || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3 font-medium text-sky-700">
                          <span className="block truncate max-w-xs">{getDocFilename(r.document_id)}</span>
                          <span className="text-[10px] text-slate-400 font-mono">{r.document_id}</span>
                        </td>
                        <td className="p-3 text-right pr-5 text-slate-400 text-[11px]">
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                      </>
                    )}

                    {/* Symptoms View */}
                    {activeCategory === 'symptoms' && (
                      <>
                        <td className="p-3 pl-5 font-semibold text-slate-900">
                          {r.symptom_name}
                        </td>
                        <td className="p-3 text-slate-600 max-w-sm truncate">
                          {r.description || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3 text-slate-700 font-medium">
                          {r.duration || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3">
                          {r.severity ? (
                            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                              r.severity.toLowerCase().includes('severe')
                                ? 'bg-rose-100 text-rose-800 border border-rose-200'
                                : r.severity.toLowerCase().includes('moderate')
                                ? 'bg-amber-100 text-amber-800 border border-amber-200'
                                : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                            }`}>
                              {r.severity}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">null</span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="px-1.5 py-0.5 font-mono text-[11px] bg-slate-100 text-slate-700 rounded border border-slate-200">
                            Page {r.page_number || 1}
                          </span>
                        </td>
                        <td className="p-3 font-medium text-sky-700">
                          <span className="block truncate max-w-xs">{getDocFilename(r.document_id)}</span>
                        </td>
                        <td className="p-3 text-right pr-5 text-slate-400 text-[11px]">
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                      </>
                    )}

                    {/* Diagnoses View */}
                    {activeCategory === 'diagnoses' && (
                      <>
                        <td className="p-3 pl-5 font-semibold text-slate-900">
                          {r.diagnosis_name}
                        </td>
                        <td className="p-3 text-slate-600 max-w-sm truncate">
                          {r.description || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3 font-mono text-slate-700">
                          {r.diagnosis_date || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                            {r.status || 'Confirmed'}
                          </span>
                        </td>
                        <td className="p-3">
                          <span className="px-1.5 py-0.5 font-mono text-[11px] bg-slate-100 text-slate-700 rounded border border-slate-200">
                            Page {r.page_number || 1}
                          </span>
                        </td>
                        <td className="p-3 font-medium text-sky-700">
                          <span className="block truncate max-w-xs">{getDocFilename(r.document_id)}</span>
                        </td>
                        <td className="p-3 text-right pr-5 text-slate-400 text-[11px]">
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                      </>
                    )}

                    {/* Medications View */}
                    {activeCategory === 'medications' && (
                      <>
                        <td className="p-3 pl-5 font-semibold text-slate-900">
                          {r.medication_name}
                        </td>
                        <td className="p-3 font-mono text-slate-800 font-medium">
                          {r.dosage || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3 text-slate-700">
                          {r.frequency || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3 text-slate-700">
                          {r.duration || <span className="text-slate-400 italic">null</span>}
                        </td>
                        <td className="p-3">
                          {r.route ? (
                            <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
                              {r.route}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">null</span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="px-1.5 py-0.5 font-mono text-[11px] bg-slate-100 text-slate-700 rounded border border-slate-200">
                            Page {r.page_number || 1}
                          </span>
                        </td>
                        <td className="p-3 font-medium text-sky-700">
                          <span className="block truncate max-w-xs">{getDocFilename(r.document_id)}</span>
                        </td>
                      </>
                    )}

                    {/* Labs View */}
                    {activeCategory === 'labs' && (
                      <>
                        <td className="p-3 pl-5 font-semibold text-slate-900">
                          {r.test_name}
                        </td>
                        <td className="p-3 font-mono font-bold text-slate-900">
                          {r.result_value}
                        </td>
                        <td className="p-3 font-mono text-slate-600">
                          {r.numeric_value !== null ? r.numeric_value : <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3 text-slate-700">
                          {r.unit || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3 font-mono text-slate-600">
                          {r.reference_range || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3">
                          {r.flag ? (
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              r.flag.toLowerCase().includes('high') || r.flag.toLowerCase().includes('critical')
                                ? 'bg-rose-100 text-rose-800 border border-rose-200'
                                : r.flag.toLowerCase().includes('low')
                                ? 'bg-blue-100 text-blue-800 border border-blue-200'
                                : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                            }`}>
                              {r.flag}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic">—</span>
                          )}
                        </td>
                        <td className="p-3">
                          <span className="px-1.5 py-0.5 font-mono text-[11px] bg-slate-100 text-slate-700 rounded border border-slate-200">
                            Page {r.page_number || 1}
                          </span>
                        </td>
                        <td className="p-3 font-medium text-sky-700">
                          <span className="block truncate max-w-xs">{getDocFilename(r.document_id)}</span>
                        </td>
                      </>
                    )}

                    {/* Recommendations View */}
                    {activeCategory === 'recommendations' && (
                      <>
                        <td className="p-3 pl-5 font-medium text-slate-900 max-w-md">
                          {r.recommendation_text}
                        </td>
                        <td className="p-3 text-slate-600 max-w-sm truncate">
                          {r.follow_up_instructions || <span className="text-slate-400 italic">—</span>}
                        </td>
                        <td className="p-3">
                          <span className="px-1.5 py-0.5 font-mono text-[11px] bg-slate-100 text-slate-700 rounded border border-slate-200">
                            Page {r.page_number || 1}
                          </span>
                        </td>
                        <td className="p-3 font-medium text-sky-700">
                          <span className="block truncate max-w-xs">{getDocFilename(r.document_id)}</span>
                        </td>
                        <td className="p-3 text-right pr-5 text-slate-400 text-[11px]">
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-16 text-center flex flex-col items-center justify-center">
            <div className="w-14 h-14 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-4">
              <Database className="w-7 h-7" />
            </div>
            <h4 className="text-base font-semibold text-slate-800">
              No {categories.find(c => c.id === activeCategory)?.name} Found
            </h4>
            <p className="text-xs text-slate-500 max-w-md mt-1 mb-4 leading-relaxed">
              {filterDocId || searchTerm ? (
                <span>No matching records found for the selected filter or search query.</span>
              ) : (
                <span>
                  The clinical database currently contains no extracted {categories.find(c => c.id === activeCategory)?.name.toLowerCase()}.
                  Select a document above and click <strong>Structure with AI</strong> to extract clinical entities.
                </span>
              )}
            </p>
            <div className="p-3 bg-sky-50 border border-sky-100 rounded-lg text-left max-w-lg text-[11px] text-sky-800 flex items-start gap-2">
              <Info className="w-4 h-4 text-sky-600 shrink-0 mt-0.5" />
              <span>
                <strong>Academic Integrity Guarantee:</strong> MediStruct AI strictly extracts documented data with source page traceability. Missing fields are stored as null and never fabricated.
              </span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
