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
  Shield,
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
import type { OracleStatus } from '@/lib/types'
import { cn } from '@/lib/utils'

const navItems = [
  { title: 'Accueil', href: '/', icon: Home },
  { title: 'Historique', href: '/history', icon: History },
  { title: 'Paramètres', href: '/settings', icon: Settings },
]

const adminItems = [
  { title: 'Administration', href: '/admin', icon: ShieldCheck },
]

interface AppSidebarProps {
  oracleStatus: OracleStatus
}

function OracleStatusBadge({ status }: { status: OracleStatus }) {
  const { state } = useSidebar()
  const isCollapsed = state === 'collapsed'

  const statusConfig = {
    connected: {
      label: 'Oracle connecté',
      color: 'bg-status-success',
      textColor: 'text-status-success',
    },
    inactive: {
      label: 'Oracle inactif',
      color: 'bg-status-warning',
      textColor: 'text-status-warning',
    },
    disconnected: {
      label: 'Oracle déconnecté',
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

export function AppSidebar({ oracleStatus }: AppSidebarProps) {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const { state } = useSidebar()
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
              <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
                <Shield className="w-4 h-4 text-primary" />
              </div>
              <span className="font-semibold text-sm tracking-tight truncate">ASKSMART</span>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent className="py-2">
        <SidebarGroup>
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
                  {user?.is_admin ? 'Administrateur' : 'Utilisateur'}
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
              <span className="ml-2">Déconnexion</span>
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
