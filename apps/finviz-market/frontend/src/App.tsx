import { useEffect, useState, useRef } from 'react'

const API = '/api/app/finviz'

type Period = '12h' | '24h' | 'weekly'

interface SummaryData {
  status: 'ready' | 'generating'
  summary?: string
  article_count?: number
  generated_at?: string
  topic?: string
}

interface Ticker {
  symbol: string
  keywords: string[]
}

function renderMarkdown(md: string): string {
  return md.trim()
    .replace(/^---+$/gm, '')
    .replace(/\r\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^#### (.+)$/gm, '<h4 style="font-size:14px;font-weight:600;margin:10px 0 4px">$1</h4>')
    .replace(/^### (.+)$/gm, '<h3 style="font-size:15px;font-weight:600;margin:12px 0 4px">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 style="font-size:16px;font-weight:700;margin:14px 0 4px">$1</h2>')
    .replace(/^# (.+)$/gm, '<h1 style="font-size:17px;font-weight:700;margin:14px 0 6px">$1</h1>')
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" style="color:var(--accent)" target="_blank">$1</a>')
    .replace(/^- (.+)$/gm, '<li style="margin:1px 0;margin-left:16px;list-style:disc">$1</li>')
    .replace(/\n\n/g, '<br/>')
    .replace(/\n/g, ' ')
}

export default function App() {
  const [period, setPeriod] = useState<Period>('24h')
  const [topic, setTopic] = useState('Market')
  const [data, setData] = useState<SummaryData | null>(null)
  const [loading, setLoading] = useState(false)
  const [tickers, setTickers] = useState<Ticker[]>([])
  const [articleCounts, setArticleCounts] = useState<Record<string, number>>({})
  const pollRef = useRef<number | null>(null)

  const isGenerating = loading || data?.status === 'generating'

  // Load tickers from DB on mount
  useEffect(() => {
    fetch(`${API}/tickers`).then(r => r.json()).then(d => setTickers(d.items || [])).catch(() => {})
    fetch(`${API}/article-counts`).then(r => r.json()).then(d => setArticleCounts(d || {})).catch(() => {})
  }, [])

  const fetchSummary = (p: Period, t: string, regen: boolean = false) => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    setLoading(true)
    setData(null)
    const params = new URLSearchParams({ topic: t })
    if (regen) params.set('regenerate', '1')
    fetch(`${API}/summary/${p}?${params}`)
      .then(r => r.json())
      .then((d: SummaryData) => {
        setData(d)
        setLoading(false)
        if (d.status === 'generating') {
          pollRef.current = window.setInterval(() => {
            fetch(`${API}/summary/${p}?topic=${t}`)
              .then(r => r.json())
              .then((d2: SummaryData) => {
                setData(d2)
                if (d2.status === 'ready' && pollRef.current) {
                  clearInterval(pollRef.current); pollRef.current = null
                }
              })
              .catch(() => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } })
          }, 3000)
          setTimeout(() => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null } }, 120000)
        }
      })
      .catch(() => setLoading(false))
  }

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleGenerate = (p: Period) => {
    if (isGenerating) return
    setPeriod(p)
    fetchSummary(p, topic, true)
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
    } catch { return iso }
  }

  // Dropdown options: Market + tickers from DB
  const allOptions = ['Market', ...tickers.map(t => t.symbol)]

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', fontFamily: '-apple-system, BlinkMacSystemFont, system-ui, sans-serif' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', padding: '12px 16px',
        paddingTop: 'calc(12px + env(safe-area-inset-top, 0px))',
        background: 'var(--card-bg)', borderBottom: '0.5px solid var(--border)',
      }}>
        <a href="/" style={{ fontSize: 17, color: 'var(--accent)', textDecoration: 'none', padding: '8px' }}>← Back</a>
        <div style={{ flex: 1, fontSize: 17, fontWeight: 600, textAlign: 'center' }}>Finviz</div>
        <div style={{ width: 60 }} />
      </div>

      {/* Control row: dropdown + period buttons */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8, padding: '10px 16px 0',
        background: 'var(--card-bg)',
      }}>
        <select
          value={topic}
          onChange={e => { setTopic(e.target.value); setData(null) }}
          disabled={isGenerating}
          style={{
            flex: '0 0 auto', minWidth: 90, fontSize: 15, fontWeight: 600,
            padding: '8px 28px 8px 10px', borderRadius: 8,
            border: '1px solid var(--border)', background: 'var(--card-bg)', color: 'var(--text)',
            outline: 'none', cursor: isGenerating ? 'not-allowed' : 'pointer',
            opacity: isGenerating ? 0.5 : 1,
            WebkitAppearance: 'none', appearance: 'none',
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 10 10'%3E%3Cpath fill='%238e8e93' d='M1 3l4 4 4-4'/%3E%3C/svg%3E")`,
            backgroundRepeat: 'no-repeat', backgroundPosition: 'right 8px center',
          }}
        >
          {allOptions.map(sym => (
            <option key={sym} value={sym}>{sym}</option>
          ))}
        </select>

        <div style={{ display: 'flex', gap: 6, flex: 1 }}>
          {(['12h', '24h', 'weekly'] as Period[]).map(p => (
            <button key={p} onClick={() => handleGenerate(p)} disabled={isGenerating}
              style={{
                flex: 1, padding: '8px 0', borderRadius: 8, border: 'none',
                fontSize: 13, fontWeight: 600,
                cursor: isGenerating ? 'not-allowed' : 'pointer',
                opacity: isGenerating ? 0.5 : 1,
                background: period === p && data ? 'var(--accent)' : 'var(--bg)',
                color: period === p && data ? '#fff' : 'var(--text)',
                transition: 'all 0.15s',
              }}>
              {p === 'weekly' ? 'Week' : p}
            </button>
          ))}
        </div>
      </div>

      {/* Article count row */}
      {articleCounts[topic] !== undefined && (
        <div style={{
          padding: '4px 16px 8px',
          fontSize: 11, color: 'var(--text-secondary)',
          background: 'var(--card-bg)', borderBottom: '0.5px solid var(--border)',
        }}>
          {articleCounts[topic]} article{articleCounts[topic] !== 1 ? 's' : ''}
        </div>
      )}

      {/* Content */}
      <div style={{ padding: '12px 16px 32px' }}>
        {!data && !loading ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📊</div>
            <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 8 }}>Select a topic and tap a period to generate</div>
            <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              Manage tickers via OpenClaw:<br/>
              <code style={{ fontSize: 11, background: 'var(--bg)', padding: '2px 6px', borderRadius: 4 }}>
                /finviz add NVDA, TSLA
              </code>
            </div>
          </div>
        ) : loading && !data ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
            <div style={spinnerStyle} />Loading...
          </div>
        ) : data?.status === 'generating' ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)' }}>
            <div style={spinnerStyle} />
            <div style={{ fontSize: 15, fontWeight: 500, marginBottom: 4 }}>Generating {topic} summary...</div>
            <div style={{ fontSize: 13 }}>30–60 seconds</div>
          </div>
        ) : data?.status === 'ready' && data.summary ? (
          <div style={{ background: 'var(--card-bg)', borderRadius: 12, padding: '16px', boxShadow: '0 0 0 0.5px var(--border)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12, fontSize: 12, color: 'var(--text-secondary)' }}>
              <span>{data.article_count} articles</span>
              {data.generated_at && <span>{formatDate(data.generated_at)}</span>}
            </div>
            <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(data.summary) }} />
          </div>
        ) : data?.summary ? (
          <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-secondary)', fontSize: 14 }}>
            {data.summary}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--text-secondary)', fontSize: 14 }}>
            No data available
          </div>
        )}
      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg) } }
        :root { --bg: #f2f2f7; --card-bg: #fff; --text: #1c1c1e; --text-secondary: #8e8e93; --border: rgba(0,0,0,0.1); --accent: #007AFF; color-scheme: light; }
        @media (prefers-color-scheme: dark) { :root { --bg: #000; --card-bg: #1c1c1e; --text: #f2f2f7; --text-secondary: #8e8e93; --border: rgba(255,255,255,0.1); --accent: #64D2FF; color-scheme: dark; } }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif; }
        .md-content { font-size: 14px; line-height: 1.7; word-break: break-word; }
        .md-content strong { font-weight: 600; }
        .md-content li { padding-left: 4px; }
        select option { background: var(--card-bg); color: var(--text); }
      `}</style>
    </div>
  )
}

const spinnerStyle: React.CSSProperties = {
  width: 24, height: 24, margin: '0 auto 12px',
  border: '2.5px solid var(--border)', borderTopColor: 'var(--accent)',
  borderRadius: '50%', animation: 'spin 0.7s linear infinite',
}
