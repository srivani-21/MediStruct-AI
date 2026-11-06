import React, { useState, useEffect } from 'react';
import { 
  Download, 
  FileSpreadsheet, 
  FileText, 
  FileCode, 
  Archive,
  CheckCircle2, 
  ShieldCheck, 
  AlertTriangle,
  AlertCircle,
  Filter, 
  Database,
  Info,
  RefreshCw,
  Layers,
  Users,
  Activity,
  Stethoscope,
  Pill,
  FlaskConical,
  FileCheck
} from 'lucide-react';
import axios from 'axios';

export default function DatasetExport() {
  const [selectedFormat, setSelectedFormat] = useState('excel');
  const [singleCsvCategory, setSingleCsvCategory] = useState('symptoms');
  const [deIdentify, setDeIdentify] = useState(true);
  const [selectedDocId, setSelectedDocId] = useState('');
  
  // Documents list
  const [documents, setDocuments] = useState([]);
  
  // Summary counts from backend
  const [summary, setSummary] = useState({
    total_documents: 0,
    total_records: 0,
    categories: {
      patients: 0,
      symptoms: 0,
      diagnoses: 0,
      medications: 0,
      labs: 0,
      recommendations: 0,
    },
  });

  const [selectedCategories, setSelectedCategories] = useState({
    patients: true,
    symptoms: true,
    diagnoses: true,
    medications: true,
    labs: true,
    recommendations: true,
  });

  const [loadingSummary, setLoadingSummary] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState(null);
  const [exportError, setExportError] = useState(null);

  // Fetch documents and summary
  useEffect(() => {
    fetchDocuments();
  }, []);

  useEffect(() => {
    fetchExportSummary(selectedDocId);
  }, [selectedDocId]);

  const fetchDocuments = async () => {
    try {
      const res = await axios.get('/api/documents/');
      setDocuments(res.data || []);
    } catch (err) {
      console.error('Failed to load documents list', err);
    }
  };

  const fetchExportSummary = async (docId) => {
    setLoadingSummary(true);
    try {
      const url = docId ? `/api/export/summary?document_id=${docId}` : '/api/export/summary';
      const res = await axios.get(url);
      setSummary(res.data);
      setExportError(null);
    } catch (err) {
      console.error('Failed to load export summary', err);
      setExportError('Unable to load cohort statistics from backend database.');
    } finally {
      setLoadingSummary(false);
    }
  };

  const exportFormats = [
    {
      id: 'excel',
      name: 'Excel Workbook (.xlsx)',
      icon: FileSpreadsheet,
      badge: 'Multi-Sheet',
      description: 'Research-ready multi-sheet workbook containing Cohort_Manifest and dedicated sheets for all selected categories.',
      extension: '.xlsx',
      mime: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    },
    {
      id: 'bundle',
      name: 'ZIP Archive Bundle (.zip)',
      icon: Archive,
      badge: 'Multi-CSV + Manifest',
      description: 'Compressed archive containing individual category CSV files, manifest.csv, and academic citation README.txt.',
      extension: '.zip',
      mime: 'application/zip',
    },
    {
      id: 'csv',
      name: 'Single Category CSV (.csv)',
      icon: FileText,
      badge: 'Flat Tabular',
      description: 'Dedicated UTF-8 CSV table with byte-order mark (BOM) for statistical analysis in R, Python pandas, Stata, and SPSS.',
      extension: '.csv',
      mime: 'text/csv',
    },
    {
      id: 'json',
      name: 'Structured JSON (.json)',
      icon: FileCode,
      badge: 'Hierarchical',
      description: 'Hierarchical schema capturing cohort metadata, source document references, and nested clinical entities.',
      extension: '.json',
      mime: 'application/json',
    },
  ];

  const categoryMeta = [
    { id: 'patients', label: 'Patients', icon: Users, color: 'text-emerald-600', bg: 'bg-emerald-50' },
    { id: 'symptoms', label: 'Symptoms', icon: Activity, color: 'text-amber-600', bg: 'bg-amber-50' },
    { id: 'diagnoses', label: 'Diagnoses', icon: Stethoscope, color: 'text-indigo-600', bg: 'bg-indigo-50' },
    { id: 'medications', label: 'Medications', icon: Pill, color: 'text-rose-600', bg: 'bg-rose-50' },
    { id: 'labs', label: 'Lab Results', icon: FlaskConical, color: 'text-teal-600', bg: 'bg-teal-50' },
    { id: 'recommendations', label: 'Recommendations', icon: FileCheck, color: 'text-sky-600', bg: 'bg-sky-50' },
  ];

  const handleSelectAll = (selectVal) => {
    setSelectedCategories({
      patients: selectVal,
      symptoms: selectVal,
      diagnoses: selectVal,
      medications: selectVal,
      labs: selectVal,
      recommendations: selectVal,
    });
  };

  const getActiveCategoriesParam = () => {
    return Object.keys(selectedCategories)
      .filter((k) => selectedCategories[k])
      .join(',');
  };

  const handleExportDownload = async () => {
    setExporting(true);
    setExportError(null);
    setExportSuccess(null);

    try {
      let endpoint = '';
      const params = new URLSearchParams();
      params.append('de_identify', String(deIdentify));

      if (selectedDocId) {
        params.append('document_id', selectedDocId);
      }

      if (selectedFormat === 'excel') {
        endpoint = '/api/export/excel';
        const cats = getActiveCategoriesParam();
        if (cats) params.append('categories', cats);
      } else if (selectedFormat === 'bundle') {
        endpoint = '/api/export/bundle';
        const cats = getActiveCategoriesParam();
        if (cats) params.append('categories', cats);
      } else if (selectedFormat === 'csv') {
        endpoint = `/api/export/csv/${singleCsvCategory}`;
      } else if (selectedFormat === 'json') {
        endpoint = '/api/export/json';
        const cats = getActiveCategoriesParam();
        if (cats) params.append('categories', cats);
      }

      const fullUrl = `${endpoint}?${params.toString()}`;

      const response = await axios.get(fullUrl, {
        responseType: 'blob',
      });

      // Extract filename from Content-Disposition header if present
      let downloadFilename = `medistruct_dataset_${new Date().toISOString().slice(0, 10)}.${selectedFormat === 'excel' ? 'xlsx' : selectedFormat === 'bundle' ? 'zip' : selectedFormat}`;
      const disposition = response.headers['content-disposition'];
      if (disposition && disposition.indexOf('filename=') !== -1) {
        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disposition);
        if (matches != null && matches[1]) {
          downloadFilename = matches[1].replace(/['"]/g, '');
        }
      }

      // Create download anchor and click
      const blob = new Blob([response.data]);
      const blobUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.setAttribute('download', downloadFilename);
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
      window.URL.revokeObjectURL(blobUrl);

      setExportSuccess({
        filename: downloadFilename,
        format: selectedFormat.toUpperCase(),
        records: summary.total_records,
        timestamp: new Date().toLocaleTimeString(),
      });
    } catch (err) {
      console.error('Export download failed:', err);
      setExportError(
        err.response?.data?.detail || 'Failed to download dataset export. Please verify database connection and retry.'
      );
    } finally {
      setExporting(false);
    }
  };

  const selectedCount = Object.values(selectedCategories).filter(Boolean).length;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Dataset Export</h2>
            <span className="text-xs bg-emerald-100 text-emerald-800 font-medium px-2.5 py-0.5 rounded-full border border-emerald-200">
              Phase 6 • Production
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            Generate and download research-grade clinical datasets with preserved page citations and HMAC-SHA256 pseudonymization.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700 font-medium self-start md:self-auto">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          <span>HIPAA Safe Harbor De-identification Active</span>
        </div>
      </div>

      {/* Cohort Scope & Document Selector */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div>
            <h3 className="text-sm font-semibold text-slate-800 uppercase tracking-wider flex items-center gap-2">
              <Filter className="w-4 h-4 text-sky-600" />
              1. Document Cohort Scope
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Export findings from the entire database cohort or isolate a single document.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-700 font-medium focus:outline-none focus:ring-2 focus:ring-sky-500"
            >
              <option value="">Entire Ingested Cohort ({documents.length} Documents)</option>
              {documents.map((doc) => (
                <option key={doc.id} value={doc.id}>
                  {doc.filename} ({doc.id.slice(0, 8)}...)
                </option>
              ))}
            </select>
            <button
              onClick={() => fetchExportSummary(selectedDocId)}
              title="Refresh counts"
              className="p-1.5 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loadingSummary ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {/* Live Available Counts Badges */}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 mt-4">
          {categoryMeta.map((cat) => {
            const Icon = cat.icon;
            const count = summary.categories?.[cat.id] ?? 0;
            return (
              <div key={cat.id} className="p-3 rounded-lg border border-slate-100 bg-slate-50/70 flex items-center gap-3">
                <div className={`p-2 rounded-lg ${cat.bg} ${cat.color}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-[11px] text-slate-500 font-medium">{cat.label}</div>
                  <div className="text-base font-bold text-slate-800">
                    {loadingSummary ? '...' : count}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Export Format Selection */}
      <div>
        <h3 className="text-sm font-semibold text-slate-800 mb-3 uppercase tracking-wider">
          2. Select Export Format
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {exportFormats.map((fmt) => {
            const Icon = fmt.icon;
            const isSelected = selectedFormat === fmt.id;
            return (
              <div
                key={fmt.id}
                onClick={() => setSelectedFormat(fmt.id)}
                className={`p-5 rounded-xl border cursor-pointer transition-all ${
                  isSelected
                    ? 'border-sky-600 bg-sky-50/50 shadow-sm ring-1 ring-sky-600'
                    : 'border-slate-200 bg-white hover:border-slate-300'
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className={`p-2 rounded-lg ${isSelected ? 'bg-sky-600 text-white' : 'bg-slate-100 text-slate-700'}`}>
                    <Icon className="w-5 h-5" />
                  </div>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                    {fmt.badge}
                  </span>
                </div>
                <h4 className="font-bold text-slate-800 text-sm">{fmt.name}</h4>
                <p className="text-xs text-slate-500 mt-1 leading-relaxed">{fmt.description}</p>
              </div>
            );
          })}
        </div>
      </div>

      {/* CSV Category Picker (Visible only when Single CSV is selected) */}
      {selectedFormat === 'csv' && (
        <div className="bg-sky-50/60 border border-sky-200 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Info className="w-4 h-4 text-sky-600 shrink-0" />
            <span className="text-xs text-sky-900 font-medium">
              Choose which single clinical category to export as CSV:
            </span>
          </div>
          <select
            value={singleCsvCategory}
            onChange={(e) => setSingleCsvCategory(e.target.value)}
            className="px-3 py-1.5 text-xs bg-white border border-sky-300 rounded-lg text-slate-800 font-medium focus:ring-2 focus:ring-sky-500"
          >
            {categoryMeta.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.label} ({summary.categories?.[cat.id] ?? 0} records)
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Category Selection Filter (For Excel, Bundle, JSON) */}
      {selectedFormat !== 'csv' && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
              3. Category Selection ({selectedCount} of 6 selected)
            </h3>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleSelectAll(true)}
                className="text-xs text-sky-600 hover:text-sky-800 font-medium"
              >
                Select All
              </button>
              <span className="text-slate-300">•</span>
              <button
                type="button"
                onClick={() => handleSelectAll(false)}
                className="text-xs text-slate-500 hover:text-slate-700 font-medium"
              >
                Clear
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 text-xs">
            {categoryMeta.map((cat) => (
              <label
                key={cat.id}
                className={`flex items-center gap-2.5 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedCategories[cat.id]
                    ? 'border-sky-300 bg-sky-50/40 text-slate-900'
                    : 'border-slate-200 bg-slate-50/50 text-slate-500'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selectedCategories[cat.id]}
                  onChange={(e) =>
                    setSelectedCategories({ ...selectedCategories, [cat.id]: e.target.checked })
                  }
                  className="rounded border-slate-300 text-sky-600 focus:ring-sky-500 w-3.5 h-3.5"
                />
                <span className="font-medium">{cat.label}</span>
                <span className="ml-auto text-[10px] text-slate-400">
                  {summary.categories?.[cat.id] ?? 0}
                </span>
              </label>
            ))}
          </div>
        </div>
      )}

      {/* Privacy & De-Identification Safeguards */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-slate-800 mb-3 uppercase tracking-wider flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-emerald-600" />
          4. Privacy Preservation & De-Identification
        </h3>
        
        <label className="flex items-start gap-3 p-3.5 rounded-lg border border-slate-200 bg-slate-50/50 cursor-pointer hover:bg-slate-50 transition-colors">
          <input
            type="checkbox"
            checked={deIdentify}
            onChange={(e) => setDeIdentify(e.target.checked)}
            className="mt-0.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 w-4 h-4"
          />
          <div className="text-xs">
            <span className="font-bold text-slate-800">
              De-identify Dataset using Secret-Keyed HMAC-SHA256 (Default & Recommended)
            </span>
            <p className="text-slate-500 mt-1 leading-relaxed">
              When enabled, direct identifiers (patient names, medical record numbers, demographic contact notes) are redacted and replaced with stable pseudonymized keys (<code className="font-mono text-emerald-700 bg-emerald-50 px-1 py-0.5 rounded">SUBJ-XXXXXXXX</code>, <code className="font-mono text-emerald-700 bg-emerald-50 px-1 py-0.5 rounded">DOC-XXXXXXXX</code>). Source page citations, age, gender, and clinical laboratory findings are preserved.
            </p>
          </div>
        </label>

        {/* Dynamic Privacy Warnings */}
        {!deIdentify ? (
          <div className="mt-3 p-3.5 rounded-lg bg-rose-50 border border-rose-200 text-rose-900 flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            <div className="text-xs">
              <h5 className="font-bold">Strict HIPAA / GDPR Privacy Warning: Non-De-Identified Export</h5>
              <p className="mt-0.5 leading-relaxed text-rose-800">
                You have unchecked de-identification. The exported dataset will contain raw patient names, internal identifiers, and free-text notes. Only proceed if you have explicit Institutional Review Board (IRB) or clinical administrative authorization.
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-3 p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div className="text-xs">
              <span className="font-semibold">Safe Harbor Compliance Guarantee:</span>
              <p className="mt-0.5 text-emerald-800">
                Direct identifiers and file paths are fully pseudonymized. Exported files are research-ready and safe for statistical evaluation.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Feedback Alerts */}
      {exportSuccess && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-start justify-between gap-3 shadow-sm">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            <div>
              <h5 className="font-bold text-sm">Dataset Export Successfully Generated</h5>
              <p className="text-xs text-emerald-800 mt-1">
                Downloaded <code className="font-mono bg-emerald-100 px-1 py-0.5 rounded">{exportSuccess.filename}</code> ({exportSuccess.format}).
              </p>
            </div>
          </div>
          <span className="text-[11px] text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded">
            {exportSuccess.timestamp}
          </span>
        </div>
      )}

      {exportError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 flex items-start gap-3 shadow-sm">
          <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs">
            <h5 className="font-bold text-sm">Export Failed</h5>
            <p className="mt-0.5 text-rose-800">{exportError}</p>
          </div>
        </div>
      )}

      {/* Export Action Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 text-center">
        <div className="w-12 h-12 rounded-full bg-sky-50 text-sky-600 flex items-center justify-center mx-auto mb-3">
          <Download className="w-6 h-6" />
        </div>
        <h4 className="text-base font-bold text-slate-800">
          Generate {exportFormats.find((f) => f.id === selectedFormat)?.name}
        </h4>
        <p className="text-xs text-slate-500 max-w-md mx-auto mt-1 mb-5">
          Deterministic database export from SQLite. Extracted clinical findings will maintain exact relational references and page citations.
        </p>

        <button
          onClick={handleExportDownload}
          disabled={exporting || (selectedFormat !== 'csv' && selectedCount === 0)}
          className={`inline-flex items-center gap-2 px-6 py-2.5 rounded-lg text-xs font-semibold shadow-sm transition-colors ${
            exporting || (selectedFormat !== 'csv' && selectedCount === 0)
              ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
              : 'bg-sky-600 hover:bg-sky-700 text-white'
          }`}
        >
          {exporting ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              <span>Generating & Packaging Dataset...</span>
            </>
          ) : (
            <>
              <Download className="w-4 h-4" />
              <span>Download {exportFormats.find((f) => f.id === selectedFormat)?.badge}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
