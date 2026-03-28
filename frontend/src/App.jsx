import { useCallback, useEffect, useRef, useState } from 'react'

const GUIDE = [
  ['SELECT', '#3b82f6', 'Lecture / consultation de donnees'],
  ['INSERT', '#f59e0b', 'Ajout d une nouvelle ligne'],
  ['UPDATE', '#f97316', 'Modification d une donnee'],
  ['DELETE', '#ef4444', 'Suppression d une ligne'],
  ['LOGON', '#22c55e', 'Connexion utilisateur Oracle'],
  ['LOGOFF', '#86efac', 'Deconnexion utilisateur'],
  ['CREATE', '#a855f7', 'Creation d un objet DB'],
  ['ALTER', '#8b5cf6', 'Modification de structure'],
  ['DROP', '#f43f5e', 'Suppression d un objet'],
  ['GRANT', '#06b6d4', 'Attribution de droits'],
  ['REVOKE', '#0ea5e9', 'Retrait de droits'],
]

const NAV = [
  { id: 'home', label: 'Accueil', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { id: 'history', label: 'Historique', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
  { id: 'settings', label: 'Parametres', icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
]

const COLUMN_LABELS = {
  DBUSERNAME: 'Utilisateur',
  USERNAME: 'Utilisateur',
  ACTION_NAME: 'Action effectuee',
  EVENT_TIMESTAMP: 'Date et heure',
  OBJECT_NAME: 'Objet concerne',
  OS_USERNAME: 'Compte poste',
  USERHOST: 'Machine source',
  SESSIONID: 'Session',
  RETURN_CODE: 'Code retour',
}

function formatColumnLabel(key) {
  if (COLUMN_LABELS[key]) return COLUMN_LABELS[key]
  const normalized = String(key || '').replace(/_/g, ' ').trim().toLowerCase()
  if (!normalized) return 'Colonne'
  return normalized.replace(/\b\w/g, c => c.toUpperCase())
}

function Icon({ d, size = 18, cls = '' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round"
      strokeLinejoin="round" className={cls}>
      {d.split(' M').map((seg, i) => (
        <path key={i} d={i === 0 ? seg : 'M' + seg} />
      ))}
    </svg>
  )
}

export default function App() {
  const [page, setPage] = useState('home')
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [health, setHealth] = useState(null)
  const [meta, setMeta] = useState({ users: [], objects: [] })
  const [history, setHistory] = useState([])
  const [histSel, setHistSel] = useState(null)
  const [usersQ, setUsersQ] = useState('')
  const [tablesQ, setTablesQ] = useState('')
  const [showAllU, setShowAllU] = useState(false)
  const [showAllT, setShowAllT] = useState(false)
  const [panel, setPanel] = useState('users')
  const [isSidebarOpen, setIsSidebarOpen] = useState(true)
  const inputRef = useRef(null)
  const dockInputRef = useRef(null)
  const panelRef = useRef(null)
  const resultRef = useRef(null)

  const fetchHealth = useCallback(async () => {
    try { const r = await fetch('/api/health'); if (r.ok) setHealth(await r.json()) } catch {}
  }, [])
  const fetchMeta = useCallback(async () => {
    try { const r = await fetch('/api/metadata'); if (r.ok) setMeta(await r.json()) } catch {}
  }, [])
  const fetchHistory = useCallback(async () => {
    try { const r = await fetch('/api/history'); if (r.ok) setHistory(await r.json()) } catch {}
  }, [])

  useEffect(() => { fetchHealth(); fetchMeta(); fetchHistory() }, [fetchHealth, fetchMeta, fetchHistory])

  const copy = t => navigator.clipboard?.writeText(t).catch(() => {})
  const oracleOk = health?.oracle === 'connected'

  const filteredUsers = (meta.users || []).filter(u => u.name.toLowerCase().includes(usersQ.toLowerCase()))
  const filteredTables = (meta.objects || []).filter(o => o.name.toLowerCase().includes(tablesQ.toLowerCase()))
  const visibleUsers = showAllU ? filteredUsers : filteredUsers.slice(0, 20)
  const visibleTables = showAllT ? filteredTables : filteredTables.slice(0, 16)

  const isCompactResult = !!result
    && (result.rows?.length || 0) <= 8
    && (result.synthesis?.length || 0) <= 350
    && (result.sql?.length || 0) <= 900

  const goToPanel = useCallback((panelId) => {
    setPage('home')
    setPanel(panelId)
    setTimeout(() => {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 80)
  }, [])

  const handleSubmit = async () => {
    if (!question.trim() || loading) return
    setLoading(true)
    setResult(null)
    try {
      const r = await fetch('/api/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setResult(data)
      setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 70)
      fetchHistory()
      fetchMeta()
    } catch (err) {
      setResult({ error: err.message, sql: '', synthesis: '', row_count: 0, rows: [], question: question.trim(), blocked: false })
      setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 70)
    } finally {
      setLoading(false)
      fetchHealth()
    }
  }

  const renderSearchBar = (variant = 'hero') => {
    const compact = variant === 'dock'
    return (
      <div className={`search-bar${compact ? ' search-bar-dock' : ''}`}>
        <div className="search-bar-icon">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
        </div>
        <input
          ref={compact ? dockInputRef : inputRef}
          className="search-bar-input"
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSubmit()}
          placeholder="Ex : Quels utilisateurs ont effectue des DELETE ce mois-ci ?"
        />
        <button className="search-bar-btn" onClick={handleSubmit} disabled={loading || !question.trim()}>
          {loading ? <><span className="spin" /> Analyse...</> : <>Envoyer</>}
        </button>
      </div>
    )
  }

  return (
    <div className={`shell${isSidebarOpen ? '' : ' sidebar-closed'}`}>
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="logo">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"
              stroke="#fff" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <ellipse cx="12" cy="5" rx="9" ry="3" />
              <path d="M3 5v10c0 1.7 4 3 9 3s9-1.3 9-3V5" />
              <path d="M3 10c0 1.7 4 3 9 3s9-1.3 9-3" />
            </svg>
          </div>
          <div className="sidebar-brand">
            <span className="brand-name">SMART<span>2D</span></span>
          </div>
        </div>

        <nav className="sidebar-nav">
          {NAV.map(n => (
            <button key={n.id}
              className={`snav-btn${page === n.id ? ' snav-active' : ''}`}
              onClick={() => { setPage(n.id); if (n.id === 'history') fetchHistory() }}>
              <Icon d={n.icon} size={16} />
              <span className="snav-label">{n.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-links">
          <div className="slinks-title">Acces rapide</div>
          <button
            className={`slink${page === 'home' && panel === 'users' ? ' slink-active' : ''}`}
            onClick={() => goToPanel('users')}>
            Utilisateurs ({(meta.users || []).length})
          </button>
          <button
            className={`slink${page === 'home' && panel === 'tables' ? ' slink-active' : ''}`}
            onClick={() => goToPanel('tables')}>
            Objets ({(meta.objects || []).length})
          </button>
          <button
            className={`slink${page === 'home' && panel === 'guide' ? ' slink-active' : ''}`}
            onClick={() => goToPanel('guide')}>
            Guide SQL
          </button>
        </div>

        <div className="sidebar-foot">
          <div className={`oracle-badge ${oracleOk ? 'ob-ok' : 'ob-err'}`}>
            <span className="ob-dot" />
            <div className="ob-info">
              <span className="ob-label">Oracle DB</span>
              <span className="ob-val">{oracleOk ? 'Connecte' : 'Hors ligne'}</span>
            </div>
          </div>
          <span className="sidebar-date">
            {new Date().toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        </div>
      </aside>

      <div className="content">
        <button
          className="sidebar-toggle"
          onClick={() => setIsSidebarOpen(v => !v)}
          aria-label={isSidebarOpen ? 'Masquer le menu lateral' : 'Afficher le menu lateral'}>
          {isSidebarOpen ? 'Masquer menu' : 'Afficher menu'}
        </button>

        {page === 'home' && (
          <main className="home">
            <section className="hero">
              <h1 className="hero-title">
                Interrogez vos donnees d audit<br />
                <span>en posant de simples questions sur celles ci</span>
              </h1>
              <p className="hero-sub">
                Posez votre question en francais, SMART2D gere tout automatiquement et vous donne une reponse.
              </p>

              {renderSearchBar('hero')}

              <div className="quick-chips">
                {['Connexions du jour', 'TOP 10 utilisateurs', 'Dernieres suppressions', 'Objets modifies'].map(q => (
                  <button key={q} className="qchip"
                    onClick={() => { setQuestion(q); setTimeout(() => inputRef.current?.focus(), 50) }}>
                    {q}
                  </button>
                ))}
              </div>
            </section>

            {(result || loading) && (
              <section className="query-dock">
                <div className="query-dock-inner">
                  <span className="dock-label">Nouvelle question</span>
                  {renderSearchBar('dock')}
                </div>
              </section>
            )}

            {(result || loading) && (
              <section ref={resultRef} className={`result-zone${isCompactResult ? ' result-zone-compact' : ''}`}>
                {loading ? (
                  <div className="result-loading">
                    <span className="spin-lg" />
                    <div>
                      <strong>Analyse en cours</strong>
                      <p>Generation de la requete SQL...</p>
                    </div>
                  </div>
                ) : result && (
                  <div className={`result-inner${isCompactResult ? ' result-inner-compact' : ''}`}>
                    <div className="result-header">
                      <div className="result-q">
                        <span className="result-q-label">Question</span>
                        {result.question}
                      </div>
                      {result.row_count > 0 && (
                        <span className="result-count">{result.row_count} ligne{result.row_count > 1 ? 's' : ''}</span>
                      )}
                    </div>

                    {result.error && !result.sql && (
                      <div className="alert alert-err">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                          strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" />
                          <line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        {result.error}
                      </div>
                    )}

                    {result.sql && (
                      <div className="sql-block">
                        <div className="sql-block-header">
                          <span>SQL</span>
                          <button className="btn-copy" onClick={() => copy(result.sql)}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                              strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="9" y="9" width="13" height="13" rx="2" />
                              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                            </svg>
                            Copier
                          </button>
                        </div>
                        <pre className="sql-code">{result.sql}</pre>
                      </div>
                    )}

                    {result.synthesis && (
                      <div className="alert alert-ok">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                          strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        {result.synthesis}
                      </div>
                    )}

                    {result.error && result.sql && (
                      <div className="alert alert-err">Erreur d execution - {result.error}</div>
                    )}

                    {result.rows?.length > 0 && (
                      <div className="tbl-scroll">
                        <table className="data-table">
                          <thead>
                            <tr>{Object.keys(result.rows[0]).map(c => <th key={c}>{formatColumnLabel(c)}</th>)}</tr>
                          </thead>
                          <tbody>
                            {result.rows.map((row, i) => (
                              <tr key={i}>
                                {Object.values(row).map((v, j) => <td key={j}>{String(v ?? '')}</td>)}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )}

            <section className="panels" ref={panelRef}>
              <div className="panel-tabs">
                {[
                  { id: 'users', label: `Utilisateurs (${(meta.users || []).length})` },
                  { id: 'tables', label: `Objets (${(meta.objects || []).length})` },
                  { id: 'guide', label: 'Guide SQL' },
                ].map(t => (
                  <button key={t.id}
                    className={`ptab${panel === t.id ? ' ptab-active' : ''}`}
                    onClick={() => setPanel(t.id)}>
                    {t.label}
                  </button>
                ))}
              </div>

              <div className="panel-body">
                {panel === 'users' && (
                  <div className="panel-list-wrap">
                    <input className="panel-search" type="search" placeholder="Rechercher un utilisateur..."
                      value={usersQ} onChange={e => { setUsersQ(e.target.value); setShowAllU(false) }} />
                    <div className="panel-grid">
                      {visibleUsers.length === 0
                        ? <span className="panel-empty">Aucun utilisateur</span>
                        : visibleUsers.map(u => (
                          <div key={u.name} className="pcard">
                            <div className="pcard-avatar">{u.name.charAt(0)}</div>
                            <div className="pcard-info">
                              <span className="pcard-name">{u.name}</span>
                              <span className="pcard-count">{u.actions.toLocaleString()} actions</span>
                            </div>
                          </div>
                        ))}
                    </div>
                    {filteredUsers.length > (showAllU ? 0 : 20) && (
                      <button className="panel-more" onClick={() => setShowAllU(v => !v)}>
                        {showAllU ? 'Reduire' : `Voir les ${filteredUsers.length - 20} autres`}
                      </button>
                    )}
                  </div>
                )}

                {panel === 'tables' && (
                  <div className="panel-list-wrap">
                    <input className="panel-search" type="search" placeholder="Rechercher un objet..."
                      value={tablesQ} onChange={e => { setTablesQ(e.target.value); setShowAllT(false) }} />
                    <div className="panel-grid">
                      {visibleTables.length === 0
                        ? <span className="panel-empty">Aucun objet</span>
                        : visibleTables.map(o => (
                          <div key={o.name} className="pcard pcard-table">
                            <div className="pcard-avatar pcard-avatar-t">
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                                <rect x="3" y="3" width="18" height="18" rx="2" />
                                <line x1="3" y1="9" x2="21" y2="9" />
                                <line x1="9" y1="3" x2="9" y2="21" />
                              </svg>
                            </div>
                            <div className="pcard-info">
                              <span className="pcard-name">{o.name}</span>
                              <span className="pcard-count">{o.actions.toLocaleString()} actions</span>
                            </div>
                          </div>
                        ))}
                    </div>
                    {filteredTables.length > (showAllT ? 0 : 16) && (
                      <button className="panel-more" onClick={() => setShowAllT(v => !v)}>
                        {showAllT ? 'Reduire' : `Voir les ${filteredTables.length - 16} autres`}
                      </button>
                    )}
                  </div>
                )}

                {panel === 'guide' && (
                  <div className="guide-grid">
                    {GUIDE.map(([code, color, desc]) => (
                      <div key={code} className="guide-card">
                        <span className="guide-tag" style={{ color, background: color + '18', border: `1px solid ${color}44` }}>
                          {code}
                        </span>
                        <span className="guide-txt">{desc}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </main>
        )}

        {page === 'history' && (
          <main className="page-inner">
            <div className="page-header">
              <h2>Historique des requetes</h2>
              <span className="page-header-count">{history.length} entree{history.length > 1 ? 's' : ''}</span>
            </div>

            <div className="hist-layout">
              <div className="hist-list">
                {history.length === 0 && (
                  <div className="hist-empty">Aucune requete executee pour l instant.</div>
                )}
                {[...history].reverse().map((item, i) => (
                  <div key={i}
                    className={`hist-item${histSel === item ? ' hist-sel' : ''}`}
                    onClick={() => setHistSel(item)}>
                    <div className="hist-item-top">
                      <span className="hist-time">
                        {item.timestamp ? new Date(item.timestamp).toLocaleTimeString('fr-FR') : '--:--'}
                      </span>
                      {item.error
                        ? <span className="badge badge-err">Erreur</span>
                        : item.blocked
                          ? <span className="badge badge-warn">Bloque</span>
                          : <span className="badge badge-ok">OK</span>
                      }
                    </div>
                    <div className="hist-item-q">
                      {item.question.length > 80 ? item.question.slice(0, 80) + '...' : item.question}
                    </div>
                    {item.sql && (
                      <div className="hist-item-sql">{item.sql.slice(0, 60)}...</div>
                    )}
                  </div>
                ))}
              </div>

              <div className="hist-detail">
                {!histSel ? (
                  <div className="hist-detail-empty">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none"
                      stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
                      strokeLinejoin="round" style={{ opacity: 0.3, marginBottom: 12 }}>
                      <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                    </svg>
                    Selectionnez une requete pour voir les details
                  </div>
                ) : (
                  <>
                    <div className="detail-section">
                      <div className="detail-label">Question</div>
                      <div className="detail-text">{histSel.question}</div>
                    </div>
                    {histSel.sql && (
                      <div className="detail-section">
                        <div className="detail-label">SQL genere</div>
                        <pre className="detail-code">{histSel.sql}</pre>
                      </div>
                    )}
                    {histSel.synthesis && (
                      <div className="detail-section">
                        <div className="detail-label">Synthese</div>
                        <div className="detail-text">{histSel.synthesis}</div>
                      </div>
                    )}
                    {histSel.error && (
                      <div className="alert alert-err" style={{ marginTop: 10 }}>{histSel.error}</div>
                    )}
                  </>
                )}
              </div>
            </div>
          </main>
        )}

        {page === 'settings' && (
          <main className="page-inner">
            <div className="page-header">
              <h2>Parametres</h2>
            </div>
            <div className="settings-cols">
              <div className="settings-block">
                <div className="settings-block-title">Connexion Oracle</div>
                {[
                  ['Utilisateur', 'aziz'],
                  ['Hote', '192.168.132.177'],
                  ['Port', '1791'],
                  ['Service', 'OSCARDB1'],
                  ['Table', 'SMART2DSECU.UNIFIED_AUDIT_DATA'],
                ].map(([lbl, val]) => (
                  <div key={lbl} className="field">
                    <label>{lbl}</label>
                    <input defaultValue={val} readOnly />
                  </div>
                ))}
              </div>
              <div className="settings-block">
                <div className="settings-block-title">Parametres d analyse</div>
                {[
                  ['Langue d interface', 'Francais'],
                  ['Resultats max par requete', '100'],
                  ['Duree session (min)', '30'],
                  ['Conservation logs (j)', '90'],
                ].map(([lbl, val]) => (
                  <div key={lbl} className="field">
                    <label>{lbl}</label>
                    <input defaultValue={val} />
                  </div>
                ))}
              </div>
            </div>
            <div className="settings-actions">
              <button className="btn-ghost">Reinitialiser</button>
              <button className="btn-primary">Sauvegarder</button>
            </div>
          </main>
        )}
      </div>
    </div>
  )
}