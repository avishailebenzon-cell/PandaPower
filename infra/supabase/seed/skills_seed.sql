-- Phase 10: Canonical Skills Taxonomy Seed Data
-- Bilingual skills library for Israeli tech market + security clearances

-- Programming Languages
INSERT INTO skills (name, name_he, category, category_he, aliases, aliases_he, popularity_score) VALUES
('Python', 'פייתון', 'Programming Language', 'שפת תכנות', ARRAY['python3', 'py'], ARRAY['py'], 0.95),
('JavaScript', 'ג''אווה סקריפט', 'Programming Language', 'שפת תכנות', ARRAY['JS', 'js', 'node'], ARRAY[], 0.92),
('TypeScript', 'טייפ סקריפט', 'Programming Language', 'שפת תכנות', ARRAY['TS', 'ts'], ARRAY[], 0.88),
('Java', 'ג''אווה', 'Programming Language', 'שפת תכנות', ARRAY['jvm'], ARRAY[], 0.85),
('Go', 'גו', 'Programming Language', 'שפת תכנות', ARRAY['golang'], ARRAY['גולנג'], 0.78),
('Rust', 'ראסט', 'Programming Language', 'שפת תכנות', ARRAY[], ARRAY[], 0.72),
('C++', 'סי פלוס פלוס', 'Programming Language', 'שפת תכנות', ARRAY['cpp', 'cplusplus'], ARRAY[], 0.75),
('C#', 'סי שארפ', 'Programming Language', 'שפת תכנות', ARRAY['csharp', 'dotnet'], ARRAY['דוט נט'], 0.78),
('SQL', 'סקל', 'Programming Language', 'שפת תכנות', ARRAY['sql', 'plsql'], ARRAY[], 0.92),
('Bash', 'בש', 'Programming Language', 'שפת תכנות', ARRAY['shell', 'sh'], ARRAY['שלל'], 0.85),
('Ruby', 'רובי', 'Programming Language', 'שפת תכנות', ARRAY['rails'], ARRAY[], 0.65),
('PHP', 'פיאיץ''פ', 'Programming Language', 'שפת תכנות', ARRAY[], ARRAY[], 0.68),

-- Frontend Frameworks
('React', 'ריאקט', 'Frontend Framework', 'פריימוורק קדמי', ARRAY['reactjs', 'react.js'], ARRAY[], 0.93),
('Vue.js', 'ויו', 'Frontend Framework', 'פריימוורק קדמי', ARRAY['vuejs', 'vue'], ARRAY['ויו'], 0.78),
('Angular', 'אנגולר', 'Frontend Framework', 'פריימוורק קדמי', ARRAY['angular.js', 'angular2'], ARRAY[], 0.82),
('Next.js', 'נקסט ג''אס', 'Frontend Framework', 'פריימוורק קדמי', ARRAY['nextjs', 'next'], ARRAY[], 0.85),
('Vue 3', 'ויו 3', 'Frontend Framework', 'פריימוורק קדמי', ARRAY['vue3'], ARRAY[], 0.72),
('Svelte', 'סוולט', 'Frontend Framework', 'פריימוורק קדמי', ARRAY[], ARRAY[], 0.55),

-- Backend Frameworks
('Django', 'ג''נגו', 'Backend Framework', 'פריימוורק אחורי', ARRAY['djangorest', 'drf'], ARRAY[], 0.82),
('FastAPI', 'פסט איי פיי איי', 'Backend Framework', 'פריימוורק אחורי', ARRAY['fastapi'], ARRAY[], 0.80),
('Express.js', 'אקספרס', 'Backend Framework', 'פריימוורק אחורי', ARRAY['express', 'expressjs'], ARRAY[], 0.88),
('Spring Boot', 'ספרינג בוט', 'Backend Framework', 'פריימוורק אחורי', ARRAY['spring', 'springboot'], ARRAY[], 0.78),
('Flask', 'פלסק', 'Backend Framework', 'פריימוורק אחורי', ARRAY['flask'], ARRAY[], 0.75),
('NestJS', 'נסט ג''אס', 'Backend Framework', 'פריימוורק אחורי', ARRAY['nest'], ARRAY[], 0.72),
('Laravel', 'לארוול', 'Backend Framework', 'פריימוורק אחורי', ARRAY['laravel'], ARRAY[], 0.68),

-- Databases
('PostgreSQL', 'פוסטגרס', 'Database', 'מסד נתונים', ARRAY['postgres', 'psql', 'pg'], ARRAY[], 0.90),
('MySQL', 'מיי אס קיו אל', 'Database', 'מסד נתונים', ARRAY['mysql'], ARRAY[], 0.85),
('MongoDB', 'מונגו דיבי', 'Database', 'מסד נתונים', ARRAY['mongo'], ARRAY[], 0.82),
('Redis', 'רדיס', 'Database', 'מסד נתונים', ARRAY['redis'], ARRAY[], 0.85),
('Elasticsearch', 'אלסטיק סרץ''', 'Database', 'מסד נתונים', ARRAY['elastic'], ARRAY[], 0.78),
('Cassandra', 'קסנדרה', 'Database', 'מסד נתונים', ARRAY[], ARRAY[], 0.65),
('DynamoDB', 'דיינמו דיבי', 'Database', 'מסד נתונים', ARRAY[], ARRAY[], 0.72),

-- Cloud Platforms
('AWS', 'איי דבליו אס', 'Cloud Platform', 'פלטפורמת ענן', ARRAY['amazon', 'ec2', 's3'], ARRAY[], 0.90),
('Azure', 'אזור', 'Cloud Platform', 'פלטפורמת ענן', ARRAY['microsoft azure'], ARRAY[], 0.80),
('Google Cloud', 'גוגל קלאוד', 'Cloud Platform', 'פלטפורמת ענן', ARRAY['gcp', 'google cloud platform'], ARRAY['ג''סי פי'], 0.82),
('Heroku', 'הרוקו', 'Cloud Platform', 'פלטפורמת ענן', ARRAY['heroku'], ARRAY[], 0.70),
('DigitalOcean', 'דיג''יטל אושן', 'Cloud Platform', 'פלטפורמת ענן', ARRAY['digitalocean'], ARRAY[], 0.68),

-- DevOps & Infrastructure
('Docker', 'דוקר', 'DevOps', 'דבאופס', ARRAY['docker', 'containers'], ARRAY['קונטיינרים'], 0.88),
('Kubernetes', 'קוברנטיס', 'DevOps', 'דבאופס', ARRAY['k8s', 'k8'], ARRAY['קייט עשמונה'], 0.85),
('Terraform', 'טרהפורם', 'DevOps', 'דבאופס', ARRAY['terraform'], ARRAY[], 0.80),
('Jenkins', 'ג''נקינס', 'DevOps', 'דבאופס', ARRAY['jenkins', 'ci'], ARRAY['סי אי'], 0.82),
('GitLab CI', 'ג''יטלאב סי אי', 'DevOps', 'דבאופס', ARRAY['gitlab-ci', 'gitlab'], ARRAY[], 0.78),
('GitHub Actions', 'ג''יטהאב אקשנס', 'DevOps', 'דבאופס', ARRAY['github actions'], ARRAY[], 0.75),
('Ansible', 'אנסיבל', 'DevOps', 'דבאופס', ARRAY['ansible'], ARRAY[], 0.72),
('ArgoCD', 'ארגו סי די', 'DevOps', 'דבאופס', ARRAY['argocd'], ARRAY[], 0.70),
('Prometheus', 'פרומתיוס', 'DevOps', 'דבאופס', ARRAY['prometheus'], ARRAY[], 0.72),
('Grafana', 'גרפנה', 'DevOps', 'דבאופס', ARRAY['grafana'], ARRAY[], 0.75),

-- Security & Networking
('Network Security', 'אבטחת רשת', 'Security', 'אבטחה', ARRAY['networking', 'firewalls'], ARRAY['קירות אש'], 0.78),
('Cloud Security', 'אבטחת ענן', 'Security', 'אבטחה', ARRAY['aws security', 'gcp security'], ARRAY[], 0.82),
('Penetration Testing', 'בדיקות חדירה', 'Security', 'אבטחה', ARRAY['pentest', 'ethical hacking'], ARRAY['האקינג אתי'], 0.70),
('Cryptography', 'קריפטוגרפיה', 'Security', 'אבטחה', ARRAY['encryption', 'crypto'], ARRAY['הצפנה'], 0.68),
('SSL/TLS', 'אס אס אל / טי אל אס', 'Security', 'אבטחה', ARRAY['tls', 'https', 'certificates'], ARRAY[], 0.80),

-- Israeli Security Clearances
('Secret', 'מסוווג', 'Security Clearance', 'סיווג ביטחוני', ARRAY['סודי', 'סיווג', 'secret clearance'], ARRAY['סודי', 'מסווג'], 0.88),
('Top Secret', 'סודי עליון', 'Security Clearance', 'סיווג ביטחוני', ARRAY['secret clearance', 'TS'], ARRAY['סודי עליון', 'סודי'], 0.88),
('TS/SCI', 'סודי עליון מידע סיווג סגור', 'Security Clearance', 'סיווג ביטחוני', ARRAY['topsecret', 'ts-sci'], ARRAY[], 0.85),

-- Project Management
('Agile', 'אג''יל', 'Project Management', 'ניהול פרויקטים', ARRAY['agile', 'agile methodology'], ARRAY['מתודולוגיית אג''יל'], 0.82),
('Scrum', 'סקראם', 'Project Management', 'ניהול פרויקטים', ARRAY['scrum', 'scrum master'], ARRAY['מסטר סקראם'], 0.80),
('Kanban', 'קנבן', 'Project Management', 'ניהול פרויקטים', ARRAY['kanban'], ARRAY[], 0.72),
('JIRA', 'ג''יירה', 'Project Management', 'ניהול פרויקטים', ARRAY['jira'], ARRAY[], 0.78),
('Confluence', 'קונפלואנס', 'Project Management', 'ניהול פרויקטים', ARRAY['confluence'], ARRAY[], 0.72),

-- Soft Skills
('Leadership', 'הנהגה', 'Soft Skill', 'כישורים רכים', ARRAY['leader', 'team lead'], ARRAY['מנהל צוות'], 0.75),
('Communication', 'תקשורת', 'Soft Skill', 'כישורים רכים', ARRAY['presentation', 'public speaking'], ARRAY['הציגות פומביות'], 0.80),
('Problem Solving', 'פתרון בעיות', 'Soft Skill', 'כישורים רכים', ARRAY['problem solving', 'critical thinking'], ARRAY['חשיבה ביקורתית'], 0.78),
('Teamwork', 'עבודת צוות', 'Soft Skill', 'כישורים רכים', ARRAY['team', 'collaboration'], ARRAY['שיתוף פעולה'], 0.82),
('Project Management', 'ניהול פרויקטים', 'Soft Skill', 'כישורים רכים', ARRAY['pm', 'project planning'], ARRAY['תכנון פרויקטים'], 0.75);

-- Insert a few more tools/technologies
INSERT INTO skills (name, name_he, category, category_he, popularity_score) VALUES
('Git', 'גיט', 'Tool', 'כלי', 0.92),
('Linux', 'לינוקס', 'Operating System', 'מערכת הפעלה', 0.85),
('macOS', 'מק אוס', 'Operating System', 'מערכת הפעלה', 0.70),
('Windows', 'וינדוס', 'Operating System', 'מערכת הפעלה', 0.72),
('REST API', 'ריסט איי פיי איי', 'Concept', 'קונספט', 0.88),
('GraphQL', 'גראף קיו אל', 'Concept', 'קונספט', 0.78),
('WebSocket', 'וובסוקט', 'Concept', 'קונספט', 0.72),
('Microservices', 'מיקרו סרוויסেס', 'Architecture', 'ארכיטקטורה', 0.80),
('System Design', 'עיצוב מערכות', 'Concept', 'קונספט', 0.75);
