--
-- PostgreSQL database dump
--

\restrict 3bT0Gs3NDbAwMKqX0MuW9olfnyd3pFhzXubcvUTcs5lNaQ7N7obRgpDPJwhqJfx

-- Dumped from database version 16.11 (Debian 16.11-1.pgdg13+1)
-- Dumped by pg_dump version 16.11 (Debian 16.11-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: erp_user
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO erp_user;

--
-- Name: driver_document_files; Type: TABLE; Schema: public; Owner: erp_user
--

CREATE TABLE public.driver_document_files (
    id integer NOT NULL,
    driver_document_id integer NOT NULL,
    storage_key character varying(1024) NOT NULL,
    original_filename character varying(255),
    content_type character varying(100),
    file_size_bytes bigint,
    sha256 character varying(64),
    is_active boolean DEFAULT true NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.driver_document_files OWNER TO erp_user;

--
-- Name: driver_document_files_id_seq; Type: SEQUENCE; Schema: public; Owner: erp_user
--

CREATE SEQUENCE public.driver_document_files_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.driver_document_files_id_seq OWNER TO erp_user;

--
-- Name: driver_document_files_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: erp_user
--

ALTER SEQUENCE public.driver_document_files_id_seq OWNED BY public.driver_document_files.id;


--
-- Name: driver_documents; Type: TABLE; Schema: public; Owner: erp_user
--

CREATE TABLE public.driver_documents (
    id integer NOT NULL,
    driver_id integer NOT NULL,
    doc_type character varying(50) NOT NULL,
    title character varying(255),
    issue_date date,
    expiry_date date,
    status character varying(30) DEFAULT 'ACTIVE'::character varying NOT NULL,
    notes text,
    is_current boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deactivated_at timestamp with time zone,
    deactivated_reason character varying(255)
);


ALTER TABLE public.driver_documents OWNER TO erp_user;

--
-- Name: driver_documents_id_seq; Type: SEQUENCE; Schema: public; Owner: erp_user
--

CREATE SEQUENCE public.driver_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.driver_documents_id_seq OWNER TO erp_user;

--
-- Name: driver_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: erp_user
--

ALTER SEQUENCE public.driver_documents_id_seq OWNED BY public.driver_documents.id;


--
-- Name: driver_phones; Type: TABLE; Schema: public; Owner: erp_user
--

CREATE TABLE public.driver_phones (
    id integer NOT NULL,
    driver_id integer NOT NULL,
    label character varying(50),
    phone character varying(30) NOT NULL,
    extension character varying(10),
    is_primary boolean DEFAULT false NOT NULL,
    is_verified boolean DEFAULT false NOT NULL,
    notes character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    deactivated_at timestamp with time zone,
    deactivated_reason character varying(255)
);


ALTER TABLE public.driver_phones OWNER TO erp_user;

--
-- Name: driver_phones_old; Type: TABLE; Schema: public; Owner: erp_user
--

CREATE TABLE public.driver_phones_old (
    id integer NOT NULL,
    driver_id integer NOT NULL,
    country_code character varying(5) NOT NULL,
    phone_number character varying(20) NOT NULL,
    phone_type character varying(20) NOT NULL,
    is_primary boolean NOT NULL
);


ALTER TABLE public.driver_phones_old OWNER TO erp_user;

--
-- Name: driver_phones_id_seq; Type: SEQUENCE; Schema: public; Owner: erp_user
--

CREATE SEQUENCE public.driver_phones_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.driver_phones_id_seq OWNER TO erp_user;

--
-- Name: driver_phones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: erp_user
--

ALTER SEQUENCE public.driver_phones_id_seq OWNED BY public.driver_phones_old.id;


--
-- Name: driver_phones_id_seq1; Type: SEQUENCE; Schema: public; Owner: erp_user
--

CREATE SEQUENCE public.driver_phones_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.driver_phones_id_seq1 OWNER TO erp_user;

--
-- Name: driver_phones_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: erp_user
--

ALTER SEQUENCE public.driver_phones_id_seq1 OWNED BY public.driver_phones.id;


--
-- Name: drivers; Type: TABLE; Schema: public; Owner: erp_user
--

CREATE TABLE public.drivers (
    id integer NOT NULL,
    first_name character varying(100) NOT NULL,
    last_name character varying(100) NOT NULL,
    email character varying(255),
    phone character varying(50),
    is_active boolean NOT NULL,
    hire_date date,
    termination_date date,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    emergency_contact_name character varying(120)
);


ALTER TABLE public.drivers OWNER TO erp_user;

--
-- Name: drivers_id_seq; Type: SEQUENCE; Schema: public; Owner: erp_user
--

CREATE SEQUENCE public.drivers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.drivers_id_seq OWNER TO erp_user;

--
-- Name: drivers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: erp_user
--

ALTER SEQUENCE public.drivers_id_seq OWNED BY public.drivers.id;


--
-- Name: driver_document_files id; Type: DEFAULT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_document_files ALTER COLUMN id SET DEFAULT nextval('public.driver_document_files_id_seq'::regclass);


--
-- Name: driver_documents id; Type: DEFAULT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_documents ALTER COLUMN id SET DEFAULT nextval('public.driver_documents_id_seq'::regclass);


--
-- Name: driver_phones id; Type: DEFAULT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones ALTER COLUMN id SET DEFAULT nextval('public.driver_phones_id_seq1'::regclass);


--
-- Name: driver_phones_old id; Type: DEFAULT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones_old ALTER COLUMN id SET DEFAULT nextval('public.driver_phones_id_seq'::regclass);


--
-- Name: drivers id; Type: DEFAULT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.drivers ALTER COLUMN id SET DEFAULT nextval('public.drivers_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: driver_document_files driver_document_files_pkey; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_document_files
    ADD CONSTRAINT driver_document_files_pkey PRIMARY KEY (id);


--
-- Name: driver_documents driver_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_documents
    ADD CONSTRAINT driver_documents_pkey PRIMARY KEY (id);


--
-- Name: driver_phones_old driver_phones_pkey; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones_old
    ADD CONSTRAINT driver_phones_pkey PRIMARY KEY (id);


--
-- Name: driver_phones driver_phones_pkey1; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones
    ADD CONSTRAINT driver_phones_pkey1 PRIMARY KEY (id);


--
-- Name: drivers drivers_pkey; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.drivers
    ADD CONSTRAINT drivers_pkey PRIMARY KEY (id);


--
-- Name: driver_phones_old uq_driver_phone_dedupe; Type: CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones_old
    ADD CONSTRAINT uq_driver_phone_dedupe UNIQUE (driver_id, country_code, phone_number);


--
-- Name: ix_driver_document_files_driver_document_id; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_document_files_driver_document_id ON public.driver_document_files USING btree (driver_document_id);


--
-- Name: ix_driver_document_files_is_active; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_document_files_is_active ON public.driver_document_files USING btree (is_active);


--
-- Name: ix_driver_documents_doc_type; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_documents_doc_type ON public.driver_documents USING btree (doc_type);


--
-- Name: ix_driver_documents_driver_id; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_documents_driver_id ON public.driver_documents USING btree (driver_id);


--
-- Name: ix_driver_documents_expiry_date; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_documents_expiry_date ON public.driver_documents USING btree (expiry_date);


--
-- Name: ix_driver_documents_is_active; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_documents_is_active ON public.driver_documents USING btree (is_active);


--
-- Name: ix_driver_documents_is_current; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_documents_is_current ON public.driver_documents USING btree (is_current);


--
-- Name: ix_driver_phones_driver_id; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_phones_driver_id ON public.driver_phones_old USING btree (driver_id);


--
-- Name: ix_driver_phones_phone_number; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE INDEX ix_driver_phones_phone_number ON public.driver_phones_old USING btree (phone_number);


--
-- Name: ux_driver_primary_phone; Type: INDEX; Schema: public; Owner: erp_user
--

CREATE UNIQUE INDEX ux_driver_primary_phone ON public.driver_phones_old USING btree (driver_id) WHERE is_primary;


--
-- Name: driver_phones_old driver_phones_driver_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones_old
    ADD CONSTRAINT driver_phones_driver_id_fkey FOREIGN KEY (driver_id) REFERENCES public.drivers(id) ON DELETE CASCADE;


--
-- Name: driver_phones driver_phones_driver_id_fkey1; Type: FK CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_phones
    ADD CONSTRAINT driver_phones_driver_id_fkey1 FOREIGN KEY (driver_id) REFERENCES public.drivers(id) ON DELETE CASCADE;


--
-- Name: driver_document_files fk_driver_document_files_driver_document_id; Type: FK CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_document_files
    ADD CONSTRAINT fk_driver_document_files_driver_document_id FOREIGN KEY (driver_document_id) REFERENCES public.driver_documents(id) ON DELETE CASCADE;


--
-- Name: driver_documents fk_driver_documents_driver_id; Type: FK CONSTRAINT; Schema: public; Owner: erp_user
--

ALTER TABLE ONLY public.driver_documents
    ADD CONSTRAINT fk_driver_documents_driver_id FOREIGN KEY (driver_id) REFERENCES public.drivers(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict 3bT0Gs3NDbAwMKqX0MuW9olfnyd3pFhzXubcvUTcs5lNaQ7N7obRgpDPJwhqJfx

