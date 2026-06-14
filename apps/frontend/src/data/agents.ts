/**
 * Recruitment Agents Data with Avatars
 * Each agent has full profile information including avatar.
 *
 * Avatars are real AI-generated photos served from /public/avatars/<code>.jpg.
 * `avatarFallback` keeps the original initial-in-a-circle SVG so the UI never
 * shows a broken image if a photo file is missing — wire it via onError, e.g.
 *   <img src={agent.avatar} onError={e => { e.currentTarget.src = agent.avatarFallback; }} />
 */

// Build the legacy "initial in a colored circle" SVG data-URI used as a fallback.
function initialsAvatar(letter: string, hexColor: string): string {
  const fill = hexColor.replace("#", "%23");
  return (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='" +
    fill +
    "'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E" +
    encodeURIComponent(letter) +
    "%3C/text%3E%3C/svg%3E"
  );
}

export interface Agent {
  code: string;
  name: string;
  title: string;
  department: string;
  emoji: string;
  avatar: string;
  avatarFallback: string;
  color: string;
  description: string;
  specialization: string[];
  experience: string;
  email?: string;
  phone?: string;
}

export const RECRUITMENT_AGENTS: Record<string, Agent> = {
  naama: {
    code: "naama",
    name: "נעמה",
    title: "ראשית תוכנה",
    department: "תוכנה",
    emoji: "👩‍💼",
    avatar: "/avatars/naama.jpg",
    avatarFallback: initialsAvatar("נ", "#1e40af"),
    color: "from-blue-600 to-blue-800",
    description: "מנהלת חטיבת תוכנה עם ניסיון 15 שנה בגיוס מהנדסים",
    specialization: ["Backend", "Frontend", "Full Stack", "DevOps", "Cloud"],
    experience: "15+ שנים",
    email: "naama@pandapower.io",
  },
  alik: {
    code: "alik",
    name: "אליק",
    title: "ראש אלקטרוניקה",
    department: "אלקטרוניקה",
    emoji: "👨‍💼",
    avatar: "/avatars/alik.jpg",
    avatarFallback: initialsAvatar("א", "#ca8a04"),
    color: "from-yellow-600 to-yellow-800",
    description: "מומחה בגיוס מהנדסי אלקטרוניקה ותכן חומרה",
    specialization: ["FPGA", "VHDL", "PCB Design", "RF Engineering", "Analog"],
    experience: "12+ שנים",
    email: "alik@pandapower.io",
  },
  dganit: {
    code: "dganit",
    name: "דגנית",
    title: "מנהלת QA",
    department: "בדיקות",
    emoji: "👩‍💼",
    avatar: "/avatars/dganit.jpg",
    avatarFallback: initialsAvatar("ד", "#be185d"),
    color: "from-pink-600 to-pink-800",
    description: "מובילה בגיוס מומחי בדיקות אוטומציה ובקרה איכות",
    specialization: ["Automation", "Selenium", "LoadRunner", "Manual Testing", "Test Management"],
    experience: "10+ שנים",
    email: "dganit@pandapower.io",
  },
  ofir: {
    code: "ofir",
    name: "אופיר",
    title: "ראש מערכות",
    department: "מערכות",
    emoji: "👨‍💼",
    avatar: "/avatars/ofir.jpg",
    avatarFallback: initialsAvatar("א", "#059669"),
    color: "from-green-600 to-green-800",
    description: "מומחה בגיוס מנהלי מערכות והנדסת תשתית",
    specialization: ["Linux", "Networking", "DevOps", "Container", "Kubernetes"],
    experience: "14+ שנים",
    email: "ofir@pandapower.io",
  },
  itai: {
    code: "itai",
    name: "איתי",
    title: "מנהל IT",
    department: "IT",
    emoji: "👨‍💼",
    avatar: "/avatars/itai.jpg",
    avatarFallback: initialsAvatar("א", "#9333ea"),
    color: "from-purple-600 to-purple-800",
    description: "מנהל מחלקת IT המתמחה בגיוס אנשי תשתיות",
    specialization: ["Windows", "Infrastructure", "Helpdesk", "Network Management", "Security"],
    experience: "11+ שנים",
    email: "itai@pandapower.io",
  },
  lior: {
    code: "lior",
    name: "ליאור",
    title: "ראש מכני",
    department: "מכני",
    emoji: "👨‍💼",
    avatar: "/avatars/lior.jpg",
    avatarFallback: initialsAvatar("ל", "#dc2626"),
    color: "from-red-600 to-red-800",
    description: "מוביל בגיוס מהנדסים מכניים וגיוס תיב\"ם",
    specialization: ["CAD", "SOLIDWORKS", "FEA", "Manufacturing", "Mechanical Design"],
    experience: "13+ שנים",
    email: "lior@pandapower.io",
  },
  gc: {
    code: "gc",
    name: "רון",
    title: "מנהל משרות שונות",
    department: "כללי",
    emoji: "👥",
    avatar: "/avatars/gc.jpg",
    avatarFallback: initialsAvatar("ר", "#475569"),
    color: "from-gray-600 to-gray-800",
    description: "טיפול במשרות שלא מתאימות לחטיבה מסוימת",
    specialization: ["General", "HR", "Management", "Admin", "Finance"],
    experience: "8+ שנים",
    email: "gc@pandapower.io",
  },
  mani: {
    code: "mani",
    name: "מני",
    title: "סיווג ביטחוני רמה 1",
    department: "סיווג",
    emoji: "🔒",
    avatar: "/avatars/mani.jpg",
    avatarFallback: initialsAvatar("מ", "#0891b2"),
    color: "from-cyan-600 to-cyan-800",
    description: "סוכן עצמאי — עובד מחוץ לתזמורת של כרמית. בכל פעם שמגיע מועמד רמה 1 ו/או משרה רמה 1, מני מתאים אוטומטית.",
    specialization: ["רמה 1", "סיווג ביטחוני", "Level 1 Clearance", "Independent"],
    experience: "סוכן עצמאי",
    email: "mani@pandapower.io",
  },
};

export interface Recruiter {
  code: string;
  name: string;
  title: string;
  role: string;
  emoji: string;
  avatar: string;
  avatarFallback: string;
  color: string;
  description: string;
  stage: string;
  email?: string;
}

export const RECRUITERS: Record<string, Recruiter> = {
  tal: {
    code: "tal",
    name: "טל",
    title: "מנהלת גיוס — סינון ראשוני",
    role: "Talent Screener",
    emoji: "🎯",
    avatar: "/avatars/tal.jpg",
    avatarFallback: initialsAvatar("ט", "#4f46e5"),
    color: "from-indigo-600 to-indigo-800",
    description: "סינון ראשוני של מועמדים בוואטסאפ. טל מנהלת שיחות וואטסאפ עם מועמדים בחלק הראשון של תהליך הגיוס לאחר הנחיה של מנהל הגיוס כרמית.",
    stage: "Initial Screening",
    email: "tal@pandapower.io",
  },
  elad: {
    code: "elad",
    name: "אלעד",
    title: "מנהל מגייסים - מיקום",
    role: "Placement Manager",
    emoji: "🎖️",
    avatar: "/avatars/elad.jpg",
    avatarFallback: initialsAvatar("א", "#1e40af"),
    color: "from-blue-600 to-blue-800",
    description: "מנהל מגייסים בשלב הסיום - סגירת עסקאות והצבה",
    stage: "Final Placement",
    email: "elad@pandapower.io",
  },
  pandius: {
    code: "pandius",
    name: "פנדיוס",
    title: "סוכן פניות מועמדים",
    role: "Candidate Intake Agent",
    emoji: "🐼",
    avatar: "/avatars/pandius.jpg",
    avatarFallback: initialsAvatar("פ", "#0f766e"),
    color: "from-teal-600 to-teal-800",
    description: "סוכן WhatsApp נכנס שעונה למועמדים המחפשים עבודה: אוסף פרטים, קולט קורות חיים ומנסה לאתר משרה מתאימה. עונה לפניות בלבד.",
    stage: "Candidate Intake",
    email: "pandius@pandapower.io",
  },
};

// Sales agents (סוכני מכירות) — client/deal-facing AI agents.
export const SALES_AGENTS: Record<string, Agent> = {
  dana: {
    code: "dana",
    name: "דנה",
    title: "סוכנת הזנת משרות",
    department: "מכירות",
    emoji: "💼",
    avatar: "/avatars/dana.jpg",
    avatarFallback: initialsAvatar("ד", "#0d9488"),
    color: "from-teal-600 to-teal-800",
    description: "מקבלת תיאור של דיל חדש, אוספת את פרטי המשרה ופותחת דיל בפייפדרייב",
    specialization: ["Deal Intake", "Pipedrive", "File Parsing", "Sales"],
    experience: "AI-powered",
    email: "dana@pandapower.io",
  },
};

export function getAgent(code: string): Agent | undefined {
  return RECRUITMENT_AGENTS[code];
}

export function getRecruiter(code: string): Recruiter | undefined {
  return RECRUITERS[code];
}

export function getAllAgents(): Agent[] {
  return Object.values(RECRUITMENT_AGENTS);
}

/**
 * Avatar + fallback for agents that don't have a full Agent/Recruiter record
 * but still appear in the UI by code: כרמית (manager) and ליבי (client agent).
 */
const EXTRA_AVATARS: Record<string, { avatar: string; avatarFallback: string }> = {
  carmit: { avatar: "/avatars/carmit.jpg", avatarFallback: initialsAvatar("כ", "#9333ea") },
  pandi: { avatar: "/avatars/pandi.jpg", avatarFallback: initialsAvatar("פ", "#0f766e") },
};

/**
 * Resolve any agent/recruiter code to its photo URL. Covers the 8 recruitment
 * agents, the 3 recruiters, the sales agent (דנה), plus כרמית and ליבי.
 * Returns undefined for unknown codes.
 */
export function agentAvatar(code: string | null | undefined): string | undefined {
  if (!code) return undefined;
  return (
    RECRUITMENT_AGENTS[code]?.avatar ||
    RECRUITERS[code]?.avatar ||
    SALES_AGENTS[code]?.avatar ||
    EXTRA_AVATARS[code]?.avatar
  );
}

/** Fallback (initials SVG) for any agent/recruiter code — use in img onError. */
export function agentAvatarFallback(code: string | null | undefined): string | undefined {
  if (!code) return undefined;
  return (
    RECRUITMENT_AGENTS[code]?.avatarFallback ||
    RECRUITERS[code]?.avatarFallback ||
    SALES_AGENTS[code]?.avatarFallback ||
    EXTRA_AVATARS[code]?.avatarFallback
  );
}

/**
 * Resolve an agent/recruiter code to its Hebrew display name.
 * Covers the 8 recruitment agents (נעמה / אליק / …) plus the two
 * recruiters (טל / אלעד) and the orchestrator (כרמית). Falls back to the
 * raw code when unknown so callers never render an empty string.
 */
export function agentNameHe(code: string | null | undefined): string {
  if (!code) return "—";
  const extra: Record<string, string> = { carmit: "כרמית", pandi: "ליבי", pandius: "פנדיוס" };
  return (
    RECRUITMENT_AGENTS[code]?.name ||
    RECRUITERS[code]?.name ||
    extra[code] ||
    code
  );
}

export function getAllRecruiters(): Recruiter[] {
  return Object.values(RECRUITERS);
}
