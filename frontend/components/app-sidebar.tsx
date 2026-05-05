'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import {
  Home,
  History,
  Settings,
  ShieldCheck,
  LogOut,
  Menu,
  Database,
  Eye,
  EyeOff,
  MessageSquare,
} from 'lucide-react'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
  useSidebar,
} from '@/components/ui/sidebar'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useAuth } from '@/lib/auth-context'
import { useT } from '@/lib/i18n'
import type { OracleStatus, HistoryEntry } from '@/lib/types'
import { cn } from '@/lib/utils'

const navItemsBase = [
  { key: 'nav.home', href: '/', icon: Home },
  { key: 'nav.history', href: '/history', icon: History },
  { key: 'nav.settings', href: '/settings', icon: Settings },
]

const adminItemsBase = [
  { key: 'nav.admin', href: '/admin', icon: ShieldCheck },
]

interface AppSidebarProps {
  oracleStatus: OracleStatus
  showUsersColumn: boolean
  showTablesColumn: boolean
  showActionsColumn: boolean
  setShowUsersColumn: (show: boolean) => void
  setShowTablesColumn: (show: boolean) => void
  setShowActionsColumn: (show: boolean) => void
  recentHistory?: HistoryEntry[]
  onSelectHistory?: (entry: HistoryEntry) => void
}

function OracleStatusBadge({ status }: { status: OracleStatus }) {
  const { state } = useSidebar()
  const isCollapsed = state === 'collapsed'
  const t = useT()

  const statusConfig = {
    connected: {
      label: t('oracle.connected'),
      color: 'bg-status-success',
      textColor: 'text-status-success',
    },
    inactive: {
      label: t('oracle.inactive'),
      color: 'bg-status-warning',
      textColor: 'text-status-warning',
    },
    disconnected: {
      label: t('oracle.disconnected'),
      color: 'bg-status-error',
      textColor: 'text-status-error',
    },
  }

  const config = statusConfig[status]

  if (isCollapsed) {
    return (
      <div className="flex justify-center py-2">
        <div className={cn('w-2.5 h-2.5 rounded-full', config.color)} title={config.label} />
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 px-2 py-1.5 rounded-md bg-sidebar-accent/50">
      <Database className={cn('w-4 h-4', config.textColor)} />
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <div className={cn('w-2 h-2 rounded-full shrink-0', config.color)} />
        <span className="text-xs font-medium truncate">{config.label}</span>
      </div>
    </div>
  )
}

export function AppSidebar({
  oracleStatus,
  showUsersColumn,
  showTablesColumn,
  showActionsColumn,
  setShowUsersColumn,
  setShowTablesColumn,
  setShowActionsColumn,
  recentHistory = [],
  onSelectHistory,
}: AppSidebarProps) {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const { state } = useSidebar()
  const t = useT()
  const navItems = navItemsBase.map(i => ({ ...i, title: t(i.key) }))
  const adminItems = adminItemsBase.map(i => ({ ...i, title: t(i.key) }))
  const isCollapsed = state === 'collapsed'

  const handleLogout = async () => {
    await logout()
    window.location.href = '/login'
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="border-b border-sidebar-border">
        <div className="flex items-center gap-2 px-1 py-1">
          <SidebarTrigger className="shrink-0">
            <Menu className="w-4 h-4" />
          </SidebarTrigger>
          {!isCollapsed && (
            <div className="flex items-center gap-2 overflow-hidden">
              <span className="font-semibold text-sm tracking-tight truncate">ASKSMART</span>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent className="py-2 overflow-x-hidden">
        <SidebarGroup className="pt-0 pb-2">
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={pathname === item.href}
                    tooltip={item.title}
                  >
                    <Link href={item.href}>
                      <item.icon className="w-4 h-4" />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
              {user?.is_admin &&
                adminItems.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={pathname === item.href}
                      tooltip={item.title}
                    >
                      <Link href={item.href}>
                        <item.icon className="w-4 h-4" />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        {!isCollapsed && (
          <>
            <Separator className="mx-3 my-1 w-auto" />
            <div className="px-3 pb-1">
              <p className="px-1 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                {t('sidebar.columns')}
              </p>
              <div className="mt-1 space-y-1">
                <button
                  onClick={() => setShowUsersColumn(!showUsersColumn)}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-sidebar-accent/50',
                    showUsersColumn ? 'text-foreground' : 'text-muted-foreground'
                  )}
                >
                  <span>{t('sidebar.users')}</span>
                  {showUsersColumn ? <EyeOff className="h-3.5 w-3.5 text-muted-foreground" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={() => setShowTablesColumn(!showTablesColumn)}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-sidebar-accent/50',
                    showTablesColumn ? 'text-foreground' : 'text-muted-foreground'
                  )}
                >
                  <span>{t('sidebar.tables')}</span>
                  {showTablesColumn ? <EyeOff className="h-3.5 w-3.5 text-muted-foreground" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
                <button
                  onClick={() => setShowActionsColumn(!showActionsColumn)}
                  className={cn(
                    'flex w-full items-center justify-between rounded-md px-2 py-1.5 text-xs transition-colors hover:bg-sidebar-accent/50',
                    showActionsColumn ? 'text-foreground' : 'text-muted-foreground'
                  )}
                >
                  <span>{t('sidebar.actions')}</span>
                  {showActionsColumn ? <EyeOff className="h-3.5 w-3.5 text-muted-foreground" /> : <Eye className="h-3.5 w-3.5" />}
                </button>
              </div>
            </div>

            {recentHistory.length > 0 && (
              <>
                <Separator className="mx-3 my-1 w-auto" />
                <div className="flex-1 min-h-0 px-3 pb-1 flex flex-col">
                  <p className="px-1 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                    {t('sidebar.recent')}
                  </p>
                  <div className="mt-1 space-y-1 flex-1 min-h-0 overflow-y-auto overflow-x-hidden">
                    {recentHistory.map((entry, i) => (
                      <button
                        key={entry.id || i}
                        type="button"
                        onClick={() => onSelectHistory?.(entry)}
                        className="flex w-full items-start gap-1.5 rounded-md px-2 py-1.5 text-[11px] leading-4 text-muted-foreground bg-sidebar-accent/20 hover:bg-sidebar-accent/40 transition-colors text-left cursor-pointer"
                      >
                        <MessageSquare className="h-3 w-3 mt-0.5 shrink-0 text-primary/60" />
                        <span className="line-clamp-2">{entry.question}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border p-2 space-y-1.5">
        {!isCollapsed && (
          <>
            <div className="flex items-center gap-2 px-2 py-1 rounded-md bg-sidebar-accent/30">
              <div className="w-7 h-7 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                <span className="text-xs font-medium text-primary">
                  {user?.username?.charAt(0).toUpperCase() || '?'}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate">{user?.username}</p>
                <p className="text-[10px] text-muted-foreground">
                  {user?.is_admin ? t('sidebar.role_admin') : t('sidebar.role_user')}
                </p>
              </div>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="w-full justify-start text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            >
              <LogOut className="w-4 h-4" />
              <span className="ml-2">{t('nav.logout')}</span>
            </Button>
            <Separator className="my-0.5" />
          </>
        )}
        <OracleStatusBadge status={oracleStatus} />
        {isCollapsed && (
          <Button
            variant="ghost"
            size="icon"
            onClick={handleLogout}
            className={cn('mt-1 text-muted-foreground hover:text-destructive hover:bg-destructive/10', 'w-8 h-8 p-0')}
          >
            <LogOut className="w-4 h-4" />
          </Button>
        )}
      </SidebarFooter>
    </Sidebar>
  )
}
