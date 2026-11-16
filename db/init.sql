-- HR database: structured data stays in the database and is protected BY the database.
--
-- The application never queries with a superuser or a shared all-access service account.
-- It logs in as `rag_gateway`, which owns no data privileges, and for every request
-- switches to the role that matches the end user (SET LOCAL ROLE) and records the
-- verified user id (app.user_id). Row-level security and column privileges decide
-- what comes back.
--
-- Dev-only passwords below. Use your secrets manager in real deployments.

CREATE ROLE rag_employee NOLOGIN;
CREATE ROLE rag_hr_comp  NOLOGIN;
-- NOINHERIT: the gateway has no privileges until it explicitly assumes a role.
CREATE ROLE rag_gateway LOGIN NOINHERIT PASSWORD 'rag_gateway_dev';
GRANT rag_employee, rag_hr_comp TO rag_gateway;

CREATE TABLE compensation (
    employee_id  text PRIMARY KEY,
    full_name    text NOT NULL,
    title        text NOT NULL,
    department   text NOT NULL,
    manager_id   text REFERENCES compensation(employee_id),
    base_salary  integer NOT NULL
);

INSERT INTO compensation VALUES
    ('cora', 'Cora', 'Chief Executive Officer',  'exec',        NULL,   410000),
    ('dan',  'Dan',  'Engineering Manager',      'engineering', 'cora', 198000),
    ('hana', 'Hana', 'HR Compensation Partner',  'people',      'cora', 141000),
    ('erin', 'Erin', 'Software Engineer',        'engineering', 'dan',  152000),
    ('ivy',  'Ivy',  'Software Engineer Intern', 'engineering', 'dan',   48000);

-- Rows: who can see which employees.
ALTER TABLE compensation ENABLE ROW LEVEL SECURITY;
ALTER TABLE compensation FORCE ROW LEVEL SECURITY;  -- applies to the table owner too

-- Employees see themselves and their direct reports. If app.user_id is unset,
-- current_setting(..., true) is NULL and the policy matches nothing (fail closed).
CREATE POLICY employee_self_and_reports ON compensation
    FOR SELECT TO rag_employee
    USING (employee_id = current_setting('app.user_id', true)
           OR manager_id = current_setting('app.user_id', true));

CREATE POLICY hr_comp_all_rows ON compensation
    FOR SELECT TO rag_hr_comp
    USING (true);

-- Columns: ordinary employees can never select base_salary, not even their reports'.
GRANT SELECT (employee_id, full_name, title, department, manager_id)
    ON compensation TO rag_employee;
GRANT SELECT ON compensation TO rag_hr_comp;
