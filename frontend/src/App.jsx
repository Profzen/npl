import { useCallback, useEffect, useRef, useState } from 'react'

const TRANSLATIONS = {
  fr: {
    home: 'Accueil',
    history: 'Historique',
    settings: 'Parametres',
    users: 'Utilisateurs',
    objects: 'Objets',
    guide_sql: 'Guide SQL',
    quick_access: 'Acces rapide',
    ask_question: 'Interrogez vos donnees d audit',
    ask_sub: 'en posant de simples questions sur ci-dessous',
    ask_intro: 'Posez votre question en francais, SMART2D gere tout automatiquement et vous donne une reponse.',
    send: 'Envoyer',
    analyzing: 'Analyse...',
    new_question: 'Nouvelle question',
    placeholder: 'Ex : Quels utilisateurs ont effectue des DELETE ce mois-ci ?',
    lines: 'ligne',
    question: 'Question',
    sql: 'SQL',
    copy: 'Copier',
    error: 'Erreur',
    searching: 'Rechercher',
    no_data: 'Aucune donnee',
    hide_menu: 'Masquer menu',
    show_menu: 'Afficher menu',
    oracle_db: 'Oracle DB',
    connected: 'Connecte',
    connected_idle: 'Connecte (non maintenue)',
    offline: 'Hors ligne',
    query_history: 'Historique des requetes',
    entries: 'entree',
    query_executed: 'Aucune requete executee pour l instant.',
    select_query: 'Selectionnez une requete pour voir les details',
    generated_sql: 'SQL genere',
    synthesis: 'Synthese',
    oracle_conn: 'Connexion Oracle',
    user: 'Utilisateur',
    host: 'Hote',
    port: 'Port',
    service: 'Service',
    table: 'Table',
    analysis_params: 'Parametres d analyse',
    interface_lang: 'Langue d interface',
    max_results: 'Resultats max par requete',
    session_duration: 'Duree session (min)',
    logs_retention: 'Conservation logs (j)',
    password: 'Mot de passe',
    reset: 'Reinitialiser',
    save: 'Sauvegarder',
    loading: 'Analyse en cours',
    generating_sql: 'Generation de la requete SQL...',
    rows: 'lignes',
    results: 'resultats',
    see_others: 'Voir les',
    reduce: 'Reduire',
    others: 'autres',
    no_users: 'Aucun utilisateur',
    no_objects: 'Aucun objet',
    no_users_found: 'Aucun utilisateur',
    actions: 'actions',
    error_execution: 'Erreur d execution',
    blocked_badge: 'Bloque',
    ok_badge: 'OK',
    error_badge: 'Erreur',
    query_detail: 'Details',
    logout: 'Se deconnecter',
    login_title: 'Connexion a SMART2D',
    login_sub: 'Identifiez-vous pour acceder a l interface',
    sign_in: 'Se connecter',
    auth_error: 'Identifiants invalides ou compte suspendu',
    admin: 'Administration',
    user_mgmt: 'Gestion des utilisateurs',
    create_user: 'Creer utilisateur',
    new_user_name: 'Nom utilisateur',
    new_user_password: 'Mot de passe initial',
    new_user_admin: 'Compte administrateur',
    create: 'Creer',
    status: 'Statut',
    active: 'Actif',
    suspended: 'Suspendu',
    role: 'Role',
    admin_role: 'Admin',
    standard_role: 'Standard',
    suspend: 'Suspendre',
    activate: 'Activer',
    delete_user: 'Supprimer',
    created_users_empty: 'Aucun utilisateur cree',
    account_label: 'Compte',
    cancel: 'Annuler',
    audit_logs: 'Logs d activite',
    timestamp: 'Horodatage',
    action_name: 'Action',
    result_status: 'Resultat',
    details: 'Details',
    refresh: 'Actualiser',
  },
  en: {
    home: 'Home',
    history: 'History',
    settings: 'Settings',
    users: 'Users',
    objects: 'Objects',
    guide_sql: 'SQL Guide',
    quick_access: 'Quick Access',
    ask_question: 'Query your audit data',
    ask_sub: 'by asking simple questions below',
    ask_intro: 'Ask your question in English, SMART2D handles everything automatically and gives you an answer.',
    send: 'Send',
    analyzing: 'Analyzing...',
    new_question: 'New question',
    placeholder: 'Ex: Which users performed DELETE this month?',
    lines: 'line',
    question: 'Question',
    sql: 'SQL',
    copy: 'Copy',
    error: 'Error',
    searching: 'Search',
    no_data: 'No data',
    hide_menu: 'Hide menu',
    show_menu: 'Show menu',
    oracle_db: 'Oracle DB',
    connected: 'Connected',
    connected_idle: 'Connected (not maintained)',
    offline: 'Offline',
    query_history: 'Query History',
    entries: 'entry',
    query_executed: 'No queries executed yet.',
    select_query: 'Select a query to see details',
    generated_sql: 'Generated SQL',
    synthesis: 'Summary',
    oracle_conn: 'Oracle Connection',
    user: 'User',
    host: 'Host',
    port: 'Port',
    service: 'Service',
    table: 'Table',
    analysis_params: 'Analysis Parameters',
    interface_lang: 'Interface Language',
    max_results: 'Max results per query',
    session_duration: 'Session duration (min)',
    logs_retention: 'Logs retention (days)',
    password: 'Password',
    reset: 'Reset',
    save: 'Save',
    loading: 'Analysis in progress',
    generating_sql: 'Generating SQL query...',
    rows: 'rows',
    results: 'results',
    see_others: 'See the',
    reduce: 'Reduce',
    others: 'others',
    no_users: 'No users',
    no_objects: 'No objects',
    no_users_found: 'No users found',
    actions: 'actions',
    error_execution: 'Execution error',
    blocked_badge: 'Blocked',
    ok_badge: 'OK',
    error_badge: 'Error',
    query_detail: 'Details',
    logout: 'Log out',
    login_title: 'SMART2D Login',
    login_sub: 'Sign in to access the interface',
    sign_in: 'Sign in',
    auth_error: 'Invalid credentials or suspended account',
    admin: 'Admin',
    user_mgmt: 'User management',
    create_user: 'Create user',
    new_user_name: 'Username',
    new_user_password: 'Initial password',
    new_user_admin: 'Administrator account',
    create: 'Create',
    status: 'Status',
    active: 'Active',
    suspended: 'Suspended',
    role: 'Role',
    admin_role: 'Admin',
    standard_role: 'Standard',
    suspend: 'Suspend',
    activate: 'Activate',
    delete_user: 'Delete',
    created_users_empty: 'No users found',
    account_label: 'Account',
    cancel: 'Cancel',
    audit_logs: 'Activity logs',
    timestamp: 'Timestamp',
    action_name: 'Action',
    result_status: 'Result',
    details: 'Details',
    refresh: 'Refresh',
  }
}

const GUIDE_CONTENT = {
  fr: [
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
  ],
  en: [
    ['SELECT', '#3b82f6', 'Read / query data'],
    ['INSERT', '#f59e0b', 'Add a new row'],
    ['UPDATE', '#f97316', 'Modify data'],
    ['DELETE', '#ef4444', 'Delete a row'],
    ['LOGON', '#22c55e', 'Oracle user login'],
    ['LOGOFF', '#86efac', 'User logout'],
    ['CREATE', '#a855f7', 'Create DB object'],
    ['ALTER', '#8b5cf6', 'Modify structure'],
    ['DROP', '#f43f5e', 'Delete an object'],
    ['GRANT', '#06b6d4', 'Grant permissions'],
    ['REVOKE', '#0ea5e9', 'Revoke permissions'],
  ]
}

const COLUMN_LABELS = {
  fr: {
    DBUSERNAME: 'Utilisateur',
    USERNAME: 'Utilisateur',
    ACTION_NAME: 'Action effectuee',
    EVENT_TIMESTAMP: 'Date et heure',
    OBJECT_NAME: 'Objet concerne',
    OS_USERNAME: 'Compte poste',
    USERHOST: 'Machine source',
    SESSIONID: 'Session',
    RETURN_CODE: 'Code retour',
  },
  en: {
    DBUSERNAME: 'User',
    USERNAME: 'User',
    ACTION_NAME: 'Action performed',
    EVENT_TIMESTAMP: 'Date and time',
    OBJECT_NAME: 'Object',
    OS_USERNAME: 'Account',
    USERHOST: 'Source machine',
    SESSIONID: 'Session',
    RETURN_CODE: 'Return code',
  }
}

function formatColumnLabel(key, lang = 'fr') {
  const labels = COLUMN_LABELS[lang] || COLUMN_LABELS.fr
  if (labels[key]) return labels[key]
  const normalized = String(key || '').replace(/_/g, ' ').trim().toLowerCase()
  if (!normalized) return TRANSLATIONS[lang]?.no_data || 'Colonne'
  return normalized.replace(/\b\w/g, c => c.toUpperCase())
}

function getNav(lang = 'fr', isAdmin = false) {
  const t = TRANSLATIONS[lang] || TRANSLATIONS.fr
  const items = [
    { id: 'home', label: t.home, icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
    { id: 'history', label: t.history, icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
    { id: 'settings', label: t.settings, icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
  ]
  if (isAdmin) {
    items.push({ id: 'admin', label: t.admin, icon: 'M12 4l8 4v6c0 5-3.5 9.5-8 11-4.5-1.5-8-6-8-11V8l8-4z M9.5 12l2 2 3-3' })
  }
  return items
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
  const [lang, setLang] = useState('fr')
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
  const [passwordVisible, setPasswordVisible] = useState(false)
  const [authToken, setAuthToken] = useState(() => localStorage.getItem('smart2d_token') || '')
  const [currentUser, setCurrentUser] = useState(null)
  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [loginState, setLoginState] = useState('idle')
  const [loginError, setLoginError] = useState('')
  const [adminUsers, setAdminUsers] = useState([])
  const [adminLogs, setAdminLogs] = useState([])
  const [adminForm, setAdminForm] = useState({ username: '', password: '', is_admin: false })
  const [showCreateUserForm, setShowCreateUserForm] = useState(false)
  const [adminState, setAdminState] = useState('idle')
  const [adminError, setAdminError] = useState('')
  const [settingsForm, setSettingsForm] = useState({
    oracle_user: 'aziz',
    oracle_password: 'aziz',
    oracle_host: '192.168.132.177',
    oracle_port: '1791',
    oracle_service: 'OSCARDB1',
    oracle_table: 'SMART2DSECU.UNIFIED_AUDIT_DATA',
    interface_lang: 'fr',
    max_results: '10',
    session_duration: '30',
    logs_retention: '90',
  })
  const [saveState, setSaveState] = useState('idle')
  const [oracleBadgeState, setOracleBadgeState] = useState('offline')
  const inputRef = useRef(null)
  const dockInputRef = useRef(null)
  const panelRef = useRef(null)
  const resultRef = useRef(null)
  const oracleIdleTimerRef = useRef(null)

  const t = TRANSLATIONS[lang] || TRANSLATIONS.fr
  const NAV = getNav(lang, !!currentUser?.is_admin)
  const GUIDE = GUIDE_CONTENT[lang] || GUIDE_CONTENT.fr

  const clearSession = useCallback(() => {
    localStorage.removeItem('smart2d_token')
    setAuthToken('')
    setCurrentUser(null)
    setPage('home')
    setResult(null)
    setHistory([])
  }, [])

  const apiFetch = useCallback(async (url, options = {}) => {
    const headers = {
      ...(options.headers || {}),
    }
    if (authToken) {
      headers['X-Auth-Token'] = authToken
    }
    const response = await fetch(url, { ...options, headers })
    if (response.status === 401) {
      clearSession()
      throw new Error('UNAUTHORIZED')
    }
    return response
  }, [authToken, clearSession])

  const scheduleOracleIdle = useCallback(() => {
    if (oracleIdleTimerRef.current) clearTimeout(oracleIdleTimerRef.current)
    oracleIdleTimerRef.current = setTimeout(() => {
      setOracleBadgeState(prev => (prev === 'active' ? 'idle' : prev))
    }, 30000)
  }, [])

  const markOracleActive = useCallback(() => {
    setOracleBadgeState('active')
    scheduleOracleIdle()
  }, [scheduleOracleIdle])

  const fetchHealth = useCallback(async () => {
    try {
      const r = await apiFetch('/api/health')
      if (!r.ok) return
      const payload = await r.json()
      setHealth(payload)
      if (payload.oracle === 'connected') {
        markOracleActive()
      } else {
        setOracleBadgeState('offline')
        if (oracleIdleTimerRef.current) clearTimeout(oracleIdleTimerRef.current)
      }
    } catch {
      setOracleBadgeState('offline')
      if (oracleIdleTimerRef.current) clearTimeout(oracleIdleTimerRef.current)
    }
  }, [apiFetch, markOracleActive])
  const fetchMeta = useCallback(async () => {
    try { const r = await apiFetch('/api/metadata'); if (r.ok) setMeta(await r.json()) } catch {}
  }, [apiFetch])
  const fetchHistory = useCallback(async () => {
    try { const r = await apiFetch('/api/history'); if (r.ok) setHistory(await r.json()) } catch {}
  }, [apiFetch])

  const fetchAdminUsers = useCallback(async () => {
    if (!currentUser?.is_admin) return
    try {
      const r = await apiFetch('/api/admin/users')
      if (!r.ok) return
      setAdminUsers(await r.json())
    } catch {}
  }, [apiFetch, currentUser])

  const fetchAdminLogs = useCallback(async () => {
    if (!currentUser?.is_admin) return
    try {
      const r = await apiFetch('/api/admin/audit-logs?limit=300')
      if (!r.ok) return
      setAdminLogs(await r.json())
    } catch {}
  }, [apiFetch, currentUser])

  const fetchSettings = useCallback(async () => {
    try {
      const r = await apiFetch('/api/settings')
      if (!r.ok) return
      const s = await r.json()
      setSettingsForm({
        oracle_user: String(s.oracle_user ?? 'aziz'),
        oracle_password: String(s.oracle_password ?? ''),
        oracle_host: String(s.oracle_host ?? '192.168.132.177'),
        oracle_port: String(s.oracle_port ?? '1791'),
        oracle_service: String(s.oracle_service ?? 'OSCARDB1'),
        oracle_table: String(s.oracle_table ?? 'SMART2DSECU.UNIFIED_AUDIT_DATA'),
        interface_lang: String(s.interface_lang ?? 'fr') === 'en' ? 'en' : 'fr',
        max_results: String(s.max_results ?? 10),
        session_duration: String(s.session_duration ?? 30),
        logs_retention: String(s.logs_retention ?? 90),
      })
      setLang(String(s.interface_lang ?? 'fr') === 'en' ? 'en' : 'fr')
    } catch {}
  }, [apiFetch])

  useEffect(() => {
    if (!authToken) {
      setCurrentUser(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const r = await fetch('/api/auth/me', { headers: { 'X-Auth-Token': authToken } })
        if (!r.ok) throw new Error('AUTH')
        const me = await r.json()
        if (!cancelled) setCurrentUser(me)
      } catch {
        if (!cancelled) clearSession()
      }
    })()
    return () => { cancelled = true }
  }, [authToken, clearSession])

  useEffect(() => {
    if (!currentUser) return
    fetchHealth()
    fetchMeta()
    fetchHistory()
    fetchSettings()
    if (currentUser.is_admin) {
      fetchAdminUsers()
      fetchAdminLogs()
    }
  }, [currentUser, fetchHealth, fetchMeta, fetchHistory, fetchSettings, fetchAdminUsers, fetchAdminLogs])

  useEffect(() => {
    if (!currentUser?.is_admin && page === 'admin') {
      setPage('home')
    }
  }, [currentUser, page])

  useEffect(() => {
    return () => {
      if (oracleIdleTimerRef.current) clearTimeout(oracleIdleTimerRef.current)
    }
  }, [])

  const copy = t => navigator.clipboard?.writeText(t).catch(() => {})
  const oracleOk = health?.oracle === 'connected'
  const oracleBadgeClass = oracleBadgeState === 'active' ? 'ob-ok' : oracleBadgeState === 'idle' ? 'ob-idle' : 'ob-err'
  const oracleBadgeText = oracleBadgeState === 'active' ? t.connected : oracleBadgeState === 'idle' ? t.connected_idle : t.offline

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
      markOracleActive()
      const r = await apiFetch('/api/query', {
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
      const errMsg = err?.message === 'UNAUTHORIZED' ? t.auth_error : err.message
      setResult({ error: errMsg, sql: '', synthesis: '', row_count: 0, rows: [], question: question.trim(), blocked: false })
      setTimeout(() => {
        resultRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 70)
    } finally {
      setLoading(false)
      fetchHealth()
    }
  }

  const handleLogin = async () => {
    if (!loginForm.username.trim() || !loginForm.password.trim() || loginState === 'loading') return
    setLoginState('loading')
    setLoginError('')
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: loginForm.username.trim(), password: loginForm.password }),
      })
      if (!r.ok) throw new Error('AUTH')
      const data = await r.json()
      localStorage.setItem('smart2d_token', data.token)
      setAuthToken(data.token)
      setCurrentUser(data.user)
      setLoginForm({ username: '', password: '' })
      setLoginState('idle')
    } catch {
      setLoginState('error')
      setLoginError(t.auth_error)
    }
  }

  const handleLogout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' })
    } catch {}
    clearSession()
  }

  const updateSettingField = (key, value) => {
    setSettingsForm(prev => ({ ...prev, [key]: value }))
    if (key === 'interface_lang') {
      setLang(value === 'en' ? 'en' : 'fr')
    }
  }

  const handleSaveSettings = async () => {
    setSaveState('saving')
    try {
      const payload = {
        oracle_user: settingsForm.oracle_user,
        oracle_password: settingsForm.oracle_password,
        oracle_host: settingsForm.oracle_host,
        oracle_port: Number(settingsForm.oracle_port || 1791),
        oracle_service: settingsForm.oracle_service,
        oracle_table: settingsForm.oracle_table,
        interface_lang: settingsForm.interface_lang === 'en' ? 'en' : 'fr',
        max_results: Number(settingsForm.max_results || 10),
        session_duration: Number(settingsForm.session_duration || 30),
        logs_retention: Number(settingsForm.logs_retention || 90),
      }

      const r = await apiFetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const saved = await r.json()
      setSettingsForm({
        oracle_user: String(saved.oracle_user),
        oracle_password: String(saved.oracle_password),
        oracle_host: String(saved.oracle_host),
        oracle_port: String(saved.oracle_port),
        oracle_service: String(saved.oracle_service),
        oracle_table: String(saved.oracle_table),
        interface_lang: String(saved.interface_lang) === 'en' ? 'en' : 'fr',
        max_results: String(saved.max_results),
        session_duration: String(saved.session_duration),
        logs_retention: String(saved.logs_retention),
      })
      setLang(String(saved.interface_lang) === 'en' ? 'en' : 'fr')
      setSaveState('saved')
      fetchHealth()
      fetchMeta()
      setTimeout(() => setSaveState('idle'), 1800)
    } catch {
      setSaveState('error')
    }
  }

  const handleResetSettings = () => {
    fetchSettings()
    setSaveState('idle')
  }

  const handleCreateUser = async () => {
    if (!currentUser?.is_admin) return
    if (!adminForm.username.trim() || !adminForm.password.trim()) return
    setAdminState('saving')
    setAdminError('')
    try {
      const r = await apiFetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: adminForm.username.trim(),
          password: adminForm.password,
          is_admin: adminForm.is_admin,
        }),
      })
      if (!r.ok) {
        const payload = await r.json().catch(() => ({}))
        throw new Error(payload.detail || 'Erreur')
      }
      setAdminForm({ username: '', password: '', is_admin: false })
      setAdminState('saved')
      setShowCreateUserForm(false)
      fetchAdminUsers()
      fetchAdminLogs()
      setTimeout(() => setAdminState('idle'), 1200)
    } catch (err) {
      setAdminState('error')
      setAdminError(err.message || 'Erreur')
    }
  }

  const handleOpenCreateUserForm = () => {
    setAdminForm({ username: '', password: '', is_admin: false })
    setAdminError('')
    setAdminState('idle')
    setShowCreateUserForm(true)
  }

  const handleCancelCreateUserForm = () => {
    setShowCreateUserForm(false)
    setAdminForm({ username: '', password: '', is_admin: false })
    setAdminError('')
    setAdminState('idle')
  }

  const handleToggleUserStatus = async (user) => {
    if (!currentUser?.is_admin) return
    try {
      await apiFetch(`/api/admin/users/${user.id}/status`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: !user.is_active }),
      })
      fetchAdminUsers()
      fetchAdminLogs()
    } catch {}
  }

  const handleDeleteUser = async (user) => {
    if (!currentUser?.is_admin) return
    try {
      await apiFetch(`/api/admin/users/${user.id}`, { method: 'DELETE' })
      fetchAdminUsers()
      fetchAdminLogs()
    } catch {}
  }

  const formatAuditTime = (ts) => {
    const raw = Number(ts || 0)
    if (!raw) return '-'
    return new Date(raw * 1000).toLocaleString(lang === 'en' ? 'en-US' : 'fr-FR')
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
          placeholder={t.placeholder}
        />
        <button className="search-bar-btn" onClick={handleSubmit} disabled={loading || !question.trim()}>
          {loading ? <><span className="spin" /> {t.analyzing}</> : <>{t.send}</>}
        </button>
      </div>
    )
  }

  if (!currentUser) {
    return (
      <main className="auth-wrap">
        <section className="auth-card">
          <div className="auth-logo">SMART2D</div>
          <h1>{t.login_title}</h1>
          <p>{t.login_sub}</p>
          <div className="field">
            <label>{t.user}</label>
            <input
              value={loginForm.username}
              onChange={e => setLoginForm(prev => ({ ...prev, username: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              placeholder="admin"
            />
          </div>
          <div className="field">
            <label>{t.password}</label>
            <input
              type="password"
              value={loginForm.password}
              onChange={e => setLoginForm(prev => ({ ...prev, password: e.target.value }))}
              onKeyDown={e => e.key === 'Enter' && handleLogin()}
              placeholder="******"
            />
          </div>
          <button className="btn-primary auth-btn" onClick={handleLogin}>
            {loginState === 'loading' ? `${t.sign_in}...` : t.sign_in}
          </button>
          {loginError && <div className="alert alert-err auth-alert">{loginError}</div>}
        </section>
      </main>
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
          {NAV.filter(n => n.id !== 'admin' || currentUser?.is_admin).map(n => (
            <button key={n.id}
              className={`snav-btn${page === n.id ? ' snav-active' : ''}`}
              onClick={() => { setPage(n.id); if (n.id === 'history') fetchHistory() }}>
              <Icon d={n.icon} size={16} />
              <span className="snav-label">{n.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-links">
          <div className="slinks-title">{t.quick_access}</div>
          <button
            className={`slink${page === 'home' && panel === 'users' ? ' slink-active' : ''}`}
            onClick={() => goToPanel('users')}>
            {t.users} ({(meta.users || []).length})
          </button>
          <button
            className={`slink${page === 'home' && panel === 'tables' ? ' slink-active' : ''}`}
            onClick={() => goToPanel('tables')}>
            {t.objects} ({(meta.objects || []).length})
          </button>
          <button
            className={`slink${page === 'home' && panel === 'guide' ? ' slink-active' : ''}`}
            onClick={() => goToPanel('guide')}>
            {t.guide_sql}
          </button>
        </div>

        <div className="sidebar-foot">
          <div className={`oracle-badge ${oracleBadgeClass}`}>
            <span className="ob-dot" />
            <div className="ob-info">
              <span className="ob-label">{t.oracle_db}</span>
              <span className="ob-val">{oracleBadgeText}</span>
            </div>
          </div>
          <button className="btn-logout" onClick={handleLogout}>{t.logout}</button>
          <span className="sidebar-date">
            {t.account_label}: {currentUser.username} | {new Date().toLocaleDateString(lang === 'en' ? 'en-US' : 'fr-FR', { day: 'numeric', month: 'short', year: 'numeric' })}
          </span>
        </div>
      </aside>

      <div className="content">
        <button
          className="sidebar-toggle"
          onClick={() => setIsSidebarOpen(v => !v)}
          aria-label={isSidebarOpen ? t.hide_menu : t.show_menu}>
          {isSidebarOpen ? t.hide_menu : t.show_menu}
        </button>

        {page === 'home' && (
          <main className="home">
            <section className="hero">
              <h1 className="hero-title">
                {t.ask_question}<br />
                <span>{t.ask_sub}</span>
              </h1>
              <p className="hero-sub">
                {t.ask_intro}
              </p>

              {renderSearchBar('hero')}

              <div className="quick-chips">
                {(lang === 'fr'
                  ? ['Connexions du jour', 'TOP 10 utilisateurs', 'Dernieres suppressions', 'Objets modifies']
                  : ['Today\'s connections', 'TOP 10 users', 'Recent deletions', 'Modified objects']
                ).map(q => (
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
                  <span className="dock-label">{t.new_question}</span>
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
                      <strong>{t.loading}</strong>
                      <p>{t.generating_sql}</p>
                    </div>
                  </div>
                ) : result && (
                  <div className={`result-inner${isCompactResult ? ' result-inner-compact' : ''}`}>
                    <div className="result-header">
                      <div className="result-q">
                        <span className="result-q-label">{t.question}</span>
                        {result.question}
                      </div>
                      {result.row_count > 0 && (
                        <span className="result-count">{result.row_count} {result.row_count > 1 ? t.rows : t.lines}</span>
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
                          <span>{t.sql}</span>
                          <button className="btn-copy" onClick={() => copy(result.sql)}>
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                              strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <rect x="9" y="9" width="13" height="13" rx="2" />
                              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                            </svg>
                            {t.copy}
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
                      <div className="alert alert-err">{t.error_execution} - {result.error}</div>
                    )}

                    {result.rows?.length > 0 && (
                      <div className="tbl-scroll">
                        <table className="data-table">
                          <thead>
                            <tr>{Object.keys(result.rows[0]).map(c => <th key={c}>{formatColumnLabel(c, lang)}</th>)}</tr>
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
                  { id: 'users', label: `${t.users} (${(meta.users || []).length})` },
                  { id: 'tables', label: `${t.objects} (${(meta.objects || []).length})` },
                  { id: 'guide', label: t.guide_sql },
                ].map(tb => (
                  <button key={tb.id}
                    className={`ptab${panel === tb.id ? ' ptab-active' : ''}`}
                    onClick={() => setPanel(tb.id)}>
                    {tb.label}
                  </button>
                ))}
              </div>

              <div className="panel-body">
                {panel === 'users' && (
                  <div className="panel-list-wrap">
                    <input className="panel-search" type="search" placeholder={`${t.searching} ${t.users.toLowerCase()}...`}
                      value={usersQ} onChange={e => { setUsersQ(e.target.value); setShowAllU(false) }} />
                    <div className="panel-grid">
                      {visibleUsers.length === 0
                        ? <span className="panel-empty">{t.no_users}</span>
                        : visibleUsers.map(u => (
                          <div key={u.name} className="pcard">
                            <div className="pcard-avatar">{u.name.charAt(0)}</div>
                            <div className="pcard-info">
                              <span className="pcard-name">{u.name}</span>
                              <span className="pcard-count">{u.actions.toLocaleString()} {t.actions}</span>
                            </div>
                          </div>
                        ))}
                    </div>
                    {filteredUsers.length > (showAllU ? 0 : 20) && (
                      <button className="panel-more" onClick={() => setShowAllU(v => !v)}>
                        {showAllU ? t.reduce : `${t.see_others} ${filteredUsers.length - 20} ${t.others}`}
                      </button>
                    )}
                  </div>
                )}

                {panel === 'tables' && (
                  <div className="panel-list-wrap">
                    <input className="panel-search" type="search" placeholder={`${t.searching} ${t.objects.toLowerCase()}...`}
                      value={tablesQ} onChange={e => { setTablesQ(e.target.value); setShowAllT(false) }} />
                    <div className="panel-grid">
                      {visibleTables.length === 0
                        ? <span className="panel-empty">{t.no_objects}</span>
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
                              <span className="pcard-count">{o.actions.toLocaleString()} {t.actions}</span>
                            </div>
                          </div>
                        ))}
                    </div>
                    {filteredTables.length > (showAllT ? 0 : 16) && (
                      <button className="panel-more" onClick={() => setShowAllT(v => !v)}>
                        {showAllT ? t.reduce : `${t.see_others} ${filteredTables.length - 16} ${t.others}`}
                      </button>
                    )}
                  </div>
                )}

                {panel === 'guide' && (
                  <div className="guide-grid">
                    {GUIDE.map(([code, _color, desc]) => (
                      <div key={code} className="guide-card">
                        <span className="guide-tag">{code}</span>
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
              <h2>{t.query_history}</h2>
              <span className="page-header-count">{history.length} {history.length > 1 ? t.entries : t.entries}</span>
            </div>

            <div className="hist-layout">
              <div className="hist-list">
                {history.length === 0 && (
                  <div className="hist-empty">{t.query_executed}</div>
                )}
                {[...history].reverse().map((item, i) => (
                  <div key={i}
                    className={`hist-item${histSel === item ? ' hist-sel' : ''}`}
                    onClick={() => setHistSel(item)}>
                    <div className="hist-item-top">
                      <span className="hist-time">
                        {item.timestamp ? new Date(item.timestamp).toLocaleTimeString(lang === 'en' ? 'en-US' : 'fr-FR') : '--:--'}
                      </span>
                      {item.error
                        ? <span className="badge badge-err">{t.error_badge}</span>
                        : item.blocked
                          ? <span className="badge badge-warn">{t.blocked_badge}</span>
                          : <span className="badge badge-ok">{t.ok_badge}</span>
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
                    {t.select_query}
                  </div>
                ) : (
                  <>
                    <div className="detail-section">
                      <div className="detail-label">{t.question}</div>
                      <div className="detail-text">{histSel.question}</div>
                    </div>
                    {histSel.sql && (
                      <div className="detail-section">
                        <div className="detail-label">{t.generated_sql}</div>
                        <pre className="detail-code">{histSel.sql}</pre>
                      </div>
                    )}
                    {histSel.synthesis && (
                      <div className="detail-section">
                        <div className="detail-label">{t.synthesis}</div>
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
              <h2>{t.settings}</h2>
            </div>
            {saveState === 'saved' && (
              <div className="alert alert-ok settings-notice">Parametres sauvegardes.</div>
            )}
            {saveState === 'error' && (
              <div className="alert alert-err settings-notice">Echec de sauvegarde des parametres.</div>
            )}
            <div className="settings-cols">
              <div className="settings-block">
                <div className="settings-block-title">{t.oracle_conn}</div>
                <div className="settings-block-body">
                  <div className="field">
                    <label>{t.user}</label>
                    <input value={settingsForm.oracle_user} onChange={e => updateSettingField('oracle_user', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.host}</label>
                    <input value={settingsForm.oracle_host} onChange={e => updateSettingField('oracle_host', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.port}</label>
                    <input value={settingsForm.oracle_port} onChange={e => updateSettingField('oracle_port', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.service}</label>
                    <input value={settingsForm.oracle_service} onChange={e => updateSettingField('oracle_service', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.table}</label>
                    <input value={settingsForm.oracle_table} onChange={e => updateSettingField('oracle_table', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.password}</label>
                    <div className="field-password-wrap">
                      <input
                        type={passwordVisible ? 'text' : 'password'}
                        value={settingsForm.oracle_password}
                        onChange={e => updateSettingField('oracle_password', e.target.value)}
                      />
                      <button
                        type="button"
                        className="field-password-toggle"
                        onClick={() => setPasswordVisible(v => !v)}>
                        {passwordVisible ? (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                            <circle cx="12" cy="12" r="3" />
                          </svg>
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
                            stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                            <line x1="1" y1="1" x2="23" y2="23" />
                          </svg>
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div className="settings-block">
                <div className="settings-block-title">{t.analysis_params}</div>
                <div className="settings-block-body">
                  <div className="field">
                    <label>{t.interface_lang}</label>
                    <select value={settingsForm.interface_lang} onChange={e => updateSettingField('interface_lang', e.target.value)}>
                      <option value="fr">Français</option>
                      <option value="en">English</option>
                    </select>
                  </div>
                  <div className="field">
                    <label>{t.max_results}</label>
                    <input value={settingsForm.max_results} onChange={e => updateSettingField('max_results', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.session_duration}</label>
                    <input value={settingsForm.session_duration} onChange={e => updateSettingField('session_duration', e.target.value)} />
                  </div>
                  <div className="field">
                    <label>{t.logs_retention}</label>
                    <input value={settingsForm.logs_retention} onChange={e => updateSettingField('logs_retention', e.target.value)} />
                  </div>
                </div>
              </div>
            </div>
            <div className="settings-actions">
              <button className="btn-ghost" onClick={handleResetSettings}>{t.reset}</button>
              <button className="btn-primary" onClick={handleSaveSettings}>
                {saveState === 'saving' ? `${t.save}...` : t.save}
              </button>
            </div>
          </main>
        )}

        {page === 'admin' && currentUser?.is_admin && (
          <main className="page-inner">
            <div className="page-header">
              <h2>{t.user_mgmt}</h2>
            </div>

            {!showCreateUserForm && (
              <div className="settings-actions" style={{ marginBottom: 16, justifyContent: 'flex-start' }}>
                <button className="btn-primary" onClick={handleOpenCreateUserForm}>{t.create_user}</button>
              </div>
            )}

            {showCreateUserForm && (
              <div className="settings-block" style={{ marginBottom: 16 }}>
                <div className="settings-block-title">{t.create_user}</div>
                <div className="settings-block-body">
                  <div className="settings-cols" style={{ marginBottom: 12 }}>
                    <div className="field">
                      <label>{t.new_user_name}</label>
                      <input value={adminForm.username} onChange={e => setAdminForm(prev => ({ ...prev, username: e.target.value }))} />
                    </div>
                    <div className="field">
                      <label>{t.new_user_password}</label>
                      <input type="password" value={adminForm.password} onChange={e => setAdminForm(prev => ({ ...prev, password: e.target.value }))} />
                    </div>
                  </div>
                  <label className="admin-check">
                    <input
                      type="checkbox"
                      checked={adminForm.is_admin}
                      onChange={e => setAdminForm(prev => ({ ...prev, is_admin: e.target.checked }))}
                    />
                    <span>{t.new_user_admin}</span>
                  </label>
                  <div className="settings-actions" style={{ marginTop: 12 }}>
                    <button className="btn-ghost" onClick={handleCancelCreateUserForm}>{t.cancel}</button>
                    <button className="btn-primary" onClick={handleCreateUser}>{adminState === 'saving' ? `${t.create}...` : t.create}</button>
                  </div>
                  {adminError && <div className="alert alert-err" style={{ marginTop: 10 }}>{adminError}</div>}
                </div>
              </div>
            )}

            <div className="tbl-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t.user}</th>
                    <th>{t.role}</th>
                    <th>{t.status}</th>
                    <th>{t.actions}</th>
                  </tr>
                </thead>
                <tbody>
                  {adminUsers.length === 0 && (
                    <tr>
                      <td colSpan={4}>{t.created_users_empty}</td>
                    </tr>
                  )}
                  {adminUsers.map(u => (
                    <tr key={u.id}>
                      <td>{u.username}</td>
                      <td>{u.is_admin ? t.admin_role : t.standard_role}</td>
                      <td>{u.is_active ? t.active : t.suspended}</td>
                      <td>
                        <div className="admin-row-actions">
                          <button className="btn-ghost admin-mini" onClick={() => handleToggleUserStatus(u)}>
                            {u.is_active ? t.suspend : t.activate}
                          </button>
                          {u.id !== currentUser.id && (
                            <button className="btn-ghost admin-mini admin-danger" onClick={() => handleDeleteUser(u)}>
                              {t.delete_user}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="settings-actions" style={{ marginTop: 16, justifyContent: 'space-between' }}>
              <h3 style={{ fontSize: 16, fontWeight: 800, color: '#0f172a' }}>{t.audit_logs}</h3>
              <button className="btn-ghost" onClick={fetchAdminLogs}>{t.refresh}</button>
            </div>

            <div className="tbl-scroll" style={{ marginTop: 10 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t.timestamp}</th>
                    <th>{t.user}</th>
                    <th>{t.action_name}</th>
                    <th>{t.result_status}</th>
                    <th>{t.question}</th>
                    <th>{t.sql}</th>
                    <th>{t.rows}</th>
                    <th>{t.details}</th>
                  </tr>
                </thead>
                <tbody>
                  {adminLogs.length === 0 && (
                    <tr>
                      <td colSpan={8}>{t.no_data}</td>
                    </tr>
                  )}
                  {adminLogs.map(log => (
                    <tr key={log.id}>
                      <td>{formatAuditTime(log.timestamp)}</td>
                      <td>{log.username}</td>
                      <td>{log.action}</td>
                      <td>{log.result_status}</td>
                      <td>{log.question || '-'}</td>
                      <td>{log.sql_text || '-'}</td>
                      <td>{log.row_count}</td>
                      <td>{log.details || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </main>
        )}
      </div>
    </div>
  )
}