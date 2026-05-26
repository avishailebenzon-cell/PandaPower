-- Phase 10: Skill Normalization & Taxonomy
-- Run this in Supabase SQL Editor to create skill-related tables

-- Create skills table (canonical skill library)
CREATE TABLE IF NOT EXISTS skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Skill information
    name TEXT NOT NULL UNIQUE,
    category TEXT NOT NULL,  -- e.g., 'Programming', 'DevOps', 'Management', 'Languages'
    description TEXT,

    -- Alternative names / aliases for the same skill
    aliases TEXT[] DEFAULT ARRAY[]::TEXT[],

    -- Skill details
    proficiency_levels TEXT[] DEFAULT ARRAY['Beginner', 'Intermediate', 'Advanced', 'Expert']::TEXT[],
    related_skills UUID[] DEFAULT ARRAY[]::UUID[],

    -- Hebrew translation for bilingual support
    name_he TEXT,
    category_he TEXT,

    -- Metadata
    is_active BOOLEAN DEFAULT true,
    popularity_score INTEGER DEFAULT 0,  -- Based on how many candidates have it

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create skill mappings table (maps raw skills to canonical skills)
CREATE TABLE IF NOT EXISTS skill_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Raw skill from CV parsing
    raw_skill_text TEXT NOT NULL,

    -- Canonical skill it maps to
    canonical_skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE SET NULL,

    -- Language of the raw skill
    source_language TEXT,  -- 'he', 'en', etc.

    -- Mapping confidence (set by Claude or manual review)
    confidence_score NUMERIC(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    mapping_method TEXT,  -- 'claude_ai', 'manual', 'rule_based'

    -- Metadata
    is_active BOOLEAN DEFAULT true,
    times_used INTEGER DEFAULT 1,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint to prevent duplicate mappings
    UNIQUE(raw_skill_text, canonical_skill_id)
);

-- Create candidate_skills table (links candidates to normalized skills)
CREATE TABLE IF NOT EXISTS candidate_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Candidate and skill reference
    candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
    skill_id UUID NOT NULL REFERENCES skills(id) ON DELETE CASCADE,

    -- Skill details for this candidate
    raw_skill_text TEXT,  -- Original text from CV
    proficiency_level TEXT,  -- 'Beginner', 'Intermediate', 'Advanced', 'Expert'
    years_of_experience NUMERIC(4,1),

    -- Confidence in this skill assignment
    confidence_score NUMERIC(3,2) CHECK (confidence_score >= 0 AND confidence_score <= 1),
    normalization_method TEXT,  -- 'claude_ai', 'manual', 'similarity_matching'

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Unique constraint: each candidate can have each skill only once
    UNIQUE(candidate_id, skill_id)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS skills_name_idx ON skills(name);
CREATE INDEX IF NOT EXISTS skills_category_idx ON skills(category);
CREATE INDEX IF NOT EXISTS skills_is_active_idx ON skills(is_active);

CREATE INDEX IF NOT EXISTS skill_mappings_raw_skill_idx ON skill_mappings(raw_skill_text);
CREATE INDEX IF NOT EXISTS skill_mappings_canonical_skill_idx ON skill_mappings(canonical_skill_id);
CREATE INDEX IF NOT EXISTS skill_mappings_is_active_idx ON skill_mappings(is_active);

CREATE INDEX IF NOT EXISTS candidate_skills_candidate_idx ON candidate_skills(candidate_id);
CREATE INDEX IF NOT EXISTS candidate_skills_skill_idx ON candidate_skills(skill_id);
CREATE INDEX IF NOT EXISTS candidate_skills_confidence_idx ON candidate_skills(confidence_score DESC);

-- Create view for quick skill lookups
CREATE OR REPLACE VIEW skill_mappings_active AS
SELECT *
FROM skill_mappings
WHERE is_active = true;

-- Create view for candidate skills with full skill info
CREATE OR REPLACE VIEW candidate_skills_detailed AS
SELECT
    cs.id,
    cs.candidate_id,
    cs.skill_id,
    s.name as skill_name,
    s.category as skill_category,
    cs.raw_skill_text,
    cs.proficiency_level,
    cs.years_of_experience,
    cs.confidence_score,
    cs.created_at
FROM candidate_skills cs
JOIN skills s ON cs.skill_id = s.id
WHERE s.is_active = true;

-- Create trigger to update updated_at
CREATE OR REPLACE FUNCTION update_skills_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER skills_updated_at_trigger
BEFORE UPDATE ON skills
FOR EACH ROW
EXECUTE FUNCTION update_skills_updated_at();

CREATE TRIGGER skill_mappings_updated_at_trigger
BEFORE UPDATE ON skill_mappings
FOR EACH ROW
EXECUTE FUNCTION update_skills_updated_at();

CREATE TRIGGER candidate_skills_updated_at_trigger
BEFORE UPDATE ON candidate_skills
FOR EACH ROW
EXECUTE FUNCTION update_skills_updated_at();

-- Seed with common skills (initial taxonomy)
INSERT INTO skills (name, category, name_he, category_he, description) VALUES
-- Programming Languages
('Python', 'Programming Languages', 'פייתון', 'שפות תכנות', 'Python programming language'),
('JavaScript', 'Programming Languages', 'ג''אווהסקריפט', 'שפות תכנות', 'JavaScript/TypeScript'),
('Java', 'Programming Languages', 'ג''אווה', 'שפות תכנות', 'Java programming language'),
('C++', 'Programming Languages', 'סי פלוס פלוס', 'שפות תכנות', 'C++ programming language'),
('C#', 'Programming Languages', 'סי שארפ', 'שפות תכנות', 'C# programming language'),
('Go', 'Programming Languages', 'גו', 'שפות תכנות', 'Go programming language'),
('Rust', 'Programming Languages', 'ראסט', 'שפות תכנות', 'Rust programming language'),
('SQL', 'Programming Languages', 'אסקיו אל', 'שפות תכנות', 'SQL query language'),

-- Web Technologies
('React', 'Web Frameworks', 'ריאקט', 'פריימוורקים לוואב', 'React.js frontend framework'),
('Vue.js', 'Web Frameworks', 'ווו ג''יס', 'פריימוורקים לוואב', 'Vue.js framework'),
('Angular', 'Web Frameworks', 'אנגולר', 'פריימוורקים לוואב', 'Angular framework'),
('Node.js', 'Web Frameworks', 'נוד ג''יס', 'פריימוורקים לוואב', 'Node.js runtime'),
('Express.js', 'Web Frameworks', 'אקספרס', 'פריימוורקים לוואב', 'Express.js backend framework'),
('Django', 'Web Frameworks', 'ג''אנגו', 'פריימוורקים לוואב', 'Django Python framework'),
('Flask', 'Web Frameworks', 'פלסק', 'פריימוורקים לוואב', 'Flask Python framework'),
('FastAPI', 'Web Frameworks', 'פסט אפאי', 'פריימוורקים לוואב', 'FastAPI Python framework'),

-- Databases
('PostgreSQL', 'Databases', 'פוסטגרס', 'מסדי נתונים', 'PostgreSQL relational database'),
('MySQL', 'Databases', 'מיי אסקיו אל', 'מסדי נתונים', 'MySQL relational database'),
('MongoDB', 'Databases', 'מונגודיבי', 'מסדי נתונים', 'MongoDB document database'),
('Redis', 'Databases', 'רדיס', 'מסדי נתונים', 'Redis in-memory cache'),
('Elasticsearch', 'Databases', 'אלסטיקסרץ', 'מסדי נתונים', 'Elasticsearch search engine'),

-- DevOps & Infrastructure
('Docker', 'DevOps', 'דוקר', 'דיווופס', 'Docker containerization'),
('Kubernetes', 'DevOps', 'קובנרטס', 'דיווופס', 'Kubernetes orchestration'),
('AWS', 'Cloud Platforms', 'ייי אז', 'פלטפורמות ענן', 'Amazon Web Services'),
('Azure', 'Cloud Platforms', 'אז\'ור', 'פלטפורמות ענן', 'Microsoft Azure'),
('GCP', 'Cloud Platforms', 'ג\'י סי פי', 'פלטפורמות ענן', 'Google Cloud Platform'),
('CI/CD', 'DevOps', 'סי אי סי די', 'דיווופס', 'Continuous Integration/Deployment'),
('Jenkins', 'DevOps', 'ג\'נקינס', 'דיווופס', 'Jenkins automation server'),
('GitHub', 'Version Control', 'גיטהאב', 'בקרת גרסאות', 'GitHub version control'),
('Git', 'Version Control', 'גיט', 'בקרת גרסאות', 'Git version control'),

-- Management & Soft Skills
('Project Management', 'Management', 'ניהול פרויקטים', 'ניהול', 'Project management'),
('Team Leadership', 'Management', 'הנהגת צוות', 'ניהול', 'Team leadership'),
('Communication', 'Soft Skills', 'תקשורת', 'כישורים רכים', 'Communication skills'),
('Problem Solving', 'Soft Skills', 'פתרון בעיות', 'כישורים רכים', 'Problem solving ability'),
('Agile', 'Methodologies', 'אג''ייל', 'מתודולוגיות', 'Agile methodology'),
('Scrum', 'Methodologies', 'סקראם', 'מתודולוגיות', 'Scrum framework'),

-- Business & Office
('Microsoft Office', 'Business Tools', 'מייקרוסופט אופיס', 'כלים עסקיים', 'Microsoft Office suite'),
('Excel', 'Business Tools', 'אקסל', 'כלים עסקיים', 'Microsoft Excel'),
('SAP', 'Business Tools', 'אס אי פי', 'כלים עסקיים', 'SAP ERP system'),
('Salesforce', 'Business Tools', 'סיילספורס', 'כלים עסקיים', 'Salesforce CRM')
ON CONFLICT (name) DO NOTHING;

-- Verify tables were created
SELECT
    'skills' as table_name, COUNT(*) as count FROM skills
UNION ALL
SELECT 'skill_mappings', COUNT(*) FROM skill_mappings
UNION ALL
SELECT 'candidate_skills', COUNT(*) FROM candidate_skills;
