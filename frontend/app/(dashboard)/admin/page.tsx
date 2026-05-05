'use client'

import { useState, useEffect, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import {
  ShieldCheck,
  Users,
  FileText,
  Plus,
  RefreshCw,
  Trash2,
  UserCheck,
  UserX,
  Loader2,
  CheckCircle2,
  XCircle,
  Eye,
  EyeOff,
  AlertCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { useAuth } from '@/lib/auth-context'
import { useT } from '@/lib/i18n'
import { getUsers, createUser, updateUserStatus, deleteUser, getAuditLogs, ApiError } from '@/lib/api'
import type { AdminUser, AuditLogEntry } from '@/lib/types'
import { cn } from '@/lib/utils'

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

const SHOW_ACTIVITY_LOGS = false

export default function AdminPage() {
  const t = useT()
  const router = useRouter()
  const { user: currentUser } = useAuth()
  
  const [users, setUsers] = useState<AdminUser[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([])
  const [isLoadingUsers, setIsLoadingUsers] = useState(true)
  const [isLoadingLogs, setIsLoadingLogs] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Create user dialog state
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newIsAdmin, setNewIsAdmin] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Delete dialog state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [userToDelete, setUserToDelete] = useState<AdminUser | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  // Redirect non-admins
  useEffect(() => {
    if (currentUser && !currentUser.is_admin) {
      router.push('/')
    }
  }, [currentUser, router])

  const loadUsers = useCallback(async () => {
    setIsLoadingUsers(true)
    try {
      const data = await getUsers()
      setUsers(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      }
    } finally {
      setIsLoadingUsers(false)
    }
  }, [])

  const loadAuditLogs = useCallback(async () => {
    if (!SHOW_ACTIVITY_LOGS) {
      setAuditLogs([])
      setIsLoadingLogs(false)
      return
    }
    setIsLoadingLogs(true)
    try {
      const data = await getAuditLogs(300)
      setAuditLogs(data)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      }
    } finally {
      setIsLoadingLogs(false)
    }
  }, [])

  useEffect(() => {
    if (currentUser?.is_admin) {
      loadUsers()
      if (SHOW_ACTIVITY_LOGS) {
        loadAuditLogs()
      }
    }
  }, [currentUser, loadUsers, loadAuditLogs])

  const handleCreateUser = async () => {
    if (!newUsername.trim() || !newPassword.trim()) return

    setIsCreating(true)
    setCreateError(null)

    try {
      await createUser(newUsername.trim(), newPassword, newIsAdmin)
      await loadUsers()
      if (SHOW_ACTIVITY_LOGS) {
        await loadAuditLogs()
      }
      setCreateDialogOpen(false)
      setNewUsername('')
      setNewPassword('')
      setNewIsAdmin(false)
    } catch (err) {
      if (err instanceof ApiError) {
        setCreateError(err.detail)
      } else {
        setCreateError(t('admin.error_create'))
      }
    } finally {
      setIsCreating(false)
    }
  }

  const handleToggleUserStatus = async (user: AdminUser) => {
    try {
      await updateUserStatus(user.id, !user.is_active)
      await loadUsers()
      if (SHOW_ACTIVITY_LOGS) {
        await loadAuditLogs()
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      }
    }
  }

  const handleDeleteUser = async () => {
    if (!userToDelete) return

    setIsDeleting(true)
    try {
      await deleteUser(userToDelete.id)
      await loadUsers()
      if (SHOW_ACTIVITY_LOGS) {
        await loadAuditLogs()
      }
      setDeleteDialogOpen(false)
      setUserToDelete(null)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail)
      }
    } finally {
      setIsDeleting(false)
    }
  }

  const confirmDelete = (user: AdminUser) => {
    setUserToDelete(user)
    setDeleteDialogOpen(true)
  }

  if (!currentUser?.is_admin) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 text-destructive mx-auto mb-4" />
          <p className="text-lg font-medium">{t('admin.access_denied')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="shrink-0 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="px-6 py-4">
          <h1 className="text-2xl font-bold tracking-tight">{t('admin.title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {t('admin.subtitle')}
          </p>
        </div>
      </header>

      {/* Error Banner */}
      {error && (
        <div className="mx-6 mt-4 p-4 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive flex items-center gap-3">
          <XCircle className="w-5 h-5 shrink-0" />
          <p className="text-sm font-medium">{error}</p>
          <button onClick={() => setError(null)} className="ml-auto text-destructive/70 hover:text-destructive">
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 overflow-auto p-6">
        <Tabs defaultValue="users" className="h-full flex flex-col">
          <TabsList className={cn("shrink-0 grid w-full max-w-md", SHOW_ACTIVITY_LOGS ? "grid-cols-2" : "grid-cols-1")}>
            <TabsTrigger value="users" className="gap-2">
              <Users className="w-4 h-4" />
              {t('admin.tab_users')}
            </TabsTrigger>
            {SHOW_ACTIVITY_LOGS && (
              <TabsTrigger value="logs" className="gap-2">
                <FileText className="w-4 h-4" />
                {t('admin.tab_logs')}
              </TabsTrigger>
            )}
          </TabsList>

          {/* Users Tab */}
          <TabsContent value="users" className="flex-1 mt-6">
            <Card className="h-full flex flex-col">
              <CardHeader className="shrink-0">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <Users className="w-5 h-5 text-primary" />
                      {t('admin.users_management')}
                    </CardTitle>
                    <CardDescription>
                      {users.length} {users.length > 1 ? t('admin.user_count_many') : t('admin.user_count_one')}
                    </CardDescription>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={loadUsers} disabled={isLoadingUsers}>
                      <RefreshCw className={cn('w-4 h-4 mr-2', isLoadingUsers && 'animate-spin')} />
                      {t('admin.refresh')}
                    </Button>
                    <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
                      <DialogTrigger asChild>
                        <Button size="sm">
                          <Plus className="w-4 h-4 mr-2" />
                          {t('admin.create')}
                        </Button>
                      </DialogTrigger>
                      <DialogContent>
                        <DialogHeader>
                          <DialogTitle>{t('admin.create_user')}</DialogTitle>
                          <DialogDescription>
                            {t('admin.create_desc')}
                          </DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-4">
                          {createError && (
                            <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20 text-destructive text-sm">
                              {createError}
                            </div>
                          )}
                          <div className="space-y-2">
                            <Label htmlFor="new-username">{t('admin.username')}</Label>
                            <Input
                              id="new-username"
                              value={newUsername}
                              onChange={(e) => setNewUsername(e.target.value)}
                              placeholder={t('admin.username_ph')}
                              minLength={3}
                              maxLength={64}
                            />
                          </div>
                          <div className="space-y-2">
                            <Label htmlFor="new-password">{t('admin.password')}</Label>
                            <div className="relative">
                              <Input
                                id="new-password"
                                type={showNewPassword ? 'text' : 'password'}
                                value={newPassword}
                                onChange={(e) => setNewPassword(e.target.value)}
                                placeholder="••••••••"
                                minLength={6}
                                maxLength={128}
                                className="pr-10"
                              />
                              <button
                                type="button"
                                onClick={() => setShowNewPassword(!showNewPassword)}
                                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                              >
                                {showNewPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                              </button>
                            </div>
                          </div>
                          <div className="flex items-center justify-between">
                            <Label htmlFor="new-admin" className="cursor-pointer">
                              {t('admin.is_admin')}
                            </Label>
                            <Switch
                              id="new-admin"
                              checked={newIsAdmin}
                              onCheckedChange={setNewIsAdmin}
                            />
                          </div>
                        </div>
                        <DialogFooter>
                          <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
                            {t('admin.cancel')}
                          </Button>
                          <Button
                            onClick={handleCreateUser}
                            disabled={isCreating || !newUsername.trim() || newPassword.length < 6}
                          >
                            {isCreating ? (
                              <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                {t('admin.creating')}
                              </>
                            ) : (
                              t('admin.create')
                            )}
                          </Button>
                        </DialogFooter>
                      </DialogContent>
                    </Dialog>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="flex-1 overflow-hidden p-0">
                <ScrollArea className="h-full">
                  {isLoadingUsers ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                  ) : users.length > 0 ? (
                    <div className="divide-y divide-border">
                      {users.map((user) => (
                        <div
                          key={user.id}
                          className="flex items-center justify-between p-4 hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <div
                              className={cn(
                                'w-10 h-10 rounded-full flex items-center justify-center shrink-0',
                                user.is_active ? 'bg-primary/10' : 'bg-muted'
                              )}
                            >
                              <span
                                className={cn(
                                  'text-sm font-medium',
                                  user.is_active ? 'text-primary' : 'text-muted-foreground'
                                )}
                              >
                                {user.username.charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div>
                              <div className="flex items-center gap-2">
                                <p className="font-medium">{user.username}</p>
                                {user.is_admin && (
                                  <Badge variant="secondary" className="text-xs">
                                    {t('admin.role_admin')}
                                  </Badge>
                                )}
                                {!user.is_active && (
                                  <Badge variant="outline" className="text-xs text-muted-foreground">
                                    {t('admin.role_suspended')}
                                  </Badge>
                                )}
                              </div>
                              {user.created_at && (
                                <p className="text-xs text-muted-foreground">
                                  {t('admin.created_on')} {formatDate(user.created_at)}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleToggleUserStatus(user)}
                              disabled={user.id === currentUser?.id}
                              title={user.is_active ? t('admin.suspend') : t('admin.activate')}
                            >
                              {user.is_active ? (
                                <UserX className="w-4 h-4 text-status-warning" />
                              ) : (
                                <UserCheck className="w-4 h-4 text-status-success" />
                              )}
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => confirmDelete(user)}
                              disabled={user.id === currentUser?.id}
                              title={t('admin.delete')}
                            >
                              <Trash2 className="w-4 h-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12">
                      <Users className="w-12 h-12 text-muted-foreground mb-4" />
                      <p className="text-muted-foreground">{t('admin.no_users')}</p>
                    </div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Logs Tab */}
          {SHOW_ACTIVITY_LOGS && (
          <TabsContent value="logs" className="flex-1 mt-6">
            <Card className="h-full flex flex-col">
              <CardHeader className="shrink-0">
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg flex items-center gap-2">
                      <FileText className="w-5 h-5 text-primary" />
                      {t('admin.logs_title')}
                    </CardTitle>
                    <CardDescription>
                      {auditLogs.length} {auditLogs.length > 1 ? t('admin.logs_count_many') : t('admin.logs_count_one')}
                    </CardDescription>
                  </div>
                  <Button variant="outline" size="sm" onClick={loadAuditLogs} disabled={isLoadingLogs}>
                    <RefreshCw className={cn('w-4 h-4 mr-2', isLoadingLogs && 'animate-spin')} />
                    {t('admin.refresh')}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="flex-1 overflow-hidden p-0">
                <ScrollArea className="h-full">
                  {isLoadingLogs ? (
                    <div className="flex items-center justify-center py-12">
                      <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    </div>
                  ) : auditLogs.length > 0 ? (
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="sticky top-0 bg-card border-b border-border">
                          <tr>
                            <th className="text-left font-medium p-3 text-xs text-muted-foreground uppercase tracking-wider">
                              {t('admin.col_date')}
                            </th>
                            <th className="text-left font-medium p-3 text-xs text-muted-foreground uppercase tracking-wider">
                              {t('admin.col_user')}
                            </th>
                            <th className="text-left font-medium p-3 text-xs text-muted-foreground uppercase tracking-wider">
                              {t('admin.col_action')}
                            </th>
                            <th className="text-left font-medium p-3 text-xs text-muted-foreground uppercase tracking-wider">
                              {t('admin.col_status')}
                            </th>
                            <th className="text-left font-medium p-3 text-xs text-muted-foreground uppercase tracking-wider">
                              {t('admin.col_details')}
                            </th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/50">
                          {auditLogs.map((log) => (
                            <tr key={log.id} className="hover:bg-muted/30">
                              <td className="p-3 text-xs text-muted-foreground whitespace-nowrap">
                                {formatDate(log.created_at)}
                              </td>
                              <td className="p-3 font-medium whitespace-nowrap">
                                {log.username || '-'}
                              </td>
                              <td className="p-3">
                                <Badge variant="outline" className="font-mono text-xs">
                                  {log.action}
                                </Badge>
                              </td>
                              <td className="p-3">
                                {log.success ? (
                                  <CheckCircle2 className="w-4 h-4 text-status-success" />
                                ) : (
                                  <XCircle className="w-4 h-4 text-destructive" />
                                )}
                              </td>
                              <td className="p-3 text-xs text-muted-foreground max-w-xs truncate">
                                {log.details || '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-12">
                      <FileText className="w-12 h-12 text-muted-foreground mb-4" />
                      <p className="text-muted-foreground">{t('admin.no_logs')}</p>
                    </div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          </TabsContent>
          )}
        </Tabs>
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('admin.delete_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('admin.delete_confirm_pre')}{' '}
              <strong>{userToDelete?.username}</strong> {t('admin.delete_confirm_post')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('admin.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteUser}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={isDeleting}
            >
              {isDeleting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  {t('admin.deleting')}
                </>
              ) : (
                t('admin.delete')
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
