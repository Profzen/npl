"use client"

import { useState, useCallback, useRef } from "react"
import {
  Search,
  Loader2,
  Code,
  MessageSquare,
  Table,
  Users,
  Database,
  Zap,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  SendHorizontal,
  Eye,
  EyeOff,
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { useAppData } from "@/components/app-shell"
import { submitQuery, ApiError } from "@/lib/api"
import type { QueryResponse } from "@/lib/types"
import { cn } from "@/lib/utils"

const auditActions = [
  { name: "SELECT", desc: "Lecture de donnees depuis une table ou vue" },
  { name: "INSERT", desc: "Ajout de nouvelles lignes dans une table" },
  { name: "UPDATE", desc: "Modification de donnees existantes" },
  { name: "DELETE", desc: "Suppression de lignes dans une table" },
  { name: "GRANT", desc: "Attribution de privileges a un utilisateur" },
  { name: "REVOKE", desc: "Retrait de privileges a un utilisateur" },
  { name: "ALTER", desc: "Modification de la structure d un objet" },
  { name: "DROP", desc: "Suppression d un objet (table, vue, index)" },
  { name: "CREATE", desc: "Creation d un nouvel objet dans la base" },
  { name: "TRUNCATE", desc: "Vidage complet d une table" },
  { name: "EXECUTE", desc: "Execution d une procedure ou fonction" },
  { name: "LOGON", desc: "Connexion d un utilisateur a la base" },
  { name: "LOGOFF", desc: "Deconnexion d un utilisateur" },
]

const USERS_VISIBLE_ITEMS = 13
const TABLES_VISIBLE_ITEMS = 13
const ACTIONS_VISIBLE_ITEMS = 7
const MIN_QUESTION_LINES = 2
const MAX_QUESTION_LINES = 4

const FRIENDLY_COLUMN_NAMES: Record<string, string> = {
  DBUSERNAME: "Utilisateur",
  USERNAME: "Utilisateur",
  ACTION_NAME: "Action",
  EVENT_TIMESTAMP: "Date et heure",
  OBJECT_NAME: "Objet",
  OBJECT_SCHEMA: "Schema",
  USERHOST: "Poste",
  SESSIONID: "Session",
  SQL_TEXT: "Texte SQL",
  INSTANCE: "Instance",
}

function toFriendlyColumnName(key: string): string {
  const normalized = key.toUpperCase()
  if (FRIENDLY_COLUMN_NAMES[normalized]) return FRIENDLY_COLUMN_NAMES[normalized]
  return normalized
    .split("_")
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(" ")
}

function resizeQuestionInput(el: HTMLTextAreaElement | null) {
  if (!el) return

  const style = window.getComputedStyle(el)
  const lineHeight = Number.parseFloat(style.lineHeight || "20") || 20
  const paddingTop = Number.parseFloat(style.paddingTop || "0") || 0
  const paddingBottom = Number.parseFloat(style.paddingBottom || "0") || 0

  const minHeight = lineHeight * MIN_QUESTION_LINES + paddingTop + paddingBottom
  const maxHeight = lineHeight * MAX_QUESTION_LINES + paddingTop + paddingBottom

  el.style.height = "auto"
  const targetHeight = Math.min(maxHeight, Math.max(minHeight, el.scrollHeight))
  el.style.height = `${targetHeight}px`
  el.style.overflowY = el.scrollHeight > maxHeight ? "auto" : "hidden"
}

export default function HomePage() {
  const { metadata, refreshMetadata, refreshHistory, markOracleActivity } = useAppData()
  const [question, setQuestion] = useState("")
  const [isLoading, setIsLoading] = useState(false)
  const [result, setResult] = useState<QueryResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [expandedUsers, setExpandedUsers] = useState(false)
  const [expandedTables, setExpandedTables] = useState(false)
  const [expandedActions, setExpandedActions] = useState(false)

  const [showUsersColumn, setShowUsersColumn] = useState(true)
  const [showTablesColumn, setShowTablesColumn] = useState(true)
  const [showActionsColumn, setShowActionsColumn] = useState(true)

  const questionInputRef = useRef<HTMLTextAreaElement | null>(null)
  const responseAnchorRef = useRef<HTMLDivElement | null>(null)

  const handleQuestionChange = (nextValue: string) => {
    setQuestion(nextValue)
    requestAnimationFrame(() => resizeQuestionInput(questionInputRef.current))
  }

  const handleSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!question.trim() || isLoading) return

    setIsLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await submitQuery({ question: question.trim() })
      setResult(response)
      setQuestion("")
      requestAnimationFrame(() => {
        resizeQuestionInput(questionInputRef.current)
        responseAnchorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })
      })
      markOracleActivity()
      await Promise.all([refreshMetadata(), refreshHistory()])
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 429 ? "Trop de requetes. Veuillez patienter." : err.detail)
      } else {
        setError("Une erreur inattendue est survenue.")
      }
    } finally {
      setIsLoading(false)
    }
  }, [question, isLoading, markOracleActivity, refreshMetadata, refreshHistory])

  const visibleUsers = expandedUsers ? metadata?.users : metadata?.users?.slice(0, USERS_VISIBLE_ITEMS)
  const visibleTables = expandedTables ? metadata?.objects : metadata?.objects?.slice(0, TABLES_VISIBLE_ITEMS)
  const visibleActions = expandedActions ? auditActions : auditActions.slice(0, ACTIONS_VISIBLE_ITEMS)

  const usersCount = metadata?.users?.length || 0
  const tablesCount = metadata?.objects?.length || 0

  const hasHiddenColumns = !showUsersColumn || !showTablesColumn || !showActionsColumn

  return (
    <div className="flex flex-col h-full">
      <header className="shrink-0 border-b-2 border-foreground/10 bg-card">
        <div className="px-6 py-4">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Posez votre question</h1>
          <p className="text-sm text-muted-foreground mt-1">Interrogez vos donnees d audit en francais</p>
        </div>
      </header>

      <div className="flex-1 overflow-auto p-4">
        <div className="flex gap-4 h-full">
          <div className="flex-1 min-w-0 flex flex-col gap-3">
            <Card className="shrink-0 border-2 border-foreground/10 shadow-md">
              <CardContent className="p-1.5">
                <form onSubmit={handleSubmit} className="relative">
                  <Textarea
                    ref={questionInputRef}
                    placeholder="Ex: Qui a modifie la table EMPLOYEES hier ?"
                    value={question}
                    onChange={(e) => handleQuestionChange(e.target.value)}
                    rows={MIN_QUESTION_LINES}
                    className="resize-none text-sm border-2 border-foreground/10 focus:border-primary min-h-[56px] max-h-[112px] overflow-y-hidden pr-12"
                    disabled={isLoading}
                  />
                  <Button
                    type="submit"
                    size="icon"
                    disabled={!question.trim() || isLoading}
                    className="absolute right-2 bottom-2 h-8 w-8"
                    title="Envoyer la question"
                  >
                    {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <SendHorizontal className="w-4 h-4" />}
                  </Button>
                </form>
              </CardContent>
            </Card>

            <div className="flex-1 min-h-0 overflow-auto">
              {error && (
                <Card className="border-2 border-primary/50 bg-primary/5 shadow-sm">
                  <CardContent className="pt-4 pb-4">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center shrink-0">
                        <AlertCircle className="w-4 h-4 text-primary" />
                      </div>
                      <div>
                        <p className="font-semibold text-primary text-sm">Erreur</p>
                        <p className="text-xs text-foreground/70 mt-1">{error}</p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {result && (
                <div className="space-y-3" ref={responseAnchorRef}>
                  <Card className="shadow-sm border-2 border-foreground/10">
                    <CardContent className="py-2 px-3">
                      <p className="text-sm font-bold leading-relaxed text-foreground flex items-start gap-2">
                        <MessageSquare className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                        <span>Question: {result.question}</span>
                      </p>
                    </CardContent>
                  </Card>

                  <Card className="shadow-sm border-2 border-status-success">
                    <CardContent className="py-3 px-3 bg-status-success/5">
                      <p className="text-base font-bold leading-relaxed text-foreground flex items-start gap-2">
                        <Zap className="w-4 h-4 text-status-success mt-1 shrink-0" />
                        <span>Synthese: {result.synthesis}</span>
                      </p>
                    </CardContent>
                  </Card>

                  {result.rows && result.rows.length > 0 && (
                    <Card className="shadow-sm border-2 border-foreground/10">
                      <CardHeader className="py-1.5 px-3 border-b border-foreground/5">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-sm flex items-center gap-2 text-foreground">
                            <Table className="w-4 h-4 text-primary" />Resultats
                          </CardTitle>
                          <Badge className="font-mono text-xs bg-foreground text-primary-foreground">{result.row_count} lignes</Badge>
                        </div>
                      </CardHeader>
                      <CardContent className="py-2 px-3">
                        <div className="max-h-64 overflow-auto border border-foreground/10 rounded-md">
                            <table className="min-w-full text-xs">
                              <thead className="sticky top-0 bg-foreground/5">
                                <tr className="border-b-2 border-foreground/20">
                                  {Object.keys(result.rows[0]).map((key) => (
                                    <th key={key} className="text-left font-bold p-1.5 text-xs text-foreground uppercase tracking-wider">
                                      {toFriendlyColumnName(key)}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {result.rows.map((row, i) => (
                                  <tr key={i} className={cn("border-b border-foreground/10 hover:bg-primary/5", i % 2 === 0 ? "bg-foreground/[0.02]" : "")}> 
                                    {Object.values(row).map((value, j) => (
                                      <td key={j} className="p-1.5 text-xs text-foreground">{String(value ?? "-")}</td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  <Card className="shadow-sm border-2 border-foreground/10">
                    <CardHeader className="py-1.5 px-3 border-b border-foreground/5">
                      <CardTitle className="text-sm flex items-center gap-2 text-foreground">
                        <Code className="w-4 h-4 text-primary" />Requete SQL
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="py-2 px-3">
                      <div className="max-h-36 overflow-auto rounded-md">
                        <pre className="text-[11px] leading-5 font-mono bg-foreground text-primary-foreground p-2 whitespace-pre-wrap">{result.sql}</pre>
                      </div>
                    </CardContent>
                  </Card>
                </div>
              )}

              {!result && !error && !isLoading && (
                <Card className="h-32 flex items-center justify-center border-2 border-dashed border-foreground/20 bg-card shadow-sm">
                  <div className="text-center">
                    <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center mx-auto mb-2 border-2 border-primary/20">
                      <Search className="w-5 h-5 text-primary" />
                    </div>
                    <p className="text-foreground font-medium text-sm">Posez une question pour interroger vos donnees</p>
                    <p className="text-xs text-muted-foreground mt-1">Ex : Qui a modifie la table EMPLOYEES ?</p>
                  </div>
                </Card>
              )}
            </div>
          </div>

          <div className="flex-none flex flex-col gap-2">
            {hasHiddenColumns && (
              <div className="flex items-center gap-2">
                {!showUsersColumn && (
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowUsersColumn(true)}>
                    <Eye className="w-3.5 h-3.5 mr-1" />Afficher Utilisateurs
                  </Button>
                )}
                {!showTablesColumn && (
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowTablesColumn(true)}>
                    <Eye className="w-3.5 h-3.5 mr-1" />Afficher Tables
                  </Button>
                )}
                {!showActionsColumn && (
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => setShowActionsColumn(true)}>
                    <Eye className="w-3.5 h-3.5 mr-1" />Afficher Actions
                  </Button>
                )}
              </div>
            )}

            <div className="flex gap-3 items-start">
              {showUsersColumn && (
                <Card className="w-60 flex-none border-2 border-foreground/10 shadow-sm self-start">
                  <CardHeader className="py-3 px-4 border-b border-foreground/5 bg-primary/5">
                    <CardTitle className="text-sm flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-7 h-7 rounded-md bg-primary text-primary-foreground flex items-center justify-center shrink-0">
                          <Users className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <span className="text-foreground font-semibold">Utilisateurs</span>
                        </div>
                      </div>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowUsersColumn(false)} title="Masquer la colonne">
                        <EyeOff className="w-4 h-4" />
                      </Button>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground font-semibold px-1 pb-1">
                      <span>Utilisateur</span>
                      <span>Occurrence</span>
                    </div>
                    <div className="space-y-1.5">
                      {visibleUsers && visibleUsers.length > 0 ? (
                        visibleUsers.map((user, i) => (
                          <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded border border-foreground/10 bg-muted/30 hover:bg-primary/5 transition-colors">
                            <span className="text-xs font-medium text-foreground truncate flex-1 mr-2">{user.name}</span>
                            <Badge className="text-xs font-mono bg-foreground text-primary-foreground px-1.5 py-0 h-5 shrink-0">{user.actions}</Badge>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-muted-foreground text-center py-4">Aucun utilisateur</p>
                      )}
                    </div>
                    {usersCount > USERS_VISIBLE_ITEMS && (
                      <Button variant="ghost" size="sm" className="w-full mt-3 h-7 text-xs text-muted-foreground hover:text-primary border border-foreground/10" onClick={() => setExpandedUsers(!expandedUsers)}>
                        {expandedUsers ? <ChevronUp className="w-3.5 h-3.5 mr-1" /> : <ChevronDown className="w-3.5 h-3.5 mr-1" />}
                        {expandedUsers ? "Reduire" : `+${usersCount - USERS_VISIBLE_ITEMS} plus`}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}

              {showTablesColumn && (
                <Card className="w-60 flex-none border-2 border-foreground/10 shadow-sm self-start">
                  <CardHeader className="py-3 px-4 border-b border-foreground/5 bg-foreground/5">
                    <CardTitle className="text-sm flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-7 h-7 rounded-md bg-foreground text-primary-foreground flex items-center justify-center shrink-0">
                          <Database className="w-4 h-4" />
                        </div>
                        <div className="min-w-0">
                          <span className="text-foreground font-semibold">Tables</span>
                        </div>
                      </div>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowTablesColumn(false)} title="Masquer la colonne">
                        <EyeOff className="w-4 h-4" />
                      </Button>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-3">
                    <div className="flex items-center justify-between text-[11px] text-muted-foreground font-semibold px-1 pb-1">
                      <span>Table</span>
                      <span>Occurrence</span>
                    </div>
                    <div className="space-y-1.5">
                      {visibleTables && visibleTables.length > 0 ? (
                        visibleTables.map((obj, i) => (
                          <div key={i} className="flex items-center justify-between py-1.5 px-2 rounded border border-foreground/10 bg-muted/30 hover:bg-foreground/5 transition-colors">
                            <span className="text-xs font-mono text-foreground truncate flex-1 mr-2">{obj.name}</span>
                            <Badge className="text-xs font-mono bg-foreground text-primary-foreground px-1.5 py-0 h-5 shrink-0">{obj.actions}</Badge>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-muted-foreground text-center py-4">Aucun objet</p>
                      )}
                    </div>
                    {tablesCount > TABLES_VISIBLE_ITEMS && (
                      <Button variant="ghost" size="sm" className="w-full mt-3 h-7 text-xs text-muted-foreground hover:text-primary border border-foreground/10" onClick={() => setExpandedTables(!expandedTables)}>
                        {expandedTables ? <ChevronUp className="w-3.5 h-3.5 mr-1" /> : <ChevronDown className="w-3.5 h-3.5 mr-1" />}
                        {expandedTables ? "Reduire" : `+${tablesCount - TABLES_VISIBLE_ITEMS} plus`}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}

              {showActionsColumn && (
                <Card className="w-60 flex-none border-2 border-foreground/10 shadow-sm self-start">
                  <CardHeader className="py-3 px-4 border-b border-foreground/5 bg-primary/5">
                    <CardTitle className="text-sm flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-7 h-7 rounded-md bg-primary text-primary-foreground flex items-center justify-center shrink-0">
                          <Zap className="w-4 h-4" />
                        </div>
                        <div>
                          <span className="text-foreground font-semibold">Actions</span>
                          <p className="text-xs font-normal text-muted-foreground">Types audites</p>
                        </div>
                      </div>
                      <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setShowActionsColumn(false)} title="Masquer la colonne">
                        <EyeOff className="w-4 h-4" />
                      </Button>
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-3">
                    <div className="space-y-1.5">
                      {visibleActions.map((action, i) => (
                        <div key={i} className="py-2 px-2 rounded border border-foreground/10 bg-muted/30 hover:bg-primary/5 transition-colors">
                          <Badge className="text-xs font-mono px-1.5 py-0 bg-primary text-primary-foreground h-5">{action.name}</Badge>
                          <p className="text-xs text-muted-foreground leading-snug mt-1">{action.desc}</p>
                        </div>
                      ))}
                    </div>
                    {auditActions.length > ACTIONS_VISIBLE_ITEMS && (
                      <Button variant="ghost" size="sm" className="w-full mt-3 h-7 text-xs text-muted-foreground hover:text-primary border border-foreground/10" onClick={() => setExpandedActions(!expandedActions)}>
                        {expandedActions ? <ChevronUp className="w-3.5 h-3.5 mr-1" /> : <ChevronDown className="w-3.5 h-3.5 mr-1" />}
                        {expandedActions ? "Reduire" : `+${auditActions.length - ACTIONS_VISIBLE_ITEMS} plus`}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
