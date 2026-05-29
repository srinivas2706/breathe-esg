import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { ingestionAPI } from '../api'
import { useAuth } from '../hooks/useAuth'
import { Upload, FileText, CheckCircle, AlertCircle, Info } from 'lucide-react'

const SOURCES = [
  {
    key: 'SAP',
    label: 'SAP — Fuel & Procurement',
    icon: '🏭',
    description: 'CSV flat-file export from SAP MM module. Accepts German or English column headers (MENGE, MEINS, WERKS, BLDAT). Supports both semicolon and comma delimiters.',
    accepts: '.csv,.txt',
    sampleFields: ['BLDAT', 'WERKS', 'MATNR', 'MENGE', 'MEINS', 'KOSTL'],
    scopeLabel: 'Scope 1 + Scope 3 (procurement)',
  },
  {
    key: 'UTILITY',
    label: 'Utility — Electricity',
    icon: '⚡',
    description: 'CSV portal export from utility providers (EcoStruxure, Siemens, direct utility portals). Handles billing periods that don\'t align with calendar months.',
    accepts: '.csv',
    sampleFields: ['account_number', 'meter_id', 'billing_start', 'billing_end', 'consumption', 'unit'],
    scopeLabel: 'Scope 2',
  },
  {
    key: 'TRAVEL',
    label: 'Corporate Travel',
    icon: '✈️',
    description: 'CSV export from Concur Expense, Navan, or similar. Flights, hotels, car hire, rail. Distances calculated via Great Circle formula when not provided.',
    accepts: '.csv',
    sampleFields: ['trip_id', 'employee_id', 'segment_type', 'origin', 'destination', 'travel_date', 'class'],
    scopeLabel: 'Scope 3, Cat. 6',
  },
]

function SourceCard({ source, selected, onSelect }) {
  return (
    <button
      onClick={() => onSelect(source.key)}
      className={`text-left p-5 rounded-xl border-2 transition-all ${
        selected
          ? 'border-brand-500 bg-brand-50'
          : 'border-gray-200 bg-white hover:border-gray-300'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="text-2xl">{source.icon}</span>
        <div className="min-w-0">
          <p className="font-semibold text-gray-900 text-sm">{source.label}</p>
          <span className="text-xs text-gray-500 font-mono">{source.scopeLabel}</span>
          <p className="text-xs text-gray-500 mt-1">{source.description}</p>
          <div className="flex flex-wrap gap-1 mt-2">
            {source.sampleFields.map(f => (
              <span key={f} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 text-xs font-mono rounded">
                {f}
              </span>
            ))}
          </div>
        </div>
      </div>
    </button>
  )
}

export default function Ingest() {
  const [selectedSource, setSelectedSource] = useState(null)
  const [file, setFile] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const fileRef = useRef()
  const { user } = useAuth()
  const navigate = useNavigate()

  const handleUpload = async () => {
    if (!file || !selectedSource) return
    setLoading(true)
    setError('')
    setResult(null)

    const fd = new FormData()
    fd.append('file', file)
    fd.append('source_type', selectedSource)
    if (user?.client_id) fd.append('client_id', user.client_id)

    try {
      const { data } = await ingestionAPI.upload(fd)
      setResult(data)
    } catch (err) {
      setError(err.response?.data?.error || 'Upload failed. Please check your file format.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-8 max-w-3xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Ingest Data</h1>
        <p className="text-gray-500 text-sm mt-1">Upload a source file to create normalised emission records.</p>
      </div>

      {/* Step 1 */}
      <div className="mb-8">
        <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
          <span className="w-5 h-5 rounded-full bg-brand-600 text-white text-xs flex items-center justify-center">1</span>
          Select source type
        </h2>
        <div className="grid gap-3">
          {SOURCES.map(s => (
            <SourceCard
              key={s.key}
              source={s}
              selected={selectedSource === s.key}
              onSelect={setSelectedSource}
            />
          ))}
        </div>
      </div>

      {/* Step 2 */}
      {selectedSource && (
        <div className="mb-8">
          <h2 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-brand-600 text-white text-xs flex items-center justify-center">2</span>
            Upload file
          </h2>
          <div
            onClick={() => fileRef.current?.click()}
            className="border-2 border-dashed border-gray-200 rounded-xl p-8 text-center cursor-pointer hover:border-brand-400 transition-colors"
          >
            {file ? (
              <div className="flex items-center justify-center gap-3 text-brand-700">
                <FileText size={20} />
                <span className="font-medium text-sm">{file.name}</span>
                <span className="text-xs text-gray-400">({(file.size / 1024).toFixed(1)} KB)</span>
              </div>
            ) : (
              <>
                <Upload size={24} className="mx-auto text-gray-400 mb-2" />
                <p className="text-sm text-gray-600 font-medium">Click to select a CSV file</p>
                <p className="text-xs text-gray-400 mt-1">Max 10 MB</p>
              </>
            )}
          </div>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,.txt"
            className="hidden"
            onChange={e => setFile(e.target.files[0])}
          />
        </div>
      )}

      {/* Upload button */}
      {file && selectedSource && !result && (
        <button
          onClick={handleUpload}
          disabled={loading}
          className="btn-primary"
        >
          {loading ? (
            <><span className="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full" /> Processing…</>
          ) : (
            <><Upload size={16} /> Upload & Process</>
          )}
        </button>
      )}

      {/* Error */}
      {error && (
        <div className="mt-4 flex items-start gap-2 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          <AlertCircle size={16} className="mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      {/* Success result */}
      {result && (
        <div className="mt-6 card p-6">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle className="text-green-600" size={20} />
            <h3 className="font-semibold text-gray-900">Ingestion Complete</h3>
          </div>
          <div className="grid grid-cols-3 gap-4 mb-4">
            <div className="text-center p-3 bg-gray-50 rounded-lg">
              <p className="text-2xl font-bold text-gray-900">{result.row_count}</p>
              <p className="text-xs text-gray-500">Total rows</p>
            </div>
            <div className="text-center p-3 bg-green-50 rounded-lg">
              <p className="text-2xl font-bold text-green-700">{result.parsed_count}</p>
              <p className="text-xs text-gray-500">Parsed OK</p>
            </div>
            <div className="text-center p-3 bg-red-50 rounded-lg">
              <p className="text-2xl font-bold text-red-700">{result.error_count}</p>
              <p className="text-xs text-gray-500">Errors</p>
            </div>
          </div>
          {result.error_summary && (
            <div className="flex items-start gap-2 p-3 bg-orange-50 border border-orange-200 rounded-lg text-xs text-orange-700 mb-4">
              <Info size={14} className="mt-0.5 shrink-0" />
              {result.error_summary}
            </div>
          )}
          <button onClick={() => navigate('/review')} className="btn-primary">
            Review Records →
          </button>
        </div>
      )}
    </div>
  )
}
