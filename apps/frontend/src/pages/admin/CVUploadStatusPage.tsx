import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { env } from "@/lib/env";

interface UploadFile {
  filename: string;
  parse_status: string;
  candidate_id?: string;
  created_at: string;
}

interface UploadStatus {
  batch_id: string;
  total_files: number;
  processing: number;
  success: number;
  failed: number;
  files: UploadFile[];
}

export function CVUploadStatusPage() {
  const { batchId } = useParams<{ batchId: string }>();

  const { data: uploadStatus, isLoading } = useQuery({
    queryKey: ["cv-upload-status", batchId],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/cv/upload-status/${batchId}`).then(r =>
        r.json()
      ),
    refetchInterval: 5000, // Refresh every 5 seconds
    enabled: !!batchId,
  });

  if (!batchId) {
    return (
      <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
        <div className="max-w-4xl mx-auto">
          <div className="p-6 bg-red-900/20 border border-red-700 rounded">
            <p className="text-red-300">❌ Batch ID not found</p>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
        <div className="max-w-4xl mx-auto">
          <div className="text-center py-12">
            <div className="animate-spin text-4xl mb-4">⟳</div>
            <p className="text-gray-300">טוען סטטוס עלאה...</p>
          </div>
        </div>
      </div>
    );
  }

  const status = uploadStatus as UploadStatus;
  const completedCount = status.success + status.failed;
  const progressPercent = (completedCount / status.total_files) * 100;

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="bg-gradient-to-r from-indigo-900 via-gray-800 to-purple-900 rounded-lg p-6 border border-gray-700">
            <h1 className="text-4xl font-bold text-white mb-2">
              📊 סטטוס עלאה
            </h1>
            <p className="text-indigo-300">
              עקוב אחרי התקדמות עלאת קורות החיים
            </p>
          </div>
        </div>

        {/* Status Summary */}
        <div className="grid grid-cols-4 gap-4 mb-8">
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 text-center">
            <div className="text-3xl font-bold text-indigo-400">
              {status.total_files}
            </div>
            <div className="text-xs text-gray-400 mt-2 uppercase tracking-wide">
              סה"כ קובצים
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 text-center">
            <div className="text-3xl font-bold text-blue-400">
              {status.processing}
            </div>
            <div className="text-xs text-gray-400 mt-2 uppercase tracking-wide">
              בתהליך
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 text-center">
            <div className="text-3xl font-bold text-green-400">
              {status.success}
            </div>
            <div className="text-xs text-gray-400 mt-2 uppercase tracking-wide">
              בהצלחה
            </div>
          </div>
          <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 text-center">
            <div className="text-3xl font-bold text-red-400">
              {status.failed}
            </div>
            <div className="text-xs text-gray-400 mt-2 uppercase tracking-wide">
              כשל
            </div>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
          <div className="mb-3 flex justify-between items-center">
            <h3 className="text-white font-semibold">התקדמות</h3>
            <span className="text-sm text-gray-400">
              {completedCount} / {status.total_files} בוצעו
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-3 overflow-hidden">
            <div
              className="bg-gradient-to-r from-indigo-600 to-purple-600 h-full transition-all duration-300"
              style={{ width: `${Math.min(progressPercent, 100)}%` }}
            />
          </div>
          <div className="mt-2 text-sm text-gray-400 text-center">
            {Math.round(progressPercent)}%
          </div>
        </div>

        {/* Files Table */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 overflow-hidden">
          <h2 className="text-xl font-semibold text-white mb-4">
            📋 רשימת קובצים
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-700 bg-gray-900/50">
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">
                    שם קובץ
                  </th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">
                    סטטוס
                  </th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">
                    מועמד
                  </th>
                  <th className="text-right py-4 px-4 text-gray-300 font-semibold">
                    זמן
                  </th>
                </tr>
              </thead>
              <tbody>
                {status.files.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="text-center py-8 text-gray-400">
                      אין קובצים
                    </td>
                  </tr>
                ) : (
                  status.files.map((file: UploadFile, index: number) => (
                    <tr
                      key={index}
                      className="border-b border-gray-700 hover:bg-gray-700/30 transition-colors"
                    >
                      <td className="py-4 px-4 font-mono text-xs text-gray-300 truncate">
                        {file.filename}
                      </td>
                      <td className="py-4 px-4">
                        <span
                          className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border ${
                            file.parse_status === "success"
                              ? "bg-green-900/30 text-green-300 border-green-700"
                              : file.parse_status === "failed"
                                ? "bg-red-900/30 text-red-300 border-red-700"
                                : file.parse_status === "parsing"
                                  ? "bg-blue-900/30 text-blue-300 border-blue-700"
                                  : "bg-gray-700/30 text-gray-300 border-gray-600"
                          }`}
                        >
                          {file.parse_status === "success" && "✓ בהצלחה"}
                          {file.parse_status === "failed" && "✗ כשל"}
                          {file.parse_status === "parsing" && "⟳ בתהליך"}
                          {file.parse_status === "pending" && "◯ בהמתנה"}
                        </span>
                      </td>
                      <td className="py-4 px-4 text-xs text-indigo-300">
                        {file.candidate_id ? (
                          <a
                            href={`/admin/candidates/${file.candidate_id}`}
                            className="hover:underline"
                          >
                            {file.candidate_id.substring(0, 8)}...
                          </a>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-4 px-4 text-xs text-gray-400">
                        {new Date(file.created_at).toLocaleString("he-IL")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Info Box */}
        <div className="mt-8 p-4 bg-gray-800 border border-gray-700 rounded">
          <p className="text-gray-400 text-sm">
            ℹ️ העמוד מרענן באופן אוטומטי כל 5 שניות. ניתן לחזור לעמוד ההעלאה כדי
            להעלות קורות חיים נוספות.
          </p>
        </div>

        <div className="mt-4">
          <a
            href="/admin/cv-upload"
            className="inline-block px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg transition-colors"
          >
            ← חזור להעלאה
          </a>
        </div>
      </div>
    </div>
  );
}
