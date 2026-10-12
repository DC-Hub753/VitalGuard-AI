import { useEffect, useState } from 'react';
import { useAuth } from '../../store/AuthContext.tsx';
import { APP_CONFIG } from '../../services/config.ts';
import { SectionCard } from '../ui/Primitives.tsx';
import { ShieldCheck, UserPlus, Users, History, AlertCircle } from 'lucide-react';

interface UserRecord {
  id: number;
  username: string;
  role: string;
  full_name: string;
  active: boolean;
  created_at: string;
}

interface AuditRecord {
  id: number;
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  created_at: string;
  details: Record<string, unknown>;
}

export function AdminControlPanel() {
  const { hasRole, token } = useAuth();
  const isAdmin = hasRole(['admin']);

  const [users, setUsers] = useState<UserRecord[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditRecord[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [loadingAudit, setLoadingAudit] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New user form state
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newFullName, setNewFullName] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'clinician' | 'nurse'>('nurse');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    if (!isAdmin || !token) return;
    loadUsers();
    loadAudit();
  }, [isAdmin, token]);

  async function loadUsers() {
    setLoadingUsers(true);
    try {
      const res = await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUsers(data);
      }
    } catch {
      // Ignore network errors in demo
    } finally {
      setLoadingUsers(false);
    }
  }

  async function loadAudit() {
    setLoadingAudit(true);
    try {
      const res = await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/admin/audit?limit=15`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAuditEvents(data.items || []);
      }
    } catch {
      // Ignore network errors in demo
    } finally {
      setLoadingAudit(false);
    }
  }

  async function handleCreateUser(e: React.FormEvent) {
    e.preventDefault();
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      const res = await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/admin/users`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          username: newUsername.trim(),
          password: newPassword,
          role: newRole,
          full_name: newFullName.trim(),
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to create user');
      }
      setNewUsername('');
      setNewPassword('');
      setNewFullName('');
      loadUsers();
      loadAudit();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error creating user');
    } finally {
      setCreating(false);
    }
  }

  async function toggleUserStatus(userId: number, currentStatus: boolean) {
    if (!token) return;
    try {
      const res = await fetch(`${APP_CONFIG.apiBaseUrl}/api/v1/admin/users/${userId}/status`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ active: !currentStatus }),
      });
      if (res.ok) {
        loadUsers();
        loadAudit();
      }
    } catch {
      // Ignore network errors in demo
    }
  }

  if (!isAdmin) {
    return (
      <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5">
        <div className="flex items-center gap-2.5 text-slate-400 text-xs">
          <ShieldCheck size={16} className="text-slate-500" />
          <span>Administrative user management and immutable audit logs require the <strong>Admin</strong> role.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SectionCard eyebrow="Security" title="Role-Based Access Control" hint="Admin user directory" label="RBAC">
        <div className="flex items-center justify-between pb-3 border-b border-slate-700/60">
          <div className="flex items-center gap-2">
            <Users size={18} className="text-amber-400" />
            <h3 className="text-sm font-semibold text-slate-200">Authorized Clinical Users</h3>
          </div>
          <button
            type="button"
            onClick={loadUsers}
            className="text-xs text-cyan-400 hover:underline"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="mt-3 flex items-center gap-2 text-xs text-rose-300 bg-rose-950/50 p-2.5 rounded-lg border border-rose-900">
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 text-slate-400">
                <th className="py-2">User</th>
                <th className="py-2">Role</th>
                <th className="py-2">Status</th>
                <th className="py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {users.map((u) => (
                <tr key={u.id} className="hover:bg-slate-800/20">
                  <td className="py-2.5 font-medium text-slate-200">
                    <div>{u.full_name || u.username}</div>
                    <div className="text-[10px] text-slate-400">@{u.username}</div>
                  </td>
                  <td className="py-2.5">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      u.role === 'admin' ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30' :
                      u.role === 'clinician' ? 'bg-teal-500/10 text-teal-400 border border-teal-500/30' :
                      'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30'
                    }`}>
                      {u.role}
                    </span>
                  </td>
                  <td className="py-2.5">
                    <span className={`inline-flex items-center gap-1 text-[11px] ${u.active ? 'text-emerald-400' : 'text-rose-400'}`}>
                      <span className={`h-1.5 w-1.5 rounded-full ${u.active ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                      {u.active ? 'Active' : 'Disabled'}
                    </span>
                  </td>
                  <td className="py-2.5 text-right">
                    <button
                      type="button"
                      onClick={() => toggleUserStatus(u.id, u.active)}
                      className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium"
                    >
                      {u.active ? 'Disable' : 'Enable'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <form onSubmit={handleCreateUser} className="mt-4 pt-4 border-t border-slate-800/80 space-y-3">
          <p className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
            <UserPlus size={14} className="text-cyan-400" /> Provision Authorized Account
          </p>
          <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-2">
            <input
              placeholder="Username"
              required
              value={newUsername}
              onChange={(e) => setNewUsername(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-500"
            />
            <input
              type="password"
              placeholder="Password (min 8 chars)"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-500"
            />
            <input
              placeholder="Full Name"
              value={newFullName}
              onChange={(e) => setNewFullName(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-500"
            />
            <select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value as any)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-cyan-500"
            >
              <option value="nurse">Nurse</option>
              <option value="clinician">Clinician</option>
              <option value="admin">Admin</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="px-3 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold disabled:opacity-60"
          >
            {creating ? 'Provisioning…' : 'Create User'}
          </button>
        </form>
      </SectionCard>

      <SectionCard eyebrow="Audit" title="Security & Mutation Audit Log" hint="Append-only event ledger" label="Ledger">
        <div className="flex items-center justify-between pb-3 border-b border-slate-700/60">
          <div className="flex items-center gap-2">
            <History size={18} className="text-cyan-400" />
            <h3 className="text-sm font-semibold text-slate-200">Recent Immutable Events</h3>
          </div>
          <button
            type="button"
            onClick={loadAudit}
            className="text-xs text-cyan-400 hover:underline"
          >
            Refresh
          </button>
        </div>

        <div className="mt-3 space-y-2 max-h-64 overflow-y-auto">
          {auditEvents.map((evt) => (
            <div key={evt.id} className="p-2.5 rounded-lg border border-slate-800 bg-slate-950/40 text-xs flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-slate-200 uppercase tracking-wider text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-cyan-300">
                    {evt.action}
                  </span>
                  <span className="text-slate-400">by <strong>{evt.actor}</strong></span>
                </div>
                <div className="text-[11px] text-slate-500 mt-1 truncate">
                  Target: {evt.entity_type} ({evt.entity_id})
                </div>
              </div>
              <span className="text-[10px] text-slate-500 whitespace-nowrap">
                {new Date(evt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
              </span>
            </div>
          ))}
          {auditEvents.length === 0 && (
            <p className="text-xs text-slate-500 text-center py-4">No audit events recorded yet.</p>
          )}
        </div>
      </SectionCard>
    </div>
  );
}
