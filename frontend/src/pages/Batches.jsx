import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestionAPI } from '../api'
import { CheckCircle, XCircle, Clock, Loader, FileText } from 'lucide-react'

function StatusIcon({ status }) {
  if (status === 'COMPLETE')    return <CheckCircle size={16} className="text-green-500" />
  if (status === 'FAILED')      return <XCircle size={16} className="text-red-500" />
  if (status === 'PROCESSING')  return <Loader size={16} className="text-blue-500 animate-spin" />
  return <Clock size={16} className="text-yellow-500" />
}

const SOURCE_COLOR = { SAP: 'bg-amber-100 text-amber-800', UTILITY: 'bg-cyan-100 text-cyan-800', TRAVEL: 'bg-purple-100 text-purple-800' }

export default function Batches() {
  const [batches, setBatches] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    ingestionAPI.getBatches()
      .then(r => setBatches(r.data.results || []))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Batch History</h1>
        <p className="text-gray-500 text-sm mt-1">All ingestion runs — with parse outcomes and error summaries.</p>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">File</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Source</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Uploaded</th>
              <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Rows</th>
              <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Parsed</th>
              <th className="text-right px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Errors</th>
              <th className="text-left px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status</th>
              <th className="px-5 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading ? (
              <tr><td colSpan={8} className="text-center py-12 text-gray-400">Loading…</td></tr>
            ) : batches.length === 0 ? (
              <tr><td colSpan={8} className="text-center py-12 text-gray-400">No batches yet. Upload your first file.</td></tr>
            ) : batches.map(b => (
              <tr key={b.id} className="hover:bg-gray-50">
                <td className="px-5 py-4">
                  <div className="flex items-center gap-2">
                    <FileText size={15} className="text-gray-400 shrink-0" />
                    <span className="font-medium text-gray-800 truncate max-w-[200px]">{b.original_filename || 'Unnamed'}</span>
                  </div>
                </td>
                <td className="px-5 py-4">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${SOURCE_COLOR[b.source_type] || 'bg-gray-100 text-gray-700'}`}>
                    {b.source_type}
                  </span>
                </td>
                <td className="px-5 py-4 text-gray-500 text-xs font-mono">
                  {new Date(b.uploaded_at).toLocaleString()}
                </td>
                <td className="px-5 py-4 text-right font-mono">{b.row_count}</td>
                <td className="px-5 py-4 text-right font-mono text-green-700">{b.parsed_count}</td>
                <td className="px-5 py-4 text-right font-mono text-red-600">{b.error_count}</td>
                <td className="px-5 py-4">
                  <div className="flex items-center gap-1.5">
                    <StatusIcon status={b.status} />
                    <span className="text-xs">{b.status}</span>
                  </div>
                  {b.error_summary && (
                    <p className="text-xs text-orange-600 mt-0.5 max-w-[200px] truncate" title={b.error_summary}>
                      {b.error_summary}
                    </p>
                  )}
                </td>
                <td className="px-5 py-4">
                  <button
                    onClick={() => navigate(`/review?batch=${b.id}`)}
                    className="text-xs text-brand-600 hover:text-brand-700 font-medium"
                  >
                    View records
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
