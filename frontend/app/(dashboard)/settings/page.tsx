'use client'

import { useState, useEffect } from 'react'
import { Settings, Database, Gauge, Clock, Globe, Eye, EyeOff, Save, RotateCcw, Loader2, CheckCircle2, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAppData } from '@/components/app-shell'
import { updateSettings, ApiError } from '@/lib/api'
import type { RuntimeSettings } from '@/lib/types'
import { cn } from '@/lib/utils'

type NotificationType = 'success' | 'error' | null

export default function SettingsPage() {
  const { settings, refreshSettings, refreshAll } = useAppData()
  const [formData, setFormData] = useState<RuntimeSettings | null>(null)
  const [showPassword, setShowPassword] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [notification, setNotification] = useState<{ type: NotificationType; message: string } | null>(null)

  // Initialize form with settings data
  useEffect(() => {
    if (settings) {
      setFormData({ ...settings })
    }
  }, [settings])

  const handleInputChange = (field: keyof RuntimeSettings, value: string | number) => {
    if (!formData) return
    setFormData({ ...formData, [field]: value })
  }

  const handleReset = () => {
    if (settings) {
      setFormData({ ...settings })
      setNotification(null)
    }
  }

  const handleSave = async () => {
    if (!formData) return

    setIsSaving(true)
    setNotification(null)

    try {
      await updateSettings(formData)
      await refreshAll()
      setNotification({ type: 'success', message: 'Paramètres enregistrés avec succès' })
    } catch (err) {
      if (err instanceof ApiError) {
        setNotification({ type: 'error', message: err.detail })
      } else {
        setNotification({ type: 'error', message: 'Erreur lors de l\'enregistrement des paramètres' })
      }
    } finally {
      setIsSaving(false)
    }
  }

  if (!formData) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="px-6 py-4">
          <h1 className="text-2xl font-bold tracking-tight">Paramètres</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configurez les paramètres de l&apos;application
          </p>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 overflow-auto p-6">
        <div className="max-w-4xl mx-auto space-y-6">
          {/* Notification */}
          {notification && (
            <div
              className={cn(
                'flex items-center gap-3 p-4 rounded-lg border',
                notification.type === 'success'
                  ? 'bg-status-success/10 border-status-success/20 text-status-success'
                  : 'bg-destructive/10 border-destructive/20 text-destructive'
              )}
            >
              {notification.type === 'success' ? (
                <CheckCircle2 className="w-5 h-5 shrink-0" />
              ) : (
                <XCircle className="w-5 h-5 shrink-0" />
              )}
              <p className="text-sm font-medium">{notification.message}</p>
            </div>
          )}

          {/* Oracle Connection */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Database className="w-5 h-5 text-primary" />
                Connexion Oracle
              </CardTitle>
              <CardDescription>
                Paramètres de connexion à la base de données Oracle
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Oracle User */}
                <div className="space-y-2">
                  <Label htmlFor="oracle_user">Utilisateur Oracle</Label>
                  <Input
                    id="oracle_user"
                    value={formData.oracle_user}
                    onChange={(e) => handleInputChange('oracle_user', e.target.value)}
                    placeholder="SYSTEM"
                  />
                </div>

                {/* Oracle Password */}
                <div className="space-y-2">
                  <Label htmlFor="oracle_password">Mot de passe Oracle</Label>
                  <div className="relative">
                    <Input
                      id="oracle_password"
                      type={showPassword ? 'text' : 'password'}
                      value={formData.oracle_password}
                      onChange={(e) => handleInputChange('oracle_password', e.target.value)}
                      placeholder="••••••••"
                      className="pr-10"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Oracle Host */}
                <div className="space-y-2">
                  <Label htmlFor="oracle_host">Hôte</Label>
                  <Input
                    id="oracle_host"
                    value={formData.oracle_host}
                    onChange={(e) => handleInputChange('oracle_host', e.target.value)}
                    placeholder="192.168.1.100"
                  />
                </div>

                {/* Oracle Port */}
                <div className="space-y-2">
                  <Label htmlFor="oracle_port">Port Oracle</Label>
                  <Input
                    id="oracle_port"
                    type="number"
                    value={formData.oracle_port}
                    onChange={(e) => handleInputChange('oracle_port', parseInt(e.target.value) || 1521)}
                    placeholder="1521"
                    min={1}
                    max={65535}
                  />
                </div>

                {/* Oracle Service */}
                <div className="space-y-2">
                  <Label htmlFor="oracle_service">Service Oracle</Label>
                  <Input
                    id="oracle_service"
                    value={formData.oracle_service}
                    onChange={(e) => handleInputChange('oracle_service', e.target.value)}
                    placeholder="ORCLPDB1"
                  />
                </div>

                {/* Oracle Table */}
                <div className="space-y-2">
                  <Label htmlFor="oracle_table">Table Oracle interrogée</Label>
                  <Input
                    id="oracle_table"
                    value={formData.oracle_table}
                    onChange={(e) => handleInputChange('oracle_table', e.target.value)}
                    placeholder="SMART2DSECU.UNIFIED_AUDIT_DATA"
                    className="font-mono text-sm"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Analysis Settings */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Gauge className="w-5 h-5 text-primary" />
                Analyse
              </CardTitle>
              <CardDescription>
                Paramètres d&apos;analyse des requêtes
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-w-sm">
                <Label htmlFor="max_results">Résultats max par requête</Label>
                <Input
                  id="max_results"
                  type="number"
                  value={formData.max_results}
                  onChange={(e) => handleInputChange('max_results', parseInt(e.target.value) || 100)}
                  placeholder="100"
                  min={1}
                  max={10000}
                />
                <p className="text-xs text-muted-foreground">
                  Nombre maximum de lignes retournées par requête
                </p>
              </div>
            </CardContent>
          </Card>

          {/* Session & Logging */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Clock className="w-5 h-5 text-primary" />
                Session et journalisation
              </CardTitle>
              <CardDescription>
                Paramètres de session et de conservation des logs
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Session Duration */}
                <div className="space-y-2">
                  <Label htmlFor="session_duration">Durée de session (minutes)</Label>
                  <Input
                    id="session_duration"
                    type="number"
                    value={formData.session_duration}
                    onChange={(e) => handleInputChange('session_duration', parseInt(e.target.value) || 60)}
                    placeholder="60"
                    min={5}
                    max={1440}
                  />
                  <p className="text-xs text-muted-foreground">
                    Durée d&apos;inactivité avant déconnexion automatique
                  </p>
                </div>

                {/* Logs Retention */}
                <div className="space-y-2">
                  <Label htmlFor="logs_retention">Conservation des logs (jours)</Label>
                  <Input
                    id="logs_retention"
                    type="number"
                    value={formData.logs_retention}
                    onChange={(e) => handleInputChange('logs_retention', parseInt(e.target.value) || 30)}
                    placeholder="30"
                    min={1}
                    max={365}
                  />
                  <p className="text-xs text-muted-foreground">
                    Durée de conservation des logs d&apos;activité
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Interface */}
          <Card>
            <CardHeader>
              <CardTitle className="text-lg flex items-center gap-2">
                <Globe className="w-5 h-5 text-primary" />
                Interface
              </CardTitle>
              <CardDescription>
                Paramètres d&apos;affichage de l&apos;interface
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-w-sm">
                <Label htmlFor="interface_lang">Langue de l&apos;interface</Label>
                <Select
                  value={formData.interface_lang}
                  onValueChange={(value) => handleInputChange('interface_lang', value as 'fr' | 'en')}
                >
                  <SelectTrigger id="interface_lang">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="fr">Français</SelectItem>
                    <SelectItem value="en">English</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-4">
            <Button variant="outline" onClick={handleReset} disabled={isSaving}>
              <RotateCcw className="w-4 h-4 mr-2" />
              Réinitialiser
            </Button>
            <Button onClick={handleSave} disabled={isSaving}>
              {isSaving ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Enregistrement...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  Sauvegarder
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
