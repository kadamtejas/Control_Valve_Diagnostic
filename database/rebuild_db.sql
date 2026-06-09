-- ============================================================
--  ValveDiagnosticDB  —  CLEAN REBUILD v2
--  Run in SSMS connected to TEJAS-KADAM\SQLEXPRESS
-- ============================================================

USE master;
GO

IF EXISTS (SELECT name FROM sys.databases WHERE name = 'ValveDiagnosticDB')
BEGIN
    ALTER DATABASE ValveDiagnosticDB SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE ValveDiagnosticDB;
    PRINT 'Dropped existing ValveDiagnosticDB.';
END
GO

CREATE DATABASE ValveDiagnosticDB;
GO
USE ValveDiagnosticDB;
GO

-- ============================================================
--  TABLE DEFINITIONS
-- ============================================================

-- 1. PLANTS
CREATE TABLE plants (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    plant_code  VARCHAR(20)  NOT NULL UNIQUE,
    plant_name  VARCHAR(100) NOT NULL,
    description VARCHAR(255) NULL,
    location    VARCHAR(100) NULL,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- 2. LOOPS
CREATE TABLE loops (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    plant_id    INT          NOT NULL REFERENCES plants(id),
    loop_tag    VARCHAR(80)  NOT NULL UNIQUE,
    description VARCHAR(255) NULL,
    unit_area   VARCHAR(100) NULL,
    is_active   BIT          NOT NULL DEFAULT 1,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- 3. TAGS
CREATE TABLE tags (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    loop_id     INT          NOT NULL REFERENCES loops(id),
    tag_name    VARCHAR(100) NOT NULL UNIQUE,
    signal_type VARCHAR(10)  NOT NULL CHECK (signal_type IN ('PV','OP','SP','MODE')),
    unit        VARCHAR(30)  NULL,
    description VARCHAR(255) NULL,
    is_active   BIT          NOT NULL DEFAULT 1,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- 4. TAG_READINGS
CREATE TABLE tag_readings (
    id          BIGINT IDENTITY(1,1) PRIMARY KEY,
    tag_id      INT          NOT NULL REFERENCES tags(id),
    recorded_at DATETIME2    NOT NULL,
    value       FLOAT        NULL,
    quality     VARCHAR(15)  NOT NULL DEFAULT 'GOOD'
                              CHECK (quality IN ('GOOD','BAD','UNCERTAIN')),
    source      VARCHAR(100) NULL,
    CONSTRAINT uq_tag_time UNIQUE (tag_id, recorded_at)
);
CREATE INDEX ix_readings_tag_time ON tag_readings (tag_id, recorded_at);

-- 5. UNIT_MAPPING
CREATE TABLE unit_mapping (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    tag_id           INT          NOT NULL REFERENCES tags(id) UNIQUE,
    plant_unit       VARCHAR(100) NULL,
    engineering_unit VARCHAR(30)  NULL,
    range_low        FLOAT        NULL,
    range_high       FLOAT        NULL
);

-- 6. MODE_MAPPING
-- One row per alias per loop (e.g. AUTO->AUTO, AUTO->A, AUTO->1, AUTO->Automatic)
CREATE TABLE mode_mapping (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    loop_id       INT         NOT NULL REFERENCES loops(id),
    mode_category VARCHAR(10) NOT NULL,  -- AUTO, CAS, RCAS, MAN
    mode_alias    VARCHAR(30) NOT NULL,  -- exact value seen in data
    CONSTRAINT uq_loop_alias UNIQUE (loop_id, mode_alias)
);

-- 7. DIAGNOSTIC_PARAMETERS
-- Stores the 16 global key-value parameters from DIAGNOSTIC_CONFIG sheet
CREATE TABLE diagnostic_parameters (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    parameter   VARCHAR(100)  NOT NULL UNIQUE,
    value       FLOAT         NOT NULL,
    description VARCHAR(255)  NULL
);

-- 8. DIAGNOSTIC_SELECTION
-- Parent-child structure from DIAGNOSTIC_SELECTION sheet
-- Top-level diagnostics have parent_id = NULL
-- Sub-methods point to their parent row
CREATE TABLE diagnostic_selection (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    diagnostic_name VARCHAR(100) NOT NULL,
    parent_id       INT          NULL REFERENCES diagnostic_selection(id),
    is_enabled      BIT          NOT NULL DEFAULT 1
);

-- 9. DIAGNOSTIC_CONFIG
-- Per-loop: which top-level diagnostics are active for this loop
-- References only top-level rows in diagnostic_selection (parent_id IS NULL)
CREATE TABLE diagnostic_config (
    id                     INT IDENTITY(1,1) PRIMARY KEY,
    loop_id                INT NOT NULL REFERENCES loops(id),
    diagnostic_selection_id INT NOT NULL REFERENCES diagnostic_selection(id),
    is_enabled             BIT NOT NULL DEFAULT 1,
    CONSTRAINT uq_loop_diag UNIQUE (loop_id, diagnostic_selection_id)
);

-- 10. USERS
CREATE TABLE users (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(20)  NOT NULL DEFAULT 'viewer'
                               CHECK (role IN ('admin','viewer')),
    created_at    DATETIME2    NOT NULL DEFAULT GETDATE(),
    last_login    DATETIME2    NULL
);

-- 11. SESSIONS
CREATE TABLE sessions (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    user_id     INT          NOT NULL REFERENCES users(id),
    jwt_token   VARCHAR(512) NOT NULL,
    expires_at  DATETIME2    NOT NULL,
    created_at  DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- 12. THRESHOLD_CONFIGS
CREATE TABLE threshold_configs (
    id               INT IDENTITY(1,1) PRIMARY KEY,
    user_id          INT          NOT NULL REFERENCES users(id),
    config_name      VARCHAR(100) NOT NULL,
    hysteresis_warn  FLOAT        NOT NULL DEFAULT 3.0,
    hysteresis_fail  FLOAT        NOT NULL DEFAULT 5.0,
    deadband_warn    FLOAT        NOT NULL DEFAULT 2.0,
    deadband_fail    FLOAT        NOT NULL DEFAULT 4.0,
    noise_warn       FLOAT        NOT NULL DEFAULT 1.5,
    noise_fail       FLOAT        NOT NULL DEFAULT 3.0,
    is_global        BIT          NOT NULL DEFAULT 0,
    created_at       DATETIME2    NOT NULL DEFAULT GETDATE()
);

-- 13. DIAGNOSTIC_RUNS
CREATE TABLE diagnostic_runs (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    user_id             INT         NOT NULL REFERENCES users(id),
    loop_id             INT         NOT NULL REFERENCES loops(id),
    threshold_config_id INT         NULL REFERENCES threshold_configs(id),
    run_mode            VARCHAR(10) NOT NULL DEFAULT 'AUTO'
                                    CHECK (run_mode IN ('AUTO','MANUAL')),
    range_start         DATETIME2   NOT NULL,
    range_end           DATETIME2   NOT NULL,
    started_at          DATETIME2   NOT NULL DEFAULT GETDATE(),
    completed_at        DATETIME2   NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'PENDING'
                                    CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED'))
);

-- 14. LOOP_RESULTS
CREATE TABLE loop_results (
    id             INT IDENTITY(1,1) PRIMARY KEY,
    run_id         INT           NOT NULL REFERENCES diagnostic_runs(id) UNIQUE,
    health_score   FLOAT         NULL,
    severity       VARCHAR(20)   NULL CHECK (severity IN ('GOOD','WARNING','CRITICAL')),
    cv_travel      FLOAT         NULL,
    hysteresis     FLOAT         NULL,
    deadband       FLOAT         NULL,
    signal_noise   FLOAT         NULL,
    recommendation NVARCHAR(MAX) NULL,
    created_at     DATETIME2     NOT NULL DEFAULT GETDATE()
);

GO

-- ============================================================
--  SEED DATA
-- ============================================================

-- ── PLANT ────────────────────────────────────────────────────
INSERT INTO plants (plant_code, plant_name, description, location)
VALUES ('ETH1', 'Ethanol Unit 1', 'Ethylene Fractionator', 'Mumbai');

-- ── LOOPS ────────────────────────────────────────────────────
DECLARE @pid INT = (SELECT id FROM plants WHERE plant_code = 'ETH1');

INSERT INTO loops (plant_id, loop_tag, description, unit_area) VALUES
(@pid, 'YN.ETH1.15FC311',  'Flow control 15FC311',    'Ethylene_Fractionator'),
(@pid, 'YN.ETH1.15LC094',  'Level control 15LC094',   'Ethylene_Fractionator'),
(@pid, 'YN.ETH1.16FC336',  'Flow control 16FC336',    'Unknown'),
(@pid, 'YN.ETH1.15PC217',  'Pressure control 15PC217','Ethylene_Fractionator'),
(@pid, 'YN.ETH1.15FC315',  'Flow control 15FC315',    'Ethylene_Fractionator'),
(@pid, 'YN.ETH1.17FC347',  'Flow control 17FC347',    'Unknown'),
(@pid, 'YN.ETH1.15FC316',  'Flow control 15FC316',    'Ethylene_Fractionator'),
(@pid, 'YN.ETH1.15FFC317', 'Flow control 15FFC317',   'Ethylene_Fractionator'),
(@pid, 'YN.ETH1.15LC095',  'Level control 15LC095',   'Ethylene_Fractionator'),
(@pid, 'YN.ETH1.15FC901',  'Flow control 15FC901',    'Ethylene_Fractionator');

-- ── TAGS ─────────────────────────────────────────────────────
DECLARE @l1  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15FC311');
DECLARE @l2  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15LC094');
DECLARE @l3  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.16FC336');
DECLARE @l4  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15PC217');
DECLARE @l5  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15FC315');
DECLARE @l6  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.17FC347');
DECLARE @l7  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15FC316');
DECLARE @l8  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15FFC317');
DECLARE @l9  INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15LC095');
DECLARE @l10 INT = (SELECT id FROM loops WHERE loop_tag='YN.ETH1.15FC901');

INSERT INTO tags (loop_id, tag_name, signal_type, unit) VALUES
(@l1, 'YN.ETH1.15FC311_PV',   'PV',   'Kg/Hr'),
(@l1, 'YN.ETH1.15FC311_OP',   'OP',   '%'),
(@l1, 'YN.ETH1.15FC311_SP',   'SP',   'Kg/Hr'),
(@l1, 'YN.ETH1.15FC311_mode', 'MODE', NULL),
(@l2, 'YN.ETH1.15LC094_PV',   'PV',   'Kg/Hr'),
(@l2, 'YN.ETH1.15LC094_OP',   'OP',   '%'),
(@l2, 'YN.ETH1.15LC094_SP',   'SP',   'Kg/Hr'),
(@l2, 'YN.ETH1.15LC094_Mode', 'MODE', NULL),
(@l3, 'YN.ETH1.16FC336_PV',   'PV',   NULL),
(@l3, 'YN.ETH1.16FC336_OP',   'OP',   '%'),
(@l3, 'YN.ETH1.16FC336_SP',   'SP',   NULL),
(@l3, 'YN.ETH1.16FC336_Mode', 'MODE', NULL),
(@l4, 'YN.ETH1.15PC217_PV',   'PV',   'Kg/Hr'),
(@l4, 'YN.ETH1.15PC217_OP',   'OP',   '%'),
(@l4, 'YN.ETH1.15PC217_SP',   'SP',   'Kg/Hr'),
(@l4, 'YN.ETH1.15PC217_Mode', 'MODE', NULL),
(@l5, 'YN.ETH1.15FC315_PV',   'PV',   'Kg/Hr'),
(@l5, 'YN.ETH1.15FC315_OP',   'OP',   '%'),
(@l5, 'YN.ETH1.15FC315_SP',   'SP',   'Kg/Hr'),
(@l5, 'YN.ETH1.15FC315_Mode', 'MODE', NULL),
(@l6, 'YN.ETH1.17FC347_PV',   'PV',   NULL),
(@l6, 'YN.ETH1.17FC347_OP',   'OP',   '%'),
(@l6, 'YN.ETH1.17FC347_SP',   'SP',   NULL),
(@l6, 'YN.ETH1.17FC347_mode', 'MODE', NULL),
(@l7, 'YN.ETH1.15FC316_PV',   'PV',   'Kg/Hr'),
(@l7, 'YN.ETH1.15FC316_OP',   'OP',   '%'),
(@l7, 'YN.ETH1.15FC316_SP',   'SP',   'Kg/Hr'),
(@l7, 'YN.ETH1.15FC316_Mode', 'MODE', NULL),
(@l8, 'YN.ETH1.15FFC317_SP',  'SP',   'Kg/Hr'),
(@l8, 'YN.ETH1.15FFC317_OP',  'OP',   '%'),
(@l8, 'YN.ETH1.15FFC317_PV',  'PV',   'Kg/Hr'),
(@l8, 'YN.ETH1.15FFC317_Mode','MODE', NULL),
(@l9, 'YN.ETH1.15LC095_PV',   'PV',   '%'),
(@l9, 'YN.ETH1.15LC095_OP',   'OP',   '%'),
(@l9, 'YN.ETH1.15LC095_SP',   'SP',   '%'),
(@l9, 'YN.ETH1.15LC095_mode', 'MODE', NULL),
(@l10,'YN.ETH1.15FC901_PV',   'PV',   NULL),
(@l10,'YN.ETH1.15FC901_OP',   'OP',   '%'),
(@l10,'YN.ETH1.15FC901_SP',   'SP',   NULL),
(@l10,'YN.ETH1.15FC901_mode', 'MODE', NULL);

-- ── UNIT_MAPPING ─────────────────────────────────────────────
INSERT INTO unit_mapping (tag_id, plant_unit, engineering_unit)
SELECT t.id, v.plant_unit, v.uom
FROM (VALUES
    ('YN.ETH1.15FC311_PV',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15FC311_SP',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15LC094_PV',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15LC094_SP',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.16FC336_PV',  'Unknown',               NULL),
    ('YN.ETH1.16FC336_SP',  'Unknown',               NULL),
    ('YN.ETH1.15PC217_PV',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15PC217_SP',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15FC315_PV',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15FC315_SP',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.17FC347_PV',  'Unknown',               NULL),
    ('YN.ETH1.17FC347_SP',  'Unknown',               NULL),
    ('YN.ETH1.15FC316_PV',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15FC316_SP',  'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15FFC317_PV', 'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15FFC317_SP', 'Ethylene_Fractionator', 'Kg/Hr'),
    ('YN.ETH1.15LC095_PV',  'Ethylene_Fractionator', '%'),
    ('YN.ETH1.15LC095_SP',  'Ethylene_Fractionator', '%'),
    ('YN.ETH1.15FC901_PV',  'Ethylene_Fractionator', NULL),
    ('YN.ETH1.15FC901_SP',  'Ethylene_Fractionator', NULL)
) AS v(tag_name, plant_unit, uom)
JOIN tags t ON t.tag_name = v.tag_name;

-- ── MODE_MAPPING (all 16 aliases from Excel, for every loop) ──
INSERT INTO mode_mapping (loop_id, mode_category, mode_alias)
SELECT l.id, v.category, v.alias
FROM loops l
CROSS JOIN (VALUES
    ('AUTO', 'AUTO'),
    ('AUTO', 'A'),
    ('AUTO', '1'),
    ('AUTO', 'Automatic'),
    ('CAS',  'CAS'),
    ('CAS',  'C'),
    ('CAS',  '2'),
    ('CAS',  'Cascade'),
    ('RCAS', 'RCAS'),
    ('RCAS', 'R'),
    ('RCAS', '3'),
    ('RCAS', 'Remote'),
    ('MAN',  'MAN'),
    ('MAN',  'M'),
    ('MAN',  '0'),
    ('MAN',  'Manual')
) AS v(category, alias);

-- ── DIAGNOSTIC_PARAMETERS (from DIAGNOSTIC_CONFIG sheet) ──────
-- 16 rows, exactly as in Excel
INSERT INTO diagnostic_parameters (parameter, value, description) VALUES
('AMP_THRESHOLD',               16,   'PV peak-to-peak amplitude threshold for ''high oscillation'''),
('OP_ACTIVITY_THRESHOLD',        1.5, 'Mean |dOP| threshold for ''high OP activity'''),
('IAE_PER_HOUR_THRESHOLD',     200,   'IAE/hour threshold for ''poor tracking'''),
('STICT_CONF_HIGH',             70,   'Stiction confidence (%) considered HIGH'),
('STICT_CONF_MED',              40,   'Stiction confidence (%) considered MEDIUM'),
('PROP_CONF_MIN',               50,   'Min propagation confidence (%) to log a link'),
('PROP_CONF_STRONG',            70,   'Propagation confidence (%) considered STRONG'),
('SERVICE_FACTOR_MIN_PCT',      70,   'Min % time in AUTO/CAS for loop to be analysed'),
('SS_DETECTION_WINDOW',         30,   'Window size (samples) for steady-state detection'),
('SS_STD_THRESHOLD',             0.5, 'Std threshold for steady-state classification'),
('FROZEN_SAMPLES_MIN',          10,   'Min consecutive identical PV samples to flag frozen sensor'),
('QUANTISATION_UNIQUE_VALS_MAX',20,   'Max unique PV values to flag quantisation'),
('COMPRESSION_FLAT_FRACTION_MAX',0.3, 'Max fraction of compressed (flat) points before flagging'),
('OSCILLATION_REGULARITY_MIN',   0.6, 'Min Hagglund regularity for oscillation flag'),
('STICTION_S_MIN_PCT',           0.5, 'Min S (stickband %) to consider stiction physically present'),
('HARRIS_INDEX_THRESHOLD',       0.3, 'Min Harris index for ''good control''');

-- ── DIAGNOSTIC_SELECTION (parent-child from DIAGNOSTIC_SELECTION sheet) ──
-- Step 1: insert top-level diagnostics (parent_id = NULL)
INSERT INTO diagnostic_selection (diagnostic_name, parent_id, is_enabled) VALUES
('Stiction detection',      NULL, 1),   -- id 1
('Aggressive tuning',       NULL, 1),   -- id 2
('Sluggish tuning',         NULL, 0),   -- id 3  (Enabled = No)
('External oscillation',    NULL, 1),   -- id 4
('Cross-loop propagation',  NULL, 1);   -- id 5

-- Step 2: insert sub-methods pointing to their parent
DECLARE @stiction  INT = (SELECT id FROM diagnostic_selection WHERE diagnostic_name = 'Stiction detection');
DECLARE @agg       INT = (SELECT id FROM diagnostic_selection WHERE diagnostic_name = 'Aggressive tuning');
DECLARE @slug      INT = (SELECT id FROM diagnostic_selection WHERE diagnostic_name = 'Sluggish tuning');
DECLARE @ext_osc   INT = (SELECT id FROM diagnostic_selection WHERE diagnostic_name = 'External oscillation');
DECLARE @prop      INT = (SELECT id FROM diagnostic_selection WHERE diagnostic_name = 'Cross-loop propagation');

INSERT INTO diagnostic_selection (diagnostic_name, parent_id, is_enabled) VALUES
-- Stiction sub-methods
('Heuristic method',                            @stiction, 1),
('Horch cross-correlation',                     @stiction, 1),
('Yamashita shape',                             @stiction, 1),
('Bicoherence',                                 @stiction, 1),
('Fall back to other indicators if methods disagree', @stiction, 1),
-- Aggressive tuning sub-methods
('Harris Index',                                @agg,      1),
('Hagglund oscillation',                        @agg,      1),
-- Sluggish tuning sub-methods
('Harris Index',                                @slug,     0),
-- External oscillation sub-methods
('Harris Index',                                @ext_osc,  1),
('Hagglund oscillation',                        @ext_osc,  1),
-- Cross-loop propagation sub-methods
('Cross-correlation',                           @prop,     1),
('Granger causality',                           @prop,     1),
('Spectral coherence',                          @prop,     1);

-- ── DIAGNOSTIC_CONFIG (per loop, top-level diagnostics only) ──
-- Links each loop to each top-level diagnostic with its enabled flag
INSERT INTO diagnostic_config (loop_id, diagnostic_selection_id, is_enabled)
SELECT l.id, ds.id, ds.is_enabled
FROM loops l
CROSS JOIN diagnostic_selection ds
WHERE ds.parent_id IS NULL;

-- ── USERS ─────────────────────────────────────────────────────
INSERT INTO users (username, email, password_hash, role) VALUES
('admin',  'admin@ingenero.com',  'REPLACE_WITH_BCRYPT_HASH', 'admin'),
('tejas',  'tejas@ingenero.com',  'REPLACE_WITH_BCRYPT_HASH', 'admin'),
('viewer', 'viewer@ingenero.com', 'REPLACE_WITH_BCRYPT_HASH', 'viewer');

-- ── THRESHOLD_CONFIGS ─────────────────────────────────────────
INSERT INTO threshold_configs
    (user_id, config_name, hysteresis_warn, hysteresis_fail,
     deadband_warn, deadband_fail, noise_warn, noise_fail, is_global)
VALUES
(1, 'Standard', 3.0, 5.0, 2.0, 4.0, 1.5, 3.0, 1),
(1, 'Strict',   2.0, 3.5, 1.5, 3.0, 1.0, 2.0, 1),
(1, 'Lenient',  5.0, 8.0, 4.0, 6.0, 2.5, 5.0, 1);

GO
PRINT '=== ValveDiagnosticDB rebuilt (v2). Run seed_readings.py next. ===';
