import { useEffect, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { supabase } from "@/lib/supabase";
import { env } from "@/lib/env";

interface SkillStats {
  canonical_skills_count: number;
  skill_mappings_count: number;
  candidate_skills_assigned: number;
  candidates_with_normalized_skills: number;
}

interface SkillInfo {
  id: string;
  name: string;
  category: string;
  description: string | null;
  name_he: string | null;
  popularity_score: number;
}

interface SkillMapping {
  id: string;
  raw_skill_text: string;
  canonical_skill_id: string;
  confidence_score: number;
  mapping_method: string;
}

interface CandidateSkillInfo {
  skill_name: string;
  skill_category: string;
  raw_skill_text: string;
  confidence_score: number;
  proficiency_level: string | null;
  years_of_experience: number | null;
}

export function SkillManagementPage() {
  const [selectedCategory, setSelectedCategory] = useState<string>("all");
  const [showAddSkillModal, setShowAddSkillModal] = useState(false);
  const [showMappingsModal, setShowMappingsModal] = useState(false);
  const [newSkill, setNewSkill] = useState({ name: "", category: "", name_he: "", description: "" });
  const [liveEvents, setLiveEvents] = useState<CandidateSkillInfo[]>([]);

  // Fetch skill statistics
  const { data: stats, refetch: refetchStats } = useQuery({
    queryKey: ["skill-stats"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/skills/stats`).then(r => r.json()),
    refetchInterval: 5000,
  });

  // Fetch categories
  const { data: categories } = useQuery({
    queryKey: ["skill-categories"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/skills/categories`).then(r => r.json()),
    refetchInterval: 30000,
  });

  // Fetch canonical skills
  const { data: canonicalSkills, refetch: refetchSkills } = useQuery({
    queryKey: ["canonical-skills", selectedCategory],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "100" });
      if (selectedCategory !== "all") {
        params.append("category", selectedCategory);
      }
      return fetch(`${env.API_BASE_URL}/admin/skills/canonical?${params}`).then(r => r.json());
    },
    refetchInterval: 10000,
  });

  // Fetch skill mappings
  const { data: mappings } = useQuery({
    queryKey: ["skill-mappings"],
    queryFn: () =>
      fetch(`${env.API_BASE_URL}/admin/skills/mappings?limit=100`).then(r => r.json()),
    refetchInterval: 15000,
  });

  // Manual trigger mutation
  const runNowMutation = useMutation({
    mutationFn: () =>
      fetch(`${env.API_BASE_URL}/admin/skills/run-now`, { method: "POST" }).then(r => r.json()),
    onSuccess: () => {
      refetchStats();
    },
  });

  // Add canonical skill mutation
  const addSkillMutation = useMutation({
    mutationFn: (skillData) =>
      fetch(`${env.API_BASE_URL}/admin/skills/add-canonical`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(skillData),
      }).then(r => r.json()),
    onSuccess: () => {
      refetchSkills();
      setNewSkill({ name: "", category: "", name_he: "", description: "" });
      setShowAddSkillModal(false);
    },
  });

  // Subscribe to candidate skill updates
  useEffect(() => {
    const channel = supabase
      .channel("skill-updates")
      .on(
        "postgres_changes",
        { event: "INSERT", schema: "public", table: "candidate_skills" },
        (payload) => {
          const newSkill = payload.new;
          setLiveEvents((prev) => [
            {
              skill_name: newSkill.skill_id,
              skill_category: "—",
              raw_skill_text: newSkill.raw_skill_text,
              confidence_score: newSkill.confidence_score,
              proficiency_level: null,
              years_of_experience: null,
            },
            ...prev,
          ].slice(0, 5));
        }
      )
      .subscribe();

    return () => {
      channel.unsubscribe();
    };
  }, []);

  const handleAddSkill = () => {
    if (!newSkill.name || !newSkill.category) {
      alert("Name and category are required");
      return;
    }
    addSkillMutation.mutate(newSkill);
  };

  const populatarityByCategory =
    canonicalSkills?.reduce((acc: Record<string, number>, skill: SkillInfo) => {
      acc[skill.category] = (acc[skill.category] || 0) + 1;
      return acc;
    }, {}) || {};

  return (
    <div className="p-8 max-w-7xl mx-auto bg-gray-900 min-h-screen" dir="rtl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2 text-white">ניהול כישורים</h1>
        <p className="text-white">ניהול כישורים קנוניים והתאמות נרמול</p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-4 gap-4 mb-8">
        <div className="bg-blue-50 p-4 rounded-lg border border-blue-200">
          <div className="text-xs text-blue-600 font-semibold">כישורים קנוניים</div>
          <div className="text-3xl font-bold text-blue-700">{stats?.canonical_skills_count || 0}</div>
        </div>
        <div className="bg-purple-50 p-4 rounded-lg border border-purple-200">
          <div className="text-xs text-purple-600 font-semibold">התאמות</div>
          <div className="text-3xl font-bold text-purple-700">{stats?.skill_mappings_count || 0}</div>
        </div>
        <div className="bg-green-50 p-4 rounded-lg border border-green-200">
          <div className="text-xs text-green-600 font-semibold">כישורים שהוקצו</div>
          <div className="text-3xl font-bold text-green-700">{stats?.candidate_skills_assigned || 0}</div>
        </div>
        <div className="bg-gray-50 p-4 rounded-lg border border-gray-200">
          <div className="text-xs text-gray-600 font-semibold">מועמדים</div>
          <div className="text-3xl font-bold text-gray-700">
            {stats?.candidates_with_normalized_skills || 0}
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="flex gap-4 mb-8">
        <button
          onClick={() => runNowMutation.mutate()}
          disabled={runNowMutation.isPending}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-semibold"
        >
          {runNowMutation.isPending ? "מעבד..." : "הפעל נרמול עכשיו"}
        </button>
        <button
          onClick={() => setShowAddSkillModal(true)}
          className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 font-semibold"
        >
          + הוסף כישור קנוני
        </button>
        <button
          onClick={() => setShowMappingsModal(true)}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 font-semibold"
        >
          צפה בהתאמות
        </button>
      </div>

      {/* Live Events */}
      <div className="bg-gray-800 p-6 rounded-lg border border-gray-700 mb-8">
        <h2 className="text-lg font-semibold mb-4 text-white">כישורים מנורמלים חדשים</h2>
        <div className="space-y-2">
          {liveEvents.length === 0 ? (
            <div className="text-sm text-white py-4">מחכה לנרמול כישורים...</div>
          ) : (
            liveEvents.map((event, idx) => (
              <div
                key={idx}
                className="flex items-center p-3 rounded text-sm gap-4 bg-green-900 border border-green-700"
              >
                <span className="font-bold text-lg w-6 text-green-400">✓</span>
                <div className="flex-1">
                  <div className="font-semibold text-white">{event.raw_skill_text}</div>
                  <div className="text-xs text-white">ביטחון: {(event.confidence_score * 100).toFixed(0)}%</div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Category Filter */}
      <div className="mb-4 flex gap-2 overflow-x-auto pb-2">
        <button
          onClick={() => setSelectedCategory("all")}
          className={`px-3 py-1 rounded text-sm font-semibold whitespace-nowrap ${
            selectedCategory === "all"
              ? "bg-blue-600 text-white"
              : "bg-gray-700 text-white hover:bg-gray-600"
          }`}
        >
          הכול
        </button>
        {categories?.map((category: string) => (
          <button
            key={category}
            onClick={() => setSelectedCategory(category)}
            className={`px-3 py-1 rounded text-sm font-semibold whitespace-nowrap ${
              selectedCategory === category
                ? "bg-blue-600 text-white"
                : "bg-gray-700 text-white hover:bg-gray-600"
            }`}
          >
            {category} ({populatarityByCategory[category] || 0})
          </button>
        ))}
      </div>

      {/* Canonical Skills Table */}
      <div className="bg-white p-6 rounded-lg border">
        <h2 className="text-lg font-semibold mb-4">Canonical Skills Library</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-gray-50">
                <th className="text-left py-3 px-3">שם</th>
                <th className="text-left py-3 px-3">שם (HE)</th>
                <th className="text-left py-3 px-3">Category</th>
                <th className="text-left py-3 px-3">Description</th>
                <th className="text-center py-3 px-3">Popularity</th>
              </tr>
            </thead>
            <tbody>
              {!canonicalSkills || canonicalSkills.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-4 text-gray-500 text-sm">
                    No skills in this category
                  </td>
                </tr>
              ) : (
                canonicalSkills.map((skill: SkillInfo) => (
                  <tr key={skill.id} className="border-b hover:bg-gray-50">
                    <td className="py-3 px-3 font-semibold text-gray-900">{skill.name}</td>
                    <td className="py-3 px-3 text-gray-600">{skill.name_he || "—"}</td>
                    <td className="py-3 px-3 text-xs">
                      <span className="px-2 py-1 bg-gray-100 rounded">{skill.category}</span>
                    </td>
                    <td className="py-3 px-3 text-xs text-gray-600 max-w-xs truncate">
                      {skill.description || "—"}
                    </td>
                    <td className="py-3 px-3 text-center font-mono">
                      <div className="flex items-center gap-2 justify-center">
                        <div className="w-16 bg-gray-200 rounded h-2">
                          <div
                            className="bg-blue-600 h-full rounded"
                            style={{ width: `${Math.min(skill.popularity_score / 10, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs w-8">{skill.popularity_score}</span>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* הוסף כישור Modal */}
      {showAddSkillModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-md p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Add Canonical Skill</h3>
              <button
                onClick={() => setShowAddSkillModal(false)}
                className="text-gray-500 hover:text-gray-700 text-xl"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold mb-1">שם (English) *</label>
                <input
                  type="text"
                  value={newSkill.name}
                  onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g., Python"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold mb-1">Category *</label>
                <select
                  value={newSkill.category}
                  onChange={(e) => setNewSkill({ ...newSkill, category: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select category...</option>
                  {categories?.map((cat: string) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-semibold mb-1">שם (Hebrew)</label>
                <input
                  type="text"
                  value={newSkill.name_he}
                  onChange={(e) => setNewSkill({ ...newSkill, name_he: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="e.g., פייתון"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold mb-1">Description</label>
                <textarea
                  value={newSkill.description}
                  onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                  rows={3}
                  placeholder="Optional description..."
                />
              </div>

              <div className="flex gap-2 pt-4">
                <button
                  onClick={handleAddSkill}
                  disabled={addSkillMutation.isPending}
                  className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-semibold"
                >
                  {addSkillMutation.isPending ? "Adding..." : "הוסף כישור"}
                </button>
                <button
                  onClick={() => setShowAddSkillModal(false)}
                  className="flex-1 px-4 py-2 bg-gray-300 text-gray-700 rounded-lg hover:bg-gray-400 font-semibold"
                >
                  ביטול
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Mappings Modal */}
      {showMappingsModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg max-w-2xl max-h-96 overflow-y-auto p-6">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold">Skill Mappings</h3>
              <button
                onClick={() => setShowMappingsModal(false)}
                className="text-gray-500 hover:text-gray-700 text-xl"
              >
                ✕
              </button>
            </div>

            <div className="space-y-2 text-sm">
              {!mappings || mappings.length === 0 ? (
                <div className="text-gray-500 py-4">No skill mappings yet</div>
              ) : (
                mappings.map((mapping: SkillMapping) => (
                  <div key={mapping.id} className="bg-gray-50 p-3 rounded border">
                    <div className="flex justify-between items-start gap-2">
                      <div className="flex-1">
                        <div className="font-semibold text-gray-900">{mapping.raw_skill_text}</div>
                        <div className="text-xs text-gray-600 mt-1">
                          Maps to: <span className="font-mono">{mapping.canonical_skill_id}</span>
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          Method: <span className="font-semibold">{mapping.mapping_method}</span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xs text-gray-600">ביטחון</div>
                        <div className="text-sm font-mono font-bold">
                          {(mapping.confidence_score * 100).toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
