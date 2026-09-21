import { useEffect, useState, useRef, Component } from "react";
import type { ComponentPropsWithoutRef, FormEvent, ReactNode } from "react";
import { StudyRewindLogo } from "./components/brand/StudyRewindLogo";
import {
  Bell,
  BookOpen,
  Bot,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleHelp,
  Clock3,
  ExternalLink,
  FileText,
  FolderOpen,
  LayoutDashboard,
  Menu,
  MoreHorizontal,
  Play,
  Plus,
  Search,
  Send,
  Settings,
  Trash2,
  Upload,
  Video,
  X,
  Zap,
} from "lucide-react";
import * as api from "./lib/api";
import type {
  User,
  SubjectRecord,
  SubjectSummary,
  PlaylistRecord,
  VideoRecord,
  TranscriptSegment,
  MaterialRecord,
  SearchResultItem,
} from "./lib/api";

type Page =
  | "landing"
  | "login"
  | "signup"
  | "dashboard"
  | "subject"
  | "add-playlist"
  | "processing"
  | "playlist"
  | "materials"
  | "chat"
  | "video"
  | "document"
  | "insights";

const nav: [Page, string, typeof LayoutDashboard][] = [
  ["dashboard", "Dashboard", LayoutDashboard],
  ["subject", "My Subjects", FolderOpen],
  ["chat", "Study Search", Bot],
  ["materials", "Study Materials", FileText],
  ["playlist", "Playlists", Video],
  ["insights", "Learning Insights", BrainCircuit],
  ["settings" as Page, "Settings", Settings],
];

const VALID_PAGES: readonly Page[] = [
  "landing",
  "login",
  "signup",
  "dashboard",
  "subject",
  "add-playlist",
  "processing",
  "playlist",
  "materials",
  "chat",
  "video",
  "document",
  "insights",
];

function usePage(): [Page, (p: Page) => void] {
  const get = (): Page => {
    const raw = location.hash.replace(/^#\/?/, "");
    const seg = raw.split("?")[0];
    if (!seg || !VALID_PAGES.includes(seg as Page)) {
      return "landing";
    }
    return seg as Page;
  };
  const [page, setPage] = useState<Page>(get);
  useEffect(() => {
    const f = () => setPage(get());
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const go = (p: Page) => {
    const target = `/${p === "landing" ? "" : p}`;
    if (location.hash !== target && location.hash !== `#${target}`) {
      location.hash = target;
    }
    setPage(p);
  };
  return [page, go];
}

function goToDetail(
  page: Page,
  key: string,
  value: string,
  extraParams?: Record<string, string>
) {
  const params = new URLSearchParams();
  params.set(key, value);
  if (extraParams) {
    for (const [k, v] of Object.entries(extraParams)) {
      if (v !== undefined && v !== null && v !== "") {
        params.set(k, v);
      }
    }
  }
  location.hash = `/${page}?${params.toString()}`;
}

function useHashParam(key: string) {
  const read = () => {
    const hash = location.hash || "";
    const queryPart = hash.includes("?")
      ? hash.split("?")[1]
      : location.search
      ? location.search.slice(1)
      : "";
    return new URLSearchParams(queryPart).get(key);
  };
  const [value, setValue] = useState(read);
  useEffect(() => {
    const update = () => setValue(read());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, [key]);
  return value;
}

function formatDuration(seconds?: number | null) {
  if (seconds === null || seconds === undefined) return "—";
  const mins = Math.floor(seconds / 60);
  const secs = String(Math.floor(seconds % 60)).padStart(2, "0");
  return `${mins}:${secs}`;
}

function formatTimestamp(seconds: number) {
  const mins = Math.floor(seconds / 60);
  const secs = String(Math.floor(seconds % 60)).padStart(2, "0");
  return `${mins}:${secs}`;
}

function SubjectSelect({
  value,
  onChange,
  required = false,
}: {
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const [subjects, setSubjects] = useState<SubjectRecord[]>([]);
  useEffect(() => {
    api
      .getSubjects()
      .then((subs) => {
        setSubjects(subs);
        if (!value && subs.length > 0) {
          onChange(subs[0].id);
        }
      })
      .catch(() => setSubjects([]));
  }, []);

  return (
    <label>
      Subject {required && "*"}
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choose a subject</option>
        {subjects.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Button({
  children,
  onClick,
  kind = "primary",
  disabled = false,
  type = "button",
  title,
}: {
  children: ReactNode;
  onClick?: () => void;
  kind?: "primary" | "secondary" | "ghost";
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
}) {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`button ${kind}`}
      title={title}
    >
      {children}
    </button>
  );
}

function Badge({
  children,
  tone = "success",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

function Card({
  children,
  className = "",
  ...props
}: ComponentPropsWithoutRef<"section">) {
  return (
    <section {...props} className={`card ${className}`}>
      {children}
    </section>
  );
}

function SectionTitle({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <div className="section-title">
      <span className="eyebrow">{eyebrow}</span>
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
  );
}

function PageFrame({
  title,
  text,
  children,
}: {
  title: string;
  text?: string;
  children: ReactNode;
}) {
  return (
    <>
      <div className="page-title">
        <div>
          <h1>{title}</h1>
          {text && <p>{text}</p>}
        </div>
      </div>
      {children}
    </>
  );
}

function SectionHeader({
  title,
  action,
  onClick,
}: {
  title: string;
  action?: string;
  onClick?: () => void;
}) {
  return (
    <div className="section-header">
      <h2>{title}</h2>
      {action && (
        <button onClick={onClick}>
          {action.startsWith("New") && <Plus />}
          {action}
        </button>
      )}
    </div>
  );
}

function Footer({ onGetStarted, onLogin }: { onGetStarted?: () => void; onLogin?: () => void }) {
  return (
    <footer>
      <div>
        <StudyRewindLogo variant="white" />
        <p>Go back to the exact point where a topic was taught.</p>
      </div>
      <div className="footer-links">
        <a href="#features">Features</a>
        <a href="#how">How it works</a>
        {onGetStarted ? (
          <button
            type="button"
            onClick={onGetStarted}
            style={{ background: "none", border: "none", color: "inherit", font: "inherit", cursor: "pointer", padding: 0 }}
          >
            Get Started
          </button>
        ) : (
          <a href="#pricing">Get Started</a>
        )}
        {onLogin ? (
          <button
            type="button"
            onClick={onLogin}
            style={{ background: "none", border: "none", color: "inherit", font: "inherit", cursor: "pointer", padding: 0 }}
          >
            Login
          </button>
        ) : (
          <a href="#/login">Login</a>
        )}
      </div>
      <small>© 2026 StudyRewind. Built for focused student learning.</small>
    </footer>
  );
}

// ---------------------------------------------------------------------------
// Landing Page
// ---------------------------------------------------------------------------

function Landing({ go, user }: { go: (p: Page) => void; user: User | null }) {
  const [menu, setMenu] = useState(false);
  const [demo, setDemo] = useState(false);

  const handleGetStarted = () => {
    if (user) {
      go("dashboard");
    } else {
      go("signup");
    }
  };

  const features = [
    [Clock3, "Timestamped Learning", "Find the exact point where a topic was explained in your YouTube lectures."],
    [Bot, "Semantic Search", "Search your course videos and lecture notes using natural language."],
    [FileText, "Page-Level Provenance", "Jump straight to the exact PDF page where a concept is documented."],
    [Zap, "100% Local & Fast", "Runs locally on your laptop with zero paid APIs or data tracking."],
  ];

  return (
    <>
      <header className="landing-nav">
        <StudyRewindLogo />
        <nav className={menu ? "open" : ""}>
          <a href="#features">Features</a>
          <a href="#how">How it works</a>
          <button type="button" onClick={handleGetStarted}>Get Started</button>
          {user ? (
            <Button onClick={() => go("dashboard")}>Dashboard</Button>
          ) : (
            <>
              <button type="button" onClick={() => go("login")}>Login</button>
              <Button onClick={() => go("signup")}>Register</Button>
            </>
          )}
        </nav>
        <button
          className="menu"
          aria-label="Toggle navigation"
          onClick={() => setMenu(!menu)}
        >
          {menu ? <X /> : <Menu />}
        </button>
      </header>
      <main className="landing">
        <section className="hero">
          <div className="hero-copy">
            <span className="eyebrow">Your local AI study assistant</span>
            <h1>
              Find your <span>learning</span>, instantly.
            </h1>
            <p>
              Connect your YouTube playlist lectures and course PDFs. Ask any question
              and retrieve the exact video timestamp or document page with complete source provenance.
            </p>
            <div className="actions">
              <Button onClick={handleGetStarted}>
                Get Started <ChevronRight />
              </Button>
              <Button kind="secondary" onClick={() => setDemo(true)}>
                <Play /> See How It Works
              </Button>
            </div>
            <div className="trusted">
              <Check /> Built for focused student learning, not endless video scrolling
            </div>
          </div>
          <ProductPreview go={go} onGetStarted={handleGetStarted} />
        </section>

        <section id="features" className="section">
          <SectionTitle
            eyebrow="Study smarter"
            title="Everything you need to find what matters"
            text="StudyRewind organizes your playlists and notes so every answer takes you directly to the original source."
          />
          <div className="feature-grid">
            {features.map(([Icon, title, text]) => (
              <Card key={title as string} className="feature">
                <span className="feature-icon">
                  <Icon />
                </span>
                <h3>{title as string}</h3>
                <p>{text as string}</p>
              </Card>
            ))}
          </div>
        </section>

        <section id="how" className="section soft">
          <SectionTitle
            eyebrow="How it works"
            title="From lectures to answers in four steps"
            text="Organize your study resources, then pick up learning exactly where you need it."
          />
          <div className="steps">
            {[
              "Create a Subject",
              "Add YouTube Playlists & PDFs",
              "Local Transcripts & Vector Extraction",
              "Search & Jump to Exact Timestamps",
            ].map((s, i) => (
              <div className="step" key={s}>
                <span>{i + 1}</span>
                <h3>{s}</h3>
                <p>
                  {
                    [
                      "Organize your coursework into clear study subjects.",
                      "Paste public playlist URLs or upload course lecture notes.",
                      "StudyRewind extracts timestamped captions and page-bounded text locally.",
                      "Retrieve exact video timestamps and PDF pages in milliseconds.",
                    ][i]
                  }
                </p>
              </div>
            ))}
          </div>
        </section>

        <section id="pricing" className="cta">
          <StudyRewindLogo size="lg" />
          <h2>Stop searching through hours of video lectures.</h2>
          <p>Start learning from the exact moment that matters.</p>
          <Button onClick={handleGetStarted}>
            Get Started Now <ChevronRight />
          </Button>
        </section>
      </main>
      <Footer onGetStarted={handleGetStarted} onLogin={() => go(user ? "dashboard" : "login")} />

      {demo && (
        <div className="modal-backdrop" role="dialog" aria-modal="true">
          <Card className="modal">
            <button
              className="icon-button close"
              onClick={() => setDemo(false)}
            >
              <X />
            </button>
            <div className="demo-video">
              <Play />
            </div>
            <h2>StudyRewind in Action</h2>
            <p>
              Ask any question, get the most relevant lecture chunk, and jump directly to the
              video timestamp or document page.
            </p>
            <Button
              onClick={() => {
                setDemo(false);
                go(user ? "dashboard" : "login");
              }}
            >
              {user ? "Open Dashboard" : "Sign In to Try It"}
            </Button>
          </Card>
        </div>
      )}
    </>
  );
}

function ProductPreview({ go, onGetStarted }: { go: (p: Page) => void; onGetStarted?: () => void }) {
  return (
    <div className="product-preview">
      <div className="preview-top">
        <span className="dots">● ● ●</span>
        <span>StudyRewind</span>
        <Bell size={15} />
      </div>
      <div className="question">
        <Bot />
        <span>Where are deadlocks and resource allocation covered?</span>
      </div>
      <div className="answer-preview">
        <div className="video-thumb">
          <Play />
        </div>
        <div>
          <b>Operating Systems · Deadlocks</b>
          <p>
            <Clock3 /> Timestamp: 10:00 – 24:30
          </p>
          <p>
            <FileText /> OS_Notes.pdf · Page 4
          </p>
        </div>
      </div>
      <p className="explain">
        "A deadlock occurs when a set of processes are blocked because each process is holding a resource..."
      </p>
      <button onClick={onGetStarted || (() => go("login"))} className="preview-link">
        Open in StudyRewind <ChevronRight />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shell & App Navigation
// ---------------------------------------------------------------------------

function Shell({
  page,
  go,
  user,
  onLogout,
  children,
}: {
  page: Page;
  go: (p: Page) => void;
  user: User;
  onLogout: () => void;
  children: ReactNode;
}) {
  const [mobile, setMobile] = useState(false);
  const [headerQuery, setHeaderQuery] = useState("");
  const displayName = user?.display_name || user?.email?.split("@")[0] || "Student";
  const avatarLetter = (displayName || "S").slice(0, 1).toUpperCase();

  const handleHeaderSearch = (e: FormEvent) => {
    e.preventDefault();
    if (headerQuery.trim()) {
      location.hash = `/chat?q=${encodeURIComponent(headerQuery.trim())}`;
    } else {
      go("chat");
    }
  };

  return (
    <div className="app-shell">
      <aside className={mobile ? "show" : ""}>
        <div className="side-head">
          <StudyRewindLogo onClick={() => go("dashboard")} />
          <button
            className="icon-button close"
            onClick={() => setMobile(false)}
          >
            <X />
          </button>
        </div>
        <nav>
          {nav.map(([key, label, Icon]) => (
            <button
              key={label}
              className={page === key ? "active" : ""}
              onClick={() => {
                go(key);
                setMobile(false);
              }}
            >
              <Icon />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <div className="side-bottom">
          <button onClick={() => go("subject")}>
            <CircleHelp />
            <span>Help & Guides</span>
          </button>
          <div className="user">
            <span>{avatarLetter}</span>
            <div>
              <b>{displayName}</b>
              <small>{user.email}</small>
            </div>
            <button className="icon-button" aria-label="Log out" title="Log out" onClick={onLogout}>
              <MoreHorizontal />
            </button>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="app-header">
          <button
            className="icon-button mobile-only"
            onClick={() => setMobile(true)}
          >
            <Menu />
          </button>
          <form className="search" onSubmit={handleHeaderSearch}>
            <Search />
            <input
              value={headerQuery}
              onChange={(e) => setHeaderQuery(e.target.value)}
              placeholder="Search across study materials…"
            />
          </form>
          <button className="icon-button" title="Notifications">
            <Bell />
          </button>
          <span className="avatar">{avatarLetter}</span>
        </header>
        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

function Dashboard({ go }: { go: (p: Page) => void }) {
  const [subjects, setSubjects] = useState<SubjectRecord[]>([]);
  const [playlists, setPlaylists] = useState<PlaylistRecord[]>([]);
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      api.getSubjects().catch((err) => {
        console.warn("Could not load subjects for dashboard:", err);
        return [] as SubjectRecord[];
      }),
      api.getPlaylists().catch((err) => {
        console.warn("Could not load playlists for dashboard:", err);
        return [] as PlaylistRecord[];
      }),
      api.getMaterials().catch((err) => {
        console.warn("Could not load materials for dashboard:", err);
        return [] as MaterialRecord[];
      }),
    ])
      .then(([s, p, m]) => {
        setSubjects(Array.isArray(s) ? s : (s as any)?.data || []);
        setPlaylists(Array.isArray(p) ? p : (p as any)?.data || []);
        setMaterials(Array.isArray(m) ? m : (m as any)?.data || []);
        setError("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load learning data. Please try again."))
      .finally(() => setLoading(false));
  }, []);

  const safeSubjects = Array.isArray(subjects) ? subjects : [];
  const safePlaylists = Array.isArray(playlists) ? playlists : [];
  const safeMaterials = Array.isArray(materials) ? materials : [];

  const stats = [
    [String(safeSubjects.length), "Subjects"],
    [String(safePlaylists.length), "Playlists"],
    [String(safeMaterials.length), "Study Materials"],
    [
      String(
        safeMaterials.reduce((acc, m) => acc + (Number(m?.page_count) || 0), 0)
      ),
      "Extracted Pages",
    ],
  ];

  return (
    <PageFrame
      title="Welcome back"
      text="Continue your learning journey with your personal study materials."
    >
      <div className="stats">
        {stats.map(([num, label]) => (
          <Card key={label}>
            <strong>{loading ? "…" : num}</strong>
            <span>{label}</span>
          </Card>
        ))}
      </div>

      <SectionHeader
        title="Your Subjects"
        action="New Subject"
        onClick={() => go("subject")}
      />

      {loading ? (
        <Card style={{ padding: "2rem", textAlign: "center" }}>
          <p>Loading your study dashboard…</p>
        </Card>
      ) : safeSubjects.length === 0 ? (
        <Card className="form-card" style={{ textAlign: "center", padding: "2.5rem" }}>
          <BookOpen size={36} color="var(--primary)" style={{ margin: "0 auto 12px" }} />
          <h3>You haven't created any subjects yet</h3>
          <p>Create your first subject to start organizing your YouTube lectures and PDF course notes.</p>
          <div style={{ marginTop: "16px" }}>
            <Button onClick={() => go("subject")}>Create First Subject</Button>
          </div>
        </Card>
      ) : (
        <div className="subject-grid">
          {safeSubjects.map((subject) => (
            <Card key={subject.id} className="subject-card">
              <span className="subject-icon">
                <BookOpen />
              </span>
              <h3>{subject.name}</h3>
              <p>{subject.description || "No description provided."}</p>
              <div className="actions">
                <Button kind="primary" onClick={() => goToDetail("subject", "subjectId", subject.id)}>
                  Open Workspace
                </Button>
                <Button kind="secondary" onClick={() => goToDetail("chat", "subjectId", subject.id)}>
                  Search
                </Button>
              </div>
            </Card>
          ))}
          <button className="add-card" onClick={() => go("subject")}>
            <Plus />
            Add New Subject
          </button>
        </div>
      )}

      {error && <p className="error" style={{ marginTop: "16px" }}>{error}</p>}

      <div className="two-col" style={{ marginTop: "24px" }}>
        <Card>
          <SectionHeader title="Recent Materials (PDFs)" action="View All" onClick={() => go("materials")} />
          {safeMaterials.length === 0 ? (
            <p style={{ padding: "16px", color: "var(--muted)" }}>No study materials uploaded yet.</p>
          ) : (
            <div className="list">
              {safeMaterials.slice(0, 4).map((m) => (
                <div
                  key={m.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => goToDetail("document", "materialId", m.id, { page: "1", subjectId: m.subject_id || "" })}
                >
                  <span>
                    <FileText />
                  </span>
                  <p>
                    {m.filename}
                    <small>{m.page_count ?? 0} pages · {m.status}</small>
                  </p>
                  <ChevronRight />
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <SectionHeader title="Recent Playlists" action="View All" onClick={() => go("playlist")} />
          {safePlaylists.length === 0 ? (
            <p style={{ padding: "16px", color: "var(--muted)" }}>No YouTube playlists added yet.</p>
          ) : (
            <div className="list">
              {safePlaylists.slice(0, 4).map((p) => (
                <div
                  key={p.id}
                  style={{ cursor: "pointer" }}
                  onClick={() => goToDetail("playlist", "playlistId", p.id)}
                >
                  <span>
                    <Video />
                  </span>
                  <p>
                    {p.title || "YouTube Playlist"}
                    <small>{p.video_count ?? "—"} videos · {p.status}</small>
                  </p>
                  <ChevronRight />
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// Subjects & Subject Workspace
// ---------------------------------------------------------------------------

function Subject({ go }: { go: (p: Page) => void }) {
  const [subjects, setSubjects] = useState<SubjectRecord[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState("");
  const [successFeedback, setSuccessFeedback] = useState("");
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deletingSubId, setDeletingSubId] = useState<string | null>(null);

  // Specific subject workspace state
  const subjectId = useHashParam("subjectId");
  const [currentSubject, setCurrentSubject] = useState<SubjectRecord | null>(null);
  const [summary, setSummary] = useState<SubjectSummary | null>(null);
  const [subjectPlaylists, setSubjectPlaylists] = useState<PlaylistRecord[]>([]);
  const [subjectMaterials, setSubjectMaterials] = useState<MaterialRecord[]>([]);

  // Rename modal state
  const [editingSubject, setEditingSubject] = useState<SubjectRecord | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editMessage, setEditMessage] = useState("");
  const [savingEdit, setSavingEdit] = useState(false);

  // Semantic Search in Subject Workspace
  const [workspaceQuery, setWorkspaceQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<SearchResultItem[] | null>(null);
  const [searchStatusMsg, setSearchStatusMsg] = useState("");

  const refreshAllSubjects = () => {
    setLoading(true);
    api.getSubjects()
      .then(setSubjects)
      .catch((e) => setMessage(e instanceof Error ? e.message : "Could not load subjects. Please try again."))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refreshAllSubjects();
  }, []);

  // When subjectId changes, load workspace details
  useEffect(() => {
    if (!subjectId) {
      setCurrentSubject(null);
      setSummary(null);
      setSubjectPlaylists([]);
      setSubjectMaterials([]);
      setSearchResults(null);
      setWorkspaceQuery("");
      return;
    }

    Promise.all([
      api.getSubject(subjectId),
      api.getSubjectSummary(subjectId),
      api.getSubjectPlaylists(subjectId),
      api.getMaterials(subjectId),
    ])
      .then(([sub, sum, pls, mats]) => {
        setCurrentSubject(sub);
        setSummary(sum);
        setSubjectPlaylists(pls);
        setSubjectMaterials(mats);
      })
      .catch((e) => setMessage(e instanceof Error ? e.message : "Could not load subject workspace. Please try again."));
  }, [subjectId]);

  const handleCreateSubject = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return setMessage("Please enter a subject name.");
    setMessage("");
    setCreating(true);
    try {
      const item = await api.createSubject(name.trim(), description.trim() || undefined);
      setName("");
      setDescription("");
      setSuccessFeedback(`Subject "${item.name}" created successfully.`);
      refreshAllSubjects();
      goToDetail("subject", "subjectId", item.id);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not create subject. Please try again.");
    } finally {
      setCreating(false);
    }
  };

  const startEdit = (subject: SubjectRecord) => {
    setEditingSubject(subject);
    setEditName(subject.name);
    setEditDescription(subject.description || "");
    setEditMessage("");
  };

  const saveEdit = async () => {
    if (!editingSubject) return;
    if (!editName.trim()) return setEditMessage("Please enter a subject name.");
    setSavingEdit(true);
    try {
      const updated = await api.updateSubject(editingSubject.id, editName.trim(), editDescription.trim() || undefined);
      setSubjects((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      if (currentSubject?.id === updated.id) {
        setCurrentSubject(updated);
      }
      setEditingSubject(null);
      setSuccessFeedback(`Subject "${updated.name}" updated successfully.`);
    } catch (e) {
      setEditMessage(e instanceof Error ? e.message : "Could not update subject. Please try again.");
    } finally {
      setSavingEdit(false);
    }
  };

  const handleDeleteSubject = async (subject: SubjectRecord) => {
    const confirmed = window.confirm(
      `Delete this subject? Its playlists, videos, transcripts, and study materials will also be removed.`
    );
    if (!confirmed) return;

    setDeletingSubId(subject.id);
    setMessage("");
    try {
      await api.deleteSubject(subject.id);
      setSubjects((current) => current.filter((item) => item.id !== subject.id));
      setSuccessFeedback(`Subject "${subject.name}" was deleted successfully.`);
      if (subjectId === subject.id) {
        go("subject");
      }
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not delete this subject. Please try again.");
    } finally {
      setDeletingSubId(null);
    }
  };

  const handleWorkspaceSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!workspaceQuery.trim() || !subjectId) return;
    setSearching(true);
    setSearchStatusMsg("Searching your study materials...");
    setSearchResults(null);
    try {
      const resp = await api.searchSubject(subjectId, workspaceQuery.trim(), 5);
      const safeResults = Array.isArray(resp?.results) ? resp.results : [];
      setSearchResults(safeResults);
      if (safeResults.length === 0) {
        setSearchStatusMsg("No relevant study material found for this question.");
      } else {
        setSearchStatusMsg("");
      }
    } catch (err) {
      setSearchResults([]);
      setSearchStatusMsg("Search could not be completed. Please try again.");
    } finally {
      setSearching(false);
    }
  };

  // -------------------------------------------------------------------------
  // Render Specific Subject Workspace if subjectId is present
  // -------------------------------------------------------------------------
  if (subjectId && currentSubject) {
    return (
      <PageFrame
        title={currentSubject.name}
        text={currentSubject.description || "Central Subject Study Workspace"}
      >
        <div style={{ display: "flex", gap: "8px", marginBottom: "20px" }}>
          <Button kind="secondary" onClick={() => go("subject")}>
            ← All Subjects
          </Button>
          <Button kind="secondary" onClick={() => startEdit(currentSubject)}>
            Rename Subject
          </Button>
          <Button
            kind="ghost"
            disabled={deletingSubId === currentSubject.id}
            onClick={() => handleDeleteSubject(currentSubject)}
          >
            {deletingSubId === currentSubject.id ? "Deleting…" : "Delete Subject"}
          </Button>
        </div>

        {successFeedback && (
          <p className="badge success" style={{ padding: "8px 12px", display: "inline-block", marginBottom: "16px" }}>
            {successFeedback}
          </p>
        )}

        {summary && (
          <div className="stats">
            <Card>
              <strong>{summary.playlist_count}</strong>
              <span>Playlists</span>
            </Card>
            <Card>
              <strong>{summary.material_count}</strong>
              <span>Study Materials</span>
            </Card>
            <Card>
              <strong>{summary.processed_video_count}</strong>
              <span>Processed Videos</span>
            </Card>
          </div>
        )}

        {/* Embedded Phase 9 Semantic Search Workspace */}
        <Card className="form-card" style={{ marginTop: "20px", background: "#f8fafc", border: "1px solid #cbd5e1" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
            <Bot size={20} color="var(--primary)" />
            <h3 style={{ margin: 0 }}>Semantic Search ({currentSubject.name})</h3>
          </div>
          <p style={{ margin: "0 0 12px 0", fontSize: "0.875rem", color: "var(--muted)" }}>
            Search across your lecture videos and uploaded PDFs using natural language.
          </p>
          <form onSubmit={handleWorkspaceSearch} style={{ display: "flex", gap: "8px" }}>
            <input
              style={{ flex: 1, padding: "10px 14px", borderRadius: "6px", border: "1px solid var(--border)" }}
              value={workspaceQuery}
              disabled={searching}
              onChange={(e) => setWorkspaceQuery(e.target.value)}
              placeholder="e.g. What is virtual memory and deadlock avoidance?"
            />
            <Button type="submit" disabled={searching || !workspaceQuery.trim()}>
              <Search size={16} />
              {searching ? "Searching…" : "Search"}
            </Button>
          </form>

          {searchStatusMsg && (
            <p style={{ marginTop: "12px", color: searchResults?.length === 0 ? "var(--muted)" : "var(--primary)" }}>
              {searchStatusMsg}
            </p>
          )}

          {searchResults && searchResults.length > 0 && (
            <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "12px" }}>
              {searchResults.map((r, i) => (
                <SearchResultCard key={i} item={r} currentSubjectId={currentSubject.id} />
              ))}
            </div>
          )}
        </Card>

        {/* Playlists in this Subject */}
        <div style={{ marginTop: "24px" }}>
          <SectionHeader
            title="Connected Playlists"
            action="+ Add YouTube Playlist"
            onClick={() => goToDetail("add-playlist", "subjectId", currentSubject.id)}
          />
          {subjectPlaylists.length === 0 ? (
            <Card style={{ padding: "20px", textAlign: "center" }}>
              <p>No YouTube playlists added yet. Connect your course lecture videos to make them searchable.</p>
              <Button kind="secondary" onClick={() => goToDetail("add-playlist", "subjectId", currentSubject.id)}>
                + Add YouTube Playlist
              </Button>
            </Card>
          ) : (
            <div className="subject-grid">
              {subjectPlaylists.map((pl) => (
                <Card key={pl.id} className="subject-card">
                  <span className="subject-icon">
                    <Video />
                  </span>
                  <h3>{pl.title || "Untitled Playlist"}</h3>
                  <p>
                    {pl.video_count ?? 0} videos · Status:{" "}
                    <Badge tone={pl.status === "completed" ? "success" : pl.status === "partial_failure" ? "warning" : "pending"}>
                      {pl.status === "completed" ? "Ready" : pl.status === "partial_failure" ? "Partial" : pl.status}
                    </Badge>
                  </p>
                  <div className="actions">
                    <Button kind="primary" onClick={() => goToDetail("playlist", "playlistId", pl.id)}>
                      Open Playlist
                    </Button>
                    <Button kind="ghost" onClick={async () => {
                      if (window.confirm("Delete this playlist? Its videos and transcripts will also be removed.")) {
                        await api.deletePlaylist(pl.id);
                        api.getSubjectPlaylists(currentSubject.id).then(setSubjectPlaylists);
                      }
                    }}>
                      Delete
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>

        {/* Study Materials (PDFs) in this Subject */}
        <div style={{ marginTop: "24px" }}>
          <SectionHeader
            title="Uploaded Study Materials (PDFs)"
            action="+ Upload PDF"
            onClick={() => goToDetail("materials", "subjectId", currentSubject.id)}
          />
          {subjectMaterials.length === 0 ? (
            <Card style={{ padding: "20px", textAlign: "center" }}>
              <p>No study materials added yet. Upload your lecture notes or syllabus PDFs.</p>
              <Button kind="secondary" onClick={() => goToDetail("materials", "subjectId", currentSubject.id)}>
                + Upload Study Material (PDF)
              </Button>
            </Card>
          ) : (
            <Card className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Document</th>
                    <th>Pages</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {subjectMaterials.map((doc) => (
                    <tr key={doc.id}>
                      <td>
                        <FileText size={16} style={{ verticalAlign: "middle", marginRight: "8px" }} />
                        {doc.filename}
                      </td>
                      <td>{doc.page_count} pages</td>
                      <td>
                        <Badge tone={doc.status === "completed" ? "success" : "warning"}>
                          {doc.status === "completed" ? "Ready" : doc.status}
                        </Badge>
                      </td>
                      <td>
                        <Button
                          kind="secondary"
                          onClick={() => goToDetail("document", "materialId", doc.id, { page: "1", subjectId: currentSubject.id })}
                        >
                          View Document
                        </Button>
                        <Button kind="ghost" onClick={async () => {
                          if (window.confirm(`Delete this study material? Its extracted pages and search embeddings will also be removed.`)) {
                            await api.deleteMaterial(doc.id);
                            api.getMaterials(currentSubject.id).then(setSubjectMaterials);
                          }
                        }}>
                          Delete
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>

        {editingSubject && (
          <RenameModal
            subject={editingSubject}
            editName={editName}
            editDescription={editDescription}
            editMessage={editMessage}
            saving={savingEdit}
            onNameChange={setEditName}
            onDescriptionChange={setEditDescription}
            onSave={saveEdit}
            onCancel={() => setEditingSubject(null)}
          />
        )}
      </PageFrame>
    );
  }

  // -------------------------------------------------------------------------
  // Render Subjects List
  // -------------------------------------------------------------------------
  return (
    <PageFrame
      title="My Subjects"
      text="Organize your university courses, video playlists, and lecture notes."
    >
      {successFeedback && (
        <p className="badge success" style={{ padding: "8px 12px", display: "inline-block", marginBottom: "16px" }}>
          {successFeedback}
        </p>
      )}

      <Card className="form-card">
        <form onSubmit={handleCreateSubject}>
          <label>
            Subject Name *
            <input
              value={name}
              disabled={creating}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Operating Systems & Cloud Architecture"
              required
            />
          </label>
          <label>
            Description (optional)
            <input
              value={description}
              disabled={creating}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="e.g. Core computer science operating system principles and cloud notes"
            />
          </label>
          <Button type="submit" disabled={creating || !name.trim()}>
            {creating ? "Creating…" : "Create Subject"}
          </Button>
        </form>
        {message && <p className="error" style={{ marginTop: "12px" }}>{message}</p>}
      </Card>

      <div className="subject-grid" style={{ marginTop: "24px" }}>
        {subjects.map((subject) => (
          <Card key={subject.id} className="subject-card">
            <span className="subject-icon">
              <BookOpen />
            </span>
            <h3>{subject.name}</h3>
            <p>{subject.description || "No description yet."}</p>
            <div className="actions" style={{ flexWrap: "wrap", gap: "6px" }}>
              <Button kind="primary" onClick={() => goToDetail("subject", "subjectId", subject.id)}>
                Open Workspace
              </Button>
              <Button kind="secondary" onClick={() => startEdit(subject)}>
                Rename
              </Button>
              <Button kind="secondary" onClick={() => goToDetail("add-playlist", "subjectId", subject.id)}>
                + Playlist
              </Button>
              <Button kind="secondary" onClick={() => goToDetail("materials", "subjectId", subject.id)}>
                + PDF
              </Button>
              <Button kind="secondary" onClick={() => goToDetail("chat", "subjectId", subject.id)}>
                Search
              </Button>
              <Button
                kind="ghost"
                disabled={deletingSubId === subject.id}
                onClick={() => handleDeleteSubject(subject)}
              >
                {deletingSubId === subject.id ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {!loading && subjects.length === 0 && !message && (
        <Card style={{ padding: "2rem", textAlign: "center", marginTop: "24px" }}>
          <p>You haven't created any subjects yet. Enter a subject name above to get started.</p>
        </Card>
      )}

      {editingSubject && (
        <RenameModal
          subject={editingSubject}
          editName={editName}
          editDescription={editDescription}
          editMessage={editMessage}
          saving={savingEdit}
          onNameChange={setEditName}
          onDescriptionChange={setEditDescription}
          onSave={saveEdit}
          onCancel={() => setEditingSubject(null)}
        />
      )}
    </PageFrame>
  );
}

function RenameModal({
  subject,
  editName,
  editDescription,
  editMessage,
  saving,
  onNameChange,
  onDescriptionChange,
  onSave,
  onCancel,
}: {
  subject: SubjectRecord;
  editName: string;
  editDescription: string;
  editMessage: string;
  saving: boolean;
  onNameChange: (v: string) => void;
  onDescriptionChange: (v: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <Card className="modal form-card" style={{ textAlign: "left", width: "100%" }}>
        <button className="icon-button close" onClick={onCancel}>
          <X />
        </button>
        <h2>Rename Subject</h2>
        <label>
          Subject Name *
          <input
            value={editName}
            disabled={saving}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="e.g. Database Management Systems"
          />
        </label>
        <label>
          Description (optional)
          <input
            value={editDescription}
            disabled={saving}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder="What are you studying?"
          />
        </label>
        <div className="actions" style={{ marginTop: "16px" }}>
          <Button onClick={onSave} disabled={saving || !editName.trim()}>
            {saving ? "Saving…" : "Save Changes"}
          </Button>
          <Button kind="secondary" onClick={onCancel}>Cancel</Button>
        </div>
        {editMessage && <p className="error" style={{ marginTop: "12px" }}>{editMessage}</p>}
      </Card>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Add YouTube Playlist
// ---------------------------------------------------------------------------

function AddPlaylist({ go }: { go: (p: Page) => void }) {
  const [url, setUrl] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const urlSubjectId = useHashParam("subjectId");
  useEffect(() => {
    if (urlSubjectId) setSubjectId(urlSubjectId);
  }, [urlSubjectId]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!url.trim() || !subjectId.trim()) {
      return setError("Please select a subject and enter a public YouTube playlist URL.");
    }
    setSaving(true);
    setError("");
    try {
      const playlist = await api.createPlaylist(subjectId.trim(), url.trim());
      goToDetail("playlist", "playlistId", playlist.id, { subjectId });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add playlist. Please verify the URL and try again.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <PageFrame
      title="Add YouTube Playlist"
      text="Paste any public YouTube playlist URL. StudyRewind parses the videos and retrieves available captions for Study Search."
    >
      <div style={{ marginBottom: "16px" }}>
        {subjectId ? (
          <Button kind="secondary" onClick={() => goToDetail("subject", "subjectId", subjectId)}>
            ← Back to Subject Workspace
          </Button>
        ) : (
          <Button kind="secondary" onClick={() => go("playlist")}>
            ← Back to Playlists
          </Button>
        )}
      </div>

      <Card className="form-card">
        <form onSubmit={submit}>
          <label>
            Playlist URL *
            <input
              value={url}
              disabled={saving}
              onChange={(e) => {
                setUrl(e.target.value);
                setError("");
              }}
              placeholder="https://www.youtube.com/playlist?list=PL..."
              required
            />
          </label>
          <SubjectSelect required value={subjectId} onChange={setSubjectId} />
          <Button type="submit" disabled={saving || !url.trim() || !subjectId}>
            {saving ? "Adding & Analyzing Playlist…" : "Analyze Playlist"} <ChevronRight />
          </Button>
          {error && <p className="error" style={{ marginTop: "12px" }}>{error}</p>}
        </form>
      </Card>

      <Card className="how-card" style={{ marginTop: "24px" }}>
        <h2>HOW PLAYLIST INGESTION WORKS</h2>
        {[
          "Select the subject this playlist belongs to.",
          "Paste the public YouTube playlist URL.",
          "StudyRewind validates the playlist and fetches video metadata.",
          "Transcripts are automatically retrieved and segmented with exact timestamps.",
          "Ask questions in Semantic Search to jump to the exact video moment.",
        ].map((t, i) => (
          <div key={t}>
            <span>{i + 1}</span>
            {t}
          </div>
        ))}
      </Card>
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// Playlists & Videos
// ---------------------------------------------------------------------------

function Playlist({ go }: { go: (p: Page) => void }) {
  const [searchFilter, setSearchFilter] = useState("");
  const [playlists, setPlaylists] = useState<PlaylistRecord[]>([]);
  const [currentPlaylist, setCurrentPlaylist] = useState<PlaylistRecord | null>(null);
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [message, setMessage] = useState("");
  const [processingAll, setProcessingAll] = useState(false);
  const [retrievingId, setRetrievingId] = useState<string | null>(null);

  const playlistId = useHashParam("playlistId");
  const safeVideos = Array.isArray(videos) ? videos : [];

  useEffect(() => {
    api.getPlaylists()
      .then(setPlaylists)
      .catch((e) => setMessage(e instanceof Error ? e.message : "Could not load playlists. Please try again."));
  }, []);

  useEffect(() => {
    if (!playlistId) {
      setCurrentPlaylist(null);
      setVideos([]);
      return;
    }

    const loadPlaylistData = () => {
      Promise.all([
        api.getPlaylist(playlistId),
        api.getPlaylistVideos(playlistId),
      ])
        .then(([pl, vids]) => {
          setCurrentPlaylist(pl);
          setVideos(vids);
        })
        .catch((e) => setMessage(e instanceof Error ? e.message : "Could not load playlist videos. Please try again."));
    };

    loadPlaylistData();

    // Smart polling: only poll while at least one video is in progress
    const timer = window.setInterval(() => {
      api.getPlaylistVideos(playlistId)
        .then((vids) => {
          setVideos(vids);
        })
        .catch(() => undefined);
    }, 4000);

    return () => window.clearInterval(timer);
  }, [playlistId]);

  const retrieveAllTranscripts = async () => {
    if (!playlistId) return;
    setProcessingAll(true);
    setMessage("Retrieving available transcripts for every video in the playlist…");
    try {
      const summary = await api.processPlaylistTranscripts(playlistId);
      setMessage(summary.message || `Processed ${summary.completed}/${summary.total} videos.`);
      const vids = await api.getPlaylistVideos(playlistId);
      setVideos(vids);
    } catch (e) {
      setMessage("Transcript retrieval could not be completed. Please try again.");
    } finally {
      setProcessingAll(false);
    }
  };

  const retrieveOneTranscript = async (video: VideoRecord) => {
    setRetrievingId(video.id);
    setMessage(`Retrieving transcript for "${video.title}"…`);
    try {
      const result = await api.processVideoTranscript(video.id);
      setMessage(
        result.transcript_status === "available"
          ? `Transcript ready with ${result.chunk_count} timestamped segments.`
          : result.processing_error || "Transcript could not be retrieved."
      );
      if (playlistId) {
        const vids = await api.getPlaylistVideos(playlistId);
        setVideos(vids);
      }
    } catch (e) {
      setMessage("Transcript could not be retrieved. Please try again.");
    } finally {
      setRetrievingId(null);
    }
  };

  return (
    <PageFrame
      title={currentPlaylist ? (currentPlaylist.title || "Playlist Videos") : "Your Playlists"}
      text={
        currentPlaylist
          ? `Playlist ID: ${currentPlaylist.youtube_playlist_id} · Status: ${currentPlaylist.status}`
          : "Select a playlist to view its videos and timestamped transcripts."
      }
    >
      {!playlistId && (
        <>
          <div className="subject-grid">
            {playlists.map((p) => (
              <Card key={p.id} className="subject-card">
                <span className="subject-icon">
                  <Video />
                </span>
                <h3>{p.title || "Untitled Playlist"}</h3>
                <p>
                  {p.video_count ?? 0} videos · Status:{" "}
                  <Badge tone={p.status === "completed" ? "success" : p.status === "partial_failure" ? "warning" : "pending"}>
                    {p.status === "completed" ? "Ready" : p.status === "partial_failure" ? "Partial" : p.status}
                  </Badge>
                </p>
                <Button kind="secondary" onClick={() => goToDetail("playlist", "playlistId", p.id)}>
                  Open Playlist
                </Button>
              </Card>
            ))}
          </div>
          {playlists.length === 0 && (
            <Card style={{ padding: "2rem", textAlign: "center", marginTop: "16px" }}>
              <p>No YouTube playlists added yet. Open a subject workspace to add your first playlist.</p>
              <div style={{ marginTop: "12px" }}>
                <Button onClick={() => go("subject")}>Go to My Subjects</Button>
              </div>
            </Card>
          )}
        </>
      )}

      {message && <p className="error" style={{ margin: "16px 0" }}>{message}</p>}

      {playlistId && currentPlaylist && (
        <>
          <div style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
            <Button kind="secondary" onClick={() => go("playlist")}>
              ← All Playlists
            </Button>
            <Button disabled={processingAll} onClick={retrieveAllTranscripts}>
              {processingAll ? "Retrieving Transcripts…" : "Retrieve All Video Transcripts"}
            </Button>
          </div>

          <div className="stats" style={{ marginBottom: "20px" }}>
            <Card>
              <strong>{safeVideos.length}</strong>
              <span>Total Videos</span>
            </Card>
            <Card>
              <strong>{safeVideos.filter((v) => v && v.transcript_status === "available").length}</strong>
              <span>Available</span>
            </Card>
            <Card>
              <strong>{safeVideos.filter((v) => v && (v.transcript_status === "processing" || v.transcript_status === "pending")).length}</strong>
              <span>Processing / Queued</span>
            </Card>
            <Card>
              <strong>{safeVideos.filter((v) => v && (v.transcript_status === "failed" || v.transcript_status === "unavailable")).length}</strong>
              <span>Failed / Unavailable</span>
            </Card>
          </div>

          <div className="search wide" style={{ marginBottom: "16px" }}>
            <Search />
            <input
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Filter videos by title…"
            />
          </div>

          <Card className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Title</th>
                  <th>Duration</th>
                  <th>Transcript Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {safeVideos
                  .filter((v) => v && v.title && v.title.toLowerCase().includes(searchFilter.toLowerCase()))
                  .map((v, i) => (
                    <tr key={v.id}>
                      <td>{v.number ?? i + 1}</td>
                      <td>{v.title}</td>
                      <td>{formatDuration(v.duration_seconds)}</td>
                      <td>
                        <Badge
                          tone={
                            v.transcript_status === "available"
                              ? "success"
                              : v.transcript_status === "processing"
                              ? "warning"
                              : v.transcript_status === "pending"
                              ? "pending"
                              : "danger"
                          }
                        >
                          {v.transcript_status === "available"
                            ? "Transcript Available"
                            : v.transcript_status === "processing"
                            ? "Processing"
                            : v.transcript_status === "pending"
                            ? "Queued"
                            : "Unavailable"}
                        </Badge>
                      </td>
                      <td>
                        <Button
                          kind="secondary"
                          onClick={() =>
                            goToDetail("video", "videoId", v.id, {
                              playlistId,
                              title: v.title,
                              yt: v.youtube_video_id,
                            })
                          }
                        >
                          View Transcript
                        </Button>
                        <Button
                          kind="ghost"
                          disabled={retrievingId === v.id}
                          onClick={() => retrieveOneTranscript(v)}
                        >
                          {retrievingId === v.id
                            ? "Retrieving…"
                            : v.transcript_status === "available"
                            ? "Refresh"
                            : "Retrieve"}
                        </Button>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// Video Transcript Player View
// ---------------------------------------------------------------------------

function VideoPage() {
  const [time, setTime] = useState(0);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [filterText, setFilterText] = useState("");

  const videoId = useHashParam("videoId");
  const initialTime = useHashParam("t");
  const videoTitleParam = useHashParam("title");
  const ytVideoIdParam = useHashParam("yt");
  const playlistIdParam = useHashParam("playlistId");

  useEffect(() => {
    if (initialTime) {
      const parsed = parseFloat(initialTime);
      if (!isNaN(parsed) && parsed >= 0) {
        setTime(parsed);
      }
    }
  }, [initialTime]);

  useEffect(() => {
    if (!videoId) {
      setMessage("Please open a video from your playlist.");
      return;
    }

    setLoading(true);
    api.getVideoTranscript(videoId)
      .then((res) => {
        const rawSegments = Array.isArray(res?.data)
          ? res.data
          : Array.isArray(res)
          ? (res as unknown as TranscriptSegment[])
          : [];
        setSegments(rawSegments);
        if (rawSegments.length > 0 && !initialTime) {
          setTime(rawSegments[0].start_time_seconds);
        }
      })
      .catch(() => {
        setSegments([]);
        setMessage("Transcript could not be loaded. Click below to retrieve.");
      })
      .finally(() => setLoading(false));

    api.getVideoTranscriptStatus(videoId)
      .then((status) => {
        if (status && status.transcript_status !== "available") {
          setMessage(status.processing_error || "Transcript is not ready yet. Click below to retrieve.");
        }
      })
      .catch(() => undefined);
  }, [videoId]);

  const handleRetrieve = async () => {
    if (!videoId) return;
    setLoading(true);
    setMessage("Retrieving transcript captions…");
    try {
      const res = await api.processVideoTranscript(videoId);
      if (res && res.transcript_status === "available") {
        const tr = await api.getVideoTranscript(videoId);
        const rawSegments = Array.isArray(tr?.data)
          ? tr.data
          : Array.isArray(tr)
          ? (tr as unknown as TranscriptSegment[])
          : [];
        setSegments(rawSegments);
        setMessage("Transcript ready!");
      } else {
        setSegments([]);
        setMessage("Transcript could not be retrieved. Please try again.");
      }
    } catch (e) {
      setSegments([]);
      setMessage("Transcript could not be retrieved. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const safeSegments = Array.isArray(segments) ? segments : [];
  const filteredSegments = safeSegments.filter((s) =>
    s && typeof s.text === "string"
      ? s.text.toLowerCase().includes(filterText.toLowerCase())
      : false
  );

  const displayTitle = videoTitleParam || "Video Transcript";

  return (
    <PageFrame
      title={displayTitle}
      text="Timestamped lecture transcript with jump-to-source navigation."
    >
      <div style={{ marginBottom: "16px" }}>
        {playlistIdParam ? (
          <Button kind="secondary" onClick={() => goToDetail("playlist", "playlistId", playlistIdParam)}>
            ← Back to Playlist
          </Button>
        ) : (
          <Button kind="secondary" onClick={() => history.back()}>
            ← Back
          </Button>
        )}
      </div>

      <div className="media-layout">
        <Card className="player">
          <div className="video-surface" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <Play size={40} />
            {ytVideoIdParam && (
              <a
                href={`https://www.youtube.com/watch?v=${ytVideoIdParam}&t=${Math.floor(time)}s`}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  color: "#fff",
                  fontSize: "0.85rem",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                  background: "rgba(0,0,0,0.5)",
                  padding: "6px 12px",
                  borderRadius: "6px",
                  marginTop: "8px",
                }}
              >
                Watch on YouTube at {formatTimestamp(time)} <ExternalLink size={14} />
              </a>
            )}
          </div>
          <input
            aria-label="Video position"
            type="range"
            min="0"
            max={safeSegments.length > 0 ? Math.ceil(safeSegments[safeSegments.length - 1].end_time_seconds) : 1000}
            value={time}
            onChange={(e) => setTime(+e.target.value)}
          />
          <div className="controls">
            <button title="Play/Pause">
              <Play />
            </button>
            <span>
              Current Position: {formatTimestamp(time)}
            </span>
          </div>
        </Card>

        <Card className="transcript">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h3 style={{ margin: 0 }}>Transcript Segments ({safeSegments.length})</h3>
            {safeSegments.length === 0 && (
              <Button kind="secondary" disabled={loading} onClick={handleRetrieve}>
                {loading ? "Retrieving…" : "Retrieve Transcript"}
              </Button>
            )}
          </div>

          {message && <p className="error" style={{ margin: "8px 0" }}>{message}</p>}

          <div className="search" style={{ marginTop: "12px", marginBottom: "12px" }}>
            <Search />
            <input
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Search words in transcript…"
            />
          </div>

          <div style={{ maxHeight: "450px", overflowY: "auto", display: "flex", flexDirection: "column", gap: "6px" }}>
            {filteredSegments.map((seg, i) => {
              const isCurrent = time >= seg.start_time_seconds && time <= seg.end_time_seconds;
              return (
                <button
                  key={seg.segment_index ?? i}
                  className={isCurrent ? "selected" : ""}
                  style={{ textAlign: "left", padding: "8px 12px", borderRadius: "6px", cursor: "pointer" }}
                  onClick={() => setTime(seg.start_time_seconds)}
                >
                  <b>[{formatTimestamp(seg.start_time_seconds)} – {formatTimestamp(seg.end_time_seconds)}] </b>
                  <span>{seg.text}</span>
                </button>
              );
            })}
            {safeSegments.length > 0 && filteredSegments.length === 0 && (
              <p style={{ color: "var(--muted)", padding: "12px" }}>No lines match your search filter.</p>
            )}
            {safeSegments.length === 0 && !loading && !message && (
              <p style={{ color: "var(--muted)", padding: "12px" }}>No transcript segments found for this video.</p>
            )}
          </div>
        </Card>
      </div>
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// Study Materials (PDF Upload & Listing)
// ---------------------------------------------------------------------------

function Materials({ go }: { go: (p: Page) => void }) {
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [subjectId, setSubjectId] = useState("");
  const [materials, setMaterials] = useState<MaterialRecord[]>([]);
  const [message, setMessage] = useState("");
  const [successFeedback, setSuccessFeedback] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deletingDocId, setDeletingDocId] = useState<string | null>(null);

  const hashSubId = useHashParam("subjectId");
  useEffect(() => {
    if (hashSubId) setSubjectId(hashSubId);
  }, [hashSubId]);

  const refreshMaterials = () => {
    api.getMaterials(subjectId || undefined)
      .then(setMaterials)
      .catch((e) => setMessage(e instanceof Error ? e.message : "Could not load study materials. Please try again."));
  };

  useEffect(() => {
    refreshMaterials();
  }, [subjectId]);

  const handleUpload = async () => {
    if (!file || !subjectId.trim()) {
      setMessage("Please choose a PDF file and select the subject first.");
      return;
    }
    setUploading(true);
    setMessage("");
    try {
      const res = await api.uploadMaterial(subjectId.trim(), file);
      setSuccessFeedback(`PDF "${res.filename}" uploaded successfully (${res.page_count} pages extracted).`);
      setFile(null);
      refreshMaterials();
    } catch (e) {
      setMessage("Could not process this PDF. Please check the file and try again.");
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (doc: MaterialRecord) => {
    const confirmed = window.confirm(
      `Delete this study material? Its extracted pages and search embeddings will also be removed.`
    );
    if (!confirmed) return;

    setDeletingDocId(doc.id);
    try {
      await api.deleteMaterial(doc.id);
      setSuccessFeedback(`Study material "${doc.filename}" deleted successfully.`);
      refreshMaterials();
    } catch (e) {
      setMessage("Could not delete this study material. Please try again.");
    } finally {
      setDeletingDocId(null);
    }
  };

  return (
    <PageFrame
      title="Study Materials (PDFs)"
      text="Upload your lecture notes, textbooks, and syllabus PDFs (up to 50MB)."
    >
      <div style={{ marginBottom: "16px" }}>
        {subjectId ? (
          <Button kind="secondary" onClick={() => goToDetail("subject", "subjectId", subjectId)}>
            ← Back to Subject Workspace
          </Button>
        ) : (
          <Button kind="secondary" onClick={() => go("subject")}>
            ← My Subjects
          </Button>
        )}
      </div>

      {successFeedback && (
        <p className="badge success" style={{ padding: "8px 12px", display: "inline-block", marginBottom: "16px" }}>
          {successFeedback}
        </p>
      )}

      <Card
        className={`dropzone ${drag ? "drag" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const droppedFile = e.dataTransfer.files[0];
          if (droppedFile && droppedFile.type === "application/pdf") {
            setFile(droppedFile);
          } else {
            setMessage("Only PDF files are supported.");
          }
        }}
      >
        <Upload />
        <h3>Drag & drop your PDF file here</h3>
        <p>PDF only · Maximum 50 MB</p>
        <label className="button secondary" style={{ marginTop: "8px" }}>
          Choose PDF
          <input
            hidden
            type="file"
            accept="application/pdf,.pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
        </label>
        {file && (
          <p style={{ marginTop: "8px", fontWeight: "bold", color: "var(--primary)" }}>
            Selected: {file.name} ({(file.size / (1024 * 1024)).toFixed(2)} MB)
          </p>
        )}
      </Card>

      <Card className="form-card" style={{ marginTop: "20px" }}>
        <SubjectSelect required value={subjectId} onChange={setSubjectId} />
        <div className="actions" style={{ marginTop: "12px" }}>
          <Button disabled={uploading || !file || !subjectId} onClick={handleUpload}>
            {uploading ? "Uploading & Extracting PDF…" : "Upload and Process PDF"}
          </Button>
          <Button kind="secondary" onClick={refreshMaterials}>
            Refresh List
          </Button>
        </div>
        {message && <p className="error" style={{ marginTop: "12px" }}>{message}</p>}
      </Card>

      <SectionHeader title="Uploaded Study Materials" />
      <Card className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Material</th>
              <th>Pages</th>
              <th>Status</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {materials.map((r) => (
              <tr key={r.id}>
                <td>
                  <FileText size={16} style={{ verticalAlign: "middle", marginRight: "8px" }} />
                  {r.filename}
                </td>
                <td>{r.page_count ?? "—"} pages</td>
                <td>
                  <Badge tone={r.status === "completed" ? "success" : "warning"}>
                    {r.status === "completed" ? "Ready" : r.status}
                  </Badge>
                  {r.processing_error && <small> · {r.processing_error}</small>}
                </td>
                <td>
                  <Button
                    kind="secondary"
                    onClick={() => goToDetail("document", "materialId", r.id, { page: "1", subjectId })}
                  >
                    View Document
                  </Button>
                  <Button
                    kind="ghost"
                    disabled={deletingDocId === r.id}
                    onClick={() => handleDelete(r)}
                  >
                    {deletingDocId === r.id ? "Deleting…" : "Delete"}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {materials.length === 0 && (
          <p style={{ padding: "16px", color: "var(--muted)" }}>No study materials added yet.</p>
        )}
      </Card>
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// PDF Document Page Viewer
// ---------------------------------------------------------------------------

function Document() {
  const [page, setPage] = useState(1);
  const [docInfo, setDocInfo] = useState<MaterialRecord | null>(null);
  const [text, setText] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const materialId = useHashParam("materialId");
  const hashPage = useHashParam("page");
  const subjectIdParam = useHashParam("subjectId");

  useEffect(() => {
    if (hashPage) {
      const p = parseInt(hashPage, 10);
      if (!isNaN(p) && p > 0) setPage(p);
    }
  }, [hashPage]);

  useEffect(() => {
    if (!materialId) {
      setMessage("Please open a document from your uploaded materials.");
      return;
    }

    api.getMaterial(materialId)
      .then(setDocInfo)
      .catch((e) => setMessage(e instanceof Error ? e.message : "Could not load document details. Please try again."));
  }, [materialId]);

  useEffect(() => {
    if (!materialId) return;

    setLoading(true);
    api.getMaterialPage(materialId, page)
      .then((data) => {
        setText(data.text || "No text was extracted from this physical page.");
        setMessage("");
      })
      .catch(() => {
        setText("");
        setMessage("Could not load this page. Please try again.");
      })
      .finally(() => setLoading(false));
  }, [materialId, page]);

  const maxPages = docInfo?.page_count || 1;

  return (
    <PageFrame
      title={docInfo?.filename || "Study Material Viewer"}
      text={`Physical Page ${page} of ${maxPages} (Page Provenance Preserved)`}
    >
      <div style={{ marginBottom: "16px" }}>
        {subjectIdParam ? (
          <Button kind="secondary" onClick={() => goToDetail("subject", "subjectId", subjectIdParam)}>
            ← Back to Subject Workspace
          </Button>
        ) : (
          <Button kind="secondary" onClick={() => history.back()}>
            ← Back
          </Button>
        )}
      </div>

      <Card className="document">
        <div className="thumbnails">
          {Array.from({ length: maxPages }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              className={page === n ? "selected" : ""}
              onClick={() => setPage(n)}
            >
              Page {n}
            </button>
          ))}
        </div>

        <article>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ margin: 0 }}>Extracted Content (Page {page} of {maxPages})</h3>
            <div className="doc-nav">
              <Button
                kind="secondary"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                ← Previous Page
              </Button>
              <Button
                kind="secondary"
                disabled={page >= maxPages}
                onClick={() => setPage((p) => Math.min(maxPages, p + 1))}
              >
                Next Page →
              </Button>
            </div>
          </div>

          {loading && <p>Loading page {page} text…</p>}
          {message && <p className="error">{message}</p>}
          {!loading && text && (
            <pre style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", lineHeight: "1.7", color: "var(--text)" }}>
              {text}
            </pre>
          )}
        </article>
      </Card>
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// Semantic Search Component (Phase 9 Integration)
// ---------------------------------------------------------------------------

function Chat({ go }: { go: (p: Page) => void }) {
  const [question, setQuestion] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [results, setResults] = useState<SearchResultItem[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  const urlSubjectId = useHashParam("subjectId");
  const urlQuery = useHashParam("q");

  useEffect(() => {
    if (urlSubjectId) setSubjectId(urlSubjectId);
    if (urlQuery) setQuestion(urlQuery);
  }, [urlSubjectId, urlQuery]);

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    if (!subjectId) {
      setStatusMessage("Please select a subject to search within.");
      return;
    }

    setSearching(true);
    setStatusMessage("Searching your study materials...");
    setResults(null);
    try {
      const resp = await api.searchSubject(subjectId, question.trim(), 5);
      const safeResults = Array.isArray(resp?.results) ? resp.results : [];
      setResults(safeResults);
      if (safeResults.length === 0) {
        setStatusMessage("No relevant study material found for this question.");
      } else {
        setStatusMessage("");
      }
    } catch (error) {
      setResults([]);
      setStatusMessage("Search could not be completed. Please try again.");
    } finally {
      setSearching(false);
    }
  };

  return (
    <div className="chat-page">
      <div className="chat-subject">
        <SubjectSelect value={subjectId} onChange={setSubjectId} required />
      </div>

      <div className="messages">
        <div className="message ai-msg">
          <div className="ai-head">
            <Search /> Semantic Search Engine
          </div>
          <p>
            {statusMessage ||
              "Ask questions about your study topics. StudyRewind retrieves exact YouTube video timestamps and PDF document pages."}
          </p>

          {results && results.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginTop: "16px" }}>
              {results.map((r, idx) => (
                <SearchResultCard key={idx} item={r} currentSubjectId={subjectId} />
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="suggestions">
        <button onClick={() => setQuestion("What is virtual memory and deadlock avoidance?")}>
          What is virtual memory and deadlock avoidance?
        </button>
        <button onClick={() => setQuestion("What are sequence diagrams and class diagrams in UML?")}>
          What are sequence diagrams and class diagrams in UML?
        </button>
      </div>

      <form className="chat-input" onSubmit={handleSearch}>
        <input
          value={question}
          disabled={searching}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask anything about your coursework..."
        />
        <Button type="submit" disabled={searching || !question.trim() || !subjectId}>
          <Send />
        </Button>
      </form>
    </div>
  );
}

function SearchResultCard({
  item,
  currentSubjectId,
}: {
  item: SearchResultItem;
  currentSubjectId?: string;
}) {
  const matchPct = Math.round(item.score * 100);

  if (item.source_type === "youtube") {
    const startTimeStr = formatTimestamp(item.transcript.start_time);
    const endTimeStr = formatTimestamp(item.transcript.end_time);

    return (
      <div className="source-card">
        <span>
          <Video />
        </span>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Badge tone="success">YouTube Video</Badge>
            <small style={{ fontWeight: "bold", color: "var(--primary)" }}>{matchPct}% Match</small>
          </div>
          <b style={{ display: "block", marginTop: "4px" }}>{item.video.title}</b>
          <p style={{ margin: "4px 0", color: "var(--navy)", fontWeight: 600 }}>
            Timestamp: {startTimeStr} – {endTimeStr}
          </p>
          <p style={{ margin: "4px 0", fontStyle: "italic" }}>"{item.transcript.text}"</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <Button
            kind="secondary"
            onClick={() => {
              goToDetail("video", "videoId", item.video.id, {
                t: String(Math.floor(item.transcript.start_time)),
                title: item.video.title,
                yt: item.video.youtube_video_id,
              });
            }}
          >
            Open at Timestamp
          </Button>
          <a
            href={`https://www.youtube.com/watch?v=${item.video.youtube_video_id}&t=${Math.floor(item.transcript.start_time)}s`}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              fontSize: "0.75rem",
              color: "var(--primary)",
              textAlign: "center",
              textDecoration: "underline",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "2px",
            }}
          >
            YouTube ↗
          </a>
        </div>
      </div>
    );
  }

  // PDF Search Result
  return (
    <div className="source-card">
      <span>
        <FileText />
      </span>
      <div style={{ flex: 1 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <Badge tone="warning">PDF Document</Badge>
          <small style={{ fontWeight: "bold", color: "var(--primary)" }}>{matchPct}% Match</small>
        </div>
        <b style={{ display: "block", marginTop: "4px" }}>{item.document.filename}</b>
        <p style={{ margin: "4px 0", color: "var(--navy)", fontWeight: 600 }}>
          Physical Page: {item.page_number}
        </p>
        <p style={{ margin: "4px 0", fontStyle: "italic" }}>"{item.text}"</p>
      </div>
      <Button
        kind="secondary"
        onClick={() => {
          goToDetail("document", "materialId", item.document.id, {
            page: String(item.page_number),
            subjectId: currentSubjectId || "",
          });
        }}
      >
        Open Page {item.page_number}
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Learning Insights Placeholder
// ---------------------------------------------------------------------------

function Insights() {
  return (
    <PageFrame
      title="Learning Insights"
      text="Personalized learning recommendations based on your revision history."
    >
      <Card>
        <p>
          Learning insights will appear when real study query data accumulates in your account.
          StudyRewind never displays synthetic or fake insights.
        </p>
      </Card>
    </PageFrame>
  );
}

// ---------------------------------------------------------------------------
// Authentication (Login & Register)
// ---------------------------------------------------------------------------

function Login({
  go,
  signup = false,
  onAuthenticated,
}: {
  go: (p: Page) => void;
  signup?: boolean;
  onAuthenticated: (user: User) => void;
}) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setMessage("");

    if (signup && password !== confirmPassword) {
      setMessage("Passwords do not match. Please try again.");
      return;
    }

    if (password.length < 8) {
      setMessage("Password must be at least 8 characters long.");
      return;
    }

    setLoading(true);
    try {
      if (signup) {
        await api.register(email, password, name.trim() || undefined);
      }
      await api.login(email, password);
      const user = await api.getMe();
      onAuthenticated(user);
      go("dashboard");
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Authentication failed.";
      const lower = errMsg.toLowerCase();
      if (
        lower.includes("already registered") ||
        lower.includes("already exists") ||
        lower.includes("conflict") ||
        lower.includes("409")
      ) {
        setMessage("An account with this email already exists. Please sign in.");
      } else if (
        lower.includes("invalid") ||
        lower.includes("credentials") ||
        lower.includes("incorrect") ||
        lower.includes("401")
      ) {
        setMessage("Invalid email or password. Please check your credentials and try again.");
      } else if (
        lower.includes("network") ||
        lower.includes("connect") ||
        lower.includes("failed to fetch") ||
        lower.includes("server running") ||
        lower.includes("abort")
      ) {
        setMessage("Unable to connect to StudyRewind. Please check your connection and try again.");
      } else {
        setMessage(errMsg || "Authentication failed. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth">
      <div className="auth-form">
        <StudyRewindLogo size="lg" />
        <h1>{signup ? "Create your account" : "Welcome back"}</h1>
        <p>
          {signup
            ? "Start your university study journey with StudyRewind."
            : "Sign in to access your course materials and timestamped videos."}
        </p>
        <form onSubmit={handleSubmit}>
          {signup && (
            <label>
              Full Name
              <input
                value={name}
                disabled={loading}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Alex Morgan"
              />
            </label>
          )}
          <label>
            Email Address *
            <input
              type="email"
              required
              disabled={loading}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@university.edu"
            />
          </label>
          <label>
            Password (min 8 characters) *
            <input
              type="password"
              required
              disabled={loading}
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </label>
          {signup && (
            <label>
              Confirm Password *
              <input
                type="password"
                required
                disabled={loading}
                minLength={8}
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
              />
            </label>
          )}
          <Button type="submit" disabled={loading}>
            {loading ? "Please wait…" : signup ? "Create Account" : "Sign In"}
          </Button>
          {message && <p className="error" style={{ marginTop: "12px" }}>{message}</p>}
        </form>
        <p className="auth-switch">
          {signup ? "Already have an account?" : "Don’t have an account?"}{" "}
          <button onClick={() => go(signup ? "login" : "signup")}>
            {signup ? "Sign in" : "Sign up"}
          </button>
        </p>
      </div>

      <div className="auth-art">
        <StudyRewindLogo variant="white" size="lg" />
        <h2>
          Your Personal
          <br />
          Study Assistant
        </h2>
        <p>Upload lecture notes. Search YouTube playlists. Learn faster.</p>
        <div className="art-card">
          <Bot />
          <span>Jump straight to the exact moment a concept was explained.</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// App Entrypoint
// ---------------------------------------------------------------------------

function App() {
  const [page, go] = usePage();
  const [user, setUser] = useState<User | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let isMounted = true;
    const safetyTimer = setTimeout(() => {
      if (isMounted) {
        setCheckingSession(false);
      }
    }, 4000);

    const token = api.getToken();
    if (!token) {
      setUser(null);
      setCheckingSession(false);
      clearTimeout(safetyTimer);
      return;
    }

    api.getMe()
      .then((u) => {
        if (isMounted) setUser(u);
      })
      .catch(() => {
        api.clearToken();
        if (isMounted) setUser(null);
      })
      .finally(() => {
        clearTimeout(safetyTimer);
        if (isMounted) setCheckingSession(false);
      });

    return () => {
      isMounted = false;
      clearTimeout(safetyTimer);
    };
  }, []);

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    go("login");
  };

  if (page === "landing") return <Landing go={go} user={user} />;

  if (checkingSession) {
    return (
      <div className="auth">
        <div className="auth-form" style={{ textAlign: "center" }}>
          <StudyRewindLogo size="lg" />
          <h2 style={{ marginTop: "20px" }}>Checking your session…</h2>
        </div>
      </div>
    );
  }

  // If user is already authenticated and visits login or signup, render dashboard
  if (user && (page === "login" || page === "signup")) {
    return (
      <Shell page="dashboard" go={go} user={user} onLogout={handleLogout}>
        <Dashboard go={go} />
      </Shell>
    );
  }

  // Redirect unauthenticated users trying to access protected workspace
  if (!user) {
    return <Login go={go} signup={page === "signup"} onAuthenticated={setUser} />;
  }

  const content =
    page === "dashboard" ? (
      <Dashboard go={go} />
    ) : page === "subject" ? (
      <Subject go={go} />
    ) : page === "add-playlist" ? (
      <AddPlaylist go={go} />
    ) : page === "playlist" ? (
      <Playlist go={go} />
    ) : page === "materials" ? (
      <Materials go={go} />
    ) : page === "chat" ? (
      <Chat go={go} />
    ) : page === "video" ? (
      <VideoPage />
    ) : page === "document" ? (
      <Document />
    ) : (
      <Insights />
    );

  return (
    <Shell page={page} go={go} user={user} onLogout={handleLogout}>
      {content}
    </Shell>
  );
}

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error("StudyRewind React ErrorBoundary caught an error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "40px", maxWidth: "600px", margin: "40px auto", textAlign: "center", fontFamily: "inherit" }}>
          <StudyRewindLogo size="lg" />
          <h2 style={{ marginTop: "24px", color: "var(--navy)" }}>Something went wrong while loading this view</h2>
          <p style={{ color: "var(--muted)", margin: "12px 0 20px" }}>
            {this.state.error?.message || "An unexpected error occurred."}
          </p>
          <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
            <button
              className="button primary"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.hash = "/dashboard";
                window.location.reload();
              }}
            >
              Reload Dashboard
            </button>
            <button
              className="button secondary"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                api.clearToken();
                window.location.hash = "/login";
                window.location.reload();
              }}
            >
              Sign In Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function SafeApp() {
  return (
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  );
}
