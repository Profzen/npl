'use client'

import { useState } from 'react'
import { History, Code, MessageSquare, Table, Zap, CheckCircle2, XCircle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'
import { useAppData } from '@/components/app-shell'
import type { HistoryEntry } from '@/lib/types'
import { cn } from '@/lib/utils'

function StatusBadge({ status }: { status: HistoryEntry['status'] }) {
  const config = {
    ok: {
      label: 'OK',
      icon: CheckCircle2,
      className: 'bg-status-success/10 text-status-success border-status-success/20',
    },
    error: {
      label: 'Erreur',
      icon: XCircle,
      className: 'bg-status-error/10 text-status-error border-status-error/20',
    },
  }

  const safeStatus = status === 'error' ? 'error' : 'ok'
  const { label, icon: Icon, className } = config[safeStatus]

  return (
    <Badge variant="outline" className={cn('gap-1', className)}>
      <Icon className="w-3 h-3" />
      {label}
    </Badge>
  )
}

function formatDate(dateString: string) {
  const date = new Date(dateString)
  return new Intl.DateTimeFormat('fr-FR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export default function HistoryPage() {
  const { history, refreshHistory } = useAppData()
  const [selectedEntry, setSelectedEntry] = useState<HistoryEntry | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await refreshHistory()
    setIsRefreshing(false)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Historique</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Consultez vos requêtes précédentes
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={isRefreshing}>
            <RefreshCw className={cn('w-4 h-4 mr-2', isRefreshing && 'animate-spin')} />
            Actualiser
          </Button>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-hidden p-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 h-full">
          {/* Left Panel - History List */}
          <Card className="flex flex-col overflow-hidden">
            <CardHeader className="shrink-0 pb-3">
              <CardTitle className="text-base flex items-center gap-2">
                <History className="w-4 h-4 text-primary" />
                Requêtes récentes
              </CardTitle>
              <CardDescription className="text-xs">
                {history.length} requête{history.length > 1 ? 's' : ''} dans l&apos;historique
              </CardDescription>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0">
              <ScrollArea className="h-full">
                {history.length > 0 ? (
                  <div className="divide-y divide-border">
                    {history.map((entry) => (
                      <button
                        key={entry.id}
                        onClick={() => setSelectedEntry(entry)}
                        className={cn(
                          'w-full text-left p-4 hover:bg-muted/50 transition-colors',
                          selectedEntry?.id === entry.id && 'bg-primary/5 border-l-2 border-l-primary'
                        )}
                      >
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <p className="text-sm font-medium line-clamp-2">{entry.question}</p>
                          <StatusBadge status={entry.status} />
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {formatDate(entry.created_at)}
                        </p>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-full py-12">
                    <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
                      <History className="w-6 h-6 text-muted-foreground" />
                    </div>
                    <p className="text-sm text-muted-foreground">Aucune requête dans l&apos;historique</p>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          {/* Right Panel - Entry Detail */}
          <Card className="flex flex-col overflow-hidden">
            <CardHeader className="shrink-0 pb-3">
              <CardTitle className="text-base">Détail</CardTitle>
            </CardHeader>
            <CardContent className="flex-1 overflow-hidden p-0">
              {selectedEntry ? (
                <ScrollArea className="h-full px-6 pb-6">
                  <div className="space-y-4 pr-4">
                    {/* Status and Date */}
                    <div className="flex items-center justify-between">
                      <StatusBadge status={selectedEntry.status} />
                      <span className="text-xs text-muted-foreground">
                        {formatDate(selectedEntry.created_at)}
                      </span>
                    </div>

                    {/* Question */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <MessageSquare className="w-4 h-4 text-primary" />
                        <span className="text-sm font-medium">Question</span>
                      </div>
                      <p className="text-sm bg-muted/50 p-3 rounded-lg whitespace-pre-wrap break-words leading-relaxed">
                        {selectedEntry.question}
                      </p>
                    </div>

                    {/* SQL */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Code className="w-4 h-4 text-primary" />
                        <span className="text-sm font-medium">SQL généré</span>
                      </div>
                      <pre className="text-xs font-mono bg-muted/50 p-3 rounded-lg whitespace-pre-wrap break-all leading-relaxed">
                        {selectedEntry.sql}
                      </pre>
                    </div>

                    {/* Synthesis */}
                    <div>
                      <div className="flex items-center gap-2 mb-2">
                        <Zap className="w-4 h-4 text-primary" />
                        <span className="text-sm font-medium">Synthèse</span>
                      </div>
                      <p className="text-sm bg-muted/50 p-3 rounded-lg leading-relaxed whitespace-pre-wrap break-words">
                        {selectedEntry.synthesis}
                      </p>
                    </div>

                    {/* Error */}
                    {selectedEntry.error && (
                      <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                        <p className="text-sm text-destructive">{selectedEntry.error}</p>
                      </div>
                    )}

                    {/* Results */}
                    {selectedEntry.rows && selectedEntry.rows.length > 0 && (
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Table className="w-4 h-4 text-primary" />
                            <span className="text-sm font-medium">Résultats</span>
                          </div>
                          <Badge variant="secondary" className="text-xs font-mono">
                            {selectedEntry.row_count} ligne{selectedEntry.row_count > 1 ? 's' : ''}
                          </Badge>
                        </div>
                        <div className="bg-muted/50 rounded-lg overflow-hidden">
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-border">
                                  {Object.keys(selectedEntry.rows[0]).map((key) => (
                                    <th
                                      key={key}
                                      className="text-left font-medium p-2 text-xs text-muted-foreground uppercase tracking-wider"
                                    >
                                      {key}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {selectedEntry.rows.slice(0, 10).map((row, i) => (
                                  <tr key={i} className="border-b border-border/50">
                                    {Object.values(row).map((value, j) => (
                                      <td key={j} className="p-2 font-mono text-xs">
                                        {String(value ?? '-')}
                                      </td>
                                    ))}
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                          {selectedEntry.rows.length > 10 && (
                            <p className="text-xs text-muted-foreground text-center py-2 border-t border-border">
                              ... et {selectedEntry.rows.length - 10} autres lignes
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </ScrollArea>
              ) : (
                <div className="flex flex-col items-center justify-center h-full py-12">
                  <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center mb-4">
                    <History className="w-6 h-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Sélectionnez une entrée pour voir les détails
                  </p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
