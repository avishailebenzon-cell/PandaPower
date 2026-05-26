import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { env } from "@/lib/env";

export function IntegrationsPage() {
  const [showModal, setShowModal] = useState(false);
  const [formData, setFormData] = useState({ tenant_id: "", client_id: "", client_secret: "", target_mailbox: "" });

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["email-status"],
    queryFn: () => fetch(`${env.API_BASE_URL}/admin/email/status`).then(r => r.json()),
    refetchInterval: 5000,
  });

  const testMutation = useMutation({
    mutationFn: (data) =>
      fetch(`${env.API_BASE_URL}/admin/email/test-connection`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      }).then(r => r.json()),
    onSuccess: (result) => {
      if (result.ok) {
        alert(`✓ Connected as ${result.mailbox_address}\n${result.total_emails_count} total emails`);
        setShowModal(false);
      } else {
        alert(`✗ Error: ${result.error}`);
      }
    },
    onError: (error) => {
      alert(`✗ Error: ${error.message}`);
    },
  });

  const backfillMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/email/start-backfill`, { method: "POST", headers: { "Content-Type": "application/json" } })
        .then(r => r.json()),
    onSuccess: () => {
      alert("✓ Backfill started");
      refetchStatus();
    },
    onError: (error) => {
      alert(`✗ Error: ${error.message}`);
    },
  });

  const runNowMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/email/run-now`, { method: "POST", headers: { "Content-Type": "application/json" } })
        .then(r => r.json()),
    onSuccess: (result) => {
      alert(`✓ Processing complete\nEmails: ${result.total_processed ?? 0}\nCVs: ${result.cv_files_extracted ?? 0}`);
      refetchStatus();
    },
    onError: (error) => {
      alert(`✗ Error: ${error.message}`);
    },
  });

  return (
    <div className="p-8 max-w-4xl mx-auto bg-gray-900 min-h-screen" dir="rtl">
      <h1 className="text-2xl font-bold mb-8 text-white">אינטגרציות</h1>

      <div className="space-y-6">
        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700">
          <h2 className="text-lg font-semibold mb-4 text-white">חיבור דוא"ל של Azure</h2>
          <p className="text-sm text-white mb-4">סטטוס: <span className="font-mono">{status?.last_status || "Not configured"}</span></p>
          <button
            onClick={() => setShowModal(true)}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700"
          >
            Configure
          </button>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700">
          <h2 className="text-lg font-semibold mb-4 text-white">בקרת מילוי חוזר</h2>
          <p className="text-xs text-white mb-3">עיבוד מחדש של דוא"ל מתאריך מסוים</p>
          <button
            onClick={() => backfillMutation.mutate()}
            disabled={backfillMutation.isPending}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50"
          >
            {backfillMutation.isPending ? "בהתחלה..." : "התחל מילוי חוזר"}
          </button>
        </div>

        <div className="bg-gray-800 p-6 rounded-lg border border-gray-700">
          <h2 className="text-lg font-semibold mb-4 text-white">סטטוס חי</h2>
          <div className="grid grid-cols-4 gap-4 mb-4">
            <div className="p-3 bg-gray-700 rounded">
              <div className="text-xs text-white">סנכרון אחרון</div>
              <div className="text-sm font-semibold text-white">{status?.last_run_at ? new Date(status.last_run_at).toLocaleTimeString() : "—"}</div>
            </div>
            <div className="p-3 bg-gray-700 rounded">
              <div className="text-xs text-white">היום</div>
              <div className="text-sm font-semibold text-white">{status?.emails_processed_today || 0}</div>
            </div>
            <div className="p-3 bg-gray-700 rounded">
              <div className="text-xs text-gray-600">CVs Today</div>
              <div className="text-sm font-semibold">{status?.cv_files_extracted_today || 0}</div>
            </div>
            <div className="p-3 bg-gray-50 rounded">
              <div className="text-xs text-gray-600">Status</div>
              <div className="text-sm font-semibold text-green-600">Idle</div>
            </div>
          </div>
          <button
            onClick={() => runNowMutation.mutate()}
            disabled={runNowMutation.isPending}
            className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
          >
            {runNowMutation.isPending ? "Running..." : "Run Now"}
          </button>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white p-6 rounded-lg max-w-md w-full">
            <h3 className="text-lg font-semibold mb-4">Configure Azure Email</h3>
            <form onSubmit={(e) => {
              e.preventDefault();
              testMutation.mutate(formData);
            }}>
              <input
                type="text"
                placeholder="Tenant ID"
                value={formData.tenant_id}
                onChange={(e) => setFormData({ ...formData, tenant_id: e.target.value })}
                className="w-full border px-3 py-2 rounded mb-3 text-sm"
                required
              />
              <input
                type="text"
                placeholder="Client ID"
                value={formData.client_id}
                onChange={(e) => setFormData({ ...formData, client_id: e.target.value })}
                className="w-full border px-3 py-2 rounded mb-3 text-sm"
                required
              />
              <input
                type="password"
                placeholder="Client Secret"
                value={formData.client_secret}
                onChange={(e) => setFormData({ ...formData, client_secret: e.target.value })}
                className="w-full border px-3 py-2 rounded mb-3 text-sm"
                required
              />
              <input
                type="email"
                placeholder="Target Mailbox"
                value={formData.target_mailbox}
                onChange={(e) => setFormData({ ...formData, target_mailbox: e.target.value })}
                className="w-full border px-3 py-2 rounded mb-4 text-sm"
                required
              />
              <button
                type="submit"
                disabled={testMutation.isPending}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 text-sm"
              >
                {testMutation.isPending ? "Testing..." : "Test Connection"}
              </button>
            </form>
            <button
              onClick={() => setShowModal(false)}
              className="w-full mt-2 px-4 py-2 border rounded hover:bg-gray-50 text-sm"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
