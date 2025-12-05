--
-- PostgreSQL database dump
--

-- Dumped from database version 10.21 (Debian 10.21-1.pgdg90+1)
-- Dumped by pg_dump version 10.21 (Debian 10.21-1.pgdg90+1)

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

--
-- Name: plpgsql; Type: EXTENSION; Schema: -; Owner: 
--

CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;


--
-- Name: EXTENSION plpgsql; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION plpgsql IS 'PL/pgSQL procedural language';


--
-- Name: gender_enum; Type: TYPE; Schema: public; Owner: admin
--

CREATE TYPE public.gender_enum AS ENUM (
    'M',
    'F'
);


ALTER TYPE public.gender_enum OWNER TO admin;

SET default_tablespace = '';

SET default_with_oids = false;

--
-- Name: dept_emp; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.dept_emp (
    emp_no integer NOT NULL,
    dept_no character(4) NOT NULL,
    from_date date NOT NULL,
    to_date date NOT NULL
);


ALTER TABLE public.dept_emp OWNER TO admin;

--
-- Name: dept_emp_latest_date; Type: VIEW; Schema: public; Owner: admin
--

CREATE VIEW public.dept_emp_latest_date AS
 SELECT dept_emp.emp_no,
    max(dept_emp.from_date) AS from_date,
    max(dept_emp.to_date) AS to_date
   FROM public.dept_emp
  GROUP BY dept_emp.emp_no;


ALTER TABLE public.dept_emp_latest_date OWNER TO admin;

--
-- Name: current_dept_emp; Type: VIEW; Schema: public; Owner: admin
--

CREATE VIEW public.current_dept_emp AS
 SELECT l.emp_no,
    d.dept_no,
    l.from_date,
    l.to_date
   FROM (public.dept_emp d
     JOIN public.dept_emp_latest_date l ON (((d.emp_no = l.emp_no) AND (d.from_date = l.from_date) AND (l.to_date = d.to_date))));


ALTER TABLE public.current_dept_emp OWNER TO admin;

--
-- Name: departments; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.departments (
    dept_no character(4) NOT NULL,
    dept_name character varying(40) NOT NULL
);


ALTER TABLE public.departments OWNER TO admin;

--
-- Name: dept_manager; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.dept_manager (
    emp_no integer NOT NULL,
    dept_no character(4) NOT NULL,
    from_date date NOT NULL,
    to_date date NOT NULL
);


ALTER TABLE public.dept_manager OWNER TO admin;

--
-- Name: employee_payment_history; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.employee_payment_history (
    payment_id integer NOT NULL,
    emp_no integer NOT NULL,
    salary_amount numeric(10,2) NOT NULL,
    payment_date date NOT NULL,
    from_date date NOT NULL,
    to_date date DEFAULT '9999-12-31'::date NOT NULL
);


ALTER TABLE public.employee_payment_history OWNER TO admin;

--
-- Name: employees; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.employees (
    emp_no integer NOT NULL,
    birth_date date NOT NULL,
    first_name character varying(14) NOT NULL,
    last_name character varying(16) NOT NULL,
    gender public.gender_enum NOT NULL,
    hire_date date NOT NULL,
    end_date date DEFAULT '9999-12-31'::date NOT NULL
);


ALTER TABLE public.employees OWNER TO admin;

--
-- Name: salaries; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.salaries (
    emp_no integer NOT NULL,
    salary integer NOT NULL,
    from_date date NOT NULL,
    to_date date NOT NULL
);


ALTER TABLE public.salaries OWNER TO admin;

--
-- Name: titles; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.titles (
    emp_no integer NOT NULL,
    title character varying(50) NOT NULL,
    from_date date NOT NULL,
    to_date date
);


ALTER TABLE public.titles OWNER TO admin;

--
-- Name: departments departments_dept_name_key; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_dept_name_key UNIQUE (dept_name);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (dept_no);


--
-- Name: dept_emp dept_emp_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dept_emp
    ADD CONSTRAINT dept_emp_pkey PRIMARY KEY (emp_no, dept_no);


--
-- Name: dept_manager dept_manager_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dept_manager
    ADD CONSTRAINT dept_manager_pkey PRIMARY KEY (emp_no, dept_no);


--
-- Name: employee_payment_history employee_payment_history_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.employee_payment_history
    ADD CONSTRAINT employee_payment_history_pkey PRIMARY KEY (payment_id);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (emp_no);


--
-- Name: salaries salaries_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.salaries
    ADD CONSTRAINT salaries_pkey PRIMARY KEY (emp_no, from_date);


--
-- Name: titles titles_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.titles
    ADD CONSTRAINT titles_pkey PRIMARY KEY (emp_no, title, from_date);


--
-- Name: dept_emp dept_emp_dept_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dept_emp
    ADD CONSTRAINT dept_emp_dept_no_fkey FOREIGN KEY (dept_no) REFERENCES public.departments(dept_no) ON DELETE CASCADE;


--
-- Name: dept_emp dept_emp_emp_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dept_emp
    ADD CONSTRAINT dept_emp_emp_no_fkey FOREIGN KEY (emp_no) REFERENCES public.employees(emp_no) ON DELETE CASCADE;


--
-- Name: dept_manager dept_manager_dept_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dept_manager
    ADD CONSTRAINT dept_manager_dept_no_fkey FOREIGN KEY (dept_no) REFERENCES public.departments(dept_no) ON DELETE CASCADE;


--
-- Name: dept_manager dept_manager_emp_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.dept_manager
    ADD CONSTRAINT dept_manager_emp_no_fkey FOREIGN KEY (emp_no) REFERENCES public.employees(emp_no) ON DELETE CASCADE;


--
-- Name: employee_payment_history employee_payment_history_emp_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.employee_payment_history
    ADD CONSTRAINT employee_payment_history_emp_no_fkey FOREIGN KEY (emp_no) REFERENCES public.employees(emp_no);


--
-- Name: salaries salaries_emp_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.salaries
    ADD CONSTRAINT salaries_emp_no_fkey FOREIGN KEY (emp_no) REFERENCES public.employees(emp_no) ON DELETE CASCADE;


--
-- Name: titles titles_emp_no_fkey; Type: FK CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.titles
    ADD CONSTRAINT titles_emp_no_fkey FOREIGN KEY (emp_no) REFERENCES public.employees(emp_no) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

