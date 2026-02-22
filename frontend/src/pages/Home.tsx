import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface AppEntry {
  id: string
  name: string
  icon: string
  description: string
  url: string
}

interface AppsResponse {
  apps: Array<{
    id: string
    name: string
    icon: string
    description: string
    builtin: boolean
    enabled: boolean
    status: string
    url?: string
  }>
}

// iOS-style solid gradient backgrounds per app
const APP_GRADIENTS: Record<string, string> = {
  'system-monitor': 'linear-gradient(135deg, #007AFF, #5856D6)',
  'file-browser':   'linear-gradient(135deg, #5856D6, #AF52DE)',
  'finviz-market':  'linear-gradient(135deg, #34C759, #30D158)',
  'science-kb':     'linear-gradient(135deg, #FF9500, #FF6B00)',
}

const DEFAULT_GRADIENT = 'linear-gradient(135deg, #8E8E93, #636366)'

export default function Home() {
  const navigate = useNavigate()
  const [apps, setApps] = useState<AppEntry[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/apps')
      .then(r => r.json())
      .then((d: AppsResponse) => {
        const enabled = (d.apps ?? [])
          .filter(a => a.enabled && a.status === 'active')
          .map(a => ({
            id: a.id,
            name: a.name,
            icon: a.icon,
            description: a.description,
            url: a.url ?? `/app/${a.id}/`,
          }))
        setApps(enabled)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const openApp = (url: string) => {
    window.location.href = url
  }

  return (
    <div className="page">
      <div className="nav-bar">
        <div className="spacer" />
        <div className="title">Private App</div>
        <button
          className="nav-btn"
          onClick={() => navigate('/settings')}
          aria-label="Settings"
          style={{ fontSize: 20 }}
        >
          ⚙️
        </button>
      </div>

      <div className="content">
        {loading ? (
          <div className="loading"><div className="spinner" /></div>
        ) : apps.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📦</div>
            <div className="empty-text">No apps installed</div>
          </div>
        ) : (
          <div className="app-grid">
            {apps.map(app => (
              <button
                key={app.id}
                className="app-tile"
                onClick={() => openApp(app.url)}
                aria-label={app.name}
              >
                <div
                  className="app-icon-wrap"
                  style={{ background: APP_GRADIENTS[app.id] || DEFAULT_GRADIENT }}
                >
                  {app.icon}
                </div>
                <div className="app-name">{app.name}</div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
