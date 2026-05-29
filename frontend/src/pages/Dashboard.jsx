import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend
} from 'recharts'
import { emissionsAPI } from '../api'
import { AlertTriangle, CheckCircle, Clock, Leaf, RefreshCw } from 'lucide-react'

const SCOPE_COLORS  = { 1: '#ef4444', 2: '#3b82f6', 3: '#a855f7' }
const SOURCE_COLORS = { SAP: '#f59e0b', UTILITY: '#06b6d4', TRAVEL: '#8b5cf6' }
const SOURCE_COLORS_LIST = ['#f59e0b', '#06b6d4', '#8b5cf6', '#10b981', '#f43f5e']

function StatCard({ label, value, unit, icon: Icon, bg }) {
  return (
    <div style={{background:'white',borderRadius:12,border:'1px solid #f0f0f0',padding:'20px',display:'flex',alignItems:'flex-start',gap:16}}>
      <div style={{width:42,height:42,borderRadius:10,display:'flex',alignItems:'center',justifyContent:'center',background:bg,flexShrink:0}}>
        <Icon size={20} color="white" />
      </div>
      <div>
        <p style={{fontSize:11,color:'#888',fontWeight:600,textTransform:'uppercase',letterSpacing:'0.05em',margin:0}}>{label}</p>
        <p style={{fontSize:26,fontWeight:700,color:'#111',margin:'4px 0 0'}}>{value}</p>
        {unit && <p style={{fontSize:12,color:'#aaa',margin:0}}>{unit}</p>}
      </div>
    </div>
  )
}

// Custom legend for pie chart — always shows all slices
const CustomLegend = ({ sourceData }) => (
  <div style={{display:'flex',flexDirection:'column',gap:8,justifyContent:'center',paddingLeft:16}}>
    {sourceData.map((entry, i) => (
      <div key={entry.name} style={{display:'flex',alignItems:'center',gap:8}}>
        <div style={{width:12,height:12,borderRadius:3,background:SOURCE_COLORS[entry.name] || SOURCE_COLORS_LIST[i % SOURCE_COLORS_LIST.length],flexShrink:0}}/>
        <div>
          <span style={{fontSize:13,fontWeight:600,color:'#374151'}}>{entry.name}</span>
          <span style={{fontSize:12,color:'#6b7280',marginLeft:6}}>{entry.value} t</span>
          <span style={{fontSize:11,color:'#9ca3af',marginLeft:4}}>
            ({entry.count} records)
          </span>
        </div>
      </div>
    ))}
  </div>
)

export default function Dashboard() {
  const [records, setRecords] = useState([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState('')
  const [year,    setYear]    = useState('')

  const load = async (selectedYear) => {
    setLoading(true)
    setError('')
    try {
      const params = { page_size: 500 }
      if (selectedYear) params.reporting_year = selectedYear
      const res = await emissionsAPI.getRecords(params)
      const data = res.data
      setRecords(data.results || (Array.isArray(data) ? data : []))
    } catch (e) {
      setError('Could not load records: ' + (e?.response?.data?.detail || e.message || String(e)))
      setRecords([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(year) }, [year])

  if (loading) return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',height:300,gap:12}}>
      <div style={{width:28,height:28,border:'3px solid #22c55e',borderTopColor:'transparent',borderRadius:'50%',animation:'spin 0.8s linear infinite'}}/>
      <span style={{color:'#6b7280',fontSize:14}}>Loading…</span>
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  )

  const totalRecords  = records.length
  const pendingCount  = records.filter(r => r.review_status === 'PENDING').length
  const approvedCount = records.filter(r => r.review_status === 'APPROVED').length
  const flaggedCount  = records.filter(r => r.flag && r.flag !== '').length
  const totalCO2e     = records.reduce((s, r) => s + parseFloat(r.co2e_kg || 0), 0)
  const totalTonnes   = (totalCO2e / 1000).toFixed(2)

  const availableYears = [...new Set(records.map(r => r.reporting_year))].filter(Boolean).sort((a,b)=>b-a)

  // Scope breakdown
  const scopeMap = {}
  records.forEach(r => { scopeMap[r.scope] = (scopeMap[r.scope]||0) + parseFloat(r.co2e_kg||0) })
  const scopeData = Object.entries(scopeMap).map(([sc, v]) => ({
    name: `Scope ${sc}`,
    'CO₂e (t)': +(v/1000).toFixed(2),
    fill: SCOPE_COLORS[sc] || '#888'
  }))

  // Source breakdown — include record count for legend
  const sourceMap = {}
  const sourceCount = {}
  records.forEach(r => {
    sourceMap[r.source_type]  = (sourceMap[r.source_type]||0)  + parseFloat(r.co2e_kg||0)
    sourceCount[r.source_type]= (sourceCount[r.source_type]||0) + 1
  })
  const sourceData = Object.entries(sourceMap).map(([name, v]) => ({
    name,
    value: +(v/1000).toFixed(2),
    count: sourceCount[name] || 0,
  }))

  // Status counts
  const statusMap = {}
  records.forEach(r => { statusMap[r.review_status] = (statusMap[r.review_status]||0)+1 })

  return (
    <div style={{padding:32,maxWidth:1200}}>
      {/* Header */}
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:28}}>
        <div>
          <h1 style={{fontSize:24,fontWeight:700,margin:0,color:'#111'}}>Emissions Dashboard</h1>
          <p style={{color:'#9ca3af',fontSize:14,marginTop:4}}>
            {year ? `Year ${year}` : 'All years'} · {totalRecords} records
          </p>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <select value={year} onChange={e=>setYear(e.target.value)}
            style={{padding:'7px 12px',border:'1px solid #e5e7eb',borderRadius:8,fontSize:14,background:'white',outline:'none'}}>
            <option value="">All years</option>
            {availableYears.map(y=><option key={y} value={y}>{y}</option>)}
          </select>
          <button onClick={()=>load(year)}
            style={{display:'flex',alignItems:'center',gap:6,padding:'7px 14px',border:'1px solid #e5e7eb',borderRadius:8,fontSize:14,background:'white',cursor:'pointer'}}>
            <RefreshCw size={13}/> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div style={{padding:12,background:'#fef2f2',border:'1px solid #fecaca',borderRadius:8,color:'#dc2626',fontSize:13,marginBottom:20}}>
          ⚠ {error}
        </div>
      )}

      {totalRecords === 0 ? (
        <div style={{background:'white',borderRadius:12,border:'1px solid #f0f0f0',padding:64,textAlign:'center'}}>
          <Leaf size={40} color="#d1d5db" style={{margin:'0 auto 12px'}}/>
          <p style={{color:'#6b7280',fontWeight:500,margin:0}}>No emission records yet</p>
          <p style={{color:'#9ca3af',fontSize:14,marginTop:6}}>
            Upload a CSV file from the <strong>Ingest Data</strong> page to get started.
          </p>
        </div>
      ) : (
        <>
          {/* KPI row */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:16,marginBottom:28}}>
            <StatCard label="Total CO₂e"     value={totalTonnes}   unit="tonnes CO₂e"      icon={Leaf}          bg="#16a34a"/>
            <StatCard label="Pending Review" value={pendingCount}  unit="awaiting review"  icon={Clock}         bg="#eab308"/>
            <StatCard label="Flagged"        value={flaggedCount}  unit="need attention"   icon={AlertTriangle} bg="#f97316"/>
            <StatCard label="Approved"       value={approvedCount} unit="locked for audit" icon={CheckCircle}   bg="#16a34a"/>
          </div>

          {/* Charts row */}
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20,marginBottom:20}}>

            {/* Scope bar chart */}
            <div style={{background:'white',borderRadius:12,border:'1px solid #f0f0f0',padding:24}}>
              <p style={{fontSize:14,fontWeight:600,color:'#374151',margin:'0 0 16px'}}>CO₂e by Scope (tonnes)</p>
              {scopeData.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={scopeData} barSize={52}>
                    <XAxis dataKey="name" tick={{fontSize:12}}/>
                    <YAxis tick={{fontSize:11}}/>
                    <Tooltip formatter={v=>[`${v} t CO₂e`]}/>
                    <Bar dataKey="CO₂e (t)" radius={[4,4,0,0]}>
                      {scopeData.map((e,i)=><Cell key={i} fill={e.fill}/>)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{height:220,display:'flex',alignItems:'center',justifyContent:'center',color:'#d1d5db',fontSize:13}}>
                  CO₂e data will appear once emission factors are matched
                </div>
              )}
            </div>

            {/* Source pie chart — FIXED with always-visible legend */}
            <div style={{background:'white',borderRadius:12,border:'1px solid #f0f0f0',padding:24}}>
              <p style={{fontSize:14,fontWeight:600,color:'#374151',margin:'0 0 16px'}}>CO₂e by Source (tonnes)</p>
              {sourceData.length > 0 ? (
                <div style={{display:'flex',alignItems:'center'}}>
                  {/* Pie — no labels on slices, legend handles it */}
                  <ResponsiveContainer width="55%" height={220}>
                    <PieChart>
                      <Pie
                        data={sourceData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        outerRadius={90}
                        innerRadius={40}
                        paddingAngle={2}
                        label={false}
                      >
                        {sourceData.map((entry, i) => (
                          <Cell
                            key={entry.name}
                            fill={SOURCE_COLORS[entry.name] || SOURCE_COLORS_LIST[i % SOURCE_COLORS_LIST.length]}
                          />
                        ))}
                      </Pie>
                      <Tooltip formatter={(v, name) => [`${v} t CO₂e`, name]}/>
                    </PieChart>
                  </ResponsiveContainer>

                  {/* Always-visible legend — shows ALL sources regardless of slice size */}
                  <div style={{flex:1,display:'flex',flexDirection:'column',gap:10,paddingLeft:8}}>
                    {sourceData.map((entry, i) => {
                      const color = SOURCE_COLORS[entry.name] || SOURCE_COLORS_LIST[i % SOURCE_COLORS_LIST.length]
                      const pct = totalCO2e > 0 ? ((entry.value * 1000 / totalCO2e) * 100).toFixed(1) : '0'
                      return (
                        <div key={entry.name} style={{display:'flex',alignItems:'flex-start',gap:8}}>
                          <div style={{width:12,height:12,borderRadius:3,background:color,flexShrink:0,marginTop:2}}/>
                          <div>
                            <div style={{fontSize:13,fontWeight:600,color:'#374151'}}>{entry.name}</div>
                            <div style={{fontSize:12,color:'#6b7280'}}>{entry.value} t · {pct}%</div>
                            <div style={{fontSize:11,color:'#9ca3af'}}>{entry.count} records</div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ) : (
                <div style={{height:220,display:'flex',alignItems:'center',justifyContent:'center',color:'#d1d5db',fontSize:13}}>No data</div>
              )}
            </div>
          </div>

          {/* Bottom row */}
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:20}}>
            {/* Status breakdown */}
            <div style={{background:'white',borderRadius:12,border:'1px solid #f0f0f0',padding:24}}>
              <p style={{fontSize:14,fontWeight:600,color:'#374151',margin:'0 0 16px'}}>Review Status</p>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
                {[
                  {key:'PENDING', label:'Pending', bg:'#fef9c3',color:'#a16207'},
                  {key:'APPROVED',label:'Approved',bg:'#dcfce7',color:'#166534'},
                  {key:'FLAGGED', label:'Flagged', bg:'#ffedd5',color:'#9a3412'},
                  {key:'REJECTED',label:'Rejected',bg:'#fee2e2',color:'#991b1b'},
                ].map(({key,label,bg,color})=>(
                  <div key={key} style={{textAlign:'center',padding:'14px 8px',background:bg,borderRadius:10}}>
                    <p style={{fontSize:28,fontWeight:700,color:'#111',margin:0}}>{statusMap[key]||0}</p>
                    <p style={{fontSize:13,fontWeight:600,color,margin:'4px 0 0'}}>{label}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* Source table */}
            <div style={{background:'white',borderRadius:12,border:'1px solid #f0f0f0',padding:24}}>
              <p style={{fontSize:14,fontWeight:600,color:'#374151',margin:'0 0 16px'}}>Source Summary</p>
              <table style={{width:'100%',fontSize:14,borderCollapse:'collapse'}}>
                <thead>
                  <tr style={{borderBottom:'1px solid #f3f4f6'}}>
                    <th style={{textAlign:'left',padding:'5px 0',color:'#6b7280',fontSize:11,fontWeight:600,textTransform:'uppercase'}}>Source</th>
                    <th style={{textAlign:'right',padding:'5px 0',color:'#6b7280',fontSize:11,fontWeight:600,textTransform:'uppercase'}}>Records</th>
                    <th style={{textAlign:'right',padding:'5px 0',color:'#6b7280',fontSize:11,fontWeight:600,textTransform:'uppercase'}}>CO₂e (t)</th>
                    <th style={{textAlign:'right',padding:'5px 0',color:'#6b7280',fontSize:11,fontWeight:600,textTransform:'uppercase'}}>%</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(sourceMap).map(([src,co2e],i)=>{
                    const pct = totalCO2e > 0 ? ((co2e/totalCO2e)*100).toFixed(1) : '0'
                    const color = SOURCE_COLORS[src] || SOURCE_COLORS_LIST[i % SOURCE_COLORS_LIST.length]
                    return (
                      <tr key={src} style={{borderBottom:'1px solid #f9fafb'}}>
                        <td style={{padding:'10px 0',fontWeight:600,display:'flex',alignItems:'center',gap:8}}>
                          <div style={{width:10,height:10,borderRadius:2,background:color,flexShrink:0}}/>
                          {src}
                        </td>
                        <td style={{padding:'10px 0',textAlign:'right',fontFamily:'monospace'}}>
                          {records.filter(r=>r.source_type===src).length}
                        </td>
                        <td style={{padding:'10px 0',textAlign:'right',fontFamily:'monospace',fontWeight:700}}>
                          {(co2e/1000).toFixed(2)}
                        </td>
                        <td style={{padding:'10px 0',textAlign:'right',color:'#6b7280',fontSize:12}}>
                          {pct}%
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
