import React, { useState, useEffect } from 'react';
import { 
  UploadCloud, 
  FileText, 
  CheckCircle2, 
  AlertCircle, 
  Clock, 
  Settings, 
  Layers, 
  RefreshCw, 
  Info, 
  Play, 
  Eye, 
  Trash2, 
  PenTool, 
  Check,
  ChevronLeft,
  ChevronRight,
  ShieldAlert,
  FileCheck2,
  HelpCircle,
  Sparkles
} from 'lucide-react';
import axios from 'axios';

export default function DocumentIngestion() {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploadedDocs, setUploadedDocs] = useState([]);
  const [forceOcr, setForceOcr] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [processingId, setProcessingId] = useState(null);
  const [activePreviewDoc, setActivePreviewDoc] = useState(null);
  const [errorMsg, setErrorMsg] = useState(null);

  // Verification panel state
  const [verifyDoc, setVerifyDoc] = useState(null);
  const [docPages, setDocPages] = useState([]);
  const [activePageIndex, setActivePageIndex] = useState(0);
  const [correctionText, setCorrectionText] = useState("");
  const [savingVerification, setSavingVerification] = useState(false);
  const [verifySuccessMsg, setVerifySuccessMsg] = useState(null);

  useEffect(() => {
    fetchDocuments();
  }, []);

  const fetchDocuments = async () => {
    try {
      const res = await axios.get('/api/documents?limit=50');
      setUploadedDocs(res.data);
    } catch (err) {
      console.error("Failed to fetch documents:", err);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files) {
      const filesArray = Array.from(e.target.files);
      setSelectedFiles(filesArray);
      setErrorMsg(null);
    }
  };

  const handleUploadAndProcess = async () => {
    if (selectedFiles.length === 0) return;
    setUploading(true);
    setErrorMsg(null);

    const formData = new FormData();
    selectedFiles.forEach((f) => formData.append('files', f));

    try {
      const uploadRes = await axios.post('/api/documents/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const newDocs = uploadRes.data;
      setSelectedFiles([]);

      for (const doc of newDocs) {
        setProcessingId(doc.id);
        try {
          await axios.post(`/api/documents/${doc.id}/process?force_ocr=${forceOcr}`);
        } catch (procErr) {
          console.error(`Extraction failed for ${doc.filename}:`, procErr);
        }
      }

      await fetchDocuments();
    } catch (err) {
      console.error("Upload failed:", err);
      setErrorMsg(err.response?.data?.detail || "Document upload failed. Ensure files are valid PDFs, JPGs, or PNGs.");
    } finally {
      setUploading(false);
      setProcessingId(null);
    }
  };

  const handleReprocess = async (docId) => {
    setProcessingId(docId);
    try {
      await axios.post(`/api/documents/${docId}/process?force_ocr=${forceOcr}`);
      await fetchDocuments();
      if (activePreviewDoc?.id === docId) {
        handleViewPreview(docId);
      }
      if (verifyDoc?.id === docId) {
        handleOpenVerify(docId);
      }
    } catch (err) {
      console.error("Reprocess error:", err);
      alert("Extraction failed: " + (err.response?.data?.detail || err.message));
    } finally {
      setProcessingId(null);
    }
  };

  const handleDelete = async (docId) => {
    if (!window.confirm("Are you sure you want to delete this document and its records?")) return;
    try {
      await axios.delete(`/api/documents/${docId}`);
      if (activePreviewDoc?.id === docId) setActivePreviewDoc(null);
      if (verifyDoc?.id === docId) setVerifyDoc(null);
      await fetchDocuments();
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  const handleViewPreview = async (docId) => {
    try {
      const res = await axios.get(`/api/documents/${docId}`);
      setActivePreviewDoc(res.data);
    } catch (err) {
      console.error("Failed to fetch preview:", err);
    }
  };

  const handleOpenVerify = async (docId) => {
    try {
      const docRes = await axios.get(`/api/documents/${docId}`);
      const pagesRes = await axios.get(`/api/documents/${docId}/pages`);
      setVerifyDoc(docRes.data);
      setDocPages(pagesRes.data);
      setActivePageIndex(0);
      setVerifySuccessMsg(null);
      if (pagesRes.data.length > 0) {
        const first = pagesRes.data[0];
        setCorrectionText(first.human_corrected_text || first.gemini_text || first.final_text || first.ocr_text || "");
      }
    } catch (err) {
      console.error("Failed to fetch pages for verification:", err);
      alert("Could not load page verification details: " + (err.response?.data?.detail || err.message));
    }
  };

  const handlePageSelect = (index) => {
    setActivePageIndex(index);
    setVerifySuccessMsg(null);
    const targetPage = docPages[index];
    if (targetPage) {
      setCorrectionText(targetPage.human_corrected_text || targetPage.gemini_text || targetPage.final_text || targetPage.ocr_text || "");
    }
  };

  const handleSaveVerification = async () => {
    if (!verifyDoc || docPages.length === 0) return;
    const curPage = docPages[activePageIndex];
    if (!curPage) return;

    setSavingVerification(true);
    setVerifySuccessMsg(null);
    try {
      const res = await axios.post(`/api/documents/${verifyDoc.id}/pages/${curPage.page_number}/verify`, {
        human_corrected_text: correctionText,
      });

      // Update local page record
      const updatedPages = [...docPages];
      updatedPages[activePageIndex] = res.data;
      setDocPages(updatedPages);
      setVerifySuccessMsg(`Page ${curPage.page_number} verified and saved successfully.`);
      await fetchDocuments();
    } catch (err) {
      console.error("Verification save error:", err);
      alert("Failed to save verification: " + (err.response?.data?.detail || err.message));
    } finally {
      setSavingVerification(false);
    }
  };

  // Helper to render text with [UNCLEAR] tokens highlighted
  const renderTextWithHighlights = (rawText) => {
    if (!rawText) return <span className="text-slate-400 italic">No text extracted for this page.</span>;
    const parts = rawText.split(/(\[UNCLEAR\])/gi);
    return parts.map((part, idx) => {
      if (part.toUpperCase() === '[UNCLEAR]') {
        return (
          <span 
            key={idx} 
            className="inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs font-bold rounded bg-amber-200 text-amber-900 border border-amber-300 shadow-xs"
            title="Ambiguous or illegible handwriting: marked by AI model"
          >
            [UNCLEAR]
          </span>
        );
      }
      return <span key={idx}>{part}</span>;
    });
  };

  const currentPage = docPages[activePageIndex] || null;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Document Ingestion</h2>
            <span className="text-xs bg-sky-100 text-sky-800 font-semibold px-2.5 py-0.5 rounded-full border border-sky-200">
              Intake Pipeline
            </span>
          </div>
          <p className="text-sm text-slate-500 mt-1">
            High-precision multi-format digital extraction, OCR, and handwriting evaluation for clinical records.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 font-medium self-start md:self-auto">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
          <span>Intake & Extraction Pipeline Ready</span>
        </div>
      </div>

      {/* Pipeline Status Banner */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-sky-600" />
            <h3 className="font-semibold text-slate-800 text-sm">Multimodal Extraction Engine Configuration</h3>
          </div>
          <span className="text-[11px] font-medium text-slate-500">
            High-Resolution Character Detection & Text Stream Analysis
          </span>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 text-xs bg-slate-50 p-3.5 rounded-lg border border-slate-200">
          <div className="flex items-center gap-3">
            <label className="relative inline-flex items-center cursor-pointer">
              <input 
                type="checkbox" 
                checked={forceOcr} 
                onChange={(e) => setForceOcr(e.target.checked)} 
                className="sr-only peer" 
              />
              <div className="w-9 h-5 bg-slate-300 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-sky-600"></div>
            </label>
            <div>
              <span className="font-semibold text-slate-800">Force OCR Setting</span>
              <p className="text-[11px] text-slate-500">
                Force OCR across all pages, bypassing digital text layers (recommended for scanned documents with noisy font artifacts).
              </p>
            </div>
          </div>
          <span className="text-[11px] font-medium text-slate-600 bg-white px-2.5 py-1 rounded border border-slate-200 shrink-0">
            Formats: PDF, JPG, PNG
          </span>
        </div>
      </div>

      {/* Error Message Alert */}
      {errorMsg && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-xs text-rose-800 flex items-start gap-3">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold">Upload Error:</span> {errorMsg}
          </div>
        </div>
      )}

      {/* Multi-Format Upload Dropzone */}
      <div className="bg-white rounded-xl border-2 border-dashed border-slate-300 hover:border-sky-500 transition-colors p-8 shadow-sm text-center">
        <input 
          type="file" 
          id="doc-upload" 
          multiple 
          accept=".pdf,.jpg,.jpeg,.png" 
          onChange={handleFileChange} 
          disabled={uploading}
          className="hidden" 
        />
        <label htmlFor="doc-upload" className="cursor-pointer flex flex-col items-center justify-center">
          <div className="w-14 h-14 rounded-full bg-sky-50 text-sky-600 flex items-center justify-center mb-3 shadow-sm">
            <UploadCloud className="w-7 h-7" />
          </div>
          <h3 className="text-base font-bold text-slate-800">Select or Drag & Drop Medical Documents</h3>
          <p className="text-xs text-slate-500 mt-1 max-w-md">
            Support for digital PDFs, scanned clinical reports, and handwritten doctor notes/prescriptions (.pdf, .jpg, .png). Maximum 50MB per file.
          </p>
          <span className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors">
            <FileText className="w-3.5 h-3.5" />
            <span>Browse Files</span>
          </span>
        </label>
      </div>

      {/* Staged Files Ready to Ingest */}
      {selectedFiles.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h4 className="text-sm font-bold text-slate-800">
                Staged Files ({selectedFiles.length})
              </h4>
              <p className="text-xs text-slate-500">Ready to upload and process with multimodal extraction pipeline</p>
            </div>
            <button
              onClick={handleUploadAndProcess}
              disabled={uploading}
              className="inline-flex items-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-4 py-2 rounded-lg shadow-sm transition-colors disabled:opacity-50"
            >
              {uploading ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Processing Extraction...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  <span>Upload & Ingest All</span>
                </>
              )}
            </button>
          </div>

          <div className="space-y-2">
            {selectedFiles.map((file, idx) => {
              const ext = file.name.split('.').pop().toUpperCase();
              return (
                <div key={idx} className="p-3 bg-slate-50 border border-slate-200 rounded-lg flex items-center justify-between text-xs">
                  <div className="flex items-center gap-3">
                    <FileText className="w-4 h-4 text-sky-600" />
                    <div>
                      <span className="font-semibold text-slate-800">{file.name}</span>
                      <span className="text-slate-400 block text-[11px]">
                        {(file.size / 1024).toFixed(1)} KB • {ext} Format
                      </span>
                    </div>
                  </div>
                  <span className="text-xs font-medium text-slate-500 bg-white px-2.5 py-1 rounded border border-slate-200">
                    Staged
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Ingested Documents Queue Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h3 className="text-base font-bold text-slate-900">Ingested Documents & Extraction Status</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Multi-page clinical documents with handwriting classification and human-verification lifecycle.
            </p>
          </div>
          <button
            onClick={fetchDocuments}
            className="p-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-slate-600 transition-colors"
            title="Refresh documents"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {uploadedDocs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold">
                  <th className="p-3 pl-5">Document</th>
                  <th className="p-3">Pages</th>
                  <th className="p-3">Characters</th>
                  <th className="p-3">Classification</th>
                  <th className="p-3">Method</th>
                  <th className="p-3">Verification</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right pr-5">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {uploadedDocs.map((doc) => {
                  const isProcessing = processingId === doc.id;
                  const isHandwritten = doc.handwriting_detected || doc.document_type === 'handwritten';

                  return (
                    <tr key={doc.id} className="hover:bg-slate-50/70 transition-colors">
                      <td className="p-3 pl-5 font-medium text-slate-900">
                        <div className="flex items-center gap-2.5">
                          <FileText className="w-4 h-4 text-sky-600 shrink-0" />
                          <div>
                            <span className="font-semibold block truncate max-w-xs">{doc.filename}</span>
                            <span className="text-[10px] text-slate-400 font-mono">{doc.id}</span>
                          </div>
                        </div>
                      </td>
                      <td className="p-3 font-mono font-medium text-slate-700">
                        {doc.page_count}
                      </td>
                      <td className="p-3 font-mono font-medium text-slate-700">
                        {doc.character_count.toLocaleString()}
                      </td>
                      <td className="p-3">
                        <div className="flex items-center gap-1.5">
                          <span className="capitalize font-medium text-slate-700">{doc.document_type}</span>
                          {doc.handwriting_detected && (
                            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-100 text-purple-800 border border-purple-200" title="Handwriting detected">
                              <PenTool className="w-2.5 h-2.5" />
                              <span>Handwritten</span>
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="p-3 font-mono text-[11px] text-slate-600">
                        {doc.extraction_method}
                      </td>
                      <td className="p-3">
                        {isHandwritten ? (
                          <button
                            onClick={() => handleOpenVerify(doc.id)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-semibold bg-amber-50 text-amber-800 hover:bg-amber-100 border border-amber-300 transition-colors"
                            title="Review handwriting and verify text"
                          >
                            <FileCheck2 className="w-3.5 h-3.5 text-amber-600" />
                            <span>Verify ✎</span>
                          </button>
                        ) : (
                          <span className="text-slate-400 font-medium">Auto-Verified</span>
                        )}
                      </td>
                      <td className="p-3">
                        {isProcessing ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11px] font-semibold bg-sky-100 text-sky-800">
                            <RefreshCw className="w-3 h-3 animate-spin" />
                            <span>Extracting...</span>
                          </span>
                        ) : (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${
                            doc.processing_status === 'COMPLETED'
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : doc.processing_status === 'FAILED'
                              ? 'bg-rose-50 text-rose-700 border-rose-200'
                              : 'bg-amber-50 text-amber-700 border-amber-200'
                          }`}>
                            {doc.processing_status}
                          </span>
                        )}
                      </td>
                      <td className="p-3 text-right pr-5">
                        <div className="inline-flex items-center gap-1.5">
                          <button
                            onClick={() => handleViewPreview(doc.id)}
                            className="p-1.5 rounded hover:bg-slate-200 text-slate-600 transition-colors"
                            title="View extracted text preview"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleReprocess(doc.id)}
                            disabled={isProcessing}
                            className="p-1.5 rounded hover:bg-slate-200 text-slate-600 transition-colors"
                            title="Reprocess document"
                          >
                            <RefreshCw className={`w-4 h-4 ${isProcessing ? 'animate-spin' : ''}`} />
                          </button>
                          <button
                            onClick={() => handleDelete(doc.id)}
                            className="p-1.5 rounded hover:bg-rose-100 text-rose-600 transition-colors"
                            title="Delete document"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center flex flex-col items-center justify-center">
            <div className="w-12 h-12 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center mb-3">
              <Layers className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-bold text-slate-800">No Documents Ingested Yet</h4>
            <p className="text-xs text-slate-500 max-w-sm mt-1">
              Select or drop PDF, JPG, or PNG files above to process multimodal digital extraction, OCR, and clinical handwriting analysis.
            </p>
          </div>
        )}
      </div>

      {/* Human Verification Studio Panel */}
      {verifyDoc && currentPage && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-md p-6 space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-200 gap-3">
            <div>
              <div className="flex items-center gap-2">
                <FileCheck2 className="w-5 h-5 text-amber-600" />
                <h3 className="text-base font-bold text-slate-900">
                  Human Verification Studio: {verifyDoc.filename}
                </h3>
                <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                  Page {currentPage.page_number} of {docPages.length}
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Classification: <span className="font-semibold capitalize text-slate-700">{currentPage.page_classification}</span> • Method: <code className="font-mono">{currentPage.extraction_method}</code> • Status: <span className="font-semibold uppercase text-amber-700">{currentPage.verification_status}</span>
              </p>
            </div>
            <div className="flex items-center gap-2">
              <div className="inline-flex rounded-md shadow-xs">
                <button
                  onClick={() => handlePageSelect(Math.max(0, activePageIndex - 1))}
                  disabled={activePageIndex === 0}
                  className="px-2.5 py-1 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-l-md hover:bg-slate-50 disabled:opacity-40"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                <span className="px-3 py-1 text-xs font-semibold bg-slate-50 border-t border-b border-slate-300 text-slate-700">
                  {activePageIndex + 1} / {docPages.length}
                </span>
                <button
                  onClick={() => handlePageSelect(Math.min(docPages.length - 1, activePageIndex + 1))}
                  disabled={activePageIndex === docPages.length - 1}
                  className="px-2.5 py-1 text-xs font-medium text-slate-700 bg-white border border-slate-300 rounded-r-md hover:bg-slate-50 disabled:opacity-40"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
              <button
                onClick={() => setVerifyDoc(null)}
                className="text-xs text-slate-500 hover:text-slate-800 font-semibold px-2.5 py-1 bg-slate-100 rounded hover:bg-slate-200 transition-colors"
              >
                Close Studio
              </button>
            </div>
          </div>

          {/* Clinical Research Notice */}
          <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-900 flex items-start gap-2.5">
            <ShieldAlert className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div>
              <span className="font-bold">Clinical Safety Protocol:</span> In accordance with medical research standards, ambiguous handwritten dosages, medicines, or names are marked with <code className="font-bold bg-amber-200 px-1 rounded">[UNCLEAR]</code>. Review the original page image below and correct any ambiguous tokens before clinical structuring.
            </div>
          </div>

          {verifySuccessMsg && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800 flex items-center gap-2">
              <Check className="w-4 h-4 text-emerald-600" />
              <span>{verifySuccessMsg}</span>
            </div>
          )}

          {/* Side-by-Side: Original Image vs Extracted / Corrected Text */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left: Original Page Image */}
            <div className="border border-slate-200 rounded-lg p-3 bg-slate-50 flex flex-col">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200 mb-3 text-xs font-semibold text-slate-700">
                <span>Original Document Page Image</span>
                {currentPage.ocr_confidence && (
                  <span className="text-[11px] font-mono text-slate-500">
                    OCR Conf: {currentPage.ocr_confidence.toFixed(1)}%
                  </span>
                )}
              </div>
              <div className="flex-1 flex items-center justify-center min-h-[350px] max-h-[500px] overflow-auto bg-white rounded border border-slate-200 p-2">
                {currentPage.image_available ? (
                  <img
                    src={`/api/documents/${verifyDoc.id}/pages/${currentPage.page_number}/image?t=${Date.now()}`}
                    alt={`Document Page ${currentPage.page_number}`}
                    className="max-h-[460px] w-auto object-contain shadow-xs"
                  />
                ) : (
                  <div className="text-center text-slate-400 p-8 text-xs">
                    <FileText className="w-10 h-10 mx-auto text-slate-300 mb-2" />
                    <span>Page image preview not stored for this digital document.</span>
                  </div>
                )}
              </div>
            </div>

            {/* Right: AI Transcription & Human Correction Editor */}
            <div className="flex flex-col space-y-4">
              {/* Highlighted AI Output Preview */}
              <div className="border border-slate-200 rounded-lg p-3 bg-slate-50">
                <div className="flex items-center justify-between pb-2 border-b border-slate-200 mb-2 text-xs font-semibold text-slate-700">
                  <div className="flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                    <span>Automated AI Transcription</span>
                  </div>
                  {currentPage.unclear_count > 0 && (
                    <span className="text-[11px] font-semibold text-amber-800 bg-amber-100 border border-amber-200 px-2 py-0.5 rounded">
                      {currentPage.unclear_count} Ambiguous Tokens
                    </span>
                  )}
                </div>
                <div className="p-3 bg-white rounded border border-slate-200 max-h-40 overflow-y-auto font-mono text-xs text-slate-800 whitespace-pre-wrap leading-relaxed">
                  {renderTextWithHighlights(currentPage.gemini_text || currentPage.ocr_text)}
                </div>
              </div>

              {/* Editable Human Correction Area */}
              <div className="flex-1 flex flex-col space-y-2">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                  <label htmlFor="correction-text" className="flex items-center gap-1.5">
                    <PenTool className="w-3.5 h-3.5 text-sky-600" />
                    <span>Verified Transcription (Editable by Clinical Reviewer)</span>
                  </label>
                  <span className="text-[11px] text-slate-400 font-normal">
                    Edit unclear tokens, medicines, or dosages above
                  </span>
                </div>
                <textarea
                  id="correction-text"
                  rows={8}
                  value={correctionText}
                  onChange={(e) => setCorrectionText(e.target.value)}
                  className="w-full p-3 font-mono text-xs text-slate-900 border border-slate-300 rounded-lg focus:ring-2 focus:ring-sky-500 focus:border-sky-500 outline-none leading-relaxed"
                  placeholder="Review and enter corrected medical text here..."
                />
                <div className="flex items-center justify-between pt-2">
                  <span className="text-[11px] text-slate-500">
                    Characters: {correctionText.length}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setVerifyDoc(null)}
                      className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 bg-slate-100 rounded-lg hover:bg-slate-200 transition-colors"
                    >
                      Skip Page
                    </button>
                    <button
                      onClick={handleSaveVerification}
                      disabled={savingVerification}
                      className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-xs transition-colors disabled:opacity-50"
                    >
                      {savingVerification ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          <span>Saving...</span>
                        </>
                      ) : (
                        <>
                          <Check className="w-3.5 h-3.5" />
                          <span>Save & Mark Verified</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Extracted Text Preview Modal / Section */}
      {activePreviewDoc && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-200">
            <div>
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <span>Extracted Text Preview: {activePreviewDoc.filename}</span>
                <span className="text-xs font-mono font-normal text-slate-400">({activePreviewDoc.id})</span>
              </h3>
              <p className="text-xs text-slate-500 mt-0.5">
                {activePreviewDoc.page_count} pages • {activePreviewDoc.character_count.toLocaleString()} characters • Method: <code className="font-mono">{activePreviewDoc.extraction_method}</code>
              </p>
            </div>
            <button
              onClick={() => setActivePreviewDoc(null)}
              className="text-xs text-slate-500 hover:text-slate-800 font-semibold px-2.5 py-1 bg-slate-100 rounded"
            >
              Close Preview
            </button>
          </div>

          <div className="bg-slate-900 text-slate-100 rounded-lg p-4 font-mono text-xs overflow-x-auto max-h-96 whitespace-pre-wrap leading-relaxed">
            {activePreviewDoc.raw_text ? (
              renderTextWithHighlights(activePreviewDoc.raw_text)
            ) : (
              <span className="text-slate-500 italic">No text extracted. Processing status: {activePreviewDoc.processing_status}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
