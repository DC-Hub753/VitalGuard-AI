import { useMemo, useState, type FormEvent } from 'react';
import { LayoutGrid, Table2, UserPlus, X } from 'lucide-react';
import { Shell } from '../components/layout/Shell.tsx';
import { PageHeader } from '../components/ui/Primitives.tsx';
import { EmptyState } from '../components/ui/States.tsx';
import { FilterBar, useFilterState } from '../components/patients/FilterBar.tsx';
import { PatientRows, PatientCards } from '../components/patients/Directory.tsx';
import { useSimulation } from '../store/useSimulation.ts';
import { useOptionalAuth } from '../store/AuthContext.tsx';

const PAGE = 6;

export function PatientsPage() {
  const { patients, risks, latest, createPatient } = useSimulation();
  const auth = useOptionalAuth();
  const [filters, setFilters] = useFilterState();
  const [view, setView] = useState<'table' | 'cards'>('table');
  const [page, setPage] = useState(0);

  // Admission Modal State
  const [showModal, setShowModal] = useState(false);
  const [newId, setNewId] = useState('');
  const [newName, setNewName] = useState('');
  const [newSex, setNewSex] = useState<'M' | 'F' | 'U'>('M');
  const [newWard, setNewWard] = useState('General Ward');
  const [newBed, setNewBed] = useState('');
  const [modalError, setModalError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const canAdmit = auth?.role === 'admin' || auth?.role === 'clinician';

  const rows = useMemo(() => {
    const out = patients
      .filter((p) => !filters.q || p.id.toLowerCase().includes(filters.q.toLowerCase()) || (p.displayName && p.displayName.toLowerCase().includes(filters.q.toLowerCase())))
      .filter((p) => filters.ward === 'All' || p.ward === filters.ward)
      .filter((p) => filters.level === 'All' || risks[p.id]?.level === filters.level.toLowerCase());
    out.sort((a, b) => {
      if (filters.sort === 'spo2') return (latest[a.id]?.spo2 ?? 0) - (latest[b.id]?.spo2 ?? 0);
      if (filters.sort === 'hr') return (latest[b.id]?.heartRate ?? 0) - (latest[a.id]?.heartRate ?? 0);
      if (filters.sort === 'updated') return +new Date(b.updatedAt) - +new Date(a.updatedAt);
      return (risks[b.id]?.score ?? 0) - (risks[a.id]?.score ?? 0);
    });
    return out;
  }, [patients, risks, latest, filters]);

  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const safePage = Math.min(page, pages - 1);
  const slice = rows.slice(safePage * PAGE, safePage * PAGE + PAGE);
  const onFilter = (v: typeof filters) => { setFilters(v); setPage(0); };

  async function handleAdmit(e: FormEvent) {
    e.preventDefault();
    setModalError('');
    if (!newId.trim() || !newName.trim()) {
      setModalError('Patient ID and Display Name are required.');
      return;
    }
    setSubmitting(true);
    try {
      await createPatient({
        patient_id: newId.trim().toUpperCase(),
        display_name: newName.trim(),
        sex: newSex,
        ward: newWard,
        bed: newBed.trim() || 'Bed 1',
      });
      setShowModal(false);
      setNewId('');
      setNewName('');
      setNewBed('');
    } catch (err) {
      setModalError(err instanceof Error ? err.message : 'Could not admit patient');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Shell title="Patients" subtitle="Authoritative monitored patient directory">
      <PageHeader
        eyebrow={`Census · ${patients.length} patients`}
        title="Patients"
        subtitle="Monitor persistent patient state, vital trends, and risk signals across wards."
        crumbs={[{ label: 'Dashboard', to: '/dashboard' }, { label: 'Patients' }]}
        actions={(
          <div className="flex items-center gap-2">
            {canAdmit && (
              <button
                onClick={() => setShowModal(true)}
                className="btn-primary !py-1.5 !text-xs flex items-center gap-1.5"
              >
                <UserPlus size={14} /> Admit Patient
              </button>
            )}
            <div className="inline-flex rounded-xl border border-slate-200 dark:border-slate-700 overflow-hidden bg-white dark:bg-slate-900" role="group" aria-label="View mode">
              <button onClick={() => setView('table')} aria-pressed={view === 'table'} aria-label="Table view" className={`p-2 transition-all ${view === 'table' ? 'text-white' : 'text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800'}`} style={view === 'table' ? { background: 'linear-gradient(135deg,#0f766e,#0891b2)' } : undefined}><Table2 size={16} /></button>
              <button onClick={() => setView('cards')} aria-pressed={view === 'cards'} aria-label="Card view" className={`p-2 transition-all ${view === 'cards' ? 'text-white' : 'text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800'}`} style={view === 'cards' ? { background: 'linear-gradient(135deg,#0f766e,#0891b2)' } : undefined}><LayoutGrid size={16} /></button>
            </div>
          </div>
        )}
      />

      <div className="mt-4"><FilterBar value={filters} onChange={onFilter} resultCount={rows.length} /></div>

      {slice.length === 0 ? (
        <div className="mt-4"><EmptyState title="No patients match these filters." hint="Adjust search or clear filters." /></div>
      ) : view === 'table' ? (
        <div className="card overflow-hidden mt-4 !p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[920px]">
              <thead className="table-head sticky top-0">
                <tr>
                  <th scope="col" className="!pl-5">Patient</th><th scope="col">Age / Sex</th><th scope="col">Ward / Bed</th>
                  <th scope="col">Risk</th><th scope="col" className="text-right">NEWS2</th><th scope="col" className="text-right">SpO₂</th>
                  <th scope="col" className="text-right">HR</th><th scope="col">Trend</th><th scope="col">Updated</th>
                  <th scope="col"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <PatientRows slice={slice} risks={risks} latest={latest} />
            </table>
          </div>
        </div>
      ) : <PatientCards slice={slice} risks={risks} latest={latest} />}

      <div className="mt-4 flex items-center gap-2 text-sm">
        <button disabled={safePage === 0} onClick={() => setPage((p) => Math.max(0, p - 1))} className="btn-secondary !py-1.5">Prev</button>
        <span aria-live="polite" className="text-xs text-slate-500 tabular-nums">Page {safePage + 1} of {pages}</span>
        <button disabled={safePage + 1 >= pages} onClick={() => setPage((p) => p + 1)} className="btn-secondary !py-1.5">Next</button>
      </div>

      {/* Patient Admission Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800">
              <h2 className="text-lg font-bold">Admit New Patient</h2>
              <button onClick={() => setShowModal(false)} className="icon-btn text-slate-400 hover:text-slate-600">
                <X size={18} />
              </button>
            </div>
            <form onSubmit={handleAdmit} className="mt-4 space-y-3">
              <div>
                <label className="block text-xs font-semibold mb-1">Patient Identifier (ID)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. P-SIM-009"
                  value={newId}
                  onChange={(e) => setNewId(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Full Legal Display Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Margaret Thorne"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold mb-1">Biological Sex</label>
                  <select
                    value={newSex}
                    onChange={(e) => setNewSex(e.target.value as any)}
                    className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="U">Unspecified</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold mb-1">Ward Department</label>
                  <select
                    value={newWard}
                    onChange={(e) => setNewWard(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-teal-500"
                  >
                    <option value="General Ward">General Ward</option>
                    <option value="ICU">ICU</option>
                    <option value="Emergency">Emergency</option>
                    <option value="Cardiology">Cardiology</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-semibold mb-1">Bed Assignment</label>
                <input
                  type="text"
                  placeholder="e.g. B-12"
                  value={newBed}
                  onChange={(e) => setNewBed(e.target.value)}
                  className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 px-3 py-2 text-sm outline-none focus:border-teal-500"
                />
              </div>

              {modalError && (
                <p className="text-xs text-rose-600 bg-rose-50 dark:bg-rose-950/50 p-2.5 rounded-lg border border-rose-200 dark:border-rose-900">
                  {modalError}
                </p>
              )}

              <div className="flex justify-end gap-2 pt-3">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="btn-secondary !py-2 !text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary !py-2 !text-xs"
                >
                  {submitting ? 'Admitting…' : 'Admit Patient'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </Shell>
  );
}

