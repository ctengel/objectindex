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
    ctime timestamp without time zone NOT NULL,
    mtime timestamp without time zone,
    url character varying(2047) NOT NULL,
    direct boolean NOT NULL,
    partial boolean NOT NULL,
    extra jsonb,
    ul_user character varying(15),
    ul_sw character varying(15),
    ul_host character varying(64)
);


ALTER TABLE public.file OWNER TO chris;

--
-- Name: object; Type: TABLE; Schema: public; Owner: chris
--

CREATE TABLE public.object (
    uuid uuid NOT NULL,
    bucket character varying(63) NOT NULL,
    key character varying(1023) NOT NULL,
    obj_size bigint NOT NULL,
    checksum bytea,
    ctime timestamp without time zone NOT NULL,
    mime character varying(255),
    completed boolean NOT NULL,
    deleted boolean NOT NULL,
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
-- Name: buckey; Type: INDEX; Schema: public; Owner: chris
--

CREATE INDEX buckey ON public.object USING btree (bucket, key);


--
-- Name: ix_file_obj_uuid; Type: INDEX; Schema: public; Owner: chris
--

CREATE INDEX ix_file_obj_uuid ON public.file USING btree (obj_uuid);


--
-- Name: ix_file_url; Type: INDEX; Schema: public; Owner: chris
--

CREATE INDEX ix_file_url ON public.file USING btree (url);


--
-- Name: ix_object_checksum; Type: INDEX; Schema: public; Owner: chris
--

CREATE INDEX ix_object_checksum ON public.object USING btree (checksum);


--
-- Name: file file_obj_uuid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: chris
--

ALTER TABLE ONLY public.file
    ADD CONSTRAINT file_obj_uuid_fkey FOREIGN KEY (obj_uuid) REFERENCES public.object(uuid);


--
-- PostgreSQL database dump complete
--

