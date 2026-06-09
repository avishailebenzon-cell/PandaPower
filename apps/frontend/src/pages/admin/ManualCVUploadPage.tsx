import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { env } from "@/lib/env";

interface CandidateCategory {
  id: string;
  name: string;
  description: string;
  skills: string[];
  level: number;
}

type UploadFile = File;

export function ManualCVUploadPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("");
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [lastBatchId, setLastBatchId] = useState<string>("");

  // Fetch available categories
  const { data: categoriesData } = useQuery({
    queryKey: ["candidate-categories"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/cv/categories`).then(r => r.json()),
  });

  const categories = categoriesData?.categories || [];

  // Upload mutation
  const uploadMutation = useMutation({
    mutationFn: async (filesToUpload: UploadFile[]) => {
      if (!selectedCategory || filesToUpload.length === 0) {
        throw new Error("Please select a category and files to upload");
      }

      const formData = new FormData();
      formData.append("category_id", selectedCategory);
      filesToUpload.forEach(file => formData.append("files", file, file.name));

      const response = await fetch(`${env.API_BASE_URL}/admin/cv/upload`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        let detail = "Upload failed";
        try {
          const err = await response.json();
          if (err?.detail) detail = err.detail;
        } catch {
          /* ignore non-JSON error bodies */
        }
        throw new Error(detail);
      }

      return response.json();
    },
    onSuccess: (data) => {
      setLastBatchId(data.batch_id);
      setFiles([]);
      setSelectedCategory("");
    },
  });

  // Handle drag and drop
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const newFiles = Array.from(e.dataTransfer.files).filter(
      file =>
        file.type === "application/pdf" ||
        file.name.endsWith(".docx") ||
        file.name.endsWith(".doc")
    );

    setFiles(prev => [...prev, ...newFiles]);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...newFiles]);
    }
  };

  const handleRemoveFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = () => {
    if (!selectedCategory || files.length === 0) return;
    uploadMutation.mutate(files);
  };

  const selectedCategoryName = categories.find(
    cat => cat.id === selectedCategory
  )?.name;

  return (
    <div className="min-h-screen bg-gray-900 p-8" dir="rtl">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="bg-gradient-to-r from-indigo-900 via-gray-800 to-purple-900 rounded-lg p-6 border border-gray-700">
            <h1 className="text-4xl font-bold text-white mb-2">
              📤 העלאה ידנית של קורות חיים
            </h1>
            <p className="text-indigo-300">
              בחר סווג מועמד והעלה קורות חיים בודדות או תיקייה שלמה
            </p>
          </div>
        </div>

        {/* Category Selection */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">
            1️⃣ בחר סווג מועמד
          </h2>

          {categories.length === 0 ? (
            <div className="text-gray-400">טוען קטגוריות...</div>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              {categories.map((cat: CandidateCategory) => (
                <div
                  key={cat.id}
                  onClick={() => setSelectedCategory(cat.id)}
                  className={`p-4 rounded-lg border-2 cursor-pointer transition-all ${
                    selectedCategory === cat.id
                      ? "border-indigo-500 bg-indigo-900/20"
                      : "border-gray-700 bg-gray-700/30 hover:border-gray-600"
                  }`}
                >
                  <h3 className="font-semibold text-white mb-2">
                    {cat.name}
                    {cat.level && (
                      <span className="ml-2 text-sm text-indigo-300">
                        רמה {cat.level}
                      </span>
                    )}
                  </h3>
                  <p className="text-sm text-gray-400 mb-3">
                    {cat.description}
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {cat.skills.slice(0, 3).map((skill, i) => (
                      <span
                        key={i}
                        className="text-xs px-2 py-1 bg-gray-700 text-gray-300 rounded"
                      >
                        {skill}
                      </span>
                    ))}
                    {cat.skills.length > 3 && (
                      <span className="text-xs text-gray-500">
                        +{cat.skills.length - 3} עוד
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          {selectedCategory && (
            <div className="mt-4 p-3 bg-green-900/20 border border-green-700 rounded">
              <p className="text-green-300 text-sm">
                ✓ בחרת: <strong>{selectedCategoryName}</strong>
              </p>
            </div>
          )}
        </div>

        {/* File Upload Area */}
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-8 mb-8">
          <h2 className="text-xl font-semibold text-white mb-6">
            2️⃣ בחר קורות חיים
          </h2>

          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-12 text-center transition-all ${
              dragActive
                ? "border-indigo-400 bg-indigo-900/10"
                : "border-gray-600 bg-gray-900/50 hover:border-gray-500"
            }`}
          >
            <div className="text-6xl mb-4">📄</div>
            <h3 className="text-white font-semibold mb-2 text-lg">
              גרור קורות חיים כאן
            </h3>
            <p className="text-gray-400 mb-6">
              או לחץ לבחירה ידנית של קובץ או תיקייה
            </p>
            <input
              type="file"
              multiple
              accept=".pdf,.doc,.docx"
              onChange={handleFileSelect}
              className="hidden"
              id="file-input"
            />
            <label
              htmlFor="file-input"
              className="inline-block px-6 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg cursor-pointer transition-colors"
            >
              בחר קורות חיים
            </label>
            <p className="text-xs text-gray-500 mt-4">
              תיבות הנתמכות: PDF, DOC, DOCX (מקסימום 20 MB כל קובץ)
            </p>
          </div>
        </div>

        {/* Files List */}
        {files.length > 0 && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
            <h2 className="text-xl font-semibold text-white mb-4">
              ✅ קובצים להעלאה ({files.length})
            </h2>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {files.map((file, index) => (
                <div
                  key={index}
                  className="flex items-center justify-between p-3 bg-gray-700/30 rounded border border-gray-700 hover:bg-gray-700/50 transition-colors"
                >
                  <div className="flex items-center gap-3 flex-1">
                    <span className="text-lg">📄</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-white font-mono text-sm truncate">
                        {file.name}
                      </p>
                      <p className="text-gray-400 text-xs">
                        {(file.size / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleRemoveFile(index)}
                    className="px-3 py-1 text-red-400 hover:text-red-300 transition-colors text-sm font-semibold"
                  >
                    הסר
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Upload Progress */}
        {uploadMutation.isPending && (
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 mb-8">
            <h3 className="text-white font-semibold mb-4">⏳ עלייה בתהליך...</h3>
            <div className="flex items-center gap-3">
              <div className="animate-spin">⟳</div>
              <span className="text-gray-300">
                מעלה {files.length} קובץ...
              </span>
            </div>
          </div>
        )}

        {/* Upload Buttons */}
        <div className="flex gap-4 mb-8">
          <button
            onClick={handleUpload}
            disabled={
              !selectedCategory ||
              files.length === 0 ||
              uploadMutation.isPending
            }
            className="flex-1 px-6 py-3 bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
          >
            {uploadMutation.isPending
              ? "בתהליך..."
              : `📤 העלה ${files.length} קובץ`}
          </button>
          <button
            onClick={() => {
              setFiles([]);
              setSelectedCategory("");
            }}
            className="px-6 py-3 bg-gray-700 hover:bg-gray-600 text-white font-semibold rounded-lg transition-colors"
          >
            ביטול
          </button>
        </div>

        {/* Success Message */}
        {uploadMutation.isSuccess && lastBatchId && (
          <div className="p-4 bg-green-900/20 border border-green-700 rounded mb-8">
            <h3 className="text-green-300 font-semibold mb-2">
              ✓ העלאה הצליחה!
            </h3>
            <p className="text-green-300 text-sm mb-2">
              {uploadMutation.data.uploaded_count} קובץ הוקלדו בהצלחה! הם יופעלו
              בהרקע.
            </p>
            <p className="text-green-400 text-xs font-mono break-all">
              Batch ID: {lastBatchId}
            </p>
            <a
              href={`/admin/cv-upload-status/${lastBatchId}`}
              className="inline-block mt-3 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-semibold rounded transition-colors"
            >
              📊 צפה בסטטוס העלאה
            </a>
          </div>
        )}

        {/* Error Message */}
        {uploadMutation.isError && (
          <div className="p-4 bg-red-900/20 border border-red-700 rounded">
            <h3 className="text-red-300 font-semibold mb-2">
              ✗ שגיאה בהעלאה
            </h3>
            <p className="text-red-300 text-sm">
              {uploadMutation.error instanceof Error
                ? uploadMutation.error.message
                : "אנא נסה שוב"}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
