/**
 * Recruitment Agents Data with Avatars
 * Each agent has full profile information including avatar
 */

export interface Agent {
  code: string;
  name: string;
  title: string;
  department: string;
  emoji: string;
  avatar: string;
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%231e40af'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E נ%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%23ca8a04'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E א%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%23be185d'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E ד%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%23059669'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E א%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%239333ea'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E א%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%23dc2626'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E ל%3C/text%3E%3C/svg%3E",
    color: "from-red-600 to-red-800",
    description: "מוביל בגיוס מהנדסים מכניים וגיוס תיב\"ם",
    specialization: ["CAD", "SOLIDWORKS", "FEA", "Manufacturing", "Mechanical Design"],
    experience: "13+ שנים",
    email: "lior@pandapower.io",
  },
  gc: {
    code: "gc",
    name: "כללי",
    title: "מנהל משרות שונות",
    department: "כללי",
    emoji: "👥",
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%23475569'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E כ%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%230891b2'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E מ%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%234f46e5'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E ט%3C/text%3E%3C/svg%3E",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%231e40af'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E א%3C/text%3E%3C/svg%3E",
    color: "from-blue-600 to-blue-800",
    description: "מנהל מגייסים בשלב הסיום - סגירת עסקאות והצבה",
    stage: "Final Placement",
    email: "elad@pandapower.io",
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
    avatar: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ccircle cx='50' cy='50' r='50' fill='%230d9488'/%3E%3Ctext x='50' y='60' text-anchor='middle' font-size='40' font-weight='bold' fill='white'%3E ד%3C/text%3E%3C/svg%3E",
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
 * Resolve an agent/recruiter code to its Hebrew display name.
 * Covers the 8 recruitment agents (נעמה / אליק / …) plus the two
 * recruiters (טל / אלעד) and the orchestrator (כרמית). Falls back to the
 * raw code when unknown so callers never render an empty string.
 */
export function agentNameHe(code: string | null | undefined): string {
  if (!code) return "—";
  const extra: Record<string, string> = { carmit: "כרמית", pandi: "פנדי" };
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
