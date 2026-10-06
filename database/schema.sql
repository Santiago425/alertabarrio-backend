-- AlertaBarrio - esquema de base de datos (PostgreSQL)
-- Generado con: pg_dump --schema-only (desde los modelos SQLAlchemy del backend)


\restrict oMZMg20deocVRTzEatwVTf8jhXP13Uulx6RdDUnexRz69Eb6Gob7bTY4JPIialw

CREATE TABLE public.ai_analyses (
    id integer NOT NULL,
    analysis_type character varying(30) NOT NULL,
    report_id integer,
    neighborhood_id integer,
    model_name character varying(100) NOT NULL,
    latency_ms integer,
    result json,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.ai_analyses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.ai_analyses_id_seq OWNED BY public.ai_analyses.id;

CREATE TABLE public.daily_summaries (
    id integer NOT NULL,
    neighborhood_id integer NOT NULL,
    summary_date date NOT NULL,
    summary_text text NOT NULL,
    reports_count integer NOT NULL,
    model_name character varying(100) NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.daily_summaries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.daily_summaries_id_seq OWNED BY public.daily_summaries.id;

CREATE TABLE public.incident_types (
    id integer NOT NULL,
    code character varying(40) NOT NULL,
    name character varying(80) NOT NULL,
    severity_level smallint NOT NULL,
    color character varying(7) NOT NULL,
    CONSTRAINT ck_severity_range CHECK (((severity_level >= 1) AND (severity_level <= 5)))
);

CREATE SEQUENCE public.incident_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.incident_types_id_seq OWNED BY public.incident_types.id;

CREATE TABLE public.neighborhood_connections (
    id integer NOT NULL,
    from_neighborhood_id integer NOT NULL,
    to_neighborhood_id integer NOT NULL,
    distance_meters double precision NOT NULL,
    road_name character varying(120),
    CONSTRAINT ck_connection_not_self CHECK ((from_neighborhood_id <> to_neighborhood_id))
);

CREATE SEQUENCE public.neighborhood_connections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.neighborhood_connections_id_seq OWNED BY public.neighborhood_connections.id;

CREATE TABLE public.neighborhoods (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    city character varying(100) NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.neighborhoods_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.neighborhoods_id_seq OWNED BY public.neighborhoods.id;

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    report_id integer,
    message character varying(300) NOT NULL,
    is_read boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;

CREATE TABLE public.report_photos (
    id integer NOT NULL,
    report_id integer NOT NULL,
    url character varying(500) NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.report_photos_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.report_photos_id_seq OWNED BY public.report_photos.id;

CREATE TABLE public.report_status_history (
    id integer NOT NULL,
    report_id integer NOT NULL,
    previous_status character varying(20),
    new_status character varying(20) NOT NULL,
    changed_by integer,
    note character varying(255),
    changed_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.report_status_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.report_status_history_id_seq OWNED BY public.report_status_history.id;

CREATE TABLE public.report_verifications (
    id integer NOT NULL,
    report_id integer NOT NULL,
    user_id integer NOT NULL,
    is_confirmed boolean NOT NULL,
    comment character varying(255),
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.report_verifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.report_verifications_id_seq OWNED BY public.report_verifications.id;

CREATE TABLE public.reports (
    id integer NOT NULL,
    user_id integer NOT NULL,
    neighborhood_id integer NOT NULL,
    incident_type_id integer NOT NULL,
    title character varying(150) NOT NULL,
    description text NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    occurred_at timestamp with time zone NOT NULL,
    status character varying(20) NOT NULL,
    priority_score double precision NOT NULL,
    ai_suggested_type_id integer,
    ai_confidence double precision,
    ai_zone_risk double precision,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_report_status CHECK (((status)::text = ANY ((ARRAY['created'::character varying, 'in_review'::character varying, 'published'::character varying, 'verified'::character varying, 'rejected'::character varying])::text[])))
);

CREATE SEQUENCE public.reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.reports_id_seq OWNED BY public.reports.id;

CREATE TABLE public.risk_hotspots (
    id integer NOT NULL,
    neighborhood_id integer NOT NULL,
    day_of_week smallint NOT NULL,
    hour_block smallint NOT NULL,
    risk_score double precision NOT NULL,
    model_name character varying(100) NOT NULL,
    generated_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_day_of_week CHECK (((day_of_week >= 0) AND (day_of_week <= 6))),
    CONSTRAINT ck_hour_block CHECK (((hour_block >= 0) AND (hour_block <= 3)))
);

CREATE SEQUENCE public.risk_hotspots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.risk_hotspots_id_seq OWNED BY public.risk_hotspots.id;

CREATE TABLE public.roles (
    id integer NOT NULL,
    name character varying(30) NOT NULL,
    description character varying(200)
);

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;

CREATE TABLE public.subscriptions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    neighborhood_id integer NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.subscriptions_id_seq OWNED BY public.subscriptions.id;

CREATE TABLE public.users (
    id integer NOT NULL,
    full_name character varying(120) NOT NULL,
    email character varying(150) NOT NULL,
    password_hash character varying(255) NOT NULL,
    phone character varying(30),
    role_id integer NOT NULL,
    neighborhood_id integer,
    is_active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;

ALTER TABLE ONLY public.ai_analyses ALTER COLUMN id SET DEFAULT nextval('public.ai_analyses_id_seq'::regclass);

ALTER TABLE ONLY public.daily_summaries ALTER COLUMN id SET DEFAULT nextval('public.daily_summaries_id_seq'::regclass);

ALTER TABLE ONLY public.incident_types ALTER COLUMN id SET DEFAULT nextval('public.incident_types_id_seq'::regclass);

ALTER TABLE ONLY public.neighborhood_connections ALTER COLUMN id SET DEFAULT nextval('public.neighborhood_connections_id_seq'::regclass);

ALTER TABLE ONLY public.neighborhoods ALTER COLUMN id SET DEFAULT nextval('public.neighborhoods_id_seq'::regclass);

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);

ALTER TABLE ONLY public.report_photos ALTER COLUMN id SET DEFAULT nextval('public.report_photos_id_seq'::regclass);

ALTER TABLE ONLY public.report_status_history ALTER COLUMN id SET DEFAULT nextval('public.report_status_history_id_seq'::regclass);

ALTER TABLE ONLY public.report_verifications ALTER COLUMN id SET DEFAULT nextval('public.report_verifications_id_seq'::regclass);

ALTER TABLE ONLY public.reports ALTER COLUMN id SET DEFAULT nextval('public.reports_id_seq'::regclass);

ALTER TABLE ONLY public.risk_hotspots ALTER COLUMN id SET DEFAULT nextval('public.risk_hotspots_id_seq'::regclass);

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);

ALTER TABLE ONLY public.subscriptions ALTER COLUMN id SET DEFAULT nextval('public.subscriptions_id_seq'::regclass);

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);

ALTER TABLE ONLY public.ai_analyses
    ADD CONSTRAINT ai_analyses_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.daily_summaries
    ADD CONSTRAINT daily_summaries_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.incident_types
    ADD CONSTRAINT incident_types_code_key UNIQUE (code);

ALTER TABLE ONLY public.incident_types
    ADD CONSTRAINT incident_types_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.neighborhood_connections
    ADD CONSTRAINT neighborhood_connections_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.neighborhoods
    ADD CONSTRAINT neighborhoods_name_key UNIQUE (name);

ALTER TABLE ONLY public.neighborhoods
    ADD CONSTRAINT neighborhoods_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.report_photos
    ADD CONSTRAINT report_photos_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.report_status_history
    ADD CONSTRAINT report_status_history_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.report_verifications
    ADD CONSTRAINT report_verifications_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.risk_hotspots
    ADD CONSTRAINT risk_hotspots_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_name_key UNIQUE (name);

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.neighborhood_connections
    ADD CONSTRAINT uq_connection UNIQUE (from_neighborhood_id, to_neighborhood_id);

ALTER TABLE ONLY public.daily_summaries
    ADD CONSTRAINT uq_daily_summary UNIQUE (neighborhood_id, summary_date);

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT uq_subscription UNIQUE (user_id, neighborhood_id);

ALTER TABLE ONLY public.report_verifications
    ADD CONSTRAINT uq_verification_once UNIQUE (report_id, user_id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);

CREATE INDEX ix_notifications_user_id ON public.notifications USING btree (user_id);

CREATE INDEX ix_report_photos_report_id ON public.report_photos USING btree (report_id);

CREATE INDEX ix_report_status_history_report_id ON public.report_status_history USING btree (report_id);

CREATE INDEX ix_report_verifications_report_id ON public.report_verifications USING btree (report_id);

CREATE INDEX ix_reports_created_at ON public.reports USING btree (created_at);

CREATE INDEX ix_reports_neighborhood_id ON public.reports USING btree (neighborhood_id);

CREATE INDEX ix_reports_status ON public.reports USING btree (status);

CREATE INDEX ix_reports_user_id ON public.reports USING btree (user_id);

CREATE INDEX ix_risk_hotspots_neighborhood_id ON public.risk_hotspots USING btree (neighborhood_id);

CREATE INDEX ix_subscriptions_neighborhood_id ON public.subscriptions USING btree (neighborhood_id);

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);

ALTER TABLE ONLY public.ai_analyses
    ADD CONSTRAINT ai_analyses_neighborhood_id_fkey FOREIGN KEY (neighborhood_id) REFERENCES public.neighborhoods(id);

ALTER TABLE ONLY public.ai_analyses
    ADD CONSTRAINT ai_analyses_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.daily_summaries
    ADD CONSTRAINT daily_summaries_neighborhood_id_fkey FOREIGN KEY (neighborhood_id) REFERENCES public.neighborhoods(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.neighborhood_connections
    ADD CONSTRAINT neighborhood_connections_from_neighborhood_id_fkey FOREIGN KEY (from_neighborhood_id) REFERENCES public.neighborhoods(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.neighborhood_connections
    ADD CONSTRAINT neighborhood_connections_to_neighborhood_id_fkey FOREIGN KEY (to_neighborhood_id) REFERENCES public.neighborhoods(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE SET NULL;

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.report_photos
    ADD CONSTRAINT report_photos_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.report_status_history
    ADD CONSTRAINT report_status_history_changed_by_fkey FOREIGN KEY (changed_by) REFERENCES public.users(id);

ALTER TABLE ONLY public.report_status_history
    ADD CONSTRAINT report_status_history_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.report_verifications
    ADD CONSTRAINT report_verifications_report_id_fkey FOREIGN KEY (report_id) REFERENCES public.reports(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.report_verifications
    ADD CONSTRAINT report_verifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_ai_suggested_type_id_fkey FOREIGN KEY (ai_suggested_type_id) REFERENCES public.incident_types(id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_incident_type_id_fkey FOREIGN KEY (incident_type_id) REFERENCES public.incident_types(id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_neighborhood_id_fkey FOREIGN KEY (neighborhood_id) REFERENCES public.neighborhoods(id);

ALTER TABLE ONLY public.reports
    ADD CONSTRAINT reports_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

ALTER TABLE ONLY public.risk_hotspots
    ADD CONSTRAINT risk_hotspots_neighborhood_id_fkey FOREIGN KEY (neighborhood_id) REFERENCES public.neighborhoods(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_neighborhood_id_fkey FOREIGN KEY (neighborhood_id) REFERENCES public.neighborhoods(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.subscriptions
    ADD CONSTRAINT subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_neighborhood_id_fkey FOREIGN KEY (neighborhood_id) REFERENCES public.neighborhoods(id);

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);

\unrestrict oMZMg20deocVRTzEatwVTf8jhXP13Uulx6RdDUnexRz69Eb6Gob7bTY4JPIialw

