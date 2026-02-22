import { useEffect, useState } from 'react'
import { getApiBase } from './api'

const API = getApiBase('skb')

interface Paper {
  arxiv_id: string; title: string; published: string
}
interface Stats {
  papers: number; chunks: number; categories: number
  last_crawl?: string; last_crawl_count?: number
}
interface PaperDetail {
  arxiv_id: string; title: string; abstract: string | null
  abstract_translated: string | null; translate_language: string | null
  published: string; has_pdf: boolean
}

export default function App() {
  const [tab, setTab] = useState<'search' | 'categories'>('search')
  const [stats, setStats] = useState<Stats | null>(null)
  const [categories, setCategories] = useState<{code: string; description: string; group: string; enabled: boolean}[]>([])
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Paper[]>([])
  const [searching, setSearching] = useState(false)
  const [detail, setDetail] = useState<PaperDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([
      fetch(`${API}/stats`).then(r => r.ok ? r.json() : null).catch(() => null),
      fetch(`${API}/categories`).then(r => r.ok ? r.json() : null).catch(() => null),
    ]).then(([s, c]) => {
      if (s) setStats(s)
      else setError('ScienceKB database not found. Run: skb ingest')
      if (c?.categories) setCategories(c.categories)
      setLoading(false)
    })
  }, [])

  const doSearch = async () => {
    if (!query.trim()) return
    setSearching(true)
    try {
      const r = await fetch(`${API}/search?q=${encodeURIComponent(query)}&top_k=20`)
      const data = await r.json()
      setResults(data.results || [])
    } catch { setResults([]) }
    setSearching(false)
  }

  const [showPdf, setShowPdf] = useState(false)
  const [translating, setTranslating] = useState(false)

  const viewPaper = async (arxivId: string) => {
    setShowPdf(false)
    setTranslating(false)
    try {
      const r = await fetch(`${API}/paper/${arxivId}`)
      const data = await r.json()
      setDetail(data)

      // Fire translation async if not cached
      if (data.translate_language && data.abstract && !data.abstract_translated) {
        setTranslating(true)
        fetch(`${API}/paper/${arxivId}/translate`)
          .then(r => r.json())
          .then(t => {
            if (t.translated) {
              setDetail((prev: any) => prev ? { ...prev, abstract_translated: t.translated } : prev)
            }
            setTranslating(false)
          })
          .catch(() => setTranslating(false))
      }
    } catch {}
  }

  if (detail) {
    return (
      <div className="page">
        <div className="nav-bar">
          <button className="nav-btn" onClick={() => { setDetail(null); setShowPdf(false) }}>← Back</button>
          <div className="title">Paper</div>
          <a href={`https://arxiv.org/abs/${detail.arxiv_id}`} target="_blank" rel="noreferrer"
            style={{ fontSize: 13, color: 'var(--accent)', textDecoration: 'none' }}>arXiv ↗</a>
        </div>
        <div style={{ padding: 16 }}>
          <h2 style={{ fontSize: 17, fontWeight: 700, marginBottom: 8, lineHeight: 1.4 }}>{detail.title}</h2>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 16 }}>
            {new Date(detail.published).toLocaleDateString()}
          </div>

          {detail.abstract && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 6 }}>
                {detail.abstract_translated
                  ? `Abstract (${detail.translate_language})`
                  : translating
                    ? <span>Abstract <span style={{ color: 'var(--accent)', fontStyle: 'italic' }}>(translating…)</span></span>
                    : 'Abstract'}
              </div>
              <div style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
                {detail.abstract_translated || detail.abstract}
              </div>
            </div>
          )}

          {detail.has_pdf && !showPdf && (
            <button onClick={() => setShowPdf(true)} style={{
              width: '100%', padding: '12px', fontSize: 14, fontWeight: 600,
              background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: 8,
              cursor: 'pointer', marginBottom: 16,
            }}>
              📄 View Paper PDF
            </button>
          )}

          {detail.has_pdf && showPdf && (
            <div style={{ marginBottom: 20 }}>
              <embed
                src={`${API}/pdf/${detail.arxiv_id}#toolbar=0`}
                type="application/pdf"
                style={{ width: '100%', height: 'calc(100vh - 240px)', borderRadius: 8 }}
              />
              <a href={`${API}/pdf/${detail.arxiv_id}`} target="_blank" rel="noreferrer"
                style={{ display: 'block', textAlign: 'center', fontSize: 12, color: 'var(--accent)', marginTop: 8 }}>
                Open PDF in new tab ↗
              </a>
            </div>
          )}

          {!detail.abstract && !detail.has_pdf && (
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>No content available.</div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="nav-bar">
        <button className="nav-btn" onClick={() => window.location.href = '/'}>← Back</button>
        <div className="title">📄 ArXiv</div>
        <div style={{ width: 60 }} />
      </div>
      <div className="content">
        {error && <div className="error">{error}</div>}

        {stats && (
          <div className="stat-row">
            {[
              { label: 'Papers', value: stats.papers },
              { label: 'Chunks', value: stats.chunks.toLocaleString() },
              { label: 'Categories', value: stats.categories },
            ].map(s => (
              <div key={s.label} className="stat-box">
                <div className="value">{s.value}</div>
                <div className="label">{s.label}</div>
              </div>
            ))}
          </div>
        )}
        {stats?.last_crawl && (
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', textAlign: 'center', marginBottom: 8 }}>
            Last crawl: {stats.last_crawl} ({stats.last_crawl_count ?? 0} papers)
          </div>
        )}

        <div className="tab-row">
          {(['search', 'categories'] as const).map(t => (
            <button key={t} className={`tab-btn ${tab === t ? 'active' : ''}`}
              onClick={() => setTab(t)}>
              {t === 'search' ? '🔍 Search' : '📂 Categories'}
            </button>
          ))}
        </div>

        {tab === 'search' && (
          <div>
            <div className="search-row">
              <input className="search-input" value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && doSearch()}
                placeholder="Search papers..." />
              <button className="search-btn" onClick={doSearch} disabled={searching}>Go</button>
            </div>
            {searching ? <div className="loading">Searching...</div>
              : results.length > 0 ? results.map(p => (
                <div key={p.arxiv_id} className="paper" onClick={() => viewPaper(p.arxiv_id)}>
                  <div className="p-title">{p.title}</div>
                  <div className="p-meta">{new Date(p.published).toLocaleDateString()}</div>
                </div>
              ))
              : query ? <div className="loading">No results</div>
              : <div className="loading">Enter a query to search indexed papers</div>}
          </div>
        )}

        {tab === 'categories' && (
          categories.length === 0
            ? <div className="loading">No categories found.</div>
            : <div>
                <div style={{ fontSize: 12, color: 'var(--text-secondary)', padding: '8px 0 12px', textAlign: 'center' }}>
                  ✅ = enabled for crawling · Manage: <code>/skb add cs.AI</code>
                </div>
                {(() => {
                  let curGroup = ''
                  return categories.map((c, i) => {
                    const groupHeader = c.group !== curGroup ? (curGroup = c.group, true) : false
                    return (
                      <div key={i}>
                        {groupHeader && <div style={{ fontSize: 13, fontWeight: 700, padding: '12px 0 6px', color: 'var(--text)' }}>{c.group}</div>}
                        <div className="topic-item" style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          opacity: c.enabled ? 1 : 0.5,
                        }}>
                          <span style={{ fontSize: 13, fontWeight: c.enabled ? 600 : 400 }}>
                            {c.enabled ? '✅ ' : ''}{c.code}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--text-secondary)', textAlign: 'right', maxWidth: '60%' }}>{c.description}</span>
                        </div>
                      </div>
                    )
                  })
                })()}
              </div>
        )}
      </div>
    </div>
  )
}
