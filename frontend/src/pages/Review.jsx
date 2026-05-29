import { useState, useEffect, useCallback } from 'react'
import { emissionsAPI } from '../api'
import { CheckCircle, Flag, XCircle, ChevronDown, Search, Filter, AlertTriangle, RefreshCw } from 'lucide-react'

const STATUS_TABS = [
  { key: '', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'FLAGGED', label: 'Flagged' },
  { key: 'APPROVED', label: 'Approved' },
  { key: 'REJECTED', label: 'Rejected' },
]

const SOURCE_OPTIONS = ['', 'SAP', 'UTILITY', 'TRAVEL']
const SCOPE_OPTIONS = ['', '1', '2', '3']

function StatusBadge({ status }) {
  const map = {
    PENDING:  <span className="badge-pending">Pending</span>,
    APPROVED: <span className="badge-approved">Approved</span>,
    FLAGGED:  <span className="badge-flagged">Flagged</span>,
    REJECTED: <span className="badge-rejected">Rejected</span>,
  }
  return map[status] || <span className="text-xs text-gray-400">{status}</span>
}

function ScopeBadge({ scope }) {
  return <span className={`badge-scope${scope}`}>Scope {scope}</span>
}

function FlagChip({ flag }) {
  if (!flag) return null
  const labels = {
    OUTLIER: '⚠ Outlier',
    UNIT_AMBIGUOUS: '⚠ Unit?',
    FACTOR_MISSING: '⚠ Factor missing',
    DATE_INVALID: '⚠ Bad date',
    BILLING_OVERLAP: '⚠ Overlap',
  }
  return <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">{labels[flag] || flag}</span>
}

function ReviewModal({ record, onClose, onDone }) {
  const [status, setStatus] = useState('')
  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    if (!status) return
    setSaving(true)
    try {
      await emissionsAPI.review(record.id, { review_status: status, note })
      onDone()
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl">
        <h3 className="text-lg font-semibold mb-1">Review Record</h3>
        <p className="text-sm text-gray-500 mb-4">
          {record.source_type} · Scope {record.scope} · {record.category} · {record.period_start}
        </p>

        <div className="bg-gray-50 rounded-xl p-4 mb-4 text-sm space-y-1">
          <div className="flex justify-between">
            <span className="text-gray-500">Activity</span>
            <span className="font-mono font-medium">{record.activity_value} {record.activity_unit}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Normalised</span>
            <span className="font-mono font-medium">{record.normalised_value} {record.normalised_unit}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">CO₂e</span>
            <span className="font-mono font-semibold text-brand-700">{record.co2e_kg ? `${(record.co2e_kg/1000).toFixed(3)} t` : '—'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Factor source</span>
            <span className="text-xs">{record.emission_factor_source || '—'}</span>
          </div>
          {record.facility_name && (
            <div className="flex justify-between">
              <span className="text-gray-500">Facility</span>
              <span>{record.facility_name}</span>
            </div>
          )}
          {record.flag && (
            <div className="mt-2 p-2 bg-orange-50 rounded-lg text-orange-700 text-xs">
              <strong>Flag:</strong> {record.flag_detail || record.flag}
            </div>
          )}
        </div>

        <div className="mb-4">
          <p className="text-sm font-medium mb-2">Decision</p>
          <div className="grid grid-cols-3 gap-2">
            {[
              { v: 'APPROVED', label: 'Approve', color: 'border-green-400 bg-green-50 text-green-700' },
              { v: 'FLAGGED',  label: 'Flag',    color: 'border-orange-400 bg-orange-50 text-orange-700' },
              { v: 'REJECTED', label: 'Reject',  color: 'border-red-400 bg-red-50 text-red-700' },
            ].map(({ v, label, color }) => (
              <button
                key={v}
                onClick={() => setStatus(v)}
                className={`py-2 text-sm font-medium rounded-lg border-2 transition-all ${
                  status === v ? color : 'border-gray-200 text-gray-600 hover:border-gray-300'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <textarea
          value={note}
          onChange={e => setNote(e.target.value)}
          placeholder="Reviewer note (optional)…"
          rows={2}
          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 mb-4"
        />

        <div className="flex gap-2 justify-end">
          <button onClick={onClose} className="btn-secondary">Cancel</button>
          <button onClick={submit} disabled={!status || saving} className="btn-primary">
            {saving ? 'Saving…' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default function Review() {
  const [records, setRecords] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('')
  const [search, setSearch] = useState('')
  const [sourceFilter, setSourceFilter] = useState('')
  const [scopeFilter, setScopeFilter] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState(new Set())
  const [reviewing, setReviewing] = useState(null)
  const [bulkNote, setBulkNote] = useState('')

  const load = useCallback(() => {
    setLoading(true)
    const params = {
      page,
      ...(tab && { review_status: tab }),
      ...(search && { search }),
      ...(sourceFilter && { source_type: sourceFilter }),
      ...(scopeFilter && { scope: scopeFilter }),
    }
    emissionsAPI.getRecords(params)
      .then(r => { setRecords(r.data.results || []); setCount(r.data.count || 0) })
      .finally(() => setLoading(false))
  }, [tab, search, sourceFilter, scopeFilter, page])

  useEffect(() => { load() }, [load])

  const toggleSelect = (id) => {
    const s = new Set(selected)
    s.has(id) ? s.delete(id) : s.add(id)
    setSelected(s)
  }

  const bulkApprove = async () => {
    await emissionsAPI.bulkApprove([...selected], bulkNote || 'Bulk approval')
    setSelected(new Set())
    load()
  }

  const totalPages = Math.ceil(count / 50)

  return (
    <div className="p-8">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Review Records</h1>
          <p className="text-gray-500 text-sm mt-1">{count} records total</p>
        </div>
        <button onClick={load} className="btn-secondary">
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-5 bg-gray-100 p-1 rounded-xl w-fit">
        {STATUS_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); setPage(1) }}
            className={`px-4 py-1.5 text-sm font-medium rounded-lg transition-all ${
              tab === t.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-5">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-2.5 text-gray-400" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search facility, ref…"
            className="pl-8 pr-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 w-56"
          />
        </div>
        <select value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none">
          <option value="">All sources</option>
          {SOURCE_OPTIONS.slice(1).map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={scopeFilter} onChange={e => setScopeFilter(e.target.value)}
          className="px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none">
          <option value="">All scopes</option>
          {SCOPE_OPTIONS.slice(1).map(s => <option key={s} value={s}>Scope {s}</option>)}
        </select>
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div className="flex items-center gap-3 p-3 bg-brand-50 border border-brand-200 rounded-xl mb-4 text-sm">
          <span className="font-medium text-brand-800">{selected.size} selected</span>
          <input
            value={bulkNote}
            onChange={e => setBulkNote(e.target.value)}
            placeholder="Note (optional)"
            className="px-2 py-1 border border-brand-200 rounded text-xs"
          />
          <button onClick={bulkApprove} className="btn-primary text-xs py-1.5">
            <CheckCircle size={13} /> Bulk Approve
          </button>
          <button onClick={() => setSelected(new Set())} className="text-gray-500 hover:text-gray-700">Clear</button>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b border-gray-100">
            <tr>
              <th className="w-10 px-4 py-3">
                <input type="checkbox" onChange={e => {
                  if (e.target.checked) setSelected(new Set(records.map(r => r.id)))
                  else setSelected(new Set())
                }} />
              </th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Source / Scope</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Category</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Period</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Activity</th>
              <th className="text-right px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">CO₂e (kg)</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Facility</th>
              <th className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">Status / Flag</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading ? (
              <tr><td colSpan={9} className="text-center py-12 text-gray-400">Loading…</td></tr>
            ) : records.length === 0 ? (
              <tr><td colSpan={9} className="text-center py-12 text-gray-400">No records found</td></tr>
            ) : records.map(r => (
              <tr key={r.id} className={`hover:bg-gray-50 transition-colors ${selected.has(r.id) ? 'bg-brand-50' : ''}`}>
                <td className="px-4 py-3">
                  <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-medium text-gray-700">{r.source_type}</span>
                    <ScopeBadge scope={r.scope} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  <span className="text-gray-800 font-medium">{r.category}</span>
                  {r.subcategory && <p className="text-xs text-gray-400">{r.subcategory}</p>}
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">{r.period_start}</td>
                <td className="px-4 py-3 font-mono text-xs">
                  {r.activity_value} <span className="text-gray-400">{r.activity_unit}</span>
                </td>
                <td className="px-4 py-3 text-right font-mono font-semibold">
                  {r.co2e_kg ? (+r.co2e_kg).toLocaleString() : <span className="text-gray-300">—</span>}
                </td>
                <td className="px-4 py-3 text-xs text-gray-600 max-w-[140px] truncate" title={r.facility_name}>
                  {r.facility_name || '—'}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col gap-1">
                    <StatusBadge status={r.review_status} />
                    <FlagChip flag={r.flag} />
                  </div>
                </td>
                <td className="px-4 py-3">
                  {!r.is_locked && (
                    <button
                      onClick={() => setReviewing(r)}
                      className="text-xs text-brand-600 hover:text-brand-700 font-medium"
                    >
                      Review
                    </button>
                  )}
                  {r.is_locked && <span className="text-xs text-gray-300">Locked</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-500">
          <span>Page {page} of {totalPages}</span>
          <div className="flex gap-2">
            <button disabled={page === 1} onClick={() => setPage(p => p-1)} className="btn-secondary py-1.5 px-3 disabled:opacity-40">← Prev</button>
            <button disabled={page >= totalPages} onClick={() => setPage(p => p+1)} className="btn-secondary py-1.5 px-3 disabled:opacity-40">Next →</button>
          </div>
        </div>
      )}

      {reviewing && (
        <ReviewModal
          record={reviewing}
          onClose={() => setReviewing(null)}
          onDone={() => { setReviewing(null); load() }}
        />
      )}
    </div>
  )
}
