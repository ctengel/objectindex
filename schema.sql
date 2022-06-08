--
-- PostgreSQL database dump
--

-- Dumped from database version 13.4
-- Dumped by pg_dump version 13.4

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
-- Name: file; Type: TABLE; Schema: public; Owner: chris
--

CREATE TABLE public.file (
    uuid uuid NOT NULL,
    obj_uuid uuid,
    ctime timestamp without time zone,
    mtime timestamp without time zone,
    url character varying(2047),
    direct boolean,
    partial boolean,
    extra jsonb,
    "user" character varying(15),
    uploader character varying(15),
    hostname character varying(64)
);


ALTER TABLE public.file OWNER TO chris;

--
-- Name: object; Type: TABLE; Schema: public; Owner: chris
--

CREATE TABLE public.object (
    uuid uuid NOT NULL,
    bucket character varying(63),
    key character varying(1023),
    size integer,
    checksum bytea,
    ctime timestamp without time zone,
    mime character varying(255),
    completed boolean,
    deleted boolean,
    extra jsonb
);


ALTER TABLE public.object OWNER TO chris;

--
-- Name: file file_pkey; Type: CONSTRAINT; Schema: public; Owner: chris
--

ALTER TABLE ONLY public.file
    ADD CONSTRAINT file_pkey PRIMARY KEY (uuid);


--
-- Name: object object_pkey; Type: CONSTRAINT; Schema: public; Owner: chris
--

ALTER TABLE ONLY public.object
    ADD CONSTRAINT object_pkey PRIMARY KEY (uuid);


--
-- Name: file file_obj_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chris
--

ALTER TABLE ONLY public.file
    ADD CONSTRAINT file_obj_uuid_fkey FOREIGN KEY (obj_uuid) REFERENCES public.object(uuid);


--
-- PostgreSQL database dump complete
--

