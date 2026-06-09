from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float, ForeignKey, Enum, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import enum
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./video_nuggets.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class VideoStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DRAFT = "draft"


class ContentSource(enum.Enum):
    BIBLE_SCRAPE = "bible_scrape"
    PDF_UPLOAD = "pdf_upload"
    PPTX_UPLOAD = "pptx_upload"
    TXT_UPLOAD = "txt_upload"
    IMAGE_UPLOAD = "image_upload"
    URL_UPLOAD = "url_upload"


class DifficultyLevel(enum.Enum):
    BASIC = "basic"
    PLATFORM_DEEP_DIVE = "platform_deep_dive"
    ADVANCED = "advanced"


class Visibility(enum.Enum):
    PUBLIC = "public"
    PRIVATE = "private"


class UserRole(enum.Enum):
    GUEST = "guest"
    VIEWER = "viewer"
    ADMIN = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.GUEST)
    display_name = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    section_key = Column(String(200), nullable=True, index=True)
    source_type = Column(Enum(ContentSource), nullable=False)
    status = Column(Enum(VideoStatus), default=VideoStatus.PENDING)
    video_path = Column(String(1000), nullable=True)
    thumbnail_path = Column(String(1000), nullable=True)
    transcript_path = Column(String(1000), nullable=True)
    slides_path = Column(String(1000), nullable=True)
    duration_seconds = Column(Float, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id"), nullable=True, index=True)
    difficulty_level = Column(Enum(DifficultyLevel), default=DifficultyLevel.BASIC)
    visibility = Column(Enum(Visibility), default=Visibility.PUBLIC)
    playlist_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions = relationship("VideoVersion", back_populates="video")
    playlist = relationship("Playlist", back_populates="videos")


class VideoVersion(Base):
    __tablename__ = "video_versions"

    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    video_path = Column(String(1000), nullable=False)
    transcript_path = Column(String(1000), nullable=True)
    slides_path = Column(String(1000), nullable=True)
    content_hash = Column(String(64), nullable=True)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    video = relationship("Video", back_populates="versions")


class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    order_index = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    videos = relationship("Video", back_populates="playlist")


class ContentSnapshot(Base):
    __tablename__ = "content_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    section_key = Column(String(200), nullable=False, index=True)
    section_title = Column(String(500), nullable=False)
    content_hash = Column(String(64), nullable=False)
    content_text = Column(Text, nullable=True)
    url = Column(String(1000), nullable=True)
    last_checked = Column(DateTime, default=datetime.utcnow)
    last_changed = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MonitorRunStatus(enum.Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


class MonitorRun(Base):
    """Audit log for one execution of the Cloud Bible content monitor.

    Each scheduled or manually-triggered check writes exactly one row here so
    the admin Monitor page can show: when it ran, whether it succeeded, and
    whether the live website matches the local PDF baseline.
    """
    __tablename__ = "monitor_runs"

    id = Column(Integer, primary_key=True, index=True)
    started_at = Column(DateTime, default=datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True)
    status = Column(Enum(MonitorRunStatus), default=MonitorRunStatus.RUNNING)
    triggered_by = Column(String(50), default="scheduler")  # 'scheduler' | 'manual:<username>'
    error_message = Column(Text, nullable=True)
    sections_checked = Column(Integer, default=0)
    web_drift_count = Column(Integer, default=0)        # sections whose website hash changed since last run
    pdf_match = Column(Boolean, nullable=True)          # True = website == PDF; False = differences; None = compare not run
    pdf_drift_count = Column(Integer, default=0)        # sections where website differs from PDF baseline
    drift_details = Column(Text, nullable=True)         # JSON: [{section_key, title, kind, web_changed, pdf_match, summary}, ...]


class MonitorRunVideoJobStatus(enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class MonitorRunVideoJob(Base):
    """One admin-triggered "apply this drift to a video" task.

    Created when the admin clicks "Apply changes to N videos" in the Monitor
    UI. Each row tracks one section's regen (or fresh-create) end-to-end so
    the frontend can poll status pills per section.
    """
    __tablename__ = "monitor_run_video_jobs"

    id = Column(Integer, primary_key=True, index=True)
    monitor_run_id = Column(Integer, ForeignKey("monitor_runs.id"), nullable=False, index=True)
    section_key = Column(String(200), nullable=False)
    section_title = Column(String(500), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=True)
    action = Column(String(20), nullable=False)  # 'update' | 'create'
    status = Column(Enum(MonitorRunVideoJobStatus), default=MonitorRunVideoJobStatus.QUEUED, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

    messages = relationship("ChatMessage", back_populates="session")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    cited_videos = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


def init_db():
    Base.metadata.create_all(bind=engine)
    _apply_lightweight_migrations()


def _apply_lightweight_migrations() -> None:
    """Lightweight schema cleanup for older dev databases.

    The email-notification feature was removed in 2026-04-30. If the legacy
    `email_config` table is still around, drop it. Orphan email_* columns on
    `monitor_runs` are harmless (always NULL) and SQLite < 3.35 cannot drop
    columns, so we leave them in place rather than rebuilding the table.
    """
    from sqlalchemy import text, inspect

    insp = inspect(engine)
    if insp.has_table("email_config"):
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE email_config"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
